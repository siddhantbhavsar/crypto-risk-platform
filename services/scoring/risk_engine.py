from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

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
    Aggregates transaction counts and amounts per edge.
    """
    required = {"src", "dst"}
    missing = required - set(txs.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    g = nx.DiGraph()
    
    # Build edge dictionary with aggregated amounts
    edge_data = {}
    for row in txs.itertuples(index=False):
        src = row.src
        dst = row.dst
        edge_key = (src, dst)
        amount = float(getattr(row, 'amount', 0.0)) if hasattr(row, 'amount') else 0.0
        
        if edge_key not in edge_data:
            edge_data[edge_key] = {"tx_count": 0, "amount": 0.0}
        
        edge_data[edge_key]["tx_count"] += 1
        edge_data[edge_key]["amount"] += amount
    
    # Add edges with aggregated data
    for (src, dst), data in edge_data.items():
        g.add_edge(src, dst, tx_count=data["tx_count"], amount=data["amount"])
    
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
        raw = raw / (deg**0.5)

    return {
        "wallet": wallet,
        "risk_score": round(float(raw), 6),
        "exposures": [{"hop": hop, "weight": w, "illicit_count": cnt} for hop, w, cnt in exposures],
        "in_degree": int(g.in_degree(wallet)),
        "out_degree": int(g.out_degree(wallet)),
    }


def score_top_wallets(
    g: nx.DiGraph, illicit: Set[str], cfg: RiskConfig, top_n: int = 20
) -> pd.DataFrame:
    rows: List[Dict] = []
    for w in g.nodes:
        r = risk_score_wallet(g, w, illicit, cfg)
        rows.append({"wallet": r["wallet"], "risk_score": r["risk_score"]})
    df = pd.DataFrame(rows).sort_values("risk_score", ascending=False).head(top_n)
    return df

def k_hop_layers_undirected(g: nx.DiGraph, start: str, max_hops: int) -> list[set[str]]:
    """
    layers[h] = set of nodes at EXACTLY h undirected hops from start
    layers[0] = {start}
    """
    if start not in g:
        return []

    layers: list[set[str]] = [{start}]
    visited: set[str] = {start}
    frontier: set[str] = {start}

    for _hop in range(1, max_hops + 1):
        nxt: set[str] = set()
        for n in frontier:
            nxt |= neighbors_undirected(g, n)  # uses your existing helper
        nxt -= visited
        layers.append(nxt)
        visited |= nxt
        frontier = nxt
        if not frontier:
            # keep appending empties is fine; we've already appended this hop
            continue

    return layers


def explain_wallet_risk(
    g: nx.DiGraph,
    wallet: str,
    illicit: set[str],
    cfg: Any,  # use your RiskConfig type if you want
    max_hops: Optional[int] = None,
    per_hop_limit: int = 15,
    total_limit: int = 50,
) -> dict[str, Any]:
    """
    Explain score with:
      - exact-hop illicit wallets (interpretability)
      - weighted contribution per hop
      - top contributors

    NOTE: Your stored exposures_json is cumulative-by-hop.
          This explain output is exact-by-hop.
    """
    if wallet not in g:
        return {"wallet": wallet, "reason": "wallet_not_in_graph"}

    hop_weights = tuple(cfg.hop_weights)
    if max_hops is None:
        max_hops = len(hop_weights) - 1
    max_hops = max(0, min(int(max_hops), len(hop_weights) - 1))

    layers = k_hop_layers_undirected(g, wallet, max_hops)

    in_deg = int(g.in_degree(wallet))
    out_deg = int(g.out_degree(wallet))
    deg = (in_deg + out_deg) or 1

    norm = math.sqrt(deg) if getattr(cfg, "degree_normalize", False) else 1.0

    hop_breakdown: list[dict[str, Any]] = []
    contributors: list[dict[str, Any]] = []

    for hop in range(0, max_hops + 1):
        layer = layers[hop] if hop < len(layers) else set()
        illicit_here = sorted([n for n in layer if n in illicit])

        w = float(hop_weights[hop])
        hop_contrib = (w * len(illicit_here)) / norm
        per_wallet = w / norm if illicit_here else 0.0

        hop_breakdown.append(
            {
                "hop": hop,
                "weight": w,
                "illicit_count_exact": len(illicit_here),
                "contribution": round(hop_contrib, 6),
                "illicit_wallets_sample": illicit_here[:per_hop_limit],
                "sample_truncated": len(illicit_here) > per_hop_limit,
            }
        )

        for n in illicit_here:
            contributors.append(
                {"wallet": n, "hop": hop, "weight": w, "contribution": round(per_wallet, 6)}
            )

    contributors.sort(key=lambda x: (-x["contribution"], x["hop"], x["wallet"]))
    if len(contributors) > total_limit:
        contributors = contributors[:total_limit]

    explain_score = sum(item["contribution"] for item in hop_breakdown)

    return {
        "wallet": wallet,
        "in_degree": in_deg,
        "out_degree": out_deg,
        "degree_normalize": bool(getattr(cfg, "degree_normalize", False)),
        "normalization_factor": round(float(norm), 6),
        "hop_breakdown": hop_breakdown,
        "top_contributors": contributors,
        "explain_score": round(float(explain_score), 6),
    }