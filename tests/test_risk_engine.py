import pandas as pd

from services.scoring.risk_engine import RiskConfig, build_tx_graph, risk_score_wallet


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
