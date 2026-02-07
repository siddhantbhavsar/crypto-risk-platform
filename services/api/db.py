import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

# Local dev default (when you run alembic/python on Windows directly)
# In Docker Compose, DATABASE_URL is set to host "db" (the service name).
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://risk:risk@localhost:5432/riskdb",
)

class Base(DeclarativeBase):
    pass

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency: yields a DB session per request and always closes it.
    Usage:
        from fastapi import Depends
        db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
