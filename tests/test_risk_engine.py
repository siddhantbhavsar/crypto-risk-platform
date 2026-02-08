import pandas as pd

from services.scoring.risk_engine import (
    RiskConfig,
    build_tx_graph,
    explain_wallet_risk,
    risk_score_wallet,
)


def test_build_tx_graph_creates_nodes_and_edges():
    txs = pd.DataFrame(
        [
            {"src": "W0001", "dst": "W0002"},
            {"src": "W0002", "dst": "W0003"},
        ]
    )
    g = build_tx_graph(txs)
    assert g.number_of_nodes() == 3
    assert g.number_of_edges() == 2


def test_risk_score_wallet_returns_expected_fields():
    txs = pd.DataFrame([{"src": "W0001", "dst": "W0002"}])
    g = build_tx_graph(txs)
    illicit = {"W0002"}
    cfg = RiskConfig(hop_weights=(1.0, 0.6, 0.3), degree_normalize=False)

    r = risk_score_wallet(g, "W0001", illicit, cfg)
    assert "wallet" in r
    assert "risk_score" in r
    assert "exposures" in r
    assert "in_degree" in r
    assert "out_degree" in r

def test_explain_wallet_risk_returns_expected_structure_and_counts():
    txs = pd.DataFrame(
        [
            {"src": "W0001", "dst": "W0002"},
            {"src": "W0002", "dst": "W0003"},
        ]
    )
    g = build_tx_graph(txs)
    illicit = {"W0003"}
    cfg = RiskConfig(hop_weights=(1.0, 0.6, 0.3), degree_normalize=False)

    exp = explain_wallet_risk(g, "W0001", illicit, cfg, max_hops=2)

    assert exp["wallet"] == "W0001"
    assert "hop_breakdown" in exp
    assert "top_contributors" in exp
    assert "explain_score" in exp

    # Exact-hop expectations:
    # W0001 is hop0 (not illicit)
    # W0002 is hop1 (not illicit)
    # W0003 is hop2 (illicit)
    hb = exp["hop_breakdown"]
    assert hb[0]["illicit_count_exact"] == 0
    assert hb[1]["illicit_count_exact"] == 0
    assert hb[2]["illicit_count_exact"] == 1

    # And W0003 should appear as a contributor at hop 2
    assert any(c["wallet"] == "W0003" and c["hop"] == 2 for c in exp["top_contributors"])
