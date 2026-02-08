# Crypto AML Risk Platform

A containerized streaming crypto risk analytics platform that simulates how real-world fintech AML backends ingest transactions, build graph models, compute wallet risk scores, and expose query APIs.

This project demonstrates end-to-end platform engineering across streaming ingestion, persistence, analytics, and API serving.

---

## Overview

This system simulates a cryptocurrency transaction monitoring backend.

Synthetic blockchain transactions are streamed through Kafka, persisted in PostgreSQL, converted into a graph model, and scored using a multi-hop exposure algorithm. Results are versioned and served via a FastAPI service.

The architecture mirrors a simplified production fintech data platform.

---

## Architecture

```
Transaction Simulator
        ↓
Kafka Producer
        ↓
Kafka Topic (transactions)
        ↓
Kafka Consumer
        ↓
PostgreSQL (transactions table)
        ↓
Graph Builder + Risk Engine
        ↓
FastAPI Service
        ↓
Risk Score APIs
```

---

## Services (Docker Compose)

The system runs as multiple containers:

### API (FastAPI)

* Builds transaction graph
* Runs wallet risk scoring
* Stores scoring runs
* Serves query endpoints

### PostgreSQL

Persistent storage for:

* transactions
* scoring_runs
* risk_scores

Acts as the system of record.

### Kafka

Streaming message broker for transaction ingestion.

### Zookeeper

Kafka coordination service.

### Consumer Worker

Reads Kafka transactions and writes them into PostgreSQL.

---

## Database Schema

### transactions

Stores ingested blockchain transactions.

Fields:

* tx_id
* sender
* receiver
* amount
* timestamp

---

### scoring_runs

Tracks each scoring execution.

Fields:

* id
* created_at
* tx_source
* config_json

Enables historical reproducibility.

---

### risk_scores

Stores wallet risk results per run.

Fields:

* wallet
* risk_score
* exposures
* in_degree
* out_degree
* run_id

Each scoring run produces a snapshot.

---

## Risk Scoring Model

The platform builds a directed transaction graph and applies a multi-hop exposure heuristic.

### Steps

1. Build directed wallet graph from transactions
2. Seed a percentage of wallets as illicit
3. Propagate risk through graph hops
4. Apply weighted scoring
5. Normalize by node degree

Score formula:

```
score = weighted illicit exposure / sqrt(in_degree + out_degree)
```

The illicit seed is configurable via environment variable for reproducibility.

---

## API Endpoints

### Health

GET /health

Returns service status.

---

### Reload Graph

POST /reload-graph

Rebuilds in-memory graph from database transactions.

---

### Run Scoring

POST /run-score

Executes a full scoring run and stores results.

---

### Top Scores

GET /scores/top?n=20

Returns highest-risk wallets from the latest run.

---

### Wallet Score

GET /scores/{wallet}

Returns latest stored score for a wallet.

---

## Running the System

### Build and start all services

```
docker compose up -d --build
```

---

### Generate synthetic transactions

```
docker compose exec api python services/ingestion/simulator.py
```

---

### Publish transactions to Kafka

```
docker compose exec api python services/ingestion/kafka_producer.py
```

---

### Reload graph

```
POST http://127.0.0.1:8000/reload-graph
```

---

### Run scoring

```
POST http://127.0.0.1:8000/run-score
```

---

### View API docs

Open in browser:

```
http://127.0.0.1:8000/docs
```

---

## Key Engineering Concepts Demonstrated

* Streaming ingestion with Kafka
* Consumer batch persistence
* PostgreSQL schema design
* Graph-based analytics
* Experiment reproducibility
* Container orchestration
* Service separation
* API-driven scoring workflows

---

## Project Goals

This project demonstrates how to design a scalable backend pipeline for financial risk analytics. It emphasizes architecture clarity, reproducibility, and production-style service boundaries.

---

## Future Roadmap

* Incremental graph updates
* Kafka dead-letter queues
* Kubernetes deployment
* Cloud infrastructure provisioning
* Monitoring and metrics
* Real-time scoring triggers


---

## Author

Built as a portfolio platform engineering project focused on fintech risk systems.
