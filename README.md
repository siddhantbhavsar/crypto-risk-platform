# Crypto AML Risk Platform

A production-style backend platform that simulates a crypto AML (Anti-Money Laundering) transaction monitoring system.

This project demonstrates how a real risk pipeline is built:

**streaming ingestion → idempotent persistence → graph analytics → scoring runs → explainability → observability**

All services are containerized and reproducible using Docker.

---

## 🚀 What this project demonstrates

* Streaming ingestion with Kafka
* Idempotent persistence in Postgres
* Graph-based multi-hop risk scoring
* Persistent scoring runs and audit trail
* Risk explainability with hop-level attribution
* Operational observability endpoints
* Automated database migrations (Alembic)
* Modern linting + CI (Ruff + pytest)
* Tests validated inside Docker containers

---

## 🧱 Architecture Diagram

```mermaid
flowchart LR

subgraph Ingestion
  SIM[Simulator]
  PROD[Kafka Producer]
  K[(Kafka Topic)]
  CONS[Kafka Consumer]
end

subgraph Storage
  DB[(Postgres)]
end

subgraph API_and_Scoring
  API[FastAPI API]
  GRAPH[Graph Reload]
  SCORE[Risk Scoring Engine]
  RUNS[(scoring_runs)]
  SCORES[(risk_scores)]
end

subgraph Dashboard
  STREAM[Streamlit Dashboard]
  GRAPH_VIZ[Wallet Graph]
  EXPLAIN[Explainer]
end

SIM --> PROD --> K --> CONS --> DB
DB --> API
API --> GRAPH --> SCORE
SCORE --> RUNS
SCORE --> SCORES

API --> STREAM
STREAM --> GRAPH_VIZ
STREAM --> EXPLAIN

API --> STATUS[/ingestion/status/]
API --> EXPLAIN_API[/scores/explain/]
```


All services run via Docker Compose.

---

## ✨ Key Features

### 📊 Interactive Streamlit Dashboard

* **Analyst-style UI** for leaderboard, explainability, and ingestion telemetry
* **Wallet Graph Visualization** with Pyvis network rendering
* **Filter Presets** — Save and load multi-filter configurations
* **Export Graph** — Download graph data as JSON for external analysis
* **Node Interaction** — Click/select nodes to inspect wallet details with real-time metrics
* **Risk Leaderboard** — View top wallets ranked by risk score
* **Explainability Viewer** — Hop-by-hop attribution and top contributors
* **Auto-refresh** — Optional real-time dashboard updates

Access the dashboard at `http://localhost:8501` (Streamlit)

---

### Streaming ingestion

* Simulator generates wallet-to-wallet transactions
* Kafka producer publishes events
* Consumer batches inserts into Postgres
* Idempotency via:

```
ON CONFLICT DO NOTHING
```

This guarantees safe retries and accurate ingestion metrics.

---

### Persistent storage

Database tables include:

* transactions (with ingested_at timestamp)
* ingestion_state
* scoring_runs
* risk_scores

Schema is managed by Alembic and automatically migrated on startup.

---

### Graph-based risk engine

* Builds a transaction graph from stored data
* Propagates multi-hop exposure risk
* Persists scoring runs and wallet scores
* Supports configurable hop weights

---

### Explainability (analyst workflow)

Endpoint:

```
GET /scores/explain/{wallet}
```

Returns:

* stored risk score
* hop-by-hop illicit exposure
* weighted risk contributions
* top contributing wallets
* scoring run metadata

This simulates how analysts investigate risky wallets.

---

### Observability

Endpoint:

```
GET /ingestion/status
```

Provides:

* ingestion progress
* throughput metrics
* seconds since last ingestion
* graph readiness
* node/edge counts
* latest scoring run

---

## 📌 API Endpoints

```
POST /reload-graph
POST /run-score
GET  /scores/top?limit=10
GET  /scores/{wallet}
GET  /scores/explain/{wallet}
GET  /ingestion/status
GET  /ready
GET  /health
```

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
  docker-compose.yml
  Dockerfile
  requirements.txt
  pyproject.toml
```

---

## ▶️ Quickstart (5 minutes)

Start the platform:

```
docker compose up -d --build
```

### Access Services

- **API** (FastAPI): http://localhost:8000
- **Dashboard** (Streamlit): http://localhost:8501
- **Database** (Postgres): localhost:5432

### Ingest Data

Generate transactions:

```
docker compose exec api python services/ingestion/simulator.py
```

Publish to Kafka:

```
docker compose exec api python -m services.ingestion.kafka_producer
```

### Use Dashboard

1. Open http://localhost:8501
2. Click **"Reload Graph"** → **"Run Score"** in the sidebar
3. Explore tabs:
   - **Leaderboard** — Top-risk wallets ranked by exposure
   - **Explainability** — Hop-by-hop risk breakdown for any wallet
   - **Wallet Graph** — Interactive transaction network
     - Save/load filter presets
     - Select & highlight nodes
     - Export graph as JSON

### Run Demo Script

```
python scripts/demo.py
```

The demo:

* reloads the graph
* runs scoring
* prints top wallets
* shows explainability for a wallet
* prints ingestion status

---

## 🧪 Developer Workflow

Lint:

```
docker compose exec api ruff check .
```

Run tests inside Docker:

```
docker compose exec api pytest -q
```

Hot reload is enabled for the API during development.

---

## � Dashboard Features (Recent Updates)

### Graph Presets
- **Save** named filter configurations (direction, hops, tags, thresholds)
- **Load** presets instantly from dropdown
- **Manage** presets with delete functionality

### Graph Export
- Export graph data as **JSON** (raw + filtered)
- Includes timestamps and full metadata
- Download directly from browser

### Node Interaction
- **Select** any node from dropdown to inspect
- **Auto-highlight** selected node in yellow
- **Real-time metrics** — in/out edges, transaction amounts, neighbors
- **Node type badges** — Distinguish center (🟢), illicit (🔴), neighbor (🔵)

---

## �🔍 CI

GitHub Actions runs:

* Ruff lint
* pytest
* Docker build validation
* pytest inside Docker containers

This ensures environment parity with production.

---


## 🖼 Screenshots

Below are real outputs from running the demo workflow locally.

### Top wallets — risk leaderboard

![Top wallets](assets/screenshots/top-wallets.png)

This view shows the highest-risk wallets ranked by graph-based exposure score.

---

### Explainability — hop-by-hop attribution

![Explainability](assets/screenshots/explainability.png)

The explainability endpoint breaks risk into hop layers and shows which neighboring wallets contribute to the score. This simulates how an AML analyst investigates suspicious entities.

---

### Ingestion status — operational telemetry

![Ingestion status](assets/screenshots/ingestion-status.png)

The ingestion status endpoint exposes throughput, processing metrics, graph readiness, and the latest scoring run — similar to real production observability dashboards.


---

## 📜 License

MIT
