import csv
import json
import os
import time
import uuid
from typing import Any, Dict, Optional

from kafka import KafkaProducer


def get_env(name: str, default: str) -> str:
    val = os.getenv(name, default)
    return val if val else default


def parse_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def normalize_row(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """
    Normalize CSV row into the canonical Kafka message schema.

    Canonical fields (always present):
      - tx_id
      - sender
      - receiver
      - amount
      - timestamp (optional/nullable)

    Also includes src/dst mirrors for compatibility/debugging.
    """
    tx_id = row.get("tx_id") or str(uuid.uuid4())

    # Support multiple possible CSV column names
    sender = row.get("sender") or row.get("from") or row.get("src")
    receiver = row.get("receiver") or row.get("to") or row.get("dst")

    if not sender or not receiver:
        return None

    amount = parse_float(row.get("amount"), 0.0)

    # Your simulator uses "timestamp" already :contentReference[oaicite:1]{index=1}
    timestamp = row.get("timestamp") or row.get("time") or None

    msg = {
        "tx_id": tx_id,
        "sender": sender,
        "receiver": receiver,
        "amount": amount,
        "timestamp": timestamp,

        # Mirrors (handy for debugging + backward compatibility)
        "src": sender,
        "dst": receiver,
    }
    return msg


def main() -> None:
    bootstrap = get_env("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    topic = get_env("KAFKA_TOPIC_TRANSACTIONS", "transactions")
    csv_path = get_env("TX_CSV_PATH", "/app/data/transactions.csv")

    producer = KafkaProducer(
        bootstrap_servers=bootstrap,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
        acks="all",
        retries=5,
    )

    sent = 0
    skipped = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            msg = normalize_row(row)
            if msg is None:
                skipped += 1
                continue

            tx_id = msg["tx_id"]
            producer.send(topic, key=tx_id, value=msg)
            sent += 1

            # small flush cadence + tiny throttle
            if sent % 1000 == 0:
                producer.flush()
                time.sleep(0.05)

    producer.flush()
    producer.close()

    print(
        f"✅ Published {sent} transactions to topic='{topic}' via {bootstrap} "
        f"(skipped={skipped})"
    )


if __name__ == "__main__":
    main()
