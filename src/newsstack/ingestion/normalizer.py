from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from newsstack.db.models import Article


def normalize_rss_entry(entry: dict, feed_name: str, feed_region: str, feed_category: str) -> Article | None:
    """Convert a feedparser entry dict to an Article."""
    url = entry.get("link", "").strip()
    if not url:
        return None

    title = _clean_html(entry.get("title", ""))
    if not title:
        return None

    summary = _clean_html(entry.get("summary", "") or entry.get("description", ""))
    content = ""
    if entry.get("content"):
        content = _clean_html(entry["content"][0].get("value", ""))

    published_at = _parse_date(entry.get("published") or entry.get("updated"))

    return Article(
        title=title,
        summary=summary,
        content=content or summary,
        source_url=url,
        source_feed=feed_name,
        author=entry.get("author", ""),
        region=feed_region,
        category=feed_category,
        published_at=published_at,
        ingested_at=datetime.now(timezone.utc),
    )


def normalize_gdelt_article(art: dict) -> Article | None:
    """Convert a GDELT DOC API article dict to an Article."""
    url = art.get("url", "").strip()
    if not url:
        return None

    title = art.get("title", "").strip()
    if not title:
        return None

    published_at = _parse_gdelt_date(art.get("seendate", ""))

    # GDELT provides a source country
    source_country = art.get("sourcecountry", "").lower()
    region = _country_to_region(source_country)

    return Article(
        title=title,
        summary=title,  # GDELT doesn't always provide a summary
        content=title,
        source_url=url,
        source_feed="gdelt",
        author=art.get("domain", ""),
        region=region,
        category="general",
        published_at=published_at,
        ingested_at=datetime.now(timezone.utc),
    )


def compute_text_hash(text: str) -> str:
    """SHA-256 hash for exact dedup."""
    return hashlib.sha256(text.encode()).hexdigest()


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return None


def _parse_gdelt_date(date_str: str) -> datetime | None:
    """Parse GDELT date format: YYYYMMDDTHHmmSS or YYYYMMDDTHHmmSSZ."""
    if not date_str:
        return None
    date_str = date_str.rstrip("Z")
    try:
        return datetime.strptime(date_str, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _country_to_region(country: str) -> str:
    region_map = {
        "united states": "north_america",
        "canada": "north_america",
        "mexico": "north_america",
        "united kingdom": "europe",
        "france": "europe",
        "germany": "europe",
        "china": "asia",
        "japan": "asia",
        "india": "asia",
        "australia": "oceania",
        "brazil": "south_america",
        "nigeria": "africa",
        "south africa": "africa",
        "egypt": "middle_east",
        "saudi arabia": "middle_east",
        "israel": "middle_east",
    }
    return region_map.get(country, "global")
