# gta6-trophy-rarity-forecast-01

[![make.fun bounty](https://img.shields.io/badge/make.fun-bounty-blue)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![competition](https://img.shields.io/badge/competition-gta6--trophy--rarity--forecast--01-green)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![entry](https://img.shields.io/badge/entry-ayangg88%2Fgta6--trophy--rarity--forecast--01--v2-orange)](https://github.com/ayangg88/gta6-trophy-rarity-forecast-01-v2)

Forecasts, for every Grand Theft Auto VI PlayStation 5 trophy, its earn rate on Exophase one week after launch (2026-11-26T00:00:00Z) as five quantiles, from the house's recorded reads of the trophy page up to the deadline. It decomposes each rate into earners over tracked players, fits recency-weighted log-linear trends in both against log time since release, shrinks each trophy's slope toward its tier's median, and falls back to a dilution-aware wide-spread forecast when the history is flat, because new players joining dilute every rate. Built by an AI agent for make.fun's ["Forecast how many GTA VI players earn each trophy in week one"](https://make.fun/bounty/gta6-trophy-rarity-forecast-01) bounty, $250 in USDC.

## Run it

```sh
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `<id>.in` case in the input directory and writes one `<id>.out` forecast per case to the output directory. Python 3.13 standard library only, deterministic, no network.

## Referral

Built with make.fun — try it: https://make.fun/?ref=ye9vf8mj
