"""Tests for SQLite database layer — schema, inserts, queries, edge cases."""

from datetime import datetime, timezone

import pytest

from newsstack.db.models import Article, Cluster, Entity
from newsstack.db import queries


@pytest.mark.asyncio
async def test_insert_and_retrieve_article(db):
    article = Article(
        title="Test headline",
        summary="A test summary",
        source_url="https://example.com/1",
        source_feed="test-feed",
        region="europe",
        category="world",
        published_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
        ingested_at=datetime.now(timezone.utc),
    )
    assert await queries.insert_article(db.conn, article) is True

    articles = await queries.get_recent_articles(db.conn, hours=1)
    assert len(articles) == 1
    assert articles[0].title == "Test headline"
    assert articles[0].source_url == "https://example.com/1"


@pytest.mark.asyncio
async def test_duplicate_url_rejected(db):
    article = Article(
        title="First",
        source_url="https://example.com/dupe",
        ingested_at=datetime.now(timezone.utc),
    )
    assert await queries.insert_article(db.conn, article) is True
    # Same URL should be rejected
    article2 = Article(
        title="Second",
        source_url="https://example.com/dupe",
        ingested_at=datetime.now(timezone.utc),
    )
    assert await queries.insert_article(db.conn, article2) is False


@pytest.mark.asyncio
async def test_url_exists(db):
    assert await queries.url_exists(db.conn, "https://example.com/nope") is False

    article = Article(
        title="Exists",
        source_url="https://example.com/exists",
        ingested_at=datetime.now(timezone.utc),
    )
    await queries.insert_article(db.conn, article)
    assert await queries.url_exists(db.conn, "https://example.com/exists") is True


@pytest.mark.asyncio
async def test_simhash_large_value_stored_correctly(db):
    """SimHash produces 64-bit unsigned ints that exceed SQLite signed int max."""
    large_hash = 2**63 + 12345  # exceeds signed 64-bit range
    article = Article(
        title="Large hash article",
        source_url="https://example.com/large-hash",
        ingested_at=datetime.now(timezone.utc),
        simhash=large_hash,
    )
    assert await queries.insert_article(db.conn, article) is True

    hashes = await queries.get_simhashes(db.conn, since_hours=1)
    assert len(hashes) == 1
    assert hashes[0][1] == large_hash


@pytest.mark.asyncio
async def test_insert_and_get_entities(db):
    article = Article(
        title="Entity test",
        source_url="https://example.com/entities",
        ingested_at=datetime.now(timezone.utc),
    )
    await queries.insert_article(db.conn, article)

    entities = [
        Entity(article_id=article.id, text="NATO", label="organization"),
        Entity(article_id=article.id, text="Brussels", label="location"),
    ]
    await queries.insert_entities(db.conn, entities)

    result = await queries.get_entities_for_article(db.conn, article.id)
    assert len(result) == 2
    labels = {e.label for e in result}
    assert labels == {"organization", "location"}


@pytest.mark.asyncio
async def test_cluster_operations(db):
    cluster = Cluster(
        id="cluster-1",
        label="Test cluster",
        summary="A test summary",
        article_count=5,
    )
    await queries.upsert_cluster(db.conn, cluster)
    await db.conn.commit()

    clusters = await queries.get_top_clusters(db.conn, hours=1, limit=10)
    assert len(clusters) == 1
    assert clusters[0].label == "Test cluster"
    assert clusters[0].article_count == 5

    # Upsert again with updated count
    cluster.article_count = 10
    await queries.upsert_cluster(db.conn, cluster)
    await db.conn.commit()

    clusters = await queries.get_top_clusters(db.conn, hours=1, limit=10)
    assert len(clusters) == 1
    assert clusters[0].article_count == 10


@pytest.mark.asyncio
async def test_get_articles_by_region(db):
    for i, region in enumerate(["europe", "europe", "asia"]):
        await queries.insert_article(
            db.conn,
            Article(
                title=f"Article {i}",
                source_url=f"https://example.com/{i}",
                region=region,
                ingested_at=datetime.now(timezone.utc),
            ),
        )

    europe = await queries.get_articles_by_region(db.conn, "europe", hours=1)
    assert len(europe) == 2

    asia = await queries.get_articles_by_region(db.conn, "asia", hours=1)
    assert len(asia) == 1


@pytest.mark.asyncio
async def test_feeds_seeded(db):
    feeds = await queries.get_all_feeds(db.conn)
    assert len(feeds) == 7
    names = {f.name for f in feeds}
    assert "BBC World" in names
    assert "AP News" in names


@pytest.mark.asyncio
async def test_unclustered_article_ids(db):
    # Insert one clustered, one unclustered
    await queries.insert_article(
        db.conn,
        Article(
            title="Clustered",
            source_url="https://example.com/c1",
            cluster_id="some-cluster",
            ingested_at=datetime.now(timezone.utc),
        ),
    )
    await queries.insert_article(
        db.conn,
        Article(
            title="Unclustered",
            source_url="https://example.com/u1",
            ingested_at=datetime.now(timezone.utc),
        ),
    )

    ids = await queries.get_unclustered_article_ids(db.conn, hours=1)
    assert len(ids) == 1
