"""Forecast GTA VI PlayStation 5 trophy earn rates on Exophase, one week out.

Reads every <id>.in case in the input directory (MAKEFUN_INPUT_DIR, else
/input) and writes one <id>.out forecast per case to the output directory
(MAKEFUN_OUTPUT_DIR, else /output). Each output is exactly
{"trophies": [{"id": n, "q": [q05, q25, q50, q75, q95]}, ...]}.

Method
------
A trophy's earn rate is a ratio: earners over tracked players. Work with the
two separately, because the tracked population grows much faster than any
trophy's earners early on, which dilutes the rates. For each read, N is
players_tracked and E_i = rate_i / 100 * N is trophy i's earners.

Let x = ln(1 + hours since the game's release, 2026-11-19T00:00:00Z). Fit
recency-weighted least squares of log(E_i) on x and of log(N) on x over the
case's history (24-hour half-life, so recent reads count more), extrapolate
both to the target's x, and take the median rate as 100 * E / N, clamped to
0.01..99.99. Each trophy's earner slope is shrunk toward its tier's median
slope, weight n / (n + 4) where n is its number of fitted reads; the
platinum, which only grows as players finish everything, is shrunk heavily
toward zero growth and its median is capped at single digits.

Flat history (every read identical, as on launch night): no trend can be
estimated, so the median is the last rate shifted down by dilution -- times
0.3 while the tracked population is still small (under 10,000 players), else
divided by sqrt(1 + horizon in days) -- with a wide spread, because the next
Exophase refresh can move every rate at once.

Spread: sigma in logit units combines a random-walk term, the fit residual
and the slope uncertainty times the distance to the target in x, floored at
0.35 and capped at 2.5. Quantiles are q_tau = inv_logit(logit(median) +
z_tau * sigma), rounded to 4 decimals half-up.

A trophy at 100% in the last read stays at ~100%. Any failure on a case
still writes a valid output: the last read's rates with a wide spread.
Deterministic, standard library only, no network.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]
RELEASE = datetime(2026, 11, 19, 0, 0, 0, tzinfo=timezone.utc)
HALF_LIFE_HOURS = 24.0
SHRINK_PRIOR = 4.0


def parse_time(value):
    """Parse an ISO 8601 timestamp (with a Z or an offset) to an aware datetime."""
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError("not a timestamp string")


def clamp_rate(pct):
    return min(99.99, max(0.01, pct))


def logit(pct):
    p = clamp_rate(pct) / 100.0
    return math.log(p / (1.0 - p))


def inv_logit(lg):
    return 100.0 / (1.0 + math.exp(-lg))


def round4(x):
    """Round to 4 decimals, half up, as the starter does."""
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000
    return int(value) if value == int(value) else value


def wls(points):
    """Recency-weighted least squares of y on x.

    points is a list of (x, y, weight). Returns (intercept, slope, resid_std,
    slope_se, xbar) or None when the fit is degenerate. Needs at least 3
    distinct x values for a slope; otherwise the slope is 0.
    """
    if not points:
        return None
    xs = [p[0] for p in points]
    if len(set(xs)) < 3:
        sw = sum(p[2] for p in points)
        xbar = sum(p[2] * p[0] for p in points) / sw if sw else xs[0]
        ybar = sum(p[2] * p[1] for p in points) / sw if sw else points[0][1]
        resid = math.sqrt(
            sum(p[2] * (p[1] - ybar) ** 2 for p in points) / sw
        ) if sw else 0.0
        return (ybar, 0.0, resid, 0.0, xbar)
    sw = sum(p[2] for p in points)
    xbar = sum(p[2] * p[0] for p in points) / sw
    ybar = sum(p[2] * p[1] for p in points) / sw
    sxx = sum(p[2] * (p[0] - xbar) ** 2 for p in points)
    if sxx <= 0:
        return (ybar, 0.0, 0.0, 0.0, xbar)
    sxy = sum(p[2] * (p[0] - xbar) * (p[1] - ybar) for p in points)
    slope = sxy / sxx
    intercept = ybar - slope * xbar
    n = len(points)
    rss = sum(p[2] * (p[1] - (intercept + slope * p[0])) ** 2 for p in points)
    dof = max(n - 2, 1)
    resid = math.sqrt(rss / sw * n / dof) if sw else 0.0
    slope_se = math.sqrt((rss / dof) / sxx) if sxx > 0 else 0.0
    return (intercept, slope, resid, slope_se, xbar)


def median_of(values):
    ordered = sorted(values)
    m = len(ordered)
    if m == 0:
        return 0.0
    if m % 2:
        return ordered[m // 2]
    return 0.5 * (ordered[m // 2 - 1] + ordered[m // 2])


def quantiles(median, sigma):
    lg = logit(median)
    out = []
    prev = None
    for z in Z:
        q = round4(inv_logit(lg + z * sigma))
        q = min(100.0, max(0.0, q))
        if prev is not None and q < prev:
            q = prev
        out.append(q)
        prev = q
    return out


def fallback_rows(case):
    """Last read's rates with a wide spread; always a valid output."""
    trophies = case.get("trophies") or []
    history = case.get("history") or []
    last_rates = history[-1].get("rates") if history else None
    rows = []
    for i, trophy in enumerate(trophies):
        rate = None
        if last_rates is not None and i < len(last_rates):
            rate = last_rates[i]
        if rate is None:
            rate = 1.0
        rows.append({"id": trophy["id"], "q": quantiles(clamp_rate(rate), 2.5)})
    return {"trophies": rows}


def forecast_case(case, name):
    trophies = case["trophies"]
    history = case["history"]
    if not history:
        raise ValueError(f"{name} has no history")
    horizon_days = case["horizon_minutes"] / 1440.0
    release = RELEASE
    try:
        rel = case.get("game", {}).get("release_date")
        if rel:
            release = datetime.fromisoformat(str(rel) + "T00:00:00+00:00")
    except (ValueError, TypeError):
        release = RELEASE
    try:
        target = parse_time(case["target"])
    except (KeyError, ValueError, TypeError):
        target = parse_time(case["at"])
    x_target = math.log1p(max(0.0, (target - release).total_seconds() / 3600.0))
    checkpoint = parse_time(case["at"])

    # Per-read x and recency weight (24h half-life from the checkpoint).
    reads = []
    for entry in history:
        try:
            at = parse_time(entry["at"])
        except (KeyError, ValueError, TypeError):
            continue
        hours = max(0.0, (at - release).total_seconds() / 3600.0)
        age = max(0.0, (checkpoint - at).total_seconds() / 3600.0)
        weight = 0.5 ** (age / HALF_LIFE_HOURS)
        reads.append((math.log1p(hours), weight, entry))
    if not reads:
        raise ValueError(f"{name} has no usable reads")
    last = reads[-1][2]
    last_n = last.get("players_tracked") or 0

    # Fit log(N) once for the whole case.
    n_points = []
    for x, w, entry in reads:
        n = entry.get("players_tracked")
        if n and n > 0:
            n_points.append((x, math.log(n), w))
    n_fit = wls(n_points)
    log_n_target = None
    if n_fit is not None:
        log_n_target = n_fit[0] + n_fit[1] * x_target

    # Fit log(E) per trophy, remembering each raw slope for tier shrinkage.
    raw_slopes = {}
    fits = {}
    for i, trophy in enumerate(trophies):
        points = []
        for x, w, entry in reads:
            rates = entry.get("rates") or []
            if i >= len(rates) or rates[i] is None:
                continue
            n = entry.get("players_tracked")
            if not n or n <= 0:
                continue
            earners = rates[i] / 100.0 * n
            if earners <= 0:
                continue
            points.append((x, math.log(earners), w))
        fit = wls(points)
        fits[i] = (fit, len(points))
        if fit is not None:
            raw_slopes.setdefault(trophy["tier"], []).append(fit[1])
    tier_median_slope = {
        tier: median_of(slopes) for tier, slopes in raw_slopes.items()
    }

    flat_sigma = min(2.5, max(0.5, 1.2 * math.sqrt(horizon_days)))
    rows = []
    for i, trophy in enumerate(trophies):
        rates = last.get("rates") or []
        last_rate = rates[i] if i < len(rates) else None
        if last_rate is None:
            last_rate = 1.0
        # A trophy at 100% in the last read stays at ~100%.
        if last_rate >= 100.0:
            rows.append({"id": trophy["id"], "q": [99.9, 100, 100, 100, 100]})
            continue
        # Flat history for this trophy: no movement at all in rates or in N.
        trophy_rates = []
        ns = []
        for _, _, entry in reads:
            r = (entry.get("rates") or [])
            trophy_rates.append(r[i] if i < len(r) else None)
            ns.append(entry.get("players_tracked"))
        flat = (
            len(set(trophy_rates)) <= 1
            and len(set(ns)) <= 1
            and trophy_rates
            and trophy_rates[0] is not None
        )
        if flat:
            if last_n < 10000:
                median = last_rate * 0.3
            else:
                median = last_rate / math.sqrt(1.0 + horizon_days)
            rows.append(
                {"id": trophy["id"], "q": quantiles(clamp_rate(median), flat_sigma)}
            )
            continue
        fit, n_pts = fits[i]
        if fit is None or log_n_target is None:
            rows.append(
                {"id": trophy["id"], "q": quantiles(clamp_rate(last_rate), flat_sigma)}
            )
            continue
        intercept, slope, resid, slope_se, xbar = fit
        # Shrink the earner slope toward the tier's median slope.
        tier_slope = tier_median_slope.get(trophy["tier"], slope)
        w = n_pts / (n_pts + SHRINK_PRIOR) if n_pts else 0.0
        slope = w * slope + (1.0 - w) * tier_slope
        if trophy["tier"] == "platinum":
            # The platinum only grows as players finish everything: shrink
            # heavily toward zero growth and keep the median single-digit.
            slope = 0.25 * slope
        log_e_target = intercept + slope * x_target
        median = 100.0 * math.exp(log_e_target) / math.exp(log_n_target)
        if trophy["tier"] == "platinum":
            median = min(median, 9.99)
        if last_rate <= 0:
            # A trophy nobody has yet: a small floor from its tier's median.
            tier_last = median_of(
                [
                    (last.get("rates") or [])[j]
                    for j, t in enumerate(trophies)
                    if t["tier"] == trophy["tier"]
                    and j < len(last.get("rates") or [])
                    and (last.get("rates") or [])[j] is not None
                ]
            )
            median = max(0.01, 0.1 * tier_last)
        median = clamp_rate(median)
        sigma = math.sqrt(
            (0.5 * math.sqrt(horizon_days)) ** 2
            + resid ** 2
            + (slope_se * abs(x_target - xbar)) ** 2
        )
        sigma = min(2.5, max(0.35, sigma))
        rows.append({"id": trophy["id"], "q": quantiles(median, sigma)})
    # Logical consistency: earning the platinum requires earning every
    # other trophy, so the platinum's rate can never exceed the lowest
    # rate among the other trophies. If the fitted platinum median sits
    # above that minimum, shift its whole quantile row down in logit
    # space by exactly the logit difference, so its median equals the
    # minimum and the row stays ordered and in range.
    plat_idx = next(
        (k for k, t in enumerate(trophies) if t["tier"] == "platinum"), None
    )
    if plat_idx is not None:
        others = [rows[k]["q"][2] for k in range(len(rows)) if k != plat_idx]
        if others:
            lowest_other = min(others)
            plat_median = rows[plat_idx]["q"][2]
            if plat_median > lowest_other:
                shift = logit(plat_median) - logit(lowest_other)
                shifted = []
                prev = None
                for q in rows[plat_idx]["q"]:
                    v = round4(inv_logit(logit(q) - shift))
                    v = min(100.0, max(0.0, v))
                    if prev is not None and v < prev:
                        v = prev
                    shifted.append(v)
                    prev = v
                rows[plat_idx]["q"] = shifted
    return {"trophies": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        try:
            forecast = forecast_case(case, path.name)
        except Exception:
            try:
                forecast = fallback_rows(case)
            except Exception:
                continue
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
