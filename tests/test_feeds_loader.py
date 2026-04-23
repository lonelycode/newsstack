"""Tests for the feed config loader and DB sync."""

from __future__ import annotations

import pytest

from newsstack.db import queries
from newsstack.feeds_loader import load_feeds_config, sync_feeds_to_db


def _write_yaml(tmp_path, body: str) -> str:
    path = tmp_path / "feeds.yaml"
    path.write_text(body)
    return str(path)


def test_load_packaged_default_feeds():
    feeds = load_feeds_config(None)
    ids = {f.id for f in feeds}
    assert "bbc-world" in ids
    assert "ap-news" in ids
    assert len(feeds) == 7


def test_load_custom_file(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: tenant-feed
    name: Tenant Feed
    url: https://example.com/rss
    region: oceania
    category: politics
""",
    )
    feeds = load_feeds_config(path)
    assert len(feeds) == 1
    assert feeds[0].id == "tenant-feed"
    assert feeds[0].region == "oceania"
    assert feeds[0].category == "politics"


def test_defaults_applied(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: minimal
    name: Minimal
    url: https://example.com/rss
""",
    )
    [feed] = load_feeds_config(path)
    assert feed.region == "global"
    assert feed.category == "general"
    assert feed.enabled is True


def test_rejects_duplicate_ids(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: dup
    name: A
    url: https://example.com/a
  - id: dup
    name: B
    url: https://example.com/b
""",
    )
    with pytest.raises(Exception, match="duplicate feed id"):
        load_feeds_config(path)


def test_rejects_duplicate_urls(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: a
    name: A
    url: https://example.com/same
  - id: b
    name: B
    url: https://example.com/same
""",
    )
    with pytest.raises(Exception, match="duplicate feed url"):
        load_feeds_config(path)


def test_rejects_malformed_url(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: a
    name: A
    url: not-a-url
""",
    )
    with pytest.raises(Exception):
        load_feeds_config(path)


def test_rejects_invalid_id_slug(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: Bad ID!
    name: A
    url: https://example.com/a
""",
    )
    with pytest.raises(Exception, match="must match"):
        load_feeds_config(path)


def test_rejects_missing_required_fields(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: missing-url
    name: No URL
""",
    )
    with pytest.raises(Exception):
        load_feeds_config(path)


def test_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_feeds_config(str(tmp_path / "does-not-exist.yaml"))


def test_rejects_empty_file(tmp_path):
    path = _write_yaml(tmp_path, "")
    with pytest.raises(ValueError, match="empty"):
        load_feeds_config(path)


@pytest.mark.asyncio
async def test_sync_inserts_new_feeds(db, tmp_path):
    # Wipe the default-seeded feeds first so we test the insert path cleanly.
    await db.conn.execute("DELETE FROM feeds")
    await db.conn.commit()

    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: one
    name: One
    url: https://example.com/one
  - id: two
    name: Two
    url: https://example.com/two
""",
    )
    await sync_feeds_to_db(db.conn, path)
    feeds = await queries.get_all_feeds(db.conn)
    assert {f.id for f in feeds} == {"one", "two"}


@pytest.mark.asyncio
async def test_sync_preserves_etag_on_unchanged_url(db, tmp_path):
    await db.conn.execute("DELETE FROM feeds")
    await db.conn.execute(
        """INSERT INTO feeds (id, name, url, region, category, etag, last_modified)
           VALUES ('keep', 'Keep', 'https://example.com/keep', 'global', 'general',
                   'etag-value', 'lm-value')"""
    )
    await db.conn.commit()

    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: keep
    name: Keep Renamed
    url: https://example.com/keep
    category: world
""",
    )
    await sync_feeds_to_db(db.conn, path)

    cursor = await db.conn.execute("SELECT * FROM feeds WHERE id = 'keep'")
    row = await cursor.fetchone()
    assert row["etag"] == "etag-value"
    assert row["last_modified"] == "lm-value"
    assert row["name"] == "Keep Renamed"
    assert row["category"] == "world"


@pytest.mark.asyncio
async def test_sync_clears_etag_on_url_change(db, tmp_path):
    await db.conn.execute("DELETE FROM feeds")
    await db.conn.execute(
        """INSERT INTO feeds (id, name, url, region, category, etag, last_modified)
           VALUES ('moved', 'Moved', 'https://example.com/old', 'global', 'general',
                   'old-etag', 'old-lm')"""
    )
    await db.conn.commit()

    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: moved
    name: Moved
    url: https://example.com/new
""",
    )
    await sync_feeds_to_db(db.conn, path)

    cursor = await db.conn.execute("SELECT * FROM feeds WHERE id = 'moved'")
    row = await cursor.fetchone()
    assert row["url"] == "https://example.com/new"
    assert row["etag"] == ""
    assert row["last_modified"] == ""


@pytest.mark.asyncio
async def test_sync_disables_removed_feeds(db, tmp_path):
    await db.conn.execute("DELETE FROM feeds")
    await db.conn.execute(
        """INSERT INTO feeds (id, name, url, region, category, enabled)
           VALUES ('keep', 'Keep', 'https://example.com/keep', 'global', 'general', 1),
                  ('drop', 'Drop', 'https://example.com/drop', 'global', 'general', 1)"""
    )
    await db.conn.commit()

    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: keep
    name: Keep
    url: https://example.com/keep
""",
    )
    await sync_feeds_to_db(db.conn, path)

    cursor = await db.conn.execute("SELECT id, enabled FROM feeds ORDER BY id")
    rows = {row["id"]: row["enabled"] for row in await cursor.fetchall()}
    assert rows == {"keep": 1, "drop": 0}


@pytest.mark.asyncio
async def test_sync_migrates_random_hex_id_by_url(db, tmp_path):
    await db.conn.execute("DELETE FROM feeds")
    await db.conn.execute(
        """INSERT INTO feeds (id, name, url, region, category, etag, last_modified)
           VALUES ('a1b2c3d4e5f6', 'BBC World', 'https://feeds.bbci.co.uk/news/world/rss.xml',
                   'global', 'world', 'preserved-etag', 'preserved-lm')"""
    )
    await db.conn.commit()

    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: bbc-world
    name: BBC World
    url: https://feeds.bbci.co.uk/news/world/rss.xml
    region: global
    category: world
""",
    )
    await sync_feeds_to_db(db.conn, path)

    cursor = await db.conn.execute("SELECT * FROM feeds")
    rows = list(await cursor.fetchall())
    assert len(rows) == 1
    assert rows[0]["id"] == "bbc-world"
    assert rows[0]["etag"] == "preserved-etag"
    assert rows[0]["last_modified"] == "preserved-lm"


@pytest.mark.asyncio
async def test_sync_idempotent(db, tmp_path):
    path = _write_yaml(
        tmp_path,
        """
feeds:
  - id: only
    name: Only
    url: https://example.com/only
""",
    )
    await db.conn.execute("DELETE FROM feeds")
    await db.conn.commit()

    await sync_feeds_to_db(db.conn, path)
    await sync_feeds_to_db(db.conn, path)

    cursor = await db.conn.execute("SELECT COUNT(*) FROM feeds")
    row = await cursor.fetchone()
    assert row[0] == 1
