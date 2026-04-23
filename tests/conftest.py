import pytest

from newsstack.db.sqlite import Database
from newsstack.feeds_loader import sync_feeds_to_db


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db(tmp_path):
    """Provide a fresh SQLite database seeded from the packaged default feed config."""
    db_path = str(tmp_path / "test.db")
    database = Database(db_path)
    await database.connect()
    await sync_feeds_to_db(database.conn, None)
    yield database
    await database.close()
