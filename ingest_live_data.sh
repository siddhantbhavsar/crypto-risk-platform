#!/bin/bash

# Script to ingest live Ethereum data and start the platform
# Usage: ./ingest_live_data.sh

set -e

echo "=========================================="
echo "🔗 Fetching Live Ethereum Data"
echo "=========================================="

# Load API key from .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

API_KEY="${ETHERSCAN_API_KEY:-YourApiKeyToken}"

# Well-known Ethereum wallets (mix of exchanges, DeFi, and popular addresses)
WALLETS=(
    "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"  # Vitalik Buterin
    "0x28c6c06298d514db089934071355e5743bf21d60"  # Binance Hot Wallet
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549"  # Binance Cold Wallet
    "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503"  # Binance Wallet
    "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8"  # Binance Wallet
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"  # WETH Contract
    "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be"  # Binance Exchange
    "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43"  # Coinbase Wallet
)

echo "📊 Fetching transactions from ${#WALLETS[@]} wallets..."
echo "🔑 Using API key: ${API_KEY:0:10}..."
echo ""

echo "🚀 Starting services first (needed to run fetch script)..."
docker compose up -d api

echo "⏳ Waiting for API container to be ready (15 seconds)..."
sleep 15

# Fetch transactions inside Docker container
echo "📥 Fetching data from Etherscan..."
docker compose exec -T api python -m services.blockchain.fetch_ethereum \
    --wallets "${WALLETS[@]}" \
    --api-key "$API_KEY" \
    --output data/transactions.csv \
    --start-block 0 \
    --end-block 99999999

# Check if data was fetched
if [ ! -f data/transactions.csv ]; then
    echo "❌ Failed to fetch data!"
    exit 1
fi

# Count transactions
TX_COUNT=$(tail -n +2 data/transactions.csv | wc -l)
echo ""
echo "✅ Successfully fetched $TX_COUNT transactions"

# Show sample
echo ""
echo "📋 Sample transactions (first 5):"
head -6 data/transactions.csv | column -t -s,

echo ""
echo "=========================================="
echo "🚀 Starting All Services"
echo "=========================================="

# Start remaining services (API already running)
docker compose up -d

echo ""
echo "⏳ Waiting for all services to be ready (20 seconds)..."
sleep 20

# Check services
echo ""
echo "📊 Service Status:"
docker compose ps

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "🎯 Next steps:"
echo "   1. Check API health: curl http://localhost:8000/health | jq"
echo "   2. Reload graph: curl -X POST http://localhost:8000/reload-graph | jq"
echo "   3. Run scoring: curl -X POST http://localhost:8000/run-score | jq"
echo "   4. View dashboard: http://localhost:8501"
echo ""
echo "📝 Alternative ingestion (via Kafka):"
echo "   docker compose exec api python -m services.ingestion.kafka_producer"
echo ""
