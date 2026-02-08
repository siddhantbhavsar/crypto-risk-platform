import json
import os
import time

from kafka import KafkaConsumer

from services.api import crud

# Import DB session + crud from API service
from services.api.db import SessionLocal


def get_env(name: str, default: str) -> str:
    v = os.getenv(name, default)
    return v if v else default


def main() -> None:
    bootstrap = get_env("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    topic = get_env("KAFKA_TOPIC_TRANSACTIONS", "transactions")
    group_id = get_env("KAFKA_GROUP_ID", "tx-consumer")

    batch_size = int(get_env("CONSUMER_BATCH_SIZE", "500"))
    poll_ms = int(get_env("CONSUMER_POLL_MS", "1000"))

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id=group_id,
        enable_auto_commit=False,   # we commit after DB write
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )

    print(f"✅ Consumer connected: {bootstrap} topic='{topic}' group='{group_id}'")

    buffer = []
    last_flush = time.time()

    try:
        while True:
            records = consumer.poll(timeout_ms=poll_ms)
            for _, msgs in records.items():
                for msg in msgs:
                    buffer.append(msg.value)

            # flush batch if big enough or time passed
            if len(buffer) >= batch_size or (buffer and (time.time() - last_flush) > 2):
                db = SessionLocal()
                try:
                    inserted = crud.upsert_transactions(db, [
                        {
                            "tx_id": r.get("tx_id"),
                            "sender": r.get("sender"),
                            "receiver": r.get("receiver"),
                            "amount": float(r.get("amount") or 0.0),
                            # store timestamp if present else None; DB has default anyway
                            "timestamp": None,
                        }
                        for r in buffer
                    ])
                    consumer.commit()
                    print(f"🟢 flushed={len(buffer)} inserted={inserted}")
                finally:
                    db.close()

                buffer.clear()
                last_flush = time.time()

    except KeyboardInterrupt:
        print("Stopping consumer...")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
