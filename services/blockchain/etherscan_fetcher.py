"""
Etherscan API client for fetching real Ethereum transaction data.

Supports free Etherscan API (https://etherscan.io/apis)
No API key required for basic queries.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import requests


class EtherscanFetcher:
    """Fetch Ethereum transactions from Etherscan API."""

    # Use V2 API endpoint
    BASE_URL = "https://api.etherscan.io/v2/api"
    # Free API key (rate limited but works for demos)
    DEFAULT_API_KEY = "YourApiKeyToken"

    def __init__(self, api_key: str = DEFAULT_API_KEY, rate_limit_delay: float = 0.1):
        """
        Initialize Etherscan fetcher.

        Args:
            api_key: Etherscan API key (get free one from https://etherscan.io/apis)
            rate_limit_delay: Delay between requests in seconds (to respect rate limits)
        """
        self.api_key = api_key
        self.rate_limit_delay = rate_limit_delay

    def get_transactions(
        self,
        address: str,
        start_block: int = 0,
        end_block: int = 99999999,
        sort: str = "asc",
        max_results: int = 10000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch transaction history for a wallet using Etherscan V2 API.

        Args:
            address: Ethereum address (with or without 0x prefix)
            start_block: Start block number
            end_block: End block number
            sort: Sort order ('asc' or 'desc')
            max_results: Maximum results (Etherscan returns max 10,000)

        Returns:
            List of transactions
        """
        if not address.startswith("0x"):
            address = f"0x{address}"

        # V2 API requires chainid (1 = Mainnet)
        params = {
            "chainid": "1",
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "sort": sort,
            "apikey": self.api_key,
        }

        try:
            print(f"   DEBUG: Calling Etherscan V2 API with address={address}")
            print(f"   DEBUG: API key (first 10 chars): {self.api_key[:10]}...")
            
            resp = requests.get(self.BASE_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            print(f"   DEBUG: API response: {data.get('message')}")
            
            if data.get("status") == "0":
                # No transactions or error
                msg = data.get("message", "").lower()
                if "rate limit" in msg:
                    print("   ⚠️  Rate limited! Try with valid API key or wait.")
                if "invalid api key" in msg or "api key" in msg:
                    print("   ⚠️  INVALID API KEY! Check your Etherscan API key.")
                    print(f"   Full message: {data.get('message')}")
                if "notok" in msg:
                    print("   ⚠️  API request failed. Check API key and address format.")
                    print(f"   Full message: {data.get('message')}")
                return []

            txs = data.get("result", [])
            if isinstance(txs, str):
                # Sometimes Etherscan returns error as result string
                print(f"   ⚠️  Error result: {txs}")
                return []
                
            print(f"   DEBUG: Found {len(txs) if isinstance(txs, list) else 0} transactions")
            return txs[:max_results] if isinstance(txs, list) else []

        except Exception as e:
            print(f"Error fetching transactions for {address}: {e}")
            return []

    def normalize_transactions(self, txs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize Etherscan transactions to internal schema.

        Internal schema:
            tx_id, sender, receiver, amount, timestamp (optional)
        """
        normalized = []

        for tx in txs:
            try:
                tx_id = tx.get("hash", "")
                sender = tx.get("from", "").lower()
                receiver = tx.get("to", "").lower()
                amount = float(tx.get("value", 0)) / 1e18  # Convert Wei to ETH

                # Skip failed transactions
                if tx.get("isError") == "1":
                    continue

                # Skip internal transactions (only interested in standard transfers)
                if tx.get("input") not in ["0x", ""]:
                    continue  # Smart contract calls have more complex data

                timestamp = tx.get("timeStamp")

                if not (tx_id and sender and receiver):
                    continue

                normalized.append(
                    {
                        "tx_id": tx_id,
                        "sender": sender,
                        "receiver": receiver,
                        "amount": amount,
                        "timestamp": timestamp,
                    }
                )

            except (ValueError, TypeError) as e:
                # Skip malformed transactions
                print(f"Skipping malformed transaction: {e}")
                continue

        return normalized

    def fetch_and_normalize(
        self,
        address: str,
        start_block: int = 0,
        end_block: int = 99999999,
    ) -> List[Dict[str, Any]]:
        """
        Fetch and normalize transactions in one call.

        Args:
            address: Wallet address
            start_block: Start block
            end_block: End block

        Returns:
            List of normalized transactions
        """
        print(f"🔗 Fetching transactions for {address}...")
        txs = self.get_transactions(address, start_block, end_block)
        print(f"   Found {len(txs)} transactions")

        normalized = self.normalize_transactions(txs)
        print(f"   Normalized {len(normalized)} valid transactions")

        time.sleep(self.rate_limit_delay)
        return normalized

    def fetch_multiple_wallets(
        self,
        addresses: List[str],
        start_block: int = 0,
        end_block: int = 99999999,
    ) -> List[Dict[str, Any]]:
        """
        Fetch transactions for multiple wallets.

        Args:
            addresses: List of wallet addresses
            start_block: Start block
            end_block: End block

        Returns:
            Combined list of normalized transactions
        """
        all_txs = []

        for addr in addresses:
            txs = self.fetch_and_normalize(addr, start_block, end_block)
            all_txs.extend(txs)
            time.sleep(self.rate_limit_delay)  # Rate limit between wallets

        # Remove duplicate transactions
        seen_ids = set()
        unique_txs = []
        for tx in all_txs:
            tx_id = tx.get("tx_id")
            if tx_id not in seen_ids:
                seen_ids.add(tx_id)
                unique_txs.append(tx)

        return unique_txs
