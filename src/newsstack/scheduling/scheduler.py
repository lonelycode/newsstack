from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from newsstack.db import queries
from newsstack.ingestion.dedup import filter_simhash_dupes, filter_vector_dupes
from newsstack.ingestion.gdelt import fetch_gdelt_articles
from newsstack.ingestion.rss import fetch_all_feeds
from newsstack.processing.clustering import run_clustering

logger = logging.getLogger(__name__)


async def ingest_rss(state) -> None:
    """Fetch all RSS feeds and process new articles."""
    started = datetime.now(timezone.utc)
    fetched = 0
    stored = 0
    error = None

    try:
        feeds = await queries.get_all_feeds(state.db.conn)
        results = await fetch_all_feeds(state.http_client, feeds)

        for feed, articles, etag, last_modified in results:
            fetched += len(articles)

            # URL dedup
            new_articles = []
            for a in articles:
                if not await queries.url_exists(state.db.conn, a.source_url):
                    new_articles.append(a)

            if not new_articles:
                await queries.update_feed_etag(state.db.conn, feed.id, etag, last_modified)
                continue

            # SimHash dedup
            existing_hashes = await queries.get_simhashes(state.db.conn)
            new_articles = filter_simhash_dupes(
                new_articles, existing_hashes, state.settings.simhash_threshold
            )

            if not new_articles:
                await queries.update_feed_etag(state.db.conn, feed.id, etag, last_modified)
                continue

            # Embed
            texts = [f"{a.title} {a.summary}" for a in new_articles]
            embeddings = await state.embedding_client.embed(texts, state.http_client)

            # Vector dedup
            new_articles, embeddings = await filter_vector_dupes(
                new_articles, embeddings, state.vector_store, state.settings.vector_dedup_threshold
            )

            # Store articles
            for article, embedding in zip(new_articles, embeddings):
                # NER
                entities = await state.ner.extract(article.id, f"{article.title} {article.content}")

                if await queries.insert_article(state.db.conn, article):
                    stored += 1
                    await queries.insert_entities(state.db.conn, entities)
                    await state.vector_store.upsert(
                        article_id=article.id,
                        vector=embedding,
                        source_feed=article.source_feed,
                        region=article.region,
                        published_at=article.published_at.isoformat() if article.published_at else "",
                    )

            await queries.update_feed_etag(state.db.conn, feed.id, etag, last_modified)

    except Exception as e:
        logger.exception("RSS ingestion error")
        error = str(e)

    finished = datetime.now(timezone.utc)
    await queries.log_ingestion(state.db.conn, "rss", started, finished, fetched, stored, error)
    logger.info("RSS ingestion: fetched=%d stored=%d", fetched, stored)


async def ingest_gdelt(state) -> None:
    """Fetch articles from GDELT and process them."""
    started = datetime.now(timezone.utc)
    fetched = 0
    stored = 0
    error = None

    try:
        articles = await fetch_gdelt_articles(state.http_client)
        fetched = len(articles)

        # URL dedup
        new_articles = []
        for a in articles:
            if not await queries.url_exists(state.db.conn, a.source_url):
                new_articles.append(a)

        if new_articles:
            # SimHash dedup
            existing_hashes = await queries.get_simhashes(state.db.conn)
            new_articles = filter_simhash_dupes(
                new_articles, existing_hashes, state.settings.simhash_threshold
            )

        if new_articles:
            # Embed
            texts = [f"{a.title} {a.summary}" for a in new_articles]
            embeddings = await state.embedding_client.embed(texts, state.http_client)

            # Vector dedup
            new_articles, embeddings = await filter_vector_dupes(
                new_articles, embeddings, state.vector_store, state.settings.vector_dedup_threshold
            )

            # Store
            for article, embedding in zip(new_articles, embeddings):
                entities = await state.ner.extract(article.id, f"{article.title} {article.content}")

                if await queries.insert_article(state.db.conn, article):
                    stored += 1
                    await queries.insert_entities(state.db.conn, entities)
                    await state.vector_store.upsert(
                        article_id=article.id,
                        vector=embedding,
                        source_feed=article.source_feed,
                        region=article.region,
                        published_at=article.published_at.isoformat() if article.published_at else "",
                    )

    except Exception as e:
        logger.exception("GDELT ingestion error")
        error = str(e)

    finished = datetime.now(timezone.utc)
    await queries.log_ingestion(state.db.conn, "gdelt", started, finished, fetched, stored, error)
    logger.info("GDELT ingestion: fetched=%d stored=%d", fetched, stored)


async def cluster_articles(state) -> None:
    """Run clustering on recent unclustered articles."""
    try:
        count = await run_clustering(
            state.db.conn,
            state.vector_store,
            state.summarizer,
            state.http_client,
            state.settings.hdbscan_min_cluster_size,
        )
        logger.info("Clustering complete: %d clusters created", count)
    except Exception:
        logger.exception("Clustering error")


async def retention_cleanup(state) -> None:
    """Delete articles and vectors older than retention window."""
    try:
        deleted_ids = await queries.delete_old_articles(state.db.conn, state.settings.retention_days)
        if deleted_ids:
            await state.vector_store.delete(deleted_ids)
            logger.info("Retention cleanup: deleted %d articles", len(deleted_ids))
    except Exception:
        logger.exception("Retention cleanup error")


def create_scheduler(state) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        ingest_rss, "interval", seconds=state.settings.rss_interval,
        args=[state], id="rss_ingestion", name="RSS Ingestion",
    )
    scheduler.add_job(
        ingest_gdelt, "interval", seconds=state.settings.gdelt_interval,
        args=[state], id="gdelt_ingestion", name="GDELT Ingestion",
    )
    scheduler.add_job(
        cluster_articles, "interval", seconds=state.settings.clustering_interval,
        args=[state], id="clustering", name="Article Clustering",
    )
    scheduler.add_job(
        retention_cleanup, "cron", hour=3, minute=0,
        args=[state], id="retention_cleanup", name="Retention Cleanup",
    )

    return scheduler
