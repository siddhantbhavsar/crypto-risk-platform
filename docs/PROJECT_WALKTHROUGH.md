# Crypto AML Risk Platform — Technical Walkthrough

## Purpose of this document

This document explains the architecture, components, and internal behavior of the Crypto AML Risk Platform. It is intended for:

* interview walkthroughs
* technical reviews
* onboarding new contributors
* demonstrating system design and engineering decisions

---

# 1. System Overview

The platform simulates a production crypto AML monitoring pipeline.

It performs the following stages:

1. Transaction simulation
2. Kafka ingestion
3. Idempotent persistence in Postgres
4. Graph construction
5. Multi-hop risk scoring
6. Explainability analysis
7. Observability reporting

The system is containerized and orchestrated using Docker Compose.

---

# 2. High-Level Architecture

```
Simulator
→ Kafka Producer
→ Kafka Topic (transactions)
→ Kafka Consumer
→ Postgres

Postgres
→ FastAPI API
→ Graph reload
→ Risk scoring engine
→ scoring_runs + risk_scores
```

All services run in isolated containers:

* api (FastAPI server + scoring)
* consumer (Kafka ingestion worker)
* kafka (message broker)
* postgres (database)
* migrate (Alembic schema migrations)

---

# 3. Repository Structure

```
services/
  api/        → FastAPI endpoints + DB access
  ingestion/  → Kafka producer/consumer + simulator
  scoring/    → Risk engine + scoring pipeline
scripts/
  demo.py     → End-to-end demo runner
alembic/      → Database migrations
```

Each directory corresponds to a logical subsystem.

---

# 4. Ingestion Pipeline

## Simulator

Generates synthetic wallet-to-wallet transaction CSV data.

Purpose:

* simulate realistic AML traffic
* enable reproducible demo runs

## Kafka Producer

Reads simulator output and publishes messages to the Kafka topic:

```
transactions
```

Each message represents a transaction event.

## Kafka Consumer

Consumes events in batches and inserts them into Postgres.

Key behaviors:

* batch inserts for performance
* idempotent writes using:

```
ON CONFLICT DO NOTHING
```

* accurate insert metrics using RETURNING
* ingestion_state table tracks processing progress

This design prevents duplicate ingestion during retries.

---

# 5. Database Design

Tables:

## transactions

Stores raw transaction events.

Important fields:

* src / dst wallets
* timestamps
* ingested_at (for telemetry)

## ingestion_state

Tracks consumer progress and operational metrics.

## scoring_runs

Represents a single scoring execution.

Stores:

* configuration used
* timestamp
* source metadata

## risk_scores

Stores computed wallet risk scores.

Includes:

* risk score
* exposure breakdown
* graph degree metrics

Alembic manages schema evolution and runs automatically on container startup.

---

# 6. Risk Engine

The scoring system builds a directed transaction graph.

## Graph construction

Transactions are converted into a graph:

* nodes = wallets
* edges = transfers

The graph is treated as undirected for exposure propagation.

## Multi-hop risk propagation

Risk spreads through neighboring wallets:

* hop 0 = wallet itself
* hop 1 = direct neighbors
* hop 2+ = extended network

Each hop has configurable weights.

Example:

```
hop_weights = [1.0, 0.6, 0.3]
```

Scores are optionally degree-normalized.

## Scoring run pipeline

Steps:

1. Reload graph from DB
2. Select illicit seed wallets
3. Compute exposures per wallet
4. Persist scoring results
5. Save scoring metadata

Each run is stored in scoring_runs.

---

# 7. Explainability Engine

Endpoint:

```
GET /scores/explain/{wallet}
```

Purpose:

Explain *why* a wallet has a risk score.

It returns:

* exact hop illicit exposure
* weighted contribution per hop
* top contributing wallets
* stored cumulative exposures
* scoring run metadata

This simulates analyst investigation workflows.

---

# 8. API Layer (FastAPI)

Key endpoints:

## POST /reload-graph

Rebuilds in-memory graph from Postgres.

## POST /run-score

Executes a scoring run and persists results.

## GET /scores/top

Returns highest risk wallets.

## GET /scores/explain/{wallet}

Provides detailed explainability.

## GET /ingestion/status

Operational telemetry:

* ingestion progress
* throughput metrics
* graph readiness
* latest scoring run

## GET /ready

Readiness probe for orchestration.

## GET /health

Basic health check.

---

# 9. Observability

The system exposes operational metrics via:

```
/ingestion/status
```

Metrics include:

* total ingested transactions
* throughput over last 5 minutes
* seconds since last processing
* graph statistics
* scoring run metadata

This mirrors production monitoring dashboards.

---

# 10. Docker Orchestration

Docker Compose provides:

* reproducible environment
* service isolation
* automated startup ordering
* DB migrations on launch

Hot reload is enabled for API development.

---

# 11. CI and Testing

GitHub Actions pipeline runs:

* Ruff linting
* pytest unit tests
* Docker build validation
* pytest inside Docker containers

Tests focus on:

* risk engine correctness
* explainability logic

This ensures environment parity with production.

---

# 12. Step-by-Step Demo Instructions

## Start services

```
docker compose up -d --build
```

## Generate transactions

```
docker compose exec api python services/ingestion/simulator.py
```

## Publish to Kafka

```
docker compose exec api python services/ingestion/kafka_producer.py
```

## Run full demo

```
python scripts/demo.py
```

The demo performs:

1. health check
2. graph reload
3. scoring run
4. top wallet ranking
5. explainability analysis
6. ingestion status reporting

---


# 13. Possible Extensions

Future improvements:

* Prometheus metrics
* authentication layer
* historical run explainability
* web dashboard
* distributed scaling
* caching strategies

---


