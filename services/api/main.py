import os

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
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

GRAPH = None
ILLICIT = None
ILLICIT_SEED = int(os.getenv("ILLICIT_SEED", "42"))


def load_transactions_from_db(db):
    rows = crud.fetch_all_transactions(db)
    return [
        {"src": r.sender, "dst": r.receiver, "amount": float(r.amount or 0.0)}
        for r in rows
    ]




@app.on_event("startup")
def startup():
    global GRAPH, ILLICIT

    if TX_SOURCE == "db":
        # Load transactions from Postgres
        db = SessionLocal()
        try:
            tx_list = load_transactions_from_db(db)
        finally:
            db.close()

        if not tx_list:
            raise RuntimeError(
                "TX_SOURCE=db but no transactions found in DB. Run producer/consumer first."
                )

        txs = pd.DataFrame(tx_list)

    else:
        # Load transactions from CSV (existing behavior)
        try:
            txs = pd.read_csv(TX_PATH)
        except FileNotFoundError:
            raise RuntimeError(f"Missing {TX_PATH}. Run: python services/ingestion/simulator.py")

    GRAPH = build_tx_graph(txs)
    ILLICIT = pick_seed_illicit_wallets(GRAPH.nodes, pct=0.05, seed=ILLICIT_SEED)



@app.get("/health")
def health():
    return {"status": "ok"}



@app.post("/reload-graph")
def reload_graph(db: Session = Depends(get_db)):
    global GRAPH, ILLICIT

    if TX_SOURCE != "db":
        return {"ok": False, "error": "Set TX_SOURCE=db to use this endpoint."}

    tx_list = load_transactions_from_db(db)
    if not tx_list:
        return {"ok": False, "error": "No transactions found in DB."}

    txs = pd.DataFrame(tx_list)
    GRAPH = build_tx_graph(txs)
    ILLICIT = pick_seed_illicit_wallets(GRAPH.nodes, pct=0.05, seed=ILLICIT_SEED)


    return {"ok": True, "tx_count": len(tx_list)}


# --- OLD: in-memory scoring (still useful) ---
@app.get("/score/{wallet}")
def score_in_memory(wallet: str):
    if GRAPH is None or ILLICIT is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    result = risk_score_wallet(GRAPH, wallet, ILLICIT, cfg)
    if result.get("reason") == "wallet_not_in_graph":
        raise HTTPException(status_code=404, detail=f"Wallet {wallet} not found")
    return result


# --- NEW: persist a scoring run + all wallet scores ---
@app.post("/run-score")
def run_score(db: Session = Depends(get_db)):
    if GRAPH is None or ILLICIT is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    # store run metadata
    run = crud.create_scoring_run(
        db,
        tx_source = f"{TX_SOURCE}:{TX_PATH}" if TX_SOURCE == "csv" else "db:transactions",
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
def top_scores(n: int = 20, db: Session = Depends(get_db)):
    n = max(1, min(n, 500))
    scores = crud.get_top_scores_latest(db, n=n)
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
