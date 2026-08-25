# infrastructure/db/engine.py
# SQLAlchemy engine + session factory + FastAPI dependency.
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for ORM models (aquavision.* + read-only shared.*)."""
    pass


DATABASE_URL = os.environ.get("DATABASE_URL", "")

if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        echo=False,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
else:
    engine = None
    SessionLocal = None
    print("WARNING: DATABASE_URL not set — DB features disabled")


def get_session():
    """FastAPI dependency: yields one DB session per request."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
