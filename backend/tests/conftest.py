"""Integration tests use a separate `phddog_test` database on the compose Postgres.

Network access is stubbed, so tests are offline and deterministic.
"""

import os

import psycopg
import pytest

ADMIN_URL = os.environ.get("TEST_ADMIN_URL", "postgresql://phddog:phddog@localhost:5432/phddog")
TEST_DB = "phddog_test"
os.environ["DATABASE_URL"] = f"postgresql+psycopg://phddog:phddog@localhost:5432/{TEST_DB}"
os.environ["LLM_PROVIDER"] = "fake"


def _db_available() -> bool:
    try:
        with psycopg.connect(ADMIN_URL, autocommit=True, connect_timeout=2) as conn:
            conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
            conn.execute(f"CREATE DATABASE {TEST_DB}")
        return True
    except psycopg.OperationalError:
        return False


@pytest.fixture(scope="session")
def database(tmp_path_factory):
    if not _db_available():
        pytest.skip("Postgres not running (docker compose up -d db)")
    os.environ["DATA_DIR"] = str(tmp_path_factory.mktemp("data"))
    from app.config import get_settings

    get_settings.cache_clear()
    from app.db.models import Base
    from app.db.session import engine

    Base.metadata.create_all(engine)
    yield
    engine.dispose()
