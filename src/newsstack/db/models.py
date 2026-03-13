from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Article:
    id: str = field(default_factory=_new_id)
    title: str = ""
    summary: str = ""
    content: str = ""
    source_url: str = ""
    source_feed: str = ""
    author: str = ""
    region: str = ""
    category: str = ""
    published_at: datetime | None = None
    ingested_at: datetime | None = None
    simhash: int = 0
    cluster_id: str | None = None


@dataclass
class Entity:
    id: str = field(default_factory=_new_id)
    article_id: str = ""
    text: str = ""
    label: str = ""


@dataclass
class Cluster:
    id: str = field(default_factory=_new_id)
    label: str = ""
    summary: str = ""
    article_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Feed:
    id: str = field(default_factory=_new_id)
    name: str = ""
    url: str = ""
    region: str = "global"
    category: str = "general"
    etag: str = ""
    last_modified: str = ""
    enabled: bool = True
