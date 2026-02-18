import os
from datetime import datetime, timezone

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from services.scoring.risk_engine import (
    RiskConfig,
    build_tx_graph,
    explain_wallet_risk,
    k_hop_layers_undirected,
    pick_seed_illicit_wallets,
    risk_score_wallet,
)

from . import crud
from .db import SessionLocal, get_db

TX_SOURCE = os.getenv("TX_SOURCE", "csv").lower()

app = FastAPI(title="Crypto Risk Platform API", version="0.2.0")

TX_PATH = "data/transactions.csv"

cfg = RiskConfig(hop_weights=(1.0, 0.6, 0.3), degree_normalize=True)

GRAPH_READY = False
GRAPH_ERROR = None
GRAPH = None
ILLICIT = None
ILLICIT_SEED = int(os.getenv("ILLICIT_SEED", "42"))


def load_transactions_from_db(db):
    rows = crud.fetch_all_transactions(db)
    transactions = []
    for r in rows:
        tx = {
            "src": r.sender,
            "dst": r.receiver,
            "amount": float(r.amount or 0.0),
        }
        # Ensure timestamp is a string, not a datetime object
        if r.timestamp:
            tx["timestamp"] = str(r.timestamp) if not isinstance(r.timestamp, str) else r.timestamp
        transactions.append(tx)
    return transactions


@app.on_event("startup")
async def startup():
    global GRAPH, ILLICIT, GRAPH_READY, GRAPH_ERROR

    print("=" * 80, flush=True)
    print("🚀 Starting up API", flush=True)
    print("=" * 80, flush=True)

    GRAPH_READY = False
    GRAPH_ERROR = None

    print(f"🔧 TX_SOURCE={TX_SOURCE}, TX_PATH={TX_PATH}", flush=True)

    try:
        if TX_SOURCE == "db":
            print("📊 Loading transactions from database...", flush=True)
            db = SessionLocal()
            try:
                tx_list = load_transactions_from_db(db)
            finally:
                db.close()

            if not tx_list:
                GRAPH_ERROR = (
                    "TX_SOURCE=db but no transactions found. Ingest first, then POST /reload-graph."
                )
                print(f"⚠️  {GRAPH_ERROR}", flush=True)
                return

            txs = pd.DataFrame(tx_list)
            print(f"✅ Loaded {len(txs)} transactions from database", flush=True)

        else:
            print(f"📄 Loading transactions from CSV: {TX_PATH}", flush=True)
            txs = pd.read_csv(TX_PATH)
            print(f"✅ Loaded {len(txs)} transactions from CSV", flush=True)

        GRAPH = build_tx_graph(txs)
        ILLICIT = pick_seed_illicit_wallets(GRAPH.nodes, pct=0.05, seed=ILLICIT_SEED)

        GRAPH_READY = True
        print(f"✅ Graph loaded successfully! Nodes: {len(GRAPH.nodes)}, Edges: {len(GRAPH.edges)}", flush=True)
        print("=" * 80, flush=True)

    except ProgrammingError as e:
        import traceback
        GRAPH_ERROR = f"Graph not loaded at startup (DB not ready/migrated): {e}"
        GRAPH_READY = False
        print(f"❌ DATABASE ERROR: {GRAPH_ERROR}", flush=True)
        print(traceback.format_exc(), flush=True)
        print("=" * 80, flush=True)

    except Exception as e:
        import traceback
        GRAPH_ERROR = f"Graph not loaded at startup: {e}"
        GRAPH_READY = False
        print(f"❌ STARTUP ERROR: {GRAPH_ERROR}", flush=True)
        print(traceback.format_exc(), flush=True)
        print("=" * 80, flush=True)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "graph_ready": GRAPH_READY,
        "graph_error": GRAPH_ERROR,
        "tx_source": TX_SOURCE,
    }


@app.post("/reload-graph")
def reload_graph(db: Session = Depends(get_db)):
    global GRAPH, ILLICIT, GRAPH_READY, GRAPH_ERROR

    try:
        if TX_SOURCE == "db":
            tx_list = load_transactions_from_db(db)
            if not tx_list:
                GRAPH_READY = False
                GRAPH_ERROR = "No transactions found in DB."
                raise HTTPException(status_code=400, detail=GRAPH_ERROR)

            txs = pd.DataFrame(tx_list)
            tx_count = len(tx_list)

        else:  # TX_SOURCE == "csv"
            txs = pd.read_csv(TX_PATH)
            tx_count = len(txs)

        GRAPH = build_tx_graph(txs)
        ILLICIT = pick_seed_illicit_wallets(GRAPH.nodes, pct=0.05, seed=ILLICIT_SEED)

        GRAPH_READY = True
        GRAPH_ERROR = None
        return {
            "ok": True, 
            "tx_count": tx_count,
            "tx_source": TX_SOURCE,
            "nodes": GRAPH.number_of_nodes(),
            "edges": GRAPH.number_of_edges()
        }

    except ProgrammingError as e:
        # common: table missing / migrations not applied
        GRAPH_READY = False
        GRAPH_ERROR = f"DB not ready/migrated: {e}"
        raise HTTPException(status_code=503, detail=GRAPH_ERROR)

    except HTTPException:
        # already set GRAPH_ERROR above
        raise

    except Exception as e:
        GRAPH_READY = False
        GRAPH_ERROR = str(e)
        raise HTTPException(status_code=500, detail=GRAPH_ERROR)


# --- Persist a scoring run + all wallet scores ---
@app.post("/run-score")
def run_score(db: Session = Depends(get_db)):
    if not GRAPH_READY:
        raise HTTPException(status_code=503, detail=f"Graph not ready: {GRAPH_ERROR}")

    if GRAPH is None or ILLICIT is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    # store run metadata
    run = crud.create_scoring_run(
        db,
        tx_source=f"{TX_SOURCE}:{TX_PATH}" if TX_SOURCE == "csv" else "db:transactions",
        config_json={
            "hop_weights": list(cfg.hop_weights),
            "degree_normalize": cfg.degree_normalize,
            "illicit_seed_pct": 0.05,
        },
    )

    rows = []
    for w in GRAPH.nodes:
        r = risk_score_wallet(GRAPH, w, ILLICIT, cfg)
        rows.append(
            {
                "wallet": r["wallet"],
                "risk_score": r["risk_score"],
                "exposures_json": r["exposures"],
                "in_degree": r["in_degree"],
                "out_degree": r["out_degree"],
            }
        )

    inserted = crud.bulk_insert_risk_scores(db, run_id=run.id, rows=rows)
    db.commit()

    return {"run_id": run.id, "wallets_scored": inserted}


# --- NEW: query from Postgres ---
@app.get("/scores/top")
def top_scores(
    n: int | None = None,
    limit: int | None = None,
    db: Session = Depends(get_db),
):
    size = limit if limit is not None else n
    if size is None:
        size = 20

    size = max(1, min(size, 500))

    scores = crud.get_top_scores_latest(db, n=size)

    return [
        {
            "wallet": s.wallet,
            "risk_score": float(s.risk_score),
            "run_id": s.run_id,
            "created_at": s.created_at,
        }
        for s in scores
    ]


@app.get("/scores/{wallet}")
def latest_score(wallet: str, db: Session = Depends(get_db)):
    s = crud.get_latest_score_for_wallet(db, wallet=wallet)
    if not s:
        raise HTTPException(status_code=404, detail=f"No stored score found for wallet {wallet}")

    return {
        "wallet": s.wallet,
        "risk_score": float(s.risk_score),
        "exposures": s.exposures_json,
        "in_degree": s.in_degree,
        "out_degree": s.out_degree,
        "run_id": s.run_id,
        "created_at": s.created_at,
    }

@app.get("/scores/explain/{wallet}")
def explain_score(
    wallet: str,
    max_hops: int | None = None,
    per_hop_limit: int = 15,
    total_limit: int = 50,
    db: Session = Depends(get_db),
):
    # anchor to stored score so "explain" refers to something persisted
    s = crud.get_latest_score_for_wallet(db, wallet=wallet)
    if not s:
        raise HTTPException(status_code=404, detail=f"No stored score for wallet {wallet}")

    run = crud.get_run_by_id(db, run_id=s.run_id)

    # ensure graph is loaded
    if not GRAPH_READY or GRAPH is None or ILLICIT is None:
        raise HTTPException(
            status_code=503,
            detail=f"Graph not ready: {GRAPH_ERROR}. Run POST /reload-graph first.",
        )

    # build config from run.config_json if present, else fallback to global cfg
    cfg_local = cfg
    if run and isinstance(run.config_json, dict):
        try:
            hop_weights = tuple(run.config_json.get("hop_weights", list(cfg.hop_weights)))
            degree_normalize = bool(run.config_json.get("degree_normalize", cfg.degree_normalize))
            cfg_local = RiskConfig(hop_weights=hop_weights, degree_normalize=degree_normalize)
        except Exception:
            cfg_local = cfg

    # clamp params
    per_hop_limit = max(1, min(int(per_hop_limit), 100))
    total_limit = max(1, min(int(total_limit), 200))

    explanation = explain_wallet_risk(
        GRAPH,
        wallet=wallet,
        illicit=ILLICIT,
        cfg=cfg_local,
        max_hops=max_hops,
        per_hop_limit=per_hop_limit,
        total_limit=total_limit,
    )

    if explanation.get("reason") == "wallet_not_in_graph":
        raise HTTPException(status_code=404, detail=f"Wallet {wallet} not found in graph")

    return {
        "wallet": wallet,
        "stored_score": {
            "risk_score": float(s.risk_score),
            "exposures_cumulative": s.exposures_json,
            "in_degree": s.in_degree,
            "out_degree": s.out_degree,
            "run_id": s.run_id,
            "created_at": s.created_at,
        },
        "run": None
        if not run
        else {
            "run_id": run.id,
            "created_at": run.created_at,
            "tx_source": run.tx_source,
            "config_json": run.config_json,
        },
        "explainability": explanation,
        "notes": {
            "exposures_in_db_are_cumulative": True,
            "explainability_uses_exact_hops": True,
        },
    }

@app.get("/ingestion/status")
def ingestion_status(db: Session = Depends(get_db)):
    try:
        tx_count = crud.count_transactions(db)
        ing = crud.get_ingestion_state(db, name="transactions_consumer")
        latest_run = crud.get_latest_run(db)

        # --- metrics ---
        seconds_since_last_processed = None
        ingested_last_5m = None
        tx_per_min_5m = None

        if ing and ing.last_processed_at:
            now = datetime.now(timezone.utc)
            last = ing.last_processed_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            seconds_since_last_processed = (now - last).total_seconds()

        if ing is not None:
            ingested_last_5m = crud.count_ingested_since(db, minutes=5)
            tx_per_min_5m = ingested_last_5m / 5.0

        # --- status (precedence: degraded > starting > ok) ---
        status = "ok"

        # starting conditions
        # For CSV mode: only require GRAPH_READY
        # For DB mode: require tx_count > 0, GRAPH_READY, and ing exists
        if TX_SOURCE == "csv":
            if not GRAPH_READY:
                status = "starting"
        else:  # TX_SOURCE == "db"
            if tx_count == 0 or not GRAPH_READY or ing is None:
                status = "starting"

        # degraded conditions
        if ing and ing.last_error:
            status = "degraded"

        if GRAPH_ERROR:
            # ignore stale startup message once tx_count > 0
            if not ("no transactions found" in str(GRAPH_ERROR).lower() and tx_count > 0):
                status = "degraded"

        # --- latest scoring run summary ---
        latest_run_summary = None
        if latest_run:
            wallets_scored = crud.count_scores_for_run(db, run_id=latest_run.id)
            latest_run_summary = {
                "run_id": latest_run.id,
                "created_at": latest_run.created_at,
                "tx_source": latest_run.tx_source,
                "wallets_scored": wallets_scored,
                "config_json": latest_run.config_json,
            }

        graph_stats = None
        if GRAPH_READY and GRAPH is not None:
            graph_stats = {
                "nodes": int(GRAPH.number_of_nodes()),
                "edges": int(GRAPH.number_of_edges()),
            }

        return {
            "status": status,
            "tx_count": tx_count,
            "metrics": None
            if not ing
            else {
                "name": ing.name,
                "last_tx_id": ing.last_tx_id,
                "last_processed_at": ing.last_processed_at,
                "total_inserted": ing.total_inserted,
                "last_error": ing.last_error,
                "seconds_since_last_processed": seconds_since_last_processed,
                "ingested_last_5m": ingested_last_5m,
                "tx_per_min_5m": tx_per_min_5m,
            },
            "latest_scoring_run": latest_run_summary,
            "graph_ready": GRAPH_READY,
            "graph_error": GRAPH_ERROR,
            "graph_stats": graph_stats,
            "tx_source": TX_SOURCE,
        }

    except ProgrammingError as e:
        raise HTTPException(status_code=503, detail=f"DB not ready/migrated: {e}")


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    status = ingestion_status(db)

    if status["status"] != "ok":
        raise HTTPException(status_code=503, detail=status)

    return {"status": "ready"}



def calculate_node_importance(node, graph, score_map, illicit_set, hop_num=999, center_wallet=None):
    """
    Calculate importance score for prioritizing nodes when limiting graph size.
    Higher score = more important to display.
    
    Prioritizes:
    1. Degree centrality (hub nodes that show network structure)
    2. Risk score (interesting from AML perspective)
    3. Connectivity to center (ensures visible edges)
    4. Minimal illicit bias (to show diverse node types)
    """
    risk_score = float(score_map.get(node, 0.0))
    degree = graph.in_degree(node) + graph.out_degree(node)
    is_illicit = 1.0 if node in illicit_set else 0.0
    
    # Direct connectivity bonus: Strongly prefer nodes with edges to center
    connected_to_center = 0.0
    if center_wallet:
        if graph.has_edge(node, center_wallet):
            connected_to_center += 2.0  # Has edge TO center
        if graph.has_edge(center_wallet, node):
            connected_to_center += 2.0  # Has edge FROM center
    
    # Weighted importance (BALANCED for diversity):
    # - Degree is PRIMARY (shows network structure)
    # - Risk score SECONDARY (interesting nodes)
    # - Illicit weight MINIMAL (just 0.2 to slightly prefer but not dominate)
    # - Connectivity important for visualization
    importance = (
        min(5.0, degree / 10.0) * 4.0 +    # PRIMARY: Degree centrality (max 5.0, weight 4.0 = up to 20 points)
        risk_score * 2.0 +                 # SECONDARY: Risk score (weight 2.0)
        connected_to_center +              # Connectivity bonus (0-4)
        is_illicit * 0.2                   # MINIMAL illicit bonus (reduced from 0.8 to 0.2)
    )
    
    return importance


@app.get("/graph/wallet/{wallet}")
def wallet_graph(
    wallet: str,
    hops: int = Query(2, ge=1, le=4),
    edge_limit: int = Query(600, ge=50, le=3000),
    node_limit: int = Query(100, ge=10, le=500),
    min_amount: float = Query(0.0, ge=0.0),
    only_connected: bool = Query(False),
    db: Session = Depends(get_db),
):
    """
    Returns an induced subgraph around `wallet` using the in-memory GRAPH for neighborhoods
    and Postgres for edge aggregation (tx_count + total_amount).
    
    Nodes are prioritized by importance (risk score, degree, illicit status) when limiting
    to ensure most relevant wallets are displayed.
    
    Args:
        wallet: Center wallet address
        hops: Maximum hops to explore (1-4)
        edge_limit: Maximum edges to return (50-3000)
        node_limit: Maximum nodes to include (10-500, default 100). Prioritized by importance.
        min_amount: Minimum transaction amount to include
        only_connected: If True, only return nodes that have edges (filter out isolated nodes)
    """
    if not GRAPH_READY or GRAPH is None or ILLICIT is None:
        raise HTTPException(status_code=503, detail=f"Graph not ready: {GRAPH_ERROR}")

    if wallet not in GRAPH:
        raise HTTPException(status_code=404, detail=f"Wallet {wallet} not found in graph")

    layers = k_hop_layers_undirected(GRAPH, start=wallet, max_hops=int(hops))
    print(f"[DEBUG] k_hop_layers returned {len(layers)} layers for wallet {wallet[:10]}..., max_hops={hops}", flush=True)
    if not layers:
        return {"center": wallet, "nodes": [], "edges": []}

    # Fetch latest scores for enrichment (before node selection)
    latest_run = crud.get_latest_run(db)
    score_map = {}
    if latest_run:
        # Get all wallets to pre-load scores
        all_wallets = set()
        for layer in layers:
            all_wallets |= layer
        
        scores = (
            db.query(crud.RiskScore.wallet, crud.RiskScore.risk_score)
            .filter(crud.RiskScore.run_id == latest_run.id)
            .filter(crud.RiskScore.wallet.in_(all_wallets))
            .all()
        )
        score_map = {w: float(s) for w, s in scores}

    # Step 1: IMPROVED node selection with hop-stratified sampling
    # This ensures we get diversity across hops instead of just top-scoring nodes from all hops
    node_set = {wallet}  # Always include center
    hop_map = {wallet: 0}  # Center is at hop 0
    
    # Debug: Log layer sizes
    print(f"[DEBUG] Wallet: {wallet}, Hops requested: {hops}", flush=True)
    print(f"[DEBUG] Layer sizes: {[len(layer) for layer in layers]}", flush=True)
    
    # Calculate how many nodes to allocate per hop
    # Strategy: Ensure balanced representation across all hops
    remaining_budget = int(node_limit) - 1  # Minus 1 for center wallet
    
    if remaining_budget > 0 and len(layers) > 1:
        # Count nodes per hop (excluding center at hop 0)
        hop_sizes = [len(layer) for layer in layers[1:]]  # Exclude hop 0 (center)
        total_available = sum(hop_sizes)
        
        print(f"[DEBUG] Hop sizes (excluding center): {hop_sizes}, Total: {total_available}", flush=True)
        
        if total_available > 0:
            # SIMPLIFIED allocation: Split budget equally across hops, then adjust by availability
            num_hops_with_nodes = len([s for s in hop_sizes if s > 0])
            
            # Start with equal allocation
            equal_share = remaining_budget // num_hops_with_nodes
            hop_allocations = []
            remaining_to_allocate = remaining_budget
            
            # First pass: allocate equal shares or cap at hop size
            for h_idx, size in enumerate(hop_sizes):
                if size == 0:
                    hop_allocations.append(0)
                else:
                    # Allocate equal share, but don't exceed hop size or remaining budget
                    alloc = min(equal_share, size, remaining_to_allocate)
                    hop_allocations.append(alloc)
                    remaining_to_allocate -= alloc
            
            # Second pass: distribute any remaining budget to hops that have capacity
            # This handles cases where small hops couldn't use their full share
            if remaining_to_allocate > 0:
                for h_idx, size in enumerate(hop_sizes):
                    if size == 0 or hop_allocations[h_idx] >= size:
                        continue
                    
                    # How much more can this hop accept?
                    can_add = min(size - hop_allocations[h_idx], remaining_to_allocate)
                    hop_allocations[h_idx] += can_add
                    remaining_to_allocate -= can_add
                    
                    if remaining_to_allocate == 0:
                        break
            
            print(f"[DEBUG] Hop allocations: {hop_allocations}", flush=True)
            
            # Now select top nodes from each hop based on allocation
            for h_idx, allocation in enumerate(hop_allocations):
                if allocation == 0:
                    print(f"[DEBUG] Hop {h_idx + 1}: skipping (allocation=0)", flush=True)
                    continue
                
                hop_num = h_idx + 1  # Actual hop number (1, 2, 3, ...)
                
                # CRITICAL BUG CHECK: Ensure hop_num is within layers bounds
                if hop_num >= len(layers):
                    print(f"[DEBUG] ERROR: hop_num {hop_num} >= len(layers) {len(layers)}", flush=True)
                    continue
                    
                layer = layers[hop_num]
                print(f"[DEBUG] Processing hop {hop_num}: allocation={allocation}, layer_size={len(layer)}", flush=True)
                
                # Rank nodes in this hop by importance
                nodes_in_hop = list(layer)
                ranked_in_hop = sorted(
                    nodes_in_hop,
                    key=lambda n: calculate_node_importance(
                        n, GRAPH, score_map, ILLICIT,
                        hop_num=hop_num,
                        center_wallet=wallet
                    ),
                    reverse=True
                )
                
                # DIVERSIFIED SELECTION: Take top 40%, middle 40%, bottom 20% to ensure variety
                # This prevents only illicit nodes being selected
                top_pct = int(allocation * 0.4)
                mid_pct = int(allocation * 0.4)
                bottom_pct = allocation - top_pct - mid_pct
                
                selected_from_hop = []
                if len(ranked_in_hop) <= allocation:
                    # Take all if we have fewer than allocation
                    selected_from_hop = ranked_in_hop
                else:
                    # Stratified sampling for diversity
                    selected_from_hop.extend(ranked_in_hop[:top_pct])  # Top nodes
                    mid_start = len(ranked_in_hop) // 3
                    selected_from_hop.extend(ranked_in_hop[mid_start:mid_start + mid_pct])  # Middle nodes
                    if bottom_pct > 0:
                        selected_from_hop.extend(ranked_in_hop[-bottom_pct:])  # Some lower-ranked nodes
                
                illicit_count = sum(1 for n in selected_from_hop if n in ILLICIT)
                print(f"[DEBUG] Hop {hop_num}: selected {len(selected_from_hop)} of {len(layer)} nodes ({illicit_count} illicit, {len(selected_from_hop)-illicit_count} non-illicit)", flush=True)
                
                for n in selected_from_hop:
                    node_set.add(n)
                    hop_map[n] = hop_num
        else:
            # No nodes available beyond center
            print("[DEBUG] No nodes available beyond center (total_available=0)", flush=True)
    
    print(f"[DEBUG] Final node_set size: {len(node_set)}", flush=True)
    hop_distribution = {}
    for h in hop_map.values():
        hop_distribution[h] = hop_distribution.get(h, 0) + 1
    print(f"[DEBUG] Hop distribution: {sorted(hop_distribution.items())}", flush=True)

    # Step 3: Build nodes payload with importance-ranked nodes
    nodes_out = []
    for n in node_set:
        tag = "center" if n == wallet else ("illicit" if n in ILLICIT else "neighbor")
        nodes_out.append(
            {
                "id": n,
                "label": n,
                "hop": int(hop_map.get(n, 999)),
                "tag": tag,
                "is_illicit": bool(n in ILLICIT),
                "risk_score": score_map.get(n),
                "in_degree": int(GRAPH.in_degree(n)),
                "out_degree": int(GRAPH.out_degree(n)),
            }
        )

    # aggregate edges from DB (gives tx_count + total_amount)
    if TX_SOURCE == "db":
        edges_out = crud.aggregate_edges_for_nodes(
            db, nodes=node_set, edge_limit=int(edge_limit), min_amount=float(min_amount)
        )
    else:
        # Build edges from in-memory GRAPH when using CSV
        # Collect all edges and sort by amount to show most significant ones
        all_edges = []
        
        for src in node_set:
            # Incoming edges (predecessors)
            for pred in GRAPH.predecessors(src):
                if pred in node_set:
                    edge_data = GRAPH.edges[pred, src]
                    amount = edge_data.get('amount', 0.0)
                    
                    if amount >= float(min_amount):
                        all_edges.append({
                            "source": pred,
                            "target": src,
                            "tx_count": edge_data.get('tx_count', 1),
                            "total_amount": float(amount)
                        })
            
            # Outgoing edges (successors)
            for succ in GRAPH.successors(src):
                if succ in node_set:
                    edge_data = GRAPH.edges[src, succ]
                    amount = edge_data.get('amount', 0.0)
                    
                    if amount >= float(min_amount):
                        all_edges.append({
                            "source": src,
                            "target": succ,
                            "tx_count": edge_data.get('tx_count', 1),
                            "total_amount": float(amount)
                        })
        
        # Sort by amount (descending) to prioritize most significant transactions
        all_edges.sort(key=lambda e: e["total_amount"], reverse=True)
        
        # Deduplicate edges: merge duplicates (same source->target) by aggregating tx_count and amount
        edge_map = {}
        for e in all_edges:
            key = (e["source"], e["target"])
            if key in edge_map:
                # Merge with existing edge
                edge_map[key]["tx_count"] += e["tx_count"]
                edge_map[key]["total_amount"] += e["total_amount"]
            else:
                # Store new edge
                edge_map[key] = {
                    "source": e["source"],
                    "target": e["target"],
                    "tx_count": e["tx_count"],
                    "total_amount": e["total_amount"]
                }
        
        # Convert back to list and sort by amount again
        all_edges = list(edge_map.values())
        all_edges.sort(key=lambda e: e["total_amount"], reverse=True)
        
        # Return deduplicated edges (is_incoming marker not needed)
        edges_out = all_edges[: int(edge_limit)]

    # Filter to only nodes with edges if requested
    if only_connected and edges_out:
        connected_nodes = set()
        for e in edges_out:
            connected_nodes.add(e["source"])
            connected_nodes.add(e["target"])
        connected_nodes.add(wallet)  # Always include center wallet
        nodes_out = [n for n in nodes_out if n["id"] in connected_nodes]

    return {"center": wallet, "nodes": nodes_out, "edges": edges_out}