🚧 Work in Progress — Building a modular crypto AML risk platform



# Crypto Risk Platform (AML + AI) — WIP

A modular, extensible sandbox for building **crypto transaction monitoring** infrastructure:
- ingestion → graph construction → risk scoring → (future) investigation assistance

## Why
This repo is a career-grade project to practice building scalable risk systems (batch today, streaming/real-time next).

## Architecture 
[Transaction Simulator] -> [CSV] -> [Graph Builder] -> [Risk Engine] -> [Top Risk Wallets]

## Services
- `services/ingestion`: generates synthetic transactions
- `services/scoring`: graph exposure scoring (0–2 hop)
- `services/investigation`: reserved for future AI investigator layer

## Quickstart
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python services/ingestion/simulator.py
python services/scoring/run_scoring.py
