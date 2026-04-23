from __future__ import annotations

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS feeds (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    region TEXT NOT NULL DEFAULT 'global',
    category TEXT NOT NULL DEFAULT 'general',
    etag TEXT NOT NULL DEFAULT '',
    last_modified TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL UNIQUE,
    source_feed TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    region TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    ingested_at TEXT NOT NULL,
    simhash TEXT NOT NULL DEFAULT '0',
    cluster_id TEXT REFERENCES clusters(id)
);

CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_region ON articles(region);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_cluster_id ON articles(cluster_id);
CREATE INDEX IF NOT EXISTS idx_articles_simhash ON articles(simhash);
CREATE INDEX IF NOT EXISTS idx_articles_ingested_at ON articles(ingested_at);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    label TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entities_article_id ON entities(article_id);
CREATE INDEX IF NOT EXISTS idx_entities_label ON entities(label);

CREATE TABLE IF NOT EXISTS clusters (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    article_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    articles_fetched INTEGER NOT NULL DEFAULT 0,
    articles_stored INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""

class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA foreign_keys=ON")
        await self.db.executescript(SCHEMA)
        await self.db.commit()

    async def close(self) -> None:
        if self.db:
            await self.db.close()
            self.db = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self.db is not None, "Database not connected"
        return self.db
