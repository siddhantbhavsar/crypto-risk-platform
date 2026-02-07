from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple

import networkx as nx
import pandas as pd


@dataclass(frozen=True)
class RiskConfig:
    # how much weight to give to exposure at each hop
    hop_weights: Tuple[float, ...] = (1.0, 0.6, 0.3)  # 0-hop, 1-hop, 2-hop
    # optional: normalize by degree to avoid huge-wallet bias
    degree_normalize: bool = True


def build_tx_graph(txs: pd.DataFrame) -> nx.DiGraph:
    """
    Directed graph: src -> dst for each transaction.
    """
    required = {"src", "dst"}
    missing = required - set(txs.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    g = nx.DiGraph()
    for row in txs[["src", "dst"]].itertuples(index=False):
        g.add_edge(row.src, row.dst)
    return g


def pick_seed_illicit_wallets(nodes: Iterable[str], pct: float = 0.05, seed: int = 42) -> Set[str]:
    """
    Simulate a tiny known-illicit set. Later you’ll replace this with real labels.
    """
    nodes = list(nodes)
    if not nodes:
        return set()
    rng = __import__("random")
    rng.seed(seed)
    k = max(1, int(len(nodes) * pct))
    return set(rng.sample(nodes, k))


def neighbors_undirected(g: nx.DiGraph, node: str) -> Set[str]:
    # exposure can come from in/out flows; treat as undirected neighborhood for exposure
    return set(g.predecessors(node)).union(set(g.successors(node)))


def k_hop_exposure(g: nx.DiGraph, node: str, illicit: Set[str], k: int) -> int:
    """
    Count illicit wallets reachable within k hops (undirected neighborhood).
    """
    if k == 0:
        return int(node in illicit)

    frontier = {node}
    visited = {node}
    for _ in range(k):
        nxt = set()
        for n in frontier:
            nxt |= neighbors_undirected(g, n)
        nxt -= visited
        visited |= nxt
        frontier = nxt
        if not frontier:
            break

    return sum(1 for n in visited if n in illicit)


def risk_score_wallet(g: nx.DiGraph, wallet: str, illicit: Set[str], cfg: RiskConfig) -> Dict:
    if wallet not in g:
        return {"wallet": wallet, "risk_score": 0.0, "reason": "wallet_not_in_graph"}

    exposures = []
    for hop, w in enumerate(cfg.hop_weights):
        exposures.append((hop, w, k_hop_exposure(g, wallet, illicit, hop)))

    raw = sum(w * cnt for hop, w, cnt in exposures)

    if cfg.degree_normalize:
        deg = (g.in_degree(wallet) + g.out_degree(wallet)) or 1
        raw = raw / (deg ** 0.5)

    return {
        "wallet": wallet,
        "risk_score": round(float(raw), 6),
        "exposures": [{"hop": hop, "weight": w, "illicit_count": cnt} for hop, w, cnt in exposures],
        "in_degree": int(g.in_degree(wallet)),
        "out_degree": int(g.out_degree(wallet)),
    }


def score_top_wallets(g: nx.DiGraph, illicit: Set[str], cfg: RiskConfig, top_n: int = 20) -> pd.DataFrame:
    rows: List[Dict] = []
    for w in g.nodes:
        r = risk_score_wallet(g, w, illicit, cfg)
        rows.append({"wallet": r["wallet"], "risk_score": r["risk_score"]})
    df = pd.DataFrame(rows).sort_values("risk_score", ascending=False).head(top_n)
    return df
