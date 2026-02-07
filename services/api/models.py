from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from services.api.db import Base


class ScoringRun(Base):
    __tablename__ = "scoring_runs"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tx_source = Column(String, nullable=False)          # e.g. "csv:data/transactions.csv"
    config_json = Column(JSONB, nullable=False)         # store hop weights, normalization flags, etc.

    scores = relationship("RiskScore", back_populates="run")


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("scoring_runs.id", ondelete="CASCADE"), nullable=False, index=True)

    wallet = Column(String, nullable=False, index=True)
    risk_score = Column(Float, nullable=False)

    exposures_json = Column(JSONB, nullable=False)      # list of exposures by hop
    in_degree = Column(Integer, nullable=False)
    out_degree = Column(Integer, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run = relationship("ScoringRun", back_populates="scores")
