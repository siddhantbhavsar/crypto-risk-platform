import json
import sys
from typing import Any, Dict, List

import requests

BASE_URL = "http://localhost:8000"
TIMEOUT = 60


def hr(title: str) -> None:
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


def pretty(obj: Any, depth: int = 6) -> str:
    # safe pretty JSON
    return json.dumps(obj, indent=2, ensure_ascii=False)


def request_json(method: str, path: str) -> Any:
    url = BASE_URL + path
    r = requests.request(method, url, timeout=TIMEOUT)
    try:
        r.raise_for_status()
    except requests.HTTPError:
        # Show error body if possible
        try:
            body = r.json()
        except Exception:
            body = r.text
        raise RuntimeError(f"{method} {path} failed: {r.status_code}\n{body}")
    return r.json()


def post(path: str) -> Any:
    return request_json("POST", path)


def get(path: str) -> Any:
    return request_json("GET", path)


def print_top_wallets(top: List[Dict[str, Any]], limit: int = 10) -> None:
    if not top:
        print("No scores returned.")
        return

    print(f"{'Rank':<6}{'Wallet':<14}{'Risk':<10}{'In':<6}{'Out':<6}")
    print("-" * 50)
    for i, row in enumerate(top[:limit], start=1):
        wallet = row.get("wallet", "")
        risk = row.get("risk_score", 0)
        in_deg = row.get("in_degree", 0)
        out_deg = row.get("out_degree", 0)
        print(f"{i:<6}{wallet:<14}{risk:<10.4f}{in_deg:<6}{out_deg:<6}")


def summarize_explain(explain: Dict[str, Any]) -> None:
    """
    Prints a human-readable explainability summary.
    Your API returns:
      explainability.hop_breakdown (exact hop)
      explainability.top_contributors
    and stored_score.exposures_cumulative (DB cumulative)
    """
    ex = explain.get("explainability", {})
    stored = explain.get("stored_score", {})

    wallet = explain.get("wallet", "UNKNOWN")
    risk_score = stored.get("risk_score")
    run_id = stored.get("run_id")

    hr(f"Explainability Summary — {wallet} (run_id={run_id}, stored_risk={risk_score})")

    hop_breakdown = ex.get("hop_breakdown", [])
    if hop_breakdown:
        print("\nHop breakdown (EXACT hop illicit exposure + weighted contribution):")
        print(f"{'Hop':<6}{'Weight':<10}{'Illicit(exact)':<16}{'Contribution':<14}{'Sample':<0}")
        print("-" * 90)
        for h in hop_breakdown:
            hop = h.get("hop")
            weight = h.get("weight")
            cnt = h.get("illicit_count_exact")
            contrib = h.get("contribution")
            sample = h.get("illicit_wallets_sample", [])
            sample_str = ", ".join(sample[:5]) + (" ..." if len(sample) > 5 else "")
            print(f"{hop:<6}{weight:<10}{cnt:<16}{contrib:<14}{sample_str}")

    contributors = ex.get("top_contributors", [])
    if contributors:
        print("\nTop contributors (sample):")
        print(f"{'Wallet':<14}{'Hop':<6}{'Weight':<10}{'Contribution':<12}")
        print("-" * 50)
        for c in contributors[:10]:
            print(
                f"{c.get('wallet',''):<14}{c.get('hop',0):<6}{c.get('weight',0):<10}{c.get('contribution',0):<12}"
            )

    # Also show what DB stored (cumulative exposure)
    exposures_cum = stored.get("exposures_cumulative")
    if exposures_cum:
        print("\nStored exposures from DB (CUMULATIVE by hop):")
        print(pretty(exposures_cum))


def main() -> None:
    hr("1) Health check")
    print(pretty(get("/health")))

    hr("2) Ingestion status (before)")
    print(pretty(get("/ingestion/status")))

    hr("3) Reload graph")
    print(pretty(post("/reload-graph")))

    hr("4) Run scoring")
    print(pretty(post("/run-score")))

    hr("5) Top wallets")
    top = get("/scores/top?limit=10")
    print_top_wallets(top, limit=10)

    if not top:
        print("\nNo top scores found. Did ingestion run and scoring persist results?")
        sys.exit(1)

    wallet = top[0]["wallet"]

    hr(f"6) Explainability for top wallet: {wallet}")
    explain = get(f"/scores/explain/{wallet}?max_hops=2&per_hop_limit=10&total_limit=25")

    # Human summary
    summarize_explain(explain)

    # Full JSON (proof) — if you want *only* summary, delete this block
    hr("Explainability JSON (full payload)")
    print(pretty(explain))

    hr("7) Ingestion status (after)")
    print(pretty(get("/ingestion/status")))

    print("\n✅ Demo complete.")


if __name__ == "__main__":
    main()
