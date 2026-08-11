# infrastructure/db/engine.py
# SQLAlchemy engine + session factory + FastAPI dependency.
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config.settings import settings


class Base(DeclarativeBase):
    """Declarative base for ORM models (aquavision.* + read-only shared.*)."""

    pass


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DB_ECHO,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session():
    """FastAPI dependency: yields one DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
