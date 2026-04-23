from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from mcp.server.fastmcp import Context, FastMCP

from newsstack.config import Settings
from newsstack.db.sqlite import Database
from newsstack.feeds_loader import sync_feeds_to_db
from newsstack.processing.embeddings import EmbeddingClient
from newsstack.processing.ner import NERProcessor
from newsstack.processing.summarizer import Summarizer
from newsstack.scheduling.scheduler import create_scheduler, ingest_rss, ingest_gdelt
from newsstack.vectors.qdrant import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    db: Database
    vector_store: VectorStore
    ner: NERProcessor
    embedding_client: EmbeddingClient
    summarizer: Summarizer
    http_client: httpx.AsyncClient
    settings: Settings


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppState]:
    settings = Settings()

    # Initialize components
    db = Database(settings.db_path)
    await db.connect()
    await sync_feeds_to_db(db.conn, settings.feeds_file)
    logger.info("SQLite connected: %s", settings.db_path)

    vector_store = VectorStore(settings.qdrant_url, settings.embedding_dim)
    await vector_store.setup()

    # Sync check: if Qdrant has points but SQLite is empty (or vice versa),
    # reset Qdrant so they stay consistent
    qdrant_count = await vector_store.count()
    cursor = await db.conn.execute("SELECT COUNT(*) FROM articles")
    row = await cursor.fetchone()
    sqlite_count = row[0] if row else 0

    if qdrant_count > 0 and sqlite_count == 0:
        logger.warning(
            "Qdrant has %d points but SQLite has 0 articles — resetting Qdrant",
            qdrant_count,
        )
        await vector_store.reset()
    elif sqlite_count > 0 and qdrant_count == 0:
        logger.warning(
            "SQLite has %d articles but Qdrant is empty — clearing SQLite for clean start",
            sqlite_count,
        )
        await db.conn.executescript("DELETE FROM entities; DELETE FROM articles; DELETE FROM clusters;")
        await db.conn.commit()

    logger.info("Qdrant connected: %s (points: %d, articles: %d)", settings.qdrant_url, qdrant_count, sqlite_count)

    ner = NERProcessor()
    await ner.load()

    embedding_client = EmbeddingClient(settings.embedding_url, settings.embedding_model, settings.embedding_max_chars)
    summarizer = Summarizer(settings.llm_url, settings.llm_model)
    http_client = httpx.AsyncClient()

    state = AppState(
        db=db,
        vector_store=vector_store,
        ner=ner,
        embedding_client=embedding_client,
        summarizer=summarizer,
        http_client=http_client,
        settings=settings,
    )

    # Run initial ingestion so data is available immediately
    logger.info("Running initial ingestion...")
    import asyncio
    initial_jobs = [ingest_rss(state)]
    if settings.gdelt_enabled:
        initial_jobs.append(ingest_gdelt(state))
    await asyncio.gather(*initial_jobs)
    logger.info("Initial ingestion complete")

    # Start scheduler for ongoing ingestion
    scheduler = create_scheduler(state)
    scheduler.start()
    logger.info("Scheduler started")

    try:
        yield state
    finally:
        scheduler.shutdown(wait=False)
        await http_client.aclose()
        await vector_store.close()
        await db.close()
        logger.info("Shutdown complete")


_init_settings = Settings()

mcp = FastMCP(
    "newsstack",
    instructions="News intelligence server — aggregates, deduplicates, clusters, and searches news articles",
    host=_init_settings.host,
    port=_init_settings.port,
    lifespan=app_lifespan,
)


def _state(ctx: Context) -> AppState:
    return ctx.request_context.lifespan_context


@mcp.tool()
async def get_latest_headlines(
    ctx: Context,
    hours: int = 24,
    limit: int = 20,
    category: str | None = None,
) -> str:
    """Get the latest news headlines grouped by story cluster.

    Args:
        hours: Look back this many hours (default 24)
        limit: Maximum number of headline clusters to return (default 20)
        category: Filter by category (world, business, technology, general)
    """
    from newsstack.tools.headlines import get_latest_headlines as _impl

    results = await _impl(_state(ctx), hours=hours, limit=limit, category=category)
    return json.dumps(results, indent=2)


@mcp.tool()
async def search_news(
    ctx: Context,
    query: str,
    limit: int = 20,
    region: str | None = None,
    hours: int | None = None,
) -> str:
    """Semantic search over news articles.

    Args:
        query: Natural language search query
        limit: Maximum results (default 20)
        region: Filter by region (north_america, europe, asia, middle_east, africa, oceania, south_america, global)
        hours: Only search articles from the last N hours
    """
    from newsstack.tools.search import search_news as _impl

    results = await _impl(_state(ctx), query=query, limit=limit, region=region, hours=hours)
    return json.dumps(results, indent=2)


@mcp.tool()
async def get_news_by_region(
    ctx: Context,
    region: str,
    hours: int = 24,
    limit: int = 50,
) -> str:
    """Get recent news articles for a specific region.

    Args:
        region: Region code (north_america, europe, asia, middle_east, africa, oceania, south_america, global)
        hours: Look back this many hours (default 24)
        limit: Maximum articles (default 50)
    """
    from newsstack.tools.region import get_news_by_region as _impl

    results = await _impl(_state(ctx), region=region, hours=hours, limit=limit)
    return json.dumps(results, indent=2)


@mcp.tool()
async def get_topic_briefing(
    ctx: Context,
    topic: str,
    hours: int = 48,
    max_articles: int = 10,
) -> str:
    """Generate an intelligence briefing on a topic using semantic search and LLM summarization.

    Args:
        topic: Topic to brief on (e.g., "US-China trade relations", "AI regulation")
        hours: Look back this many hours (default 48)
        max_articles: Maximum articles to include in the briefing (default 10)
    """
    from newsstack.tools.briefing import get_topic_briefing as _impl

    result = await _impl(_state(ctx), topic=topic, hours=hours, max_articles=max_articles)
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_trending_topics(
    ctx: Context,
    hours: int = 12,
    limit: int = 10,
) -> str:
    """Get trending news topics based on article cluster size and velocity.

    Args:
        hours: Look back this many hours (default 12)
        limit: Maximum topics (default 10)
    """
    from newsstack.tools.trending import get_trending_topics as _impl

    results = await _impl(_state(ctx), hours=hours, limit=limit)
    return json.dumps(results, indent=2)
