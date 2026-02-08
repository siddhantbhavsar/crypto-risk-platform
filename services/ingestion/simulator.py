from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from typing import List

import pandas as pd


def generate_wallet_id(i: int) -> str:
    return f"W{i:04d}"


def simulate_transactions(
    n_wallets: int = 200,
    n_txs: int = 2000,
    start_days_ago: int = 30,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Create a toy transaction table:
    tx_id, ts, src, dst, amount
    """
    random.seed(seed)
    RUN_PREFIX = int(time.time())

    wallets = [generate_wallet_id(i) for i in range(n_wallets)]
    start = datetime.utcnow() - timedelta(days=start_days_ago)

    rows: List[dict] = []
    for t in range(n_txs):
        src = random.choice(wallets)
        dst = random.choice(wallets)
        while dst == src:
            dst = random.choice(wallets)

        ts = start + timedelta(seconds=random.randint(0, start_days_ago * 24 * 3600))
        amount = round(max(0.01, random.random() ** 2 * 10_000), 2)  # skewed amounts

        rows.append(
            {
                "tx_id": f"T{RUN_PREFIX}_{t:06d}",
                "timestamp": ts.isoformat(),
                "src": src,
                "dst": dst,
                "amount": amount,
            }
        )

    return pd.DataFrame(rows)


def write_transactions_csv(df: pd.DataFrame, path: str = "data/transactions.csv") -> str:
    df.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    df = simulate_transactions()
    out = write_transactions_csv(df)
    print(f"Wrote {len(df)} transactions to {out}")
