from fastapi import FastAPI, HTTPException
import pandas as pd

from services.scoring.risk_engine import (
    RiskConfig,
    build_tx_graph,
    pick_seed_illicit_wallets,
    risk_score_wallet,
)

app = FastAPI(title="Crypto Risk Platform API", version="0.1.0")

# Load once at startup (simple + fast for now)
TX_PATH = "data/transactions.csv"
cfg = RiskConfig(hop_weights=(1.0, 0.6, 0.3), degree_normalize=True)

GRAPH = None
ILLICIT = None


@app.on_event("startup")
def startup():
    global GRAPH, ILLICIT
    try:
        txs = pd.read_csv(TX_PATH)
    except FileNotFoundError:
        raise RuntimeError(
            f"Missing {TX_PATH}. Run: python services/ingestion/simulator.py"
        )

    GRAPH = build_tx_graph(txs)
    ILLICIT = pick_seed_illicit_wallets(GRAPH.nodes, pct=0.05)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/score/{wallet}")
def score(wallet: str):
    if GRAPH is None or ILLICIT is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    result = risk_score_wallet(GRAPH, wallet, ILLICIT, cfg)

    if result.get("reason") == "wallet_not_in_graph":
        raise HTTPException(status_code=404, detail=f"Wallet {wallet} not found")

    return result
