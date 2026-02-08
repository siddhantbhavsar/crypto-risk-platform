# Crypto AML Risk Platform

A fintech-style backend platform that simulates a production crypto transaction monitoring system.

This project demonstrates real-world data engineering and backend architecture patterns used in AML and fraud detection systems.

---

## Overview

This platform simulates an end-to-end crypto risk pipeline:

```
Transaction Simulator
→ Kafka Streaming Ingestion
→ Postgres Persistent Storage
→ Graph-Based Risk Scoring
→ FastAPI Analytics API
→ Dockerized Deployment
```

The goal is to showcase production-style system design including streaming ingestion, idempotent persistence, scoring pipelines, and operational observability.

---

## Features

### Streaming Ingestion

* Kafka producer publishes simulated crypto transactions
* Consumer ingests into Postgres in batched writes
* Idempotent inserts using:

```
ON CONFLICT DO NOTHING + RETURNING
```

This guarantees accurate ingestion metrics even under retries.

### Persistent Storage

Postgres stores:

* transactions
* ingestion_state metrics
* scoring_runs
* risk_scores

### Graph-Based Risk Engine

* Builds transaction graph from database
* Computes wallet risk scores
* Persists scoring runs for analytics

### FastAPI Analytics Layer

Endpoints:

* `POST /reload-graph`
* `POST /run-score`
* `GET /scores/top`
* `GET /ingestion/status` *(planned next)*

### Containerized Deployment

All services run in Docker Compose:

* API
* Kafka + Zookeeper
* Postgres
* Consumer

Hot reload enabled for rapid development.

---

## Architecture

```
Simulator → Kafka → Consumer → Postgres
                     ↓
                FastAPI API
                     ↓
              Risk Scoring Engine
```

The system is designed to mimic real AML transaction monitoring pipelines used in fintech environments.

---

## Repository Structure

```
crypto-risk-platform/

services/
  api/
    main.py
    db.py
    models.py
    crud.py

  ingestion/
    simulator.py
    kafka_producer.py
    kafka_consumer.py

  scoring/
    risk_engine.py
    run_scoring.py

alembic/
tests/
data/

docker-compose.yml
Dockerfile
requirements.txt
```

---

## Setup

### Requirements

* Docker
* Docker Compose

### Start the platform

```
docker compose up -d --build
```

### Create database tables (dev mode)

```
docker compose exec api python -c "from services.api.db import engine, Base; import services.api.models; Base.metadata.create_all(bind=engine)"
```

---

## Demo Workflow

### Generate transactions

```
docker compose exec api python services/ingestion/simulator.py
```

### Publish to Kafka

```
docker compose exec api python services/ingestion/kafka_producer.py
```

### Reload graph

```
POST /reload-graph
```

### Run scoring

```
POST /run-score
```

### Fetch top risk wallets

```
GET /scores/top?limit=10
```

---

## Key Engineering Highlights

### Idempotent ingestion

Transactions are deduplicated using primary key constraints and Postgres upserts.

Accurate insert metrics are computed using:

```
INSERT ... RETURNING
```

instead of unreliable rowcount behavior.

### Schema normalization

The pipeline supports both:

```
src/dst
sender/receiver
```

and normalizes records to prevent null wallet corruption.

### Observability

The ingestion_state table tracks:

* last processed transaction
* total inserted count
* error status
* timestamps

---

## Development Workflow

Hot reload is enabled inside Docker:

```
Edit code → save → API reloads automatically
```

Consumer restarts only when ingestion code changes.

---

## Future Improvements

* Ingestion status endpoint
* Kafka lag metrics
* Alembic migration automation
* Prometheus monitoring
* Authentication & rate limiting
* UI dashboard

---

## Purpose

This project is built as a portfolio demonstration of:

* Streaming data engineering
* Backend system design
* Risk analytics pipelines
* Production deployment patterns

It simulates infrastructure used in real-world fintech AML systems.

---

