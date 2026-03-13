import pytest
import tempfile
import os

from newsstack.db.sqlite import Database


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db(tmp_path):
    """Provide a fresh in-memory-like SQLite database for each test."""
    db_path = str(tmp_path / "test.db")
    database = Database(db_path)
    await database.connect()
    yield database
    await database.close()
