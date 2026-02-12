import json
from typing import Any

import pandas as pd
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Crypto AML Risk Platform",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Crypto AML Risk Platform — Dashboard")
st.caption("Analyst-style UI for leaderboard, explainability, and ingestion telemetry.")
st.divider()


DEFAULT_API = "http://api:8000"  # Docker Compose service name
TIMEOUT = 30



def _get(base: str, path: str) -> Any:
    r = requests.get(f"{base}{path}", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _post(base: str, path: str) -> Any:
    r = requests.post(f"{base}{path}", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except Exception as e:
        return None, str(e)

@st.cache_data(ttl=5, show_spinner=False)
def cached_get(base: str, path: str):
    return _get(base, path)

# Sidebar
st.sidebar.header("Settings")
api_base = st.sidebar.text_input("API Base URL", value=DEFAULT_API)
auto_refresh = st.sidebar.checkbox("Auto refresh", value=False)
refresh_seconds = st.sidebar.slider("Refresh interval (seconds)", 3, 60, 10)


st.sidebar.divider()
st.sidebar.header("Actions")

b1, b2 = st.sidebar.columns(2)

reload_clicked = b1.button("Reload Graph", use_container_width=True)
run_score_clicked = b2.button("Run Score", use_container_width=True)

if reload_clicked:
    res, err = safe_call(_post, api_base, "/reload-graph")
    if err:
        st.sidebar.error(err)
    else:
        st.sidebar.success("Graph reloaded")
        # optional: remove JSON spam
        # st.sidebar.json(res)

if run_score_clicked:
    res, err = safe_call(_post, api_base, "/run-score")
    if err:
        st.sidebar.error(err)
    else:
        st.sidebar.success("Scoring complete")
        # st.sidebar.json(res)

# ----------------------------
# Shared fetch (used by multiple tabs)
# ----------------------------
top_for_wallets, _ = safe_call(cached_get, api_base, "/scores/top?limit=50")
wallets = []
if isinstance(top_for_wallets, list) and top_for_wallets:
    try:
        wallets = [row.get("wallet") for row in top_for_wallets if isinstance(row, dict) and row.get("wallet")]
    except Exception:
        wallets = []


# ----------------------------
# Tabs
# ----------------------------
tab_overview, tab_leaderboard, tab_explain = st.tabs(["Overview", "Leaderboard", "Explainability"])


# ============================
# TAB 1: OVERVIEW
# ============================
with tab_overview:
    c1, c2, c3 = st.columns(3)

    with c1:
        st.subheader("Health")
        health, err = safe_call(cached_get, api_base, "/health")
        if err:
            st.error(err)
        else:
            st.success("OK")
            st.metric("API Status", "OK")
            with st.expander("Raw response"):
                st.json(health)

    with c2:
        st.subheader("Readiness")
        ready, err = safe_call(cached_get, api_base, "/ready")
        if err:
            st.warning("Not ready")
            st.caption("Reload graph to become ready.")
            st.write(err)
        else:
            st.success("Ready")
            st.metric("Graph Ready", "YES")
            with st.expander("Raw response"):
                st.json(ready)

    with c3:
        st.subheader("Ingestion Status")
        status, err = safe_call(cached_get, api_base, "/ingestion/status")
        if err:
            st.error(err)
        else:
            metrics = status.get("metrics", {}) if isinstance(status, dict) else {}
            tx_count = status.get("tx_count")
            seconds_since = metrics.get("seconds_since_last_processed")
            total_inserted = metrics.get("total_inserted")

            a, b, c = st.columns(3)
            a.metric("Tx Count", tx_count if tx_count is not None else "n/a")
            b.metric("Inserted", total_inserted if total_inserted is not None else "n/a")
            c.metric(
                "Last Ingest (sec)",
                f"{seconds_since:.0f}" if isinstance(seconds_since, (int, float)) else "n/a",
            )

            with st.expander("Raw response"):
                st.json(status)


# ============================
# TAB 2: LEADERBOARD
# ============================
with tab_leaderboard:
    st.subheader("Top Wallets (Leaderboard)")
    limit = st.slider("Limit", 5, 50, 10, key="leader_limit")

    top, err = safe_call(cached_get, api_base, f"/scores/top?limit={limit}")
    if err:
        st.error(err)
        top = []

    if not top:
        st.info("No scores yet. Ingest data → Reload graph → Run score.")
    else:
        df = pd.DataFrame(top)

        # Show table first
        cols = [
            c for c in ["wallet", "risk_score", "in_degree", "out_degree", "created_at", "run_id"]
            if c in df.columns
        ]
        df2 = df[cols] if cols else df

        if "risk_score" in df2.columns:
            st.dataframe(
                df2.style.format({"risk_score": "{:.4f}"}).background_gradient(subset=["risk_score"], cmap="Reds"),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.dataframe(df2, use_container_width=True, hide_index=True)

        # Chart AFTER table (cleaner UX)
        st.markdown("### Risk Snapshot (Top 20)")
        if "wallet" in df.columns and "risk_score" in df.columns:
            chart_df = (
                df[["wallet", "risk_score"]]
                .head(20)
                .sort_values("risk_score", ascending=False)
                .set_index("wallet")
            )
            st.bar_chart(chart_df)


# ============================
# TAB 3: EXPLAINABILITY
# ============================
with tab_explain:
    st.subheader("Explainability Viewer")

    if not wallets:
        st.info("Run scoring to populate leaderboard first.")
    else:
        wallet = st.selectbox("Select wallet", wallets, index=0)
        max_hops = st.selectbox("Max hops", [1, 2, 3], index=1)
        per_hop_limit = st.slider("Per-hop sample", 5, 50, 10, key="per_hop_limit")
        total_limit = st.slider("Total contributors limit", 10, 200, 25, key="total_limit")

        explain, err = safe_call(
            _get,
            api_base,
            f"/scores/explain/{wallet}?max_hops={max_hops}&per_hop_limit={per_hop_limit}&total_limit={total_limit}",
        )

        if err:
            st.error(err)
        else:
            stored = explain.get("stored_score", {})
            st.metric("Stored Risk Score", value=stored.get("risk_score", "n/a"))
            st.caption(f"run_id={stored.get('run_id','n/a')} • created_at={stored.get('created_at','n/a')}")

            ex = explain.get("explainability", {})
            hb = ex.get("hop_breakdown", [])
            contrib = ex.get("top_contributors", [])

            # ---- 3 sub-tabs inside Explainability (optional but nice)
            t1, t2, t3 = st.tabs(["Hop Breakdown", "Top Contributors", "Raw JSON"])

            with t1:
                if hb:
                    hb_df = pd.DataFrame(hb)
                    hb_cols = [
                        c for c in ["hop", "weight", "illicit_count_exact", "contribution", "sample_truncated"]
                        if c in hb_df.columns
                    ]
                    st.dataframe(hb_df[hb_cols], use_container_width=True, hide_index=True)
                else:
                    st.info("No hop breakdown returned.")

            with t2:
                if contrib:
                    c_df = pd.DataFrame(contrib)
                    c_cols = [c for c in ["wallet", "hop", "weight", "contribution"] if c in c_df.columns]
                    st.dataframe(c_df[c_cols], use_container_width=True, hide_index=True)

                    st.markdown("### Contribution Chart (Top)")
                    if "wallet" in c_df.columns and "contribution" in c_df.columns:
                        st.bar_chart(
                            c_df[["wallet", "contribution"]].head(15).set_index("wallet")["contribution"]
                        )
                else:
                    st.info("No contributors returned.")

            with t3:
                st.code(pretty(explain), language="json")


# ----------------------------
# Auto refresh (keep LAST)
# ----------------------------
if auto_refresh:
    try:
        st_autorefresh(interval=refresh_seconds * 1000, key="auto_refresh")
    except Exception as e:
        st.warning(f"Auto refresh unavailable: {e}")