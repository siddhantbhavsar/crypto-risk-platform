"""
Fetch real Ethereum transaction data and save to CSV.

Usage:
    python services/blockchain/fetch_ethereum.py --wallets 0x1234... 0x5678... [--output data/ethereum_transactions.csv]
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from services.blockchain.etherscan_fetcher import EtherscanFetcher


def main():
    parser = argparse.ArgumentParser(description="Fetch Ethereum transactions from Etherscan")
    parser.add_argument(
        "--wallets",
        nargs="+",
        required=True,
        help="Ethereum wallet addresses to fetch (space-separated)",
    )
    parser.add_argument(
        "--output",
        default="data/ethereum_transactions.csv",
        help="Output CSV file path",
    )
    parser.add_argument(
        "--api-key",
        default="YourApiKeyToken",
        help="Etherscan API key (get free one at https://etherscan.io/apis)",
    )
    parser.add_argument(
        "--start-block",
        type=int,
        default=0,
        help="Start block number",
    )
    parser.add_argument(
        "--end-block",
        type=int,
        default=99999999,
        help="End block number",
    )

    args = parser.parse_args()

    # Initialize fetcher
    fetcher = EtherscanFetcher(api_key=args.api_key)

    # Fetch transactions
    print(f"🔗 Fetching transactions for {len(args.wallets)} wallet(s)...")
    transactions = fetcher.fetch_multiple_wallets(
        args.wallets,
        start_block=args.start_block,
        end_block=args.end_block,
    )

    if not transactions:
        print("❌ No transactions found!")
        return

    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to CSV with correct column names (src/dst for compatibility)
    print(f"📝 Writing {len(transactions)} transactions to {args.output}...")
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["tx_id", "src", "dst", "amount", "timestamp"])
        writer.writeheader()
        for tx in transactions:
            # Rename sender/receiver to src/dst for compatibility
            writer.writerow({
                "tx_id": tx["tx_id"],
                "src": tx["sender"],
                "dst": tx["receiver"],
                "amount": tx["amount"],
                "timestamp": tx["timestamp"],
            })

    print(f"✅ Wrote {len(transactions)} transactions to {args.output}")
    print("\nUsage:")
    print("  Publish to Kafka: docker compose exec api python -m services.ingestion.kafka_producer")
    print("  Then reload graph and score in dashboard")


if __name__ == "__main__":
    main()
