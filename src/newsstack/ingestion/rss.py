from __future__ import annotations

import asyncio
import logging

import feedparser
import httpx

from newsstack.db.models import Article, Feed
from newsstack.ingestion.normalizer import normalize_rss_entry

logger = logging.getLogger(__name__)


async def fetch_feed(client: httpx.AsyncClient, feed: Feed) -> tuple[list[Article], str, str]:
    """Fetch and parse a single RSS feed. Returns (articles, new_etag, new_last_modified)."""
    headers: dict[str, str] = {}
    if feed.etag:
        headers["If-None-Match"] = feed.etag
    if feed.last_modified:
        headers["If-Modified-Since"] = feed.last_modified

    try:
        resp = await client.get(feed.url, headers=headers, timeout=30.0)
    except httpx.HTTPError as e:
        logger.warning("Failed to fetch %s: %s", feed.name, e)
        return [], feed.etag, feed.last_modified

    if resp.status_code == 304:
        logger.debug("Feed %s not modified", feed.name)
        return [], feed.etag, feed.last_modified

    if resp.status_code != 200:
        logger.warning("Feed %s returned %d", feed.name, resp.status_code)
        return [], feed.etag, feed.last_modified

    new_etag = resp.headers.get("ETag", "")
    new_last_modified = resp.headers.get("Last-Modified", "")

    parsed = await asyncio.to_thread(feedparser.parse, resp.text)
    articles: list[Article] = []
    for entry in parsed.entries:
        article = normalize_rss_entry(entry, feed.name, feed.region, feed.category)
        if article:
            articles.append(article)

    logger.info("Fetched %d articles from %s", len(articles), feed.name)
    return articles, new_etag, new_last_modified


async def fetch_all_feeds(
    client: httpx.AsyncClient, feeds: list[Feed]
) -> list[tuple[Feed, list[Article], str, str]]:
    """Fetch all feeds concurrently. Returns list of (feed, articles, etag, last_modified)."""
    tasks = [fetch_feed(client, feed) for feed in feeds]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: list[tuple[Feed, list[Article], str, str]] = []
    for feed, result in zip(feeds, results):
        if isinstance(result, Exception):
            logger.error("Error fetching %s: %s", feed.name, result)
            continue
        articles, etag, last_modified = result
        output.append((feed, articles, etag, last_modified))
    return output
