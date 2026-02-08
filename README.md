# Crypto AML Risk Platform

A fintech-style backend platform that simulates a production crypto AML transaction monitoring system.

This project demonstrates how a real-world risk pipeline is built: streaming ingestion, persistent storage, graph analytics, scoring orchestration, and operational observability — all containerized and reproducible.

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

```
Simulator → Kafka → Consumer → Postgres
                     ↓
                FastAPI API
                     ↓
              Risk Scoring Engine
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

`/ingestion/status` exposes real operational state:

* transaction counts
* ingestion progress
* latest scoring run
* graph health
* system readiness

Example response:

```json
{
  "status": "ok",
  "tx_count": 4000,
  "ingestion": {
    "name": "transactions_consumer",
    "total_inserted": 4000,
    "last_error": null
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

Create database tables (dev mode):

```
docker compose exec api python -c "from services.api.db import engine, Base; import services.api.models; Base.metadata.create_all(bind=engine)"
```

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

## 🔬 Key Engineering Highlights

### Idempotent ingestion

Duplicate transactions are safely ignored via Postgres upserts. Accurate insert counts are computed using `RETURNING` instead of unreliable rowcount behavior.

---

### Schema normalization

The ingestion pipeline supports both:

```
src/dst
sender/receiver
```

and normalizes records to prevent null wallet corruption.

---

### Operational observability

The platform exposes ingestion and scoring health via structured API endpoints suitable for dashboards and monitoring systems.

---

## 🧪 Development Workflow

Hot reload is enabled inside Docker:

```
Edit code → save → API reloads automatically
```

Consumer restarts only when ingestion code changes.

---

## 🛣 Future Improvements

* Automatic DB migrations on startup
* Kafka lag and throughput metrics
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
