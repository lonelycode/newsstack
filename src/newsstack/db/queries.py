from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from newsstack.db.models import Article, Cluster, Entity, Feed


async def insert_article(db: aiosqlite.Connection, article: Article) -> bool:
    """Insert an article. Returns True if inserted, False if URL already exists."""
    try:
        await db.execute(
            """INSERT INTO articles
               (id, title, summary, content, source_url, source_feed, author,
                region, category, published_at, ingested_at, simhash, cluster_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                article.id,
                article.title,
                article.summary,
                article.content,
                article.source_url,
                article.source_feed,
                article.author,
                article.region,
                article.category,
                article.published_at.isoformat() if article.published_at else None,
                article.ingested_at.isoformat() if article.ingested_at else datetime.now(timezone.utc).isoformat(),
                str(article.simhash),
                article.cluster_id,
            ),
        )
        await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def insert_entities(db: aiosqlite.Connection, entities: list[Entity]) -> None:
    await db.executemany(
        "INSERT OR IGNORE INTO entities (id, article_id, text, label) VALUES (?, ?, ?, ?)",
        [(e.id, e.article_id, e.text, e.label) for e in entities],
    )
    await db.commit()


async def url_exists(db: aiosqlite.Connection, url: str) -> bool:
    cursor = await db.execute("SELECT 1 FROM articles WHERE source_url = ?", (url,))
    return await cursor.fetchone() is not None


async def get_simhashes(db: aiosqlite.Connection, since_hours: int = 48) -> list[tuple[str, int]]:
    """Get (id, simhash) pairs for recent articles."""
    cutoff = datetime.now(timezone.utc).isoformat()
    cursor = await db.execute(
        """SELECT id, simhash FROM articles
           WHERE ingested_at > datetime(?, '-' || ? || ' hours')""",
        (cutoff, since_hours),
    )
    return [(row["id"], int(row["simhash"])) for row in await cursor.fetchall()]


async def get_recent_articles(
    db: aiosqlite.Connection,
    hours: int = 24,
    limit: int = 100,
    category: str | None = None,
    region: str | None = None,
) -> list[Article]:
    query = """SELECT * FROM articles
               WHERE ingested_at > datetime('now', '-' || ? || ' hours')"""
    params: list = [hours]
    if category:
        query += " AND category = ?"
        params.append(category)
    if region:
        query += " AND region = ?"
        params.append(region)
    query += " ORDER BY published_at DESC LIMIT ?"
    params.append(limit)
    cursor = await db.execute(query, params)
    return [_row_to_article(row) for row in await cursor.fetchall()]


async def get_articles_by_cluster(db: aiosqlite.Connection, cluster_id: str) -> list[Article]:
    cursor = await db.execute(
        "SELECT * FROM articles WHERE cluster_id = ? ORDER BY published_at DESC",
        (cluster_id,),
    )
    return [_row_to_article(row) for row in await cursor.fetchall()]


async def get_articles_by_ids(db: aiosqlite.Connection, ids: list[str]) -> list[Article]:
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    cursor = await db.execute(
        f"SELECT * FROM articles WHERE id IN ({placeholders})", ids
    )
    return [_row_to_article(row) for row in await cursor.fetchall()]


async def get_articles_by_region(
    db: aiosqlite.Connection, region: str, hours: int = 24, limit: int = 50
) -> list[Article]:
    cursor = await db.execute(
        """SELECT * FROM articles
           WHERE region = ? AND ingested_at > datetime('now', '-' || ? || ' hours')
           ORDER BY published_at DESC LIMIT ?""",
        (region, hours, limit),
    )
    return [_row_to_article(row) for row in await cursor.fetchall()]


async def get_unclustered_article_ids(
    db: aiosqlite.Connection, hours: int = 24
) -> list[str]:
    cursor = await db.execute(
        """SELECT id FROM articles
           WHERE cluster_id IS NULL
             AND ingested_at > datetime('now', '-' || ? || ' hours')""",
        (hours,),
    )
    return [row["id"] for row in await cursor.fetchall()]


async def update_article_cluster(
    db: aiosqlite.Connection, article_id: str, cluster_id: str
) -> None:
    await db.execute(
        "UPDATE articles SET cluster_id = ? WHERE id = ?",
        (cluster_id, article_id),
    )


async def upsert_cluster(db: aiosqlite.Connection, cluster: Cluster) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO clusters (id, label, summary, article_count, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             label = excluded.label,
             summary = excluded.summary,
             article_count = excluded.article_count,
             updated_at = excluded.updated_at""",
        (cluster.id, cluster.label, cluster.summary, cluster.article_count, now, now),
    )


async def get_top_clusters(
    db: aiosqlite.Connection, hours: int = 24, limit: int = 10
) -> list[Cluster]:
    cursor = await db.execute(
        """SELECT * FROM clusters
           WHERE updated_at > datetime('now', '-' || ? || ' hours')
           ORDER BY article_count DESC LIMIT ?""",
        (hours, limit),
    )
    return [_row_to_cluster(row) for row in await cursor.fetchall()]


async def get_all_feeds(db: aiosqlite.Connection, enabled_only: bool = True) -> list[Feed]:
    query = "SELECT * FROM feeds"
    if enabled_only:
        query += " WHERE enabled = 1"
    cursor = await db.execute(query)
    return [_row_to_feed(row) for row in await cursor.fetchall()]


async def update_feed_etag(
    db: aiosqlite.Connection, feed_id: str, etag: str, last_modified: str
) -> None:
    await db.execute(
        "UPDATE feeds SET etag = ?, last_modified = ? WHERE id = ?",
        (etag, last_modified, feed_id),
    )
    await db.commit()


async def log_ingestion(
    db: aiosqlite.Connection,
    source: str,
    started_at: datetime,
    finished_at: datetime,
    fetched: int,
    stored: int,
    error: str | None = None,
) -> None:
    await db.execute(
        """INSERT INTO ingestion_log (source, started_at, finished_at, articles_fetched, articles_stored, error)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (source, started_at.isoformat(), finished_at.isoformat(), fetched, stored, error),
    )
    await db.commit()


async def delete_old_articles(db: aiosqlite.Connection, retention_days: int) -> list[str]:
    """Delete articles older than retention_days. Returns deleted IDs for vector cleanup."""
    cursor = await db.execute(
        """SELECT id FROM articles
           WHERE ingested_at < datetime('now', '-' || ? || ' days')""",
        (retention_days,),
    )
    ids = [row["id"] for row in await cursor.fetchall()]
    if ids:
        placeholders = ",".join("?" for _ in ids)
        await db.execute(f"DELETE FROM articles WHERE id IN ({placeholders})", ids)
        # Clean up empty clusters
        await db.execute(
            """DELETE FROM clusters WHERE id NOT IN
               (SELECT DISTINCT cluster_id FROM articles WHERE cluster_id IS NOT NULL)"""
        )
        await db.commit()
    return ids


async def get_entities_for_article(db: aiosqlite.Connection, article_id: str) -> list[Entity]:
    cursor = await db.execute(
        "SELECT * FROM entities WHERE article_id = ?", (article_id,)
    )
    return [Entity(id=row["id"], article_id=row["article_id"], text=row["text"], label=row["label"])
            for row in await cursor.fetchall()]


def _row_to_article(row: aiosqlite.Row) -> Article:
    return Article(
        id=row["id"],
        title=row["title"],
        summary=row["summary"],
        content=row["content"],
        source_url=row["source_url"],
        source_feed=row["source_feed"],
        author=row["author"],
        region=row["region"],
        category=row["category"],
        published_at=datetime.fromisoformat(row["published_at"]) if row["published_at"] else None,
        ingested_at=datetime.fromisoformat(row["ingested_at"]) if row["ingested_at"] else None,
        simhash=int(row["simhash"]),
        cluster_id=row["cluster_id"],
    )


def _row_to_cluster(row: aiosqlite.Row) -> Cluster:
    return Cluster(
        id=row["id"],
        label=row["label"],
        summary=row["summary"],
        article_count=row["article_count"],
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
    )


def _row_to_feed(row: aiosqlite.Row) -> Feed:
    return Feed(
        id=row["id"],
        name=row["name"],
        url=row["url"],
        region=row["region"],
        category=row["category"],
        etag=row["etag"],
        last_modified=row["last_modified"],
        enabled=bool(row["enabled"]),
    )
