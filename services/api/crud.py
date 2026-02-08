from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from services.api.models import RiskScore, ScoringRun

from .models import IngestionState, Transaction

CONSUMER_NAME = "transactions_consumer"


def create_scoring_run(
    db: Session,
    tx_source: str,
    config_json: Dict[str, Any],
) -> ScoringRun:
    run = ScoringRun(
        created_at=datetime.now(timezone.utc),
        tx_source=tx_source,
        config_json=config_json,
    )
    db.add(run)
    db.flush()  # assigns run.id
    return run


def bulk_insert_risk_scores(
    db: Session,
    run_id: int,
    rows: List[Dict[str, Any]],
) -> int:
    """
    rows items should contain:
      wallet, risk_score, exposures_json, in_degree, out_degree
    """
    objs = [
        RiskScore(
            run_id=run_id,
            wallet=r["wallet"],
            risk_score=r["risk_score"],
            exposures_json=r["exposures_json"],
            in_degree=r["in_degree"],
            out_degree=r["out_degree"],
            created_at=datetime.now(timezone.utc),
        )
        for r in rows
    ]
    db.add_all(objs)
    return len(objs)


def upsert_transactions(db, tx_rows):
    """
    tx_rows: list[dict] each with keys:
      tx_id, sender, receiver, amount, timestamp (optional)
    """
    if not tx_rows:
        return 0

    stmt = insert(Transaction).values(tx_rows)

    # If tx_id already exists, do nothing (dedupe)

    stmt = stmt.on_conflict_do_nothing(index_elements=["tx_id"]).returning(Transaction.tx_id)

    result = db.execute(stmt)
    inserted_ids = result.scalars().all()
    db.commit()
    return len(inserted_ids)


def get_top_scores_latest(db: Session, n: int = 20) -> List[RiskScore]:
    latest = get_latest_run(db)
    if not latest:
        return []

    return (
        db.query(RiskScore)
        .filter(RiskScore.run_id == latest.id)
        .order_by(desc(RiskScore.risk_score))
        .limit(n)
        .all()
    )


def get_latest_score_for_wallet(db: Session, wallet: str) -> Optional[RiskScore]:
    return (
        db.query(RiskScore)
        .filter(RiskScore.wallet == wallet)
        .order_by(desc(RiskScore.created_at))
        .first()
    )


def get_latest_run(db: Session) -> Optional[ScoringRun]:
    return db.query(ScoringRun).order_by(desc(ScoringRun.created_at)).first()


def fetch_all_transactions(db):
    return db.query(Transaction).all()


def record_ingestion(
    db, name: str, last_tx_id: str | None, inserted: int, last_error: str | None = None
):
    stmt = (
        insert(IngestionState)
        .values(
            name=name,
            last_tx_id=last_tx_id,
            total_inserted=inserted,
            last_error=last_error,
        )
        .on_conflict_do_update(
            index_elements=["name"],
            set_={
                "last_tx_id": last_tx_id,
                "last_processed_at": func.now(),
                "total_inserted": IngestionState.total_inserted + inserted,
                "last_error": last_error,
            },
        )
    )
    db.execute(stmt)
    db.commit()


def count_transactions(db: Session) -> int:
    return int(db.query(func.count(Transaction.id)).scalar() or 0)


def get_ingestion_state(db: Session, name: str = CONSUMER_NAME) -> IngestionState | None:
    return db.query(IngestionState).filter(IngestionState.name == name).first()


def count_scores_for_run(db: Session, run_id: int) -> int:
    return int(db.query(func.count(RiskScore.id)).filter(RiskScore.run_id == run_id).scalar() or 0)


def count_recent_transactions(db: Session, minutes: int = 5) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return int(
        db.query(func.count(Transaction.id)).filter(Transaction.timestamp >= cutoff).scalar() or 0
    )


def count_ingested_since(db: Session, minutes: int = 5) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return int(
        db.query(func.count(Transaction.id)).filter(Transaction.ingested_at >= cutoff).scalar() or 0
    )

def get_run_by_id(db: Session, run_id: int) -> Optional[ScoringRun]:
    return db.query(ScoringRun).filter(ScoringRun.id == run_id).first()
