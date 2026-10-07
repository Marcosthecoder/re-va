"""Engine/session factory. Reads DATABASE_URL from the environment (.env),
defaulting to a SQLite file in the project root so the app works with zero
configuration.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = f"sqlite:///{PROJECT_ROOT / 're_va.db'}"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create all tables if they don't already exist. Safe to call repeatedly."""
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """One session per call; caller is responsible for closing it (or use as a context manager)."""
    return SessionLocal()
