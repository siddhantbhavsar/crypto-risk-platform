# Crypto AML Risk Platform

A fintech-style backend platform that simulates a production crypto AML transaction monitoring system.

This project demonstrates how a real-world risk pipeline is built: streaming ingestion, persistent storage, graph analytics, scoring orchestration, automated migrations, and operational observability — all containerized and reproducible.

---

## 🚀 Overview

The platform simulates an end-to-end crypto risk pipeline:

```
Transaction Simulator
→ Kafka Streaming Ingestion
→ Postgres Persistent Storage
→ Graph-Based Risk Scoring
→ FastAPI Analytics API
→ Dockerized Deployment
```

The goal is to showcase production-grade backend engineering patterns used in AML and fraud detection systems.

---

## 🧱 Architecture

```mermaid
flowchart LR
  sim[Simulator] --> prod[Kafka Producer]
  prod --> k[(Kafka Topic: transactions)]
  k --> cons[Kafka Consumer]
  cons --> db[(Postgres)]

  db --> api[FastAPI API]
  api --> graph[Graph Reload]
  api --> score[Risk Scoring Engine]

  score --> rs[(risk_scores table)]
  api --> obs[/ingestion/status/]
```

All services run via Docker Compose.

---

## ✨ Features

### Streaming Ingestion

* Kafka producer publishes simulated crypto transactions
* Consumer writes batched inserts into Postgres
* Idempotent ingestion using:

```
ON CONFLICT DO NOTHING + RETURNING
```

This guarantees accurate insert metrics even with retries.

---

### Persistent Storage

Postgres stores:

* `transactions`
* `ingestion_state` (operational metrics)
* `scoring_runs`
* `risk_scores`

Schema is managed via **Alembic migrations**.

---

### Graph-Based Risk Engine

* Builds wallet transaction graph from database
* Computes multi-hop exposure risk
* Persists scoring runs for auditability

---

### FastAPI Analytics Layer

Endpoints:

```
POST /reload-graph
POST /run-score
GET  /scores/top?limit=10
GET  /ingestion/status
GET  /ready
GET  /health
```

---

### Observability

`/ingestion/status` exposes real operational telemetry:

* ingestion progress
* transaction throughput (last 5 minutes)
* time since last ingestion
* graph health
* system readiness

Example:

```json
{
  "status": "ok",
  "tx_count": 2000,
  "metrics": {
    "total_inserted": 2000,
    "tx_per_min_5m": 400.0
  },
  "graph_ready": true
}
```

This mirrors production monitoring endpoints used in fintech services.

---

## 📁 Repository Structure

```
crypto-risk-platform/

services/
  api/
  ingestion/
  scoring/

scripts/
  demo.py

alembic/
data/

docker-compose.yml
Dockerfile
requirements.txt
```

---

## ⚙️ Setup

### Requirements

* Docker
* Docker Compose
* Python 3.11+ (for demo script)

---

### Start the platform

```
docker compose up -d --build
```

Database schema is applied automatically via the **migrate** service using Alembic.

No manual setup is required.

---

## ▶️ Quick Demo

### 1. Generate simulated transactions

```
docker compose exec api python services/ingestion/simulator.py
```

### 2. Publish to Kafka

```
docker compose exec api python services/ingestion/kafka_producer.py
```

### 3. Run full demo pipeline

```
python scripts/demo.py
```

This automatically:

* reloads graph
* runs scoring
* prints top risky wallets
* shows ingestion status

---

## 🧪 Development Workflow

Hot reload is enabled inside Docker:

```
Edit code → save → API reloads automatically
```

Consumer restarts only when ingestion code changes.

---

## 🔍 Linting & CI

Before pushing changes:

```
docker compose exec api ruff check .
docker compose exec api pytest
```

CI runs lint + tests automatically on GitHub push.

---

## 🔬 Key Engineering Highlights

### Idempotent ingestion

Duplicate transactions are safely ignored via Postgres upserts. Accurate insert counts are computed using `RETURNING` instead of unreliable rowcount behavior.

---

### Automated migrations

Database schema is versioned with Alembic and applied automatically during container startup.

---

### Operational observability

The platform exposes ingestion and scoring health via structured API endpoints suitable for dashboards and monitoring systems.

---

## 🛣 Future Improvements

* Kafka lag monitoring
* Scheduled scoring jobs
* Risk explainability endpoints
* Monitoring dashboard UI
* Authentication & rate limiting

---

## 🎯 Purpose

This project is a portfolio demonstration of:

* streaming data engineering
* backend system design
* graph analytics pipelines
* production deployment patterns

It simulates infrastructure used in real fintech AML systems.

---

## 📜 License

MIT
