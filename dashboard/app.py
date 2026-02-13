import json
from typing import Any

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Crypto AML Risk Platform",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Crypto AML Risk Platform — Dashboard")
st.caption("Analyst-style UI for leaderboard, explainability, and ingestion telemetry.")
st.divider()

st.session_state.setdefault("selected_wallet", None)
st.session_state.setdefault("wallet_graph_payload", None)
st.session_state.setdefault("wallet_graph_params", None)
st.session_state.setdefault("graph_presets", {})  # Store named filter presets

DEFAULT_API = "http://api:8000"  # Docker Compose service name
TIMEOUT = 30
df = pd.DataFrame()  # always defined to avoid blank-page crashes



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

# ----------------------------
# Preset & Export Helpers
# ----------------------------

def save_graph_preset(name: str, preset_data: dict):
    """Save current filter settings as a preset."""
    st.session_state.graph_presets[name] = preset_data
    st.success(f"✅ Preset '{name}' saved!")

def load_graph_preset(name: str) -> dict:
    """Load a saved preset."""
    return st.session_state.graph_presets.get(name, {})

def delete_graph_preset(name: str):
    """Delete a saved preset."""
    if name in st.session_state.graph_presets:
        del st.session_state.graph_presets[name]
        st.success(f"✅ Preset '{name}' deleted!")

def get_preset_names() -> list:
    """Get list of all saved preset names."""
    return sorted(list(st.session_state.graph_presets.keys()))

def export_graph_json(payload: dict, filtered_payload: dict = None) -> str:
    """Export graph data as JSON string."""
    export_data = {
        "raw_graph": payload,
        "filtered_graph": filtered_payload or payload,
        "export_timestamp": pd.Timestamp.now().isoformat(),
    }
    return json.dumps(export_data, indent=2, ensure_ascii=False)

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
tab_overview, tab_leaderboard, tab_explain, tab_graph = st.tabs(
    ["Overview", "Leaderboard", "Explainability", "Wallet Graph"]
)

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
        # --- Risk Snapshot chart (after leaderboard) ---
        st.markdown("### Risk Snapshot (Top 20)")
        if not df.empty and {"wallet", "risk_score"}.issubset(df.columns):
            chart_df = df[["wallet", "risk_score"]].head(20).set_index("wallet")
            st.bar_chart(chart_df)
        else:
            st.caption("No risk snapshot yet (run scoring to populate leaderboard).")






# ============================
# TAB 3: EXPLAINABILITY
# ============================
with tab_explain:
    st.subheader("Explainability Viewer")

    if not wallets:
        st.info("Run scoring to populate leaderboard first.")
    else:
        wallet = st.selectbox("Select wallet", wallets, index=0)
        st.session_state["selected_wallet"] = wallet
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


# ============================
# TAB 4: WALLET GRAPH (REFINED)
# ============================

def render_pyvis_graph(payload: dict):
    highlight = (payload.get("highlight") or "").strip()
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])

    net = Network(
        height="650px",
        width="100%",
        directed=True,
        bgcolor="#0E1117",
        font_color="#E6EDF3",
        cdn_resources="in_line",  # avoids blank embeds in Codespaces sometimes
    )
    net.barnes_hut(gravity=-20000, central_gravity=0.15, spring_length=160, spring_strength=0.04, damping=0.09)

    for n in nodes:
        nid = str(n.get("id"))
        tag = n.get("tag", "neighbor")
        hop = n.get("hop", None)
        rs = n.get("risk_score", None)

        # base styling by tag
        if tag == "center":
            color, size = "#00C853", 30
        elif tag == "illicit":
            color, size = "#FF5252", 22
        else:
            color, size = "#64B5F6", 16

        # apply highlight LAST so it wins
        if highlight and nid == highlight:
            color, size = "#FFD54F", 36  # highlight gold

        title = (
            f"wallet={nid}<br>"
            f"hop={hop}<br>"
            f"risk_score={rs}<br>"
            f"in={n.get('in_degree')} out={n.get('out_degree')}"
        )
        net.add_node(nid, label=nid, title=title, color=color, size=size)

    for e in edges:
        src = str(e.get("source"))
        dst = str(e.get("target"))
        txc = int(e.get("tx_count", 1))
        amt = float(e.get("total_amount", 0.0))
        width = 1 + min(8, txc)
        title = f"tx_count={txc}<br>total_amount={amt:.2f}"
        net.add_edge(src, dst, title=title, width=width)

    html = net.generate_html(notebook=False)
    components.html(html, height=700, scrolling=True)


def apply_graph_filters(payload: dict, *, direction: str, max_hop_show: int, allowed_tags: list[str],
                        min_tx_count: int, min_total_amount: float, top_k_edges: int, highlight_wallet: str) -> dict:
    center = str(payload.get("center")) if payload.get("center") is not None else None

    # normalize nodes/edges to str IDs
    nodes_in = []
    for n in payload.get("nodes", []):
        if isinstance(n, dict) and n.get("id") is not None:
            nn = dict(n)
            nn["id"] = str(nn["id"])
            nodes_in.append(nn)

    edges_in = []
    for e in payload.get("edges", []):
        if isinstance(e, dict) and e.get("source") is not None and e.get("target") is not None:
            ee = dict(e)
            ee["source"] = str(ee["source"])
            ee["target"] = str(ee["target"])
            edges_in.append(ee)

    # 1) nodes by hop + tag
    nodes_kept = [
        n for n in nodes_in
        if (n.get("tag", "neighbor") in allowed_tags)
        and (n.get("hop") is None or int(n.get("hop", 0)) <= int(max_hop_show))
    ]
    node_ids = {n["id"] for n in nodes_kept}

    # 2) edges by direction + thresholds + endpoint presence
    def edge_passes_dir(e):
        if not center:
            return True
        if direction == "outgoing":
            return e["source"] == center
        if direction == "incoming":
            return e["target"] == center
        return True

    edges_kept = []
    for e in edges_in:
        txc = int(e.get("tx_count", 1))
        amt = float(e.get("total_amount", 0.0))

        if not edge_passes_dir(e):
            continue
        if txc < int(min_tx_count):
            continue
        if amt < float(min_total_amount):
            continue
        if e["source"] not in node_ids or e["target"] not in node_ids:
            continue
        edges_kept.append(e)

    # 3) optional top-K edges
    if int(top_k_edges) > 0 and edges_kept:
        edges_kept = sorted(edges_kept, key=lambda x: float(x.get("total_amount", 0.0)), reverse=True)[: int(top_k_edges)]
        connected = set()
        for e in edges_kept:
            connected.add(e["source"])
            connected.add(e["target"])
        if center:
            connected.add(center)
        nodes_kept = [n for n in nodes_kept if n["id"] in connected]

    return {
        "center": center,
        "nodes": nodes_kept,
        "edges": edges_kept,
        "highlight": highlight_wallet.strip(),
    }


with tab_graph:
    st.subheader("Wallet Transaction Network")
    st.caption("Fetch a wallet subgraph from API, then refine it locally with filters.")

    default_wallet = st.session_state.get("selected_wallet", "W0001") or "W0001"

    # ---- Preset Management
    st.markdown("### 💾 Filter Presets")
    preset_cols = st.columns([2, 1, 1])
    with preset_cols[0]:
        preset_name = st.text_input("Preset name", placeholder="e.g., 'illicit_only'", key="preset_name_input")
    with preset_cols[1]:
        if st.button("Save Preset", use_container_width=True):
            if preset_name:
                save_graph_preset(
                    preset_name,
                    {
                        "wallet": st.session_state.get("selected_wallet", "W0001"),
                        "hops": 2,
                        "edge_limit": 600,
                    },
                )
            else:
                st.warning("Enter a preset name first")
    with preset_cols[2]:
        preset_names = get_preset_names()
        if preset_names:
            selected_preset = st.selectbox("Load preset", preset_names, key="preset_selector")
            if st.button("Load", use_container_width=True):
                preset = load_graph_preset(selected_preset)
                st.session_state["selected_wallet"] = preset.get("wallet", "W0001")
                st.info(f"✅ Loaded preset '{selected_preset}'")
                st.rerun()

    if preset_names:
        with st.expander("Manage Presets"):
            for pname in preset_names:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"📌 {pname}")
                with col2:
                    if st.button("🗑️", key=f"del_{pname}"):
                        delete_graph_preset(pname)
                        st.rerun()

    # ---- Fetch controls (minimal, avoids duplicates)
    with st.form("graph_fetch_form", clear_on_submit=False):
        c1, c2, c3 = st.columns([1.2, 1, 1])
        with c1:
            wallet = st.text_input("Wallet", value=default_wallet)
        with c2:
            hops = st.slider("Hops (API)", 1, 4, 2)
        with c3:
            edge_limit = st.slider("Max edges (API)", 50, 3000, 600, step=50)

        b_fetch, b_clear = st.columns(2)
        load_clicked = b_fetch.form_submit_button("Load Graph", use_container_width=True)
        clear_clicked = b_clear.form_submit_button("Clear Graph", use_container_width=True)

    if clear_clicked:
        st.session_state["wallet_graph_payload"] = None
        st.session_state["wallet_graph_params"] = None
        st.info("Cleared graph.")

    if load_clicked:
        payload, err = safe_call(
            _get,
            api_base,
            f"/graph/wallet/{wallet}?hops={hops}&edge_limit={edge_limit}",
        )
        if err:
            st.error(err)
        else:
            st.session_state["wallet_graph_payload"] = payload
            st.session_state["wallet_graph_params"] = {"wallet": wallet, "hops": hops, "edge_limit": edge_limit}
            st.success(f"Loaded {len(payload.get('nodes', []))} nodes and {len(payload.get('edges', []))} edges.")

    payload = st.session_state.get("wallet_graph_payload")

    # ---- View filters (single place for filtering)
    filtered_payload = None
    if payload:
        st.markdown("### Graph Filters (View)")

        f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.6, 1.4])
        with f1:
            direction = st.selectbox("Direction", ["both", "outgoing", "incoming"], index=0)
        with f2:
            # default to API hops so it doesn’t feel duplicated
            max_hop_show = st.slider("Show hops ≤", 0, 4, int(st.session_state["wallet_graph_params"]["hops"]))
        with f3:
            allowed_tags = st.multiselect(
                "Include tags",
                ["center", "illicit", "neighbor"],
                default=["center", "illicit", "neighbor"],
            )
        with f4:
            # Auto-highlight selected node from wallet info panel
            default_highlight = st.session_state.get("highlighted_node", "").strip()
            highlight_wallet = st.text_input("Highlight wallet (optional)", value=default_highlight).strip()
            if default_highlight and not highlight_wallet:
                highlight_wallet = default_highlight

        g1, g2, g3 = st.columns(3)
        with g1:
            min_tx_count = st.number_input("Min tx_count", min_value=0, value=0, step=1)
        with g2:
            min_total_amount = st.number_input("Min total_amount", min_value=0.0, value=0.0, step=10.0)
        with g3:
            top_k_edges = st.number_input("Top-K edges by amount (0=off)", min_value=0, value=0, step=50)

        filtered_payload = apply_graph_filters(
            payload,
            direction=direction,
            max_hop_show=max_hop_show,
            allowed_tags=allowed_tags,
            min_tx_count=min_tx_count,
            min_total_amount=min_total_amount,
            top_k_edges=top_k_edges,
            highlight_wallet=highlight_wallet,
        )

    # ---- Export Controls
    if payload:
        # Update payload with selected node highlight for display
        display_payload = filtered_payload if filtered_payload else payload
        selected_highlight = st.session_state.get("highlighted_node", "")
        if selected_highlight and display_payload:
            display_payload = dict(display_payload)  # Make a copy
            display_payload["highlight"] = selected_highlight
        st.markdown("### 📥 Export Graph")
        exp_col1, exp_col2 = st.columns(2)
        
        with exp_col1:
            # Export raw JSON
            raw_json = export_graph_json(payload, filtered_payload)
            st.download_button(
                label="📄 Export JSON (Raw + Filtered)",
                data=raw_json,
                file_name=f"graph_{st.session_state.get('wallet_graph_params', {}).get('wallet', 'unknown')}.json",
                mime="application/json",
                use_container_width=True,
            )
        
        with exp_col2:
            # Export CSV (nodes & edges)
            var_json = export_graph_json(payload, filtered_payload)
            st.download_button(
                label="📊 Export as JSON (Pretty)",
                data=var_json,
                file_name=f"graph_data_{st.session_state.get('wallet_graph_params', {}).get('wallet', 'unknown')}_formatted.json",
                mime="application/json",
                use_container_width=True,
            )

    left, right = st.columns([3, 1], gap="large")

    with left:
        if filtered_payload:
            render_pyvis_graph(display_payload if payload else filtered_payload)
        elif payload:
            render_pyvis_graph(display_payload if payload else payload)
        else:
            st.info("Load a wallet graph to visualize it here.")

    with right:
        st.subheader("Wallet Info")
        if not payload:
            st.caption("No graph loaded yet.")
        else:
            center = str(payload.get("center")) if payload.get("center") is not None else None
            nodes = payload.get("nodes", [])
            edges = payload.get("edges", [])

            node_by_id = {str(n.get("id")): n for n in nodes if isinstance(n, dict) and n.get("id") is not None}
            
            # ---- Node selector for direct click simulation
            st.markdown("**🔍 Select a Node**")
            node_ids = sorted(list(node_by_id.keys()))
            selected_node = st.selectbox(
                "Click to inspect wallet:",
                node_ids,
                index=node_ids.index(center) if center in node_ids else 0,
                key="node_selector",
            )
            
            # Update highlight in session state for graph rendering
            st.session_state["highlighted_node"] = selected_node
            
            # Use selected node for info display
            center = selected_node
            center_node = node_by_id.get(center, {})
            
            # Show node tag with visual indicator
            tag = center_node.get("tag", "neighbor")
            tag_colors = {"center": "🟢 Center", "illicit": "🔴 Illicit", "neighbor": "🔵 Neighbor"}
            st.info(f"**Node Type:** {tag_colors.get(tag, tag)}")

            in_edges = [e for e in edges if str(e.get("target")) == center]
            out_edges = [e for e in edges if str(e.get("source")) == center]

            def _sum_amount(es):
                s = 0.0
                for e in es:
                    try:
                        s += float(e.get("total_amount", 0.0))
                    except Exception:
                        pass
                return s

            total_in = _sum_amount(in_edges)
            total_out = _sum_amount(out_edges)

            neighbors = set()
            for e in edges:
                if str(e.get("source")) == center:
                    neighbors.add(str(e.get("target")))
                if str(e.get("target")) == center:
                    neighbors.add(str(e.get("source")))

            st.metric("Wallet", center or "n/a")
            a, b = st.columns(2)
            a.metric("Nodes", len(nodes))
            b.metric("Edges", len(edges))

            a, b = st.columns(2)
            a.metric("Neighbors", len([n for n in neighbors if n]))
            b.metric("Tag", center_node.get("tag", "n/a"))

            a, b = st.columns(2)
            a.metric("In edges", len(in_edges))
            b.metric("Out edges", len(out_edges))

            st.metric("Total In Amount", f"{total_in:,.2f}")
            st.metric("Total Out Amount", f"{total_out:,.2f}")

            if st.button("Use in Explainability", use_container_width=True):
                st.session_state["selected_wallet"] = center

            with st.expander("Raw node"):
                st.json(center_node)

# ----------------------------
# Auto refresh (keep LAST)
# ----------------------------

pause_refresh_when_graph_loaded = st.sidebar.checkbox(
    "Pause auto-refresh when graph is loaded",
    value=True,
)

graph_loaded = bool(st.session_state.get("wallet_graph_payload"))

if auto_refresh and not (pause_refresh_when_graph_loaded and graph_loaded):
    st_autorefresh(interval=refresh_seconds * 1000, key="auto_refresh")