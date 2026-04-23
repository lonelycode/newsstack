"""Load and sync the feed configuration file into the SQLite `feeds` table.

The file is authoritative: on every startup, rows are upserted from the file
and rows whose `id` no longer appears in the file are disabled (not deleted —
existing articles still reference them by name).

Per-row ETag and Last-Modified values are runtime cache state and are never
overwritten unless the URL itself changes for that id.
"""

from __future__ import annotations

import logging
import re
from importlib import resources
from pathlib import Path

import aiosqlite
import yaml
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class FeedConfig(BaseModel):
    id: str
    name: str = Field(min_length=1)
    url: HttpUrl
    region: str = "global"
    category: str = "general"
    enabled: bool = True

    @field_validator("id")
    @classmethod
    def _id_is_slug(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError(
                f"feed id {v!r} must match {_ID_RE.pattern} "
                "(lowercase alphanumerics, hyphens, underscores; must start with alnum)"
            )
        return v


class FeedsFile(BaseModel):
    feeds: list[FeedConfig]

    @model_validator(mode="after")
    def _no_duplicates(self) -> FeedsFile:
        ids: set[str] = set()
        urls: set[str] = set()
        for f in self.feeds:
            if f.id in ids:
                raise ValueError(f"duplicate feed id: {f.id!r}")
            ids.add(f.id)
            url_str = str(f.url)
            if url_str in urls:
                raise ValueError(f"duplicate feed url: {url_str!r}")
            urls.add(url_str)
        return self


def load_feeds_config(path: str | None) -> list[FeedConfig]:
    """Load feed config from `path` if set, otherwise from the packaged default.

    Raises on missing file, malformed YAML, or schema violations — startup
    should fail loudly rather than silently load a partial set.
    """
    if path:
        text = Path(path).read_text()
        source = path
    else:
        text = resources.files("newsstack").joinpath("feeds.default.yaml").read_text()
        source = "feeds.default.yaml (packaged default)"

    raw = yaml.safe_load(text)
    if raw is None:
        raise ValueError(f"{source}: file is empty")
    parsed = FeedsFile.model_validate(raw)
    logger.info("Loaded %d feeds from %s", len(parsed.feeds), source)
    return parsed.feeds


async def sync_feeds_to_db(db: aiosqlite.Connection, path: str | None) -> None:
    """Sync the feeds table to the config file.

    - Upserts each entry; preserves etag/last_modified on unchanged URLs.
    - Clears etag/last_modified when the URL changes for an existing id.
    - One-time migration: if a config id is missing but its URL matches an
      existing row (random hex id from pre-config-file installs), rewrite that
      row's id to the config id, preserving etag/last_modified.
    - Disables rows whose id is not in the file (does not delete).
    """
    configs = load_feeds_config(path)

    cursor = await db.execute("SELECT id, url, etag, last_modified FROM feeds")
    existing = {row["id"]: dict(row) for row in await cursor.fetchall()}
    existing_by_url = {row["url"]: row["id"] for row in existing.values()}

    config_ids: set[str] = set()
    for cfg in configs:
        config_ids.add(cfg.id)
        url = str(cfg.url)
        prior = existing.get(cfg.id)

        if prior is None and url in existing_by_url:
            # One-time id migration: same URL, different id (random hex) → adopt config id.
            old_id = existing_by_url[url]
            await db.execute("UPDATE feeds SET id = ? WHERE id = ?", (cfg.id, old_id))
            logger.info("Migrated feed id %s -> %s (matched by url)", old_id, cfg.id)
            prior = existing.pop(old_id)
            del existing_by_url[url]

        if prior is None:
            await db.execute(
                """INSERT INTO feeds (id, name, url, region, category, enabled)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (cfg.id, cfg.name, url, cfg.region, cfg.category, int(cfg.enabled)),
            )
        else:
            url_changed = prior["url"] != url
            if url_changed:
                await db.execute(
                    """UPDATE feeds
                       SET name = ?, url = ?, region = ?, category = ?, enabled = ?,
                           etag = '', last_modified = ''
                       WHERE id = ?""",
                    (cfg.name, url, cfg.region, cfg.category, int(cfg.enabled), cfg.id),
                )
            else:
                await db.execute(
                    """UPDATE feeds
                       SET name = ?, region = ?, category = ?, enabled = ?
                       WHERE id = ?""",
                    (cfg.name, cfg.region, cfg.category, int(cfg.enabled), cfg.id),
                )

    stale = set(existing.keys()) - config_ids
    for stale_id in stale:
        await db.execute("UPDATE feeds SET enabled = 0 WHERE id = ?", (stale_id,))
        logger.info("Disabled feed %s (no longer in config)", stale_id)

    await db.commit()
