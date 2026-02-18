import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

from services.api import crud
from services.api.db import SessionLocal

CONSUMER_NAME = "transactions_consumer"


def get_env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v else default


def normalize_record(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Normalize incoming record into DB insert dict.

    Supports both schemas:
      - sender/receiver
      - src/dst

    Returns None if required fields are missing.
    """
    tx_id = r.get("tx_id")
    sender = r.get("sender") or r.get("src")
    receiver = r.get("receiver") or r.get("dst")

    if not tx_id or not sender or not receiver:
        return None

    # amount can be missing or malformed; default to 0.0
    amount_raw = r.get("amount", 0.0)
    try:
        amount = float(amount_raw or 0.0)
    except (TypeError, ValueError):
        amount = 0.0

    # timestamp is optional; db default may apply
    ts = r.get("timestamp") or None

    return {
        "tx_id": tx_id,
        "sender": sender,
        "receiver": receiver,
        "amount": amount,
        "timestamp": ts,
    }


def flush_batch(
    consumer: KafkaConsumer,
    buffer: List[Dict[str, Any]],
) -> Tuple[int, int, Optional[str]]:
    """
    Writes buffered messages to DB, updates ingestion_state, commits Kafka offsets.
    Returns: (received_count, inserted_count, last_tx_id_seen)
    """
    received = len(buffer)
    if received == 0:
        return 0, 0, None

    # Track last tx_id seen in the polled messages (even if invalid)
    last_tx_id_seen = None
    for r in reversed(buffer):
        if r.get("tx_id"):
            last_tx_id_seen = r.get("tx_id")
            break

    rows: List[Dict[str, Any]] = []
    skipped = 0

    for r in buffer:
        norm = normalize_record(r)
        if norm is None:
            skipped += 1
            continue
        rows.append(norm)

    db = SessionLocal()
    try:
        inserted = crud.upsert_transactions(db, rows) if rows else 0

        # Only commit Kafka offsets if DB work succeeded
        consumer.commit()

        # Record ingestion metrics (inserted is accurate due to RETURNING-based upsert)
        crud.record_ingestion(
            db,
            name=CONSUMER_NAME,
            last_tx_id=last_tx_id_seen,
            inserted=inserted,
            last_error=None,
        )

        print(
            f"🟢 flushed received={received} valid={len(rows)} skipped={skipped} "
            f"inserted={inserted} last_tx_id={last_tx_id_seen}"
        )

        return received, inserted, last_tx_id_seen

    finally:
        db.close()


def main() -> None:
    bootstrap = get_env("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    topic = get_env("KAFKA_TOPIC_TRANSACTIONS", "transactions")
    group_id = get_env("KAFKA_GROUP_ID", "tx-consumer-v2")

    batch_size = int(get_env("CONSUMER_BATCH_SIZE", "500"))
    poll_ms = int(get_env("CONSUMER_POLL_MS", "1000"))
    flush_seconds = float(get_env("CONSUMER_FLUSH_SECONDS", "2.0"))
    connect_retry_seconds = float(get_env("CONSUMER_CONNECT_RETRY_SECONDS", "5"))
    connect_max_attempts = int(get_env("CONSUMER_CONNECT_MAX_ATTEMPTS", "0"))

    attempt = 0
    consumer = None
    while True:
        attempt += 1
        try:
            consumer = KafkaConsumer(
                topic,
                bootstrap_servers=bootstrap,
                group_id=group_id,
                enable_auto_commit=False,  # commit only after DB commit
                auto_offset_reset="earliest",
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            )
            break
        except NoBrokersAvailable:
            if connect_max_attempts > 0 and attempt >= connect_max_attempts:
                raise
            print(
                f"⏳ Kafka not ready (attempt {attempt}); retrying in {connect_retry_seconds:.1f}s"
            )
            time.sleep(connect_retry_seconds)

    print(f"✅ Consumer connected: {bootstrap} topic='{topic}' group='{group_id}'")

    buffer: List[Dict[str, Any]] = []
    last_flush = time.time()

    try:
        while True:
            records = consumer.poll(timeout_ms=poll_ms)

            for _, msgs in records.items():
                for msg in msgs:
                    buffer.append(msg.value)

            time_due = (time.time() - last_flush) >= flush_seconds
            size_due = len(buffer) >= batch_size

            if buffer and (time_due or size_due):
                try:
                    flush_batch(consumer, buffer)
                    buffer.clear()
                    last_flush = time.time()
                except Exception as e:
                    # IMPORTANT: do NOT commit offsets here (flush_batch only commits on success)
                    # Record error state best-effort
                    print(f"❌ Flush failed (will retry next loop): {e}")

                    db = SessionLocal()
                    try:
                        crud.record_ingestion(
                            db,
                            name=CONSUMER_NAME,
                            last_tx_id=None,
                            inserted=0,
                            last_error=str(e),
                        )
                    finally:
                        db.close()

                    # brief backoff so we don't tight-loop on a failing DB
                    time.sleep(1.0)

    except KeyboardInterrupt:
        print("Stopping consumer... (Ctrl+C)")

    except Exception as e:
        print(f"❌ Consumer crashed: {e}")

        # Best-effort: record crash
        db = SessionLocal()
        try:
            crud.record_ingestion(
                db,
                name=CONSUMER_NAME,
                last_tx_id=None,
                inserted=0,
                last_error=str(e),
            )
        finally:
            db.close()
        raise

    finally:
        try:
            consumer.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
