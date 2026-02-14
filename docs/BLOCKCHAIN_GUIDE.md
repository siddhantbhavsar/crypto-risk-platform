# Blockchain Integration Guide

This guide explains how to integrate real Ethereum transaction data into the Crypto AML Risk Platform.

---

## Quick Start

### 1. Fetch Ethereum Transactions

```bash
# For a single wallet
python services/blockchain/fetch_ethereum.py \
  --wallets 0x1234567890123456789012345678901234567890

# For multiple wallets
python services/blockchain/fetch_ethereum.py \
  --wallets 0x1234... 0x5678... 0xabcd...

# Specify output file
python services/blockchain/fetch_ethereum.py \
  --wallets 0x1234... \
  --output data/ethereum_transactions.csv
```

### 2. Publish to Kafka

```bash
python -m services.ingestion.kafka_producer
```

### 3. Load in Dashboard

1. Open http://localhost:8501
2. Click **"Reload Graph"** in sidebar
3. Click **"Run Score"**
4. Explore the real transaction network!

---

## How It Works

### Architecture

```
┌─────────────────────┐
│  Etherscan API      │
│  (Free, no key)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ services/blockchain/                │
│ etherscan_fetcher.py                │
│ - Fetch txs                         │
│ - Normalize to schema               │
│ - Handle rate limits                │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ data/ethereum_transactions.csv      │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Kafka Producer                      │
│ (Publish to transactions topic)     │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Kafka Consumer                      │
│ (Insert into Postgres)              │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Risk Scoring Engine                 │
│ (Build graph, calculate risk)       │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Streamlit Dashboard                 │
│ (Visualize risk network)            │
└─────────────────────────────────────┘
```

---

## API Reference

### EtherscanFetcher

```python
from services.blockchain.etherscan_fetcher import EtherscanFetcher

# Initialize
fetcher = EtherscanFetcher(api_key="YourApiKeyToken")

# Fetch transactions for one wallet
txs = fetcher.get_transactions("0x1234...")

# Fetch and normalize
normalized = fetcher.fetch_and_normalize("0x1234...")

# Fetch multiple wallets
all_txs = fetcher.fetch_multiple_wallets([
    "0x1234...",
    "0x5678...",
])
```

### Transaction Schema

Normalized transactions follow this schema:

```json
{
  "tx_id": "0xabcd1234...",
  "sender": "0x1234...",
  "receiver": "0x5678...",
  "amount": 1.5,
  "timestamp": "1234567890"
}
```

---

## Examples

### Example 1: Monitor a Known Phishing Address

```bash
python services/blockchain/fetch_ethereum.py \
  --wallets 0x9f4cda013e354cd123f51caf10d57d72d8d28f92 \
  --output data/phishing_network.csv

python -m services.ingestion.kafka_producer
```

Then in dashboard: Select the phishing address and see all connected wallets in the network.

### Example 2: Analyze a DeFi Protocol

```bash
# Uniswap Router
python services/blockchain/fetch_ethereum.py \
  --wallets 0xE592427A0AEce92De3Edee1F18E0157C05861564 \
  --output data/uniswap_txs.csv
```

### Example 3: Track Multiple Suspect Wallets

```bash
python services/blockchain/fetch_ethereum.py \
  --wallets \
    0x9f4cda013e354cd123f51caf10d57d72d8d28f92 \
    0xbbcf1ef7e1dd0c19d9dc85e5e88fde9899b03c2d \
    0x8ebf3a51fd23e0d3cf6264f8e1cfa0b4d76f7e41 \
  --output data/suspect_wallets.csv
```

---

## Etherscan API Setup

### Get Free API Key

1. Visit https://etherscan.io/apis
2. Click "Create New API Key"
3. Fill in app name (e.g., "Crypto AML")
4. Copy your API key
5. Use it in the fetcher:

```bash
python services/blockchain/fetch_ethereum.py \
  --wallets 0x1234... \
  --api-key your-actual-api-key-here
```

### Rate Limits

- **Free tier:** 5 calls/sec, 100,000 calls/day
- Built-in rate limiting: 0.1s delay between requests
- Respects Etherscan rate limits automatically

---

## Troubleshooting

### "No transactions found"

Possible causes:
- Invalid wallet address (check 0x prefix)
- Wallet has no transactions
- Wrong network (Mainnet vs Testnet)

**Solution:**
```bash
# Verify address is correct
# Use Etherscan.io to check the address first
```

### "API rate limited"

Increase the delay:

```python
fetcher = EtherscanFetcher(rate_limit_delay=0.5)  # 500ms delay
```

Or get a paid API key from Etherscan.

### "Request timeout"

The connection to Etherscan failed. Check:
- Internet connection
- Etherscan is not down (check https://etherscan.io)
- Try again later

---

## Advanced: Docker Integration

Run the fetcher inside Docker:

```bash
docker compose exec api python services/blockchain/fetch_ethereum.py \
  --wallets 0x1234...
```

Or create a dedicated blockchain ingestion worker:

```yaml
# Add to docker-compose.yml
blockchain-fetcher:
  build: .
  command: python services/blockchain/fetch_ethereum.py --wallets 0x1234...
  depends_on:
    - api
  environment:
    DATABASE_URL: postgresql+psycopg2://risk:risk@db:5432/riskdb
```

---

## Future Enhancements

- [ ] Support Bitcoin/Polygon/Solana chains
- [ ] Real-time WebSocket updates via Alchemy
- [ ] Token transfers (ERC-20) tracking
- [ ] Smart contract interaction analysis
- [ ] DeFi flash loan detection
- [ ] MEV sandwich detection
- [ ] OFAC/Chainalysis sanctions screening

---

## References

- [Etherscan API Docs](https://docs.etherscan.io/)
- [Web3.py Documentation](https://web3py.readthedocs.io/)
- [Ethereum Yellow Paper](https://ethereum.org/en/developers/docs/)
