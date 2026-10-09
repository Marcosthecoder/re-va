import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base


@pytest.fixture
def db_session():
    """An isolated in-memory SQLite session, independent of the app's real
    re_va.db file, for tests that exercise db.repository / roadmap.tracker /
    market.comps / llm call logging."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def user(db_session):
    """A real signed-up test account, for tests that need a user_id to scope
    deals/comps to."""
    from auth.users import create_user

    return create_user(db_session, "testuser", "testpassword123")
