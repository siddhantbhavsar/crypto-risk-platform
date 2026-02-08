import os
from datetime import datetime, timezone

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from services.scoring.risk_engine import (
    RiskConfig,
    build_tx_graph,
    pick_seed_illicit_wallets,
    risk_score_wallet,
)

from . import crud
from .db import SessionLocal, get_db

TX_SOURCE = os.getenv("TX_SOURCE", "csv").lower()

app = FastAPI(title="Crypto Risk Platform API", version="0.2.0")

TX_PATH = "data/transactions.csv"

cfg = RiskConfig(hop_weights=(1.0, 0.6, 0.3), degree_normalize=True)

GRAPH_READY = False
GRAPH_ERROR = None
GRAPH = None
ILLICIT = None
ILLICIT_SEED = int(os.getenv("ILLICIT_SEED", "42"))


def load_transactions_from_db(db):
    rows = crud.fetch_all_transactions(db)
    return [{"src": r.sender, "dst": r.receiver, "amount": float(r.amount or 0.0)} for r in rows]


@app.on_event("startup")
def startup():
    global GRAPH, ILLICIT, GRAPH_READY, GRAPH_ERROR

    # --- existing logic below ---
    GRAPH_READY = False
    GRAPH_ERROR = None

    try:
        if TX_SOURCE == "db":
            db = SessionLocal()
            try:
                tx_list = load_transactions_from_db(db)
            finally:
                db.close()

            if not tx_list:
                GRAPH_ERROR = (
                    "TX_SOURCE=db but no transactions found. Ingest first, then POST /reload-graph."
                )
                return

            txs = pd.DataFrame(tx_list)

        else:
            txs = pd.read_csv(TX_PATH)

        GRAPH = build_tx_graph(txs)
        ILLICIT = pick_seed_illicit_wallets(GRAPH.nodes, pct=0.05, seed=ILLICIT_SEED)

        GRAPH_READY = True

    except ProgrammingError as e:
        GRAPH_ERROR = f"Graph not loaded at startup (DB not ready/migrated): {e}"
        GRAPH_READY = False

    except Exception as e:
        GRAPH_ERROR = f"Graph not loaded at startup: {e}"
        GRAPH_READY = False


@app.get("/health")
def health():
    return {
        "status": "ok",
        "graph_ready": GRAPH_READY,
        "graph_error": GRAPH_ERROR,
        "tx_source": TX_SOURCE,
    }


@app.post("/reload-graph")
def reload_graph(db: Session = Depends(get_db)):
    global GRAPH, ILLICIT, GRAPH_READY, GRAPH_ERROR

    try:
        if TX_SOURCE != "db":
            GRAPH_READY = False
            GRAPH_ERROR = "Set TX_SOURCE=db to use this endpoint."
            raise HTTPException(status_code=400, detail=GRAPH_ERROR)

        tx_list = load_transactions_from_db(db)
        if not tx_list:
            GRAPH_READY = False
            GRAPH_ERROR = "No transactions found in DB."
            raise HTTPException(status_code=400, detail=GRAPH_ERROR)

        txs = pd.DataFrame(tx_list)
        GRAPH = build_tx_graph(txs)
        ILLICIT = pick_seed_illicit_wallets(GRAPH.nodes, pct=0.05, seed=ILLICIT_SEED)

        GRAPH_READY = True
        GRAPH_ERROR = None
        return {"ok": True, "tx_count": len(tx_list)}

    except ProgrammingError as e:
        # common: table missing / migrations not applied
        GRAPH_READY = False
        GRAPH_ERROR = f"DB not ready/migrated: {e}"
        raise HTTPException(status_code=503, detail=GRAPH_ERROR)

    except HTTPException:
        # already set GRAPH_ERROR above
        raise

    except Exception as e:
        GRAPH_READY = False
        GRAPH_ERROR = str(e)
        raise HTTPException(status_code=500, detail=GRAPH_ERROR)


# --- OLD: in-memory scoring (still useful) ---
@app.get("/score/{wallet}")
def score_in_memory(wallet: str):
    if not GRAPH_READY:
        raise HTTPException(status_code=503, detail=f"Graph not ready: {GRAPH_ERROR}")

    if GRAPH is None or ILLICIT is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    result = risk_score_wallet(GRAPH, wallet, ILLICIT, cfg)
    if result.get("reason") == "wallet_not_in_graph":
        raise HTTPException(status_code=404, detail=f"Wallet {wallet} not found")
    return result


# --- NEW: persist a scoring run + all wallet scores ---
@app.post("/run-score")
def run_score(db: Session = Depends(get_db)):
    if not GRAPH_READY:
        raise HTTPException(status_code=503, detail=f"Graph not ready: {GRAPH_ERROR}")

    if GRAPH is None or ILLICIT is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    # store run metadata
    run = crud.create_scoring_run(
        db,
        tx_source=f"{TX_SOURCE}:{TX_PATH}" if TX_SOURCE == "csv" else "db:transactions",
        config_json={
            "hop_weights": list(cfg.hop_weights),
            "degree_normalize": cfg.degree_normalize,
            "illicit_seed_pct": 0.05,
        },
    )

    rows = []
    for w in GRAPH.nodes:
        r = risk_score_wallet(GRAPH, w, ILLICIT, cfg)
        rows.append(
            {
                "wallet": r["wallet"],
                "risk_score": r["risk_score"],
                "exposures_json": r["exposures"],
                "in_degree": r["in_degree"],
                "out_degree": r["out_degree"],
            }
        )

    inserted = crud.bulk_insert_risk_scores(db, run_id=run.id, rows=rows)
    db.commit()

    return {"run_id": run.id, "wallets_scored": inserted}


# --- NEW: query from Postgres ---
@app.get("/scores/top")
def top_scores(
    n: int | None = None,
    limit: int | None = None,
    db: Session = Depends(get_db),
):
    size = limit if limit is not None else n
    if size is None:
        size = 20

    size = max(1, min(size, 500))

    scores = crud.get_top_scores_latest(db, n=size)

    return [
        {
            "wallet": s.wallet,
            "risk_score": float(s.risk_score),
            "run_id": s.run_id,
            "created_at": s.created_at,
        }
        for s in scores
    ]


@app.get("/scores/{wallet}")
def latest_score(wallet: str, db: Session = Depends(get_db)):
    s = crud.get_latest_score_for_wallet(db, wallet=wallet)
    if not s:
        raise HTTPException(status_code=404, detail=f"No stored score found for wallet {wallet}")

    return {
        "wallet": s.wallet,
        "risk_score": float(s.risk_score),
        "exposures": s.exposures_json,
        "in_degree": s.in_degree,
        "out_degree": s.out_degree,
        "run_id": s.run_id,
        "created_at": s.created_at,
    }


@app.get("/ingestion/status")
def ingestion_status(db: Session = Depends(get_db)):
    try:
        tx_count = crud.count_transactions(db)
        ing = crud.get_ingestion_state(db, name="transactions_consumer")
        latest_run = crud.get_latest_run(db)

        # --- metrics ---
        seconds_since_last_processed = None
        ingested_last_5m = None
        tx_per_min_5m = None

        if ing and ing.last_processed_at:
            now = datetime.now(timezone.utc)
            last = ing.last_processed_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            seconds_since_last_processed = (now - last).total_seconds()

        if ing is not None:
            ingested_last_5m = crud.count_ingested_since(db, minutes=5)
            tx_per_min_5m = ingested_last_5m / 5.0

        # --- status (precedence: degraded > starting > ok) ---
        status = "ok"

        # starting conditions
        if tx_count == 0 or not GRAPH_READY or ing is None:
            status = "starting"

        # degraded conditions
        if ing and ing.last_error:
            status = "degraded"

        if GRAPH_ERROR:
            # ignore stale startup message once tx_count > 0
            if not ("no transactions found" in str(GRAPH_ERROR).lower() and tx_count > 0):
                status = "degraded"

        # --- latest scoring run summary ---
        latest_run_summary = None
        if latest_run:
            wallets_scored = crud.count_scores_for_run(db, run_id=latest_run.id)
            latest_run_summary = {
                "run_id": latest_run.id,
                "created_at": latest_run.created_at,
                "tx_source": latest_run.tx_source,
                "wallets_scored": wallets_scored,
                "config_json": latest_run.config_json,
            }

        graph_stats = None
        if GRAPH_READY and GRAPH is not None:
            graph_stats = {
                "nodes": int(GRAPH.number_of_nodes()),
                "edges": int(GRAPH.number_of_edges()),
            }

        return {
            "status": status,
            "tx_count": tx_count,
            "metrics": None
            if not ing
            else {
                "name": ing.name,
                "last_tx_id": ing.last_tx_id,
                "last_processed_at": ing.last_processed_at,
                "total_inserted": ing.total_inserted,
                "last_error": ing.last_error,
                "seconds_since_last_processed": seconds_since_last_processed,
                "ingested_last_5m": ingested_last_5m,
                "tx_per_min_5m": tx_per_min_5m,
            },
            "latest_scoring_run": latest_run_summary,
            "graph_ready": GRAPH_READY,
            "graph_error": GRAPH_ERROR,
            "graph_stats": graph_stats,
            "tx_source": TX_SOURCE,
        }

    except ProgrammingError as e:
        raise HTTPException(status_code=503, detail=f"DB not ready/migrated: {e}")


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    status = ingestion_status(db)

    if status["status"] != "ok":
        raise HTTPException(status_code=503, detail=status)

    return {"status": "ready"}
