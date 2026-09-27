# infrastructure/db/engine.py
# SQLAlchemy engine + session factory + FastAPI dependency.
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for ORM models (aquavision.* + read-only shared.*)."""
    pass


from config.settings import settings

DATABASE_URL = os.environ.get("DATABASE_URL") or settings.DATABASE_URL

def _connect_args(url: str) -> dict:
    """TCP keepalives for a remote database.

    Neon suspends an idle compute and drops the socket; without keepalives the
    pool hands out a dead connection and the request stalls until the OS gives
    up. psycopg2 passes these straight to libpq, so only enable them for the
    psycopg2 driver.
    """
    if url.startswith(("postgresql://", "postgres://", "postgresql+psycopg2://")):
        return {
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        }
    return {}


if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        # Sized for a network database. Handlers run in FastAPI's threadpool,
        # so several may want a connection at once; requests beyond the pool
        # queue for pool_timeout rather than failing.
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        # Recycle below Neon's idle-suspend window so pooled sockets are never
        # the stale side of a closed connection.
        pool_recycle=300,
        pool_pre_ping=True,
        connect_args=_connect_args(DATABASE_URL),
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
