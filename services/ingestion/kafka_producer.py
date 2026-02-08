import csv
import json
import os
import time
import uuid

from kafka import KafkaProducer


def get_env(name: str, default: str) -> str:
    val = os.getenv(name, default)
    if not val:
        return default
    return val


def main() -> None:
    bootstrap = get_env("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
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
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Ensure a stable tx_id. If your CSV already has tx_id, keep it.
            tx_id = row.get("tx_id") or str(uuid.uuid4())
            msg = {
                "tx_id": tx_id,
                "sender": row.get("sender") or row.get("from") or row.get("src"),
                "receiver": row.get("receiver") or row.get("to") or row.get("dst"),
                "amount": float(row.get("amount") or 0.0),
                "timestamp": row.get("timestamp") or row.get("time"),
            }

            producer.send(topic, key=tx_id, value=msg)
            sent += 1

            # tiny throttle to avoid flooding on first run
            if sent % 1000 == 0:
                producer.flush()
                time.sleep(0.05)

    producer.flush()
    producer.close()

    print(f"✅ Published {sent} transactions to topic='{topic}' via {bootstrap}")


if __name__ == "__main__":
    main()
