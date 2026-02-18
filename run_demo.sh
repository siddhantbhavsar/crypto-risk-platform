#!/bin/bash

# ============================================================================
# CRYPTO AML RISK PLATFORM - COMPLETE DEMO
# ============================================================================
# Full demonstration including Kafka streaming ingestion, scoring, and visualization
# Pipeline: Generate Data → Kafka → Consumer → PostgreSQL → Graph → Scoring
# Works in both local and GitHub Codespaces environments
# ============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Detect environment
if [ -n "$CODESPACE_NAME" ]; then
    IS_CODESPACE=true
    API_HOST="https://${CODESPACE_NAME}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
    DASHBOARD_HOST="https://${CODESPACE_NAME}-8501.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
else
    IS_CODESPACE=false
    API_HOST="http://localhost:8000"
    DASHBOARD_HOST="http://localhost:8501"
fi

echo -e "${BLUE}"
cat << 'EOF'
╔═══════════════════════════════════════════════════════════╗
║     CRYPTO AML RISK PLATFORM - COMPLETE DEMO             ║
║     Full Pipeline: Kafka → DB → Graph → Score            ║
╚═══════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

if [ "$IS_CODESPACE" = true ]; then
    echo -e "${YELLOW}📍 Running in GitHub Codespaces${NC}"
    echo -e "   API: $API_HOST"
    echo -e "   Dashboard: $DASHBOARD_HOST"
else
    echo -e "${YELLOW}📍 Running locally${NC}"
    echo -e "   API: $API_HOST"
    echo -e "   Dashboard: $DASHBOARD_HOST"
fi
echo ""

section() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# ============================================================================
# STEP 1: CLEANUP & SETUP
# ============================================================================
section "STEP 1: Environment Setup"

echo -e "${YELLOW}🧹 Cleaning up existing containers...${NC}"
docker compose down -v 2>/dev/null || true
echo ""

# ============================================================================
# STEP 2: START INFRASTRUCTURE (KAFKA, ZOOKEEPER, DATABASE)
# ============================================================================
section "STEP 2: Starting Infrastructure Services"

echo "🚀 Starting database, Kafka, and ZooKeeper..."
docker compose up -d db kafka zookeeper
echo ""
echo "⏳ Waiting for Kafka/ZooKeeper to initialize (30 seconds)..."
sleep 30

echo "📊 Infrastructure Status:"
docker compose ps db kafka zookeeper
echo ""

# ============================================================================
# STEP 3: GENERATE SAMPLE DATA
# ============================================================================
section "STEP 3: Generating Sample Transaction Data"

# Load API key from .env (for future use with live data)
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "🎲 Generating synthetic transaction data..."
docker compose run --rm -T api python -c "
from services.ingestion.simulator import simulate_transactions, write_transactions_csv
df = simulate_transactions(n_wallets=300, n_txs=2500, start_days_ago=60)
write_transactions_csv(df, '/app/data/transactions.csv')
print(f'✅ Generated {len(df)} sample transactions')
"

# Count transactions
TX_COUNT=$(tail -n +2 data/transactions.csv 2>/dev/null | wc -l || echo "0")
echo ""
echo -e "${GREEN}✅ Data ready: $TX_COUNT transactions${NC}"
echo ""
echo "📋 Sample data (first 5 rows):"
head -6 data/transactions.csv | column -t -s, || true
echo ""

# ============================================================================
# STEP 4: KAFKA INGESTION PIPELINE
# ============================================================================
section "STEP 4: Streaming Data via Kafka Pipeline"

echo "🚀 Starting consumer service..."
docker compose up -d consumer
sleep 5

echo ""
echo "📤 Publishing transactions to Kafka..."
docker compose exec -T consumer python -m services.ingestion.kafka_producer

echo ""
echo "⏳ Waiting for consumer to process transactions (10 seconds)..."
sleep 10

echo ""
echo "📊 Checking ingestion progress..."
INGESTED=$(docker compose exec -T db psql -U postgres -d crypto_risk -t -c "SELECT COUNT(*) FROM transactions;" 2>/dev/null || echo "0")
echo -e "${GREEN}✅ Ingested $INGESTED transactions into PostgreSQL${NC}"

# ============================================================================
# STEP 5: START API & DASHBOARD (WITH DATABASE MODE)
# ============================================================================
section "STEP 5: Starting API & Dashboard Services"

echo "🚀 Launching API and dashboard (with TX_SOURCE=db)..."
# Export environment variable for API to use database mode
export TX_SOURCE=db
docker compose up -d api dashboard
echo ""
echo "⏳ Waiting for services to initialize (15 seconds)..."
sleep 15

echo ""
echo "📊 Service Status:"
docker compose ps

# ============================================================================
# STEP 6: HEALTH CHECKS
# ============================================================================
section "STEP 6: Health & Readiness Checks"

echo "🏥 Checking API health..."
curl -s $API_HOST/health | jq '.' || echo "⚠️  API not responding yet"
echo ""

sleep 3

echo "✅ Checking readiness..."
curl -s $API_HOST/ready | jq '.' || echo "⚠️  System not ready yet (normal, continue...)"
echo ""

# ============================================================================
# STEP 7: LOAD GRAPH FROM DATABASE
# ============================================================================
section "STEP 7: Building Transaction Graph from Database"

echo "🔄 Loading graph from PostgreSQL database..."
RELOAD_RESULT=$(curl -s -X POST $API_HOST/reload-graph)
echo "$RELOAD_RESULT" | jq '.'

NODES=$(echo "$RELOAD_RESULT" | jq -r '.nodes // "N/A"')
EDGES=$(echo "$RELOAD_RESULT" | jq -r '.edges // "N/A"')

echo ""
echo -e "${GREEN}✅ Graph built from database: $NODES nodes, $EDGES edges${NC}"

# ============================================================================
# STEP 8: RUN RISK SCORING
# ============================================================================
section "STEP 8: Running Risk Scoring Algorithm"

echo "🎯 Calculating risk scores for all wallets..."
echo "   (Multi-hop algorithm with weights: 1.0, 0.6, 0.3)"
echo ""

SCORE_RESULT=$(curl -s -X POST $API_HOST/run-score)
echo "$SCORE_RESULT" | jq '.'

WALLETS_SCORED=$(echo "$SCORE_RESULT" | jq -r '.wallets_scored // "N/A"')
echo ""
echo -e "${GREEN}✅ Scored $WALLETS_SCORED wallets${NC}"

# ============================================================================
# STEP 9: VIEW RESULTS
# ============================================================================
section "STEP 9: Top 10 Highest Risk Wallets"

echo "🏆 Risk Leaderboard:"
echo ""

TOP_SCORES=$(curl -s "$API_HOST/scores/top?limit=10")
echo "$TOP_SCORES" | jq -r '
    ["Rank", "Wallet", "Risk Score", "In°", "Out°"] | @tsv,
    ("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"),
    (to_entries[] | [
        (.key + 1),
        .value.wallet[0:14],
        (.value.risk_score | tostring | .[0:8]),
        .value.in_degree,
        .value.out_degree
    ] | @tsv)
' | column -t

# ============================================================================
# STEP 10: EXPLAINABILITY
# ============================================================================
section "STEP 10: Explainability - Why is the top wallet risky?"

WALLET=$(echo "$TOP_SCORES" | jq -r '.[0].wallet')
echo "🔍 Analyzing wallet: $WALLET"
echo ""

EXPLAIN=$(curl -s "$API_HOST/scores/explain/$WALLET?max_hops=2&per_hop_limit=10")

echo "Risk Score: $(echo "$EXPLAIN" | jq -r '.stored_score.risk_score')"
echo ""
echo "📊 Hop Breakdown (Exact-hop illicit exposure):"
echo "$EXPLAIN" | jq -r '.explainability.hop_breakdown[] | 
    ["  Hop \(.hop):", "Weight=\(.weight)", "Illicit=\(.illicit_count_exact)", "→ Contribution=\(.contribution)"] | @tsv
' | column -t
echo ""

echo "👥 Top 5 Contributing Illicit Wallets:"
echo "$EXPLAIN" | jq -r '.explainability.top_contributors[0:5][] | 
    ["  ", .wallet[0:14], "at hop \(.hop)", "→ contrib \(.contribution)"] | @tsv
' | column -t

# ============================================================================
# STEP 11: GRAPH VISUALIZATION
# ============================================================================
section "STEP 11: Transaction Network Graph"

echo "🕸️  Fetching wallet network for: $WALLET"
echo ""

GRAPH=$(curl -s "$API_HOST/graph/wallet/$WALLET?hops=2&node_limit=50&edge_limit=100")

NODE_COUNT=$(echo "$GRAPH" | jq '.nodes | length')
EDGE_COUNT=$(echo "$GRAPH" | jq '.edges | length')
ILLICIT_COUNT=$(echo "$GRAPH" | jq '[.nodes[] | select(.is_illicit == true)] | length')

echo "Network Statistics:"
echo "  • Total Nodes: $NODE_COUNT"
echo "  • Total Edges: $EDGE_COUNT"
echo "  • Illicit Nodes: $ILLICIT_COUNT"
echo ""

echo "Top 5 Transactions by Amount:"
echo "$GRAPH" | jq -r '.edges | sort_by(-.total_amount) | .[0:5][] | 
    ["  ", .source[0:12], "→", .target[0:12], "Amount:", .total_amount, "Txs:", .tx_count] | @tsv
' | column -t

# ============================================================================
# STEP 12: INGESTION STATUS
# ============================================================================
section "STEP 12: Ingestion & System Status"

echo "📊 Kafka Ingestion Metrics (now using database mode):"
STATUS=$(curl -s $API_HOST/ingestion/status)
echo "$STATUS" | jq '{
    status: .status,
    tx_count: .tx_count,
    graph_stats: .graph_stats,
    tx_source: .tx_source,
    metrics: .metrics,
    latest_run: .latest_scoring_run.wallets_scored
}'

echo ""
echo -e "${GREEN}✅ Ingestion metrics now show real Kafka consumer activity!${NC}"

# ============================================================================
# COMPLETION
# ============================================================================
section "✅ DEMO COMPLETE!"

echo -e "${GREEN}All steps completed successfully!${NC}"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}🌐 Access the platform:${NC}"
echo ""
echo -e "  ${GREEN}Dashboard (Visual UI):${NC}"
if [ "$IS_CODESPACE" = true ]; then
    echo -e "    $DASHBOARD_HOST"
    echo -e "    ${BLUE}(Click the Ports tab and open port 8501)${NC}"
else
    echo -e "    $DASHBOARD_HOST"
fi
echo ""
echo -e "  ${GREEN}API Documentation:${NC}"
if [ "$IS_CODESPACE" = true ]; then
    echo -e "    $API_HOST/docs"
    echo -e "    ${BLUE}(Click the Ports tab and open port 8000)${NC}"
else
    echo -e "    $API_HOST/docs"
fi
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${YELLOW}💡 What to explore in the dashboard:${NC}"
echo "  1. Overview Tab - Health metrics, Kafka ingestion status, and graph statistics"
echo "  2. Leaderboard Tab - Top risk wallets with scores"
echo "  3. Explainability Tab - Understand why wallets are risky"
echo "  4. Wallet Graph Tab - Interactive network visualization"
echo ""

echo -e "${YELLOW}🔧 Useful commands:${NC}"
echo "  • View logs: docker compose logs -f"
echo "  • View consumer logs: docker compose logs -f consumer"
echo "  • Restart: docker compose restart"
echo "  • Stop: docker compose down"
echo "  • Re-run scoring: curl -X POST $API_HOST/run-score | jq"
echo "  • Check ingestion: curl $API_HOST/ingestion/status | jq"
echo ""

echo -e "${GREEN}Thank you for the demo! 🚀${NC}"
echo ""
