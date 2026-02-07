import pandas as pd

from services.scoring.risk_engine import (
    RiskConfig,
    build_tx_graph,
    pick_seed_illicit_wallets,
    score_top_wallets,
)

TX_PATH = "data/transactions.csv"

if __name__ == "__main__":
    txs = pd.read_csv(TX_PATH)
    g = build_tx_graph(txs)

    illicit = pick_seed_illicit_wallets(g.nodes, pct=0.05)
    cfg = RiskConfig(hop_weights=(1.0, 0.6, 0.3), degree_normalize=True)

    top = score_top_wallets(g, illicit, cfg, top_n=20)
    print("\n=== Top Risk Wallets (toy) ===")
    print(top.to_string(index=False))
    print(f"\nKnown-illicit seeds: {len(illicit)}")
    print(f"Graph nodes: {g.number_of_nodes()}, edges: {g.number_of_edges()}")
