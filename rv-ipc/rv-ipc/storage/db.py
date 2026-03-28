"""R&V IPC — Database connection."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from config.settings import get_settings


def get_engine():
    s = get_settings()
    return create_engine(s.DATABASE_URL_SYNC, pool_pre_ping=True)


def get_session() -> Session:
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
