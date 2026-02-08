# Crypto Risk Platform (AML + AI) — WIP

A modular, extensible sandbox project to practice building fintech-grade crypto transaction monitoring infrastructure.

This project simulates a simplified AML risk platform similar to what modern fintech and blockchain analytics companies build. It focuses on architecture, reproducibility, and engineering discipline — not just modeling.

---

## Why this project

I work in transaction monitoring / AML and I’m building this to level up into platform engineering for fintech systems:

- reproducible services
- persistent audit trails
- containerized deployment
- CI/CD pipelines
- scalable architecture (Kafka / Kubernetes / AWS coming next)

---

## Current Architecture

Batch scoring pipeline:

Transaction Simulator (CSV)
→ Graph Builder (NetworkX)
→ Risk Engine (multi-hop exposure scoring)
→ FastAPI service (Docker)
→ PostgreSQL (persisted scoring runs + scores)

Future roadmap:

Kafka streaming ingestion
→ consumer writes transactions to Postgres
→ scoring reads from Postgres
→ CI/CD + Kubernetes + Terraform + AWS

---

## Features (Current)

- Synthetic crypto-style transaction generation
- Directed graph modeling of wallet flows
- Multi-hop illicit exposure scoring
- Explainable risk outputs (exposure breakdown + degrees)
- FastAPI backend service
- PostgreSQL persistence:
  - scoring_runs table (metadata per run)
  - risk_scores table (wallet scores + explainability)
- Alembic migrations for schema evolution
- Docker + docker-compose runtime
- GitHub Actions CI (lint + tests + docker build)

---

## Risk Scoring Logic

Each wallet is a node in a directed transaction graph.

Risk is based on multi-hop exposure to illicit wallets:

- 0-hop: wallet itself illicit
- 1-hop: neighbors
- 2-hop: neighbors of neighbors

Weighted scoring:

score = sum(weight × illicit_count_by_hop)

Then normalized by:

score / sqrt(in_degree + out_degree)

This reduces bias toward high-traffic hub wallets.

---

## API Endpoints

GET /health  
Service health check

GET /score/{wallet}  
In-memory scoring (computed live from loaded graph)

POST /run-score  
Compute scores for all wallets and persist a scoring run

GET /scores/top?n=20  
Top risky wallets from the latest scoring run

GET /scores/{wallet}  
Latest stored score for a wallet

Swagger UI:

http://127.0.0.1:8000/docs

---

## Run locally (Windows friendly)

Create virtual environment and install dependencies:

python -m venv .venv  
.venv\Scripts\activate  
python -m pip install -r requirements.txt

Generate sample transactions:

python services\ingestion\simulator.py

Run API locally:

python -m uvicorn services.api.main:app --reload

---

## Run with Docker Compose

docker compose up --build -d

Check database tables:

docker compose exec db psql -U risk -d riskdb -c "\dt"

---

## Database Migrations (Alembic)

Create migration:

python -m alembic revision --autogenerate -m "your message"

Apply migrations:

python -m alembic upgrade head

---

## Code Quality and CI

This project uses:

- ruff for linting
- pytest for tests
- GitHub Actions CI to run lint/tests and validate Docker builds

Run locally:

python -m ruff check .  
python -m pytest -q

---

## Roadmap

- Add transactions table and persist ingested data
- Kafka ingestion (producer + consumer)
- Scoring reads from Postgres instead of CSV
- Docker health checks + CI smoke tests
- Kubernetes deployment manifests
- Terraform infrastructure on AWS
- Optional Java ingestion service

---

## Project Goal

This repository is a long-running sandbox to simulate how real AML risk platforms are engineered:

reproducible  
scalable  
auditable  
production-ready

Each iteration adds another layer of real-world backend architecture.
