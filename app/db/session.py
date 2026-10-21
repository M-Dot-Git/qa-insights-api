from sqlalchemy.engine.base import Engine
from collections.abc import Generator

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import DATABASE_URL

engine = None
SessionLocal: sessionmaker[Session] | None = None

if DATABASE_URL:
    database_url = DATABASE_URL
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    if database_url.startswith("postgresql+psycopg://"):
        database_url = database_url.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
    engine: Engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal: sessionmaker[Session] = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise HTTPException(
            status_code=503,
            detail="Set PSQL_STR or DATABASE_URL to connect to PostgreSQL.",
        )
    with SessionLocal() as session:
        yield session
