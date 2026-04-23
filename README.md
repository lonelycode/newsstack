# Newsstack

MCP server for news intelligence. Aggregates articles from RSS feeds and GDELT, deduplicates, clusters related stories, and exposes structured news data to AI agents via MCP tools.

All ML inference runs locally — no external API keys needed for core functionality.

## Architecture

```
RSS Feeds ──┐                                  ┌── get_latest_headlines
GDELT API ──┤► Normalize ► Dedup ► Embed ► NER ├── search_news
            │    (URL/SimHash/Vector)           ├── get_news_by_region
            └──────────────────────────────────►├── get_topic_briefing
                  ↕            ↕                └── get_trending_topics
               SQLite       Qdrant
              (articles,   (embeddings,
              entities,     768-dim
              clusters)     cosine)
```

- **Transport:** Streamable HTTP on port 8080
- **Embedding:** `nomic-embed-text-v1.5` via local OpenAI-compatible server (port 9097)
- **Summarization:** Local LLM via OpenAI-compatible server (port 9096)
- **NER:** GLiNER (in-process, no external service)
- **Clustering:** HDBSCAN over article embeddings

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker (for Qdrant, or run it natively)
- Local embedding server on port 9097 (e.g., llama.cpp, Ollama, vLLM)
- Local LLM server on port 9096 (e.g., llama.cpp, Ollama, vLLM)

## Quickstart

### With Docker (recommended)

```bash
docker compose up
```

This starts both the MCP server and Qdrant. The server is available at `http://localhost:8080/mcp`.

Your embedding and LLM servers should be running on the host at ports 9097 and 9096 respectively.

### Local development

```bash
# Install dependencies
uv sync

# Start Qdrant separately
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant

# Run the server
uv run python -m newsstack
```

## MCP Client Configuration

Add to your MCP client config (e.g., Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "newsstack": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `get_latest_headlines` | Top story clusters from the last N hours, optionally filtered by category |
| `search_news` | Semantic vector search with optional region/time filters |
| `get_news_by_region` | Articles filtered by region code |
| `get_topic_briefing` | LLM-generated intelligence briefing on a topic |
| `get_trending_topics` | Trending story clusters ranked by article count |

## Data Sources

### RSS Feeds (fetched every 5 minutes)

Feeds are defined in a YAML file. By default, newsstack ships a global news bundle (AP, NPR, NYT, BBC World, BBC Tech, Guardian World, Al Jazeera) at `src/newsstack/feeds.default.yaml`. To override, set `NEWSSTACK_FEEDS_FILE` to the path of your own YAML file with this schema:

```yaml
feeds:
  - id: bbc-world              # required, slug ([a-z0-9][a-z0-9_-]*)
    name: BBC World            # required
    url: https://feeds.bbci.co.uk/news/world/rss.xml  # required
    region: global             # optional, default "global", free-form string
    category: world            # optional, default "general", free-form string
    enabled: true              # optional, default true
```

The file is authoritative on every startup:

- new ids are inserted
- existing ids are updated (name/region/category/enabled)
- ids no longer in the file are disabled (not deleted — preserves article references)
- per-row ETag / Last-Modified cache is preserved when the URL is unchanged, and cleared when the URL changes

Bad YAML, malformed URLs, duplicate ids or URLs, or missing required fields all cause startup to fail with a clear error — prefer loud failure over silent partial-load.

### GDELT (fetched every 10 minutes)

The [GDELT DOC API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) is queried for recent English-language articles. No API key required. Set `NEWSSTACK_GDELT_ENABLED=false` to disable entirely (useful for single-region tenants).

## Deduplication

Articles pass through three dedup layers:

1. **URL hash** — exact match against SQLite unique constraint
2. **SimHash** — near-duplicate detection (hamming distance <= 3)
3. **Vector cosine** — semantic dedup (cosine similarity > 0.95)

## Scheduling

| Job | Interval |
|-----|----------|
| RSS ingestion | 5 min |
| GDELT ingestion | 10 min |
| Clustering (HDBSCAN) | 15 min |
| Retention cleanup | Daily 3:00 AM |

Data retention window is 180 days (configurable).

## Configuration

All settings are configurable via environment variables with the `NEWSSTACK_` prefix. See `.env.example` for the full list.

| Variable | Default | Description |
|----------|---------|-------------|
| `NEWSSTACK_EMBEDDING_URL` | `http://localhost:9097/v1/embeddings` | Embedding server endpoint |
| `NEWSSTACK_EMBEDDING_MODEL` | `nomic-embed-text-v1.5` | Embedding model name |
| `NEWSSTACK_LLM_URL` | `http://localhost:9096/v1/chat/completions` | LLM server endpoint |
| `NEWSSTACK_LLM_MODEL` | `qwen3.5` | LLM model name |
| `NEWSSTACK_QDRANT_URL` | `http://localhost:6333` | Qdrant server URL |
| `NEWSSTACK_DB_PATH` | `newsstack.db` | SQLite database path |
| `NEWSSTACK_FEEDS_FILE` | _(packaged default)_ | Path to YAML feed config |
| `NEWSSTACK_GDELT_ENABLED` | `true` | Toggle GDELT ingestion |
| `NEWSSTACK_HOST` | `0.0.0.0` | Server bind host |
| `NEWSSTACK_PORT` | `8080` | Server bind port |
| `NEWSSTACK_RETENTION_DAYS` | `180` | Data retention window |

### Running a different tenant

Mount your feed config and isolate state:

```bash
NEWSSTACK_FEEDS_FILE=/etc/newsstack/nz-feeds.yaml \
NEWSSTACK_GDELT_ENABLED=false \
NEWSSTACK_DB_PATH=nz.db \
NEWSSTACK_QDRANT_URL=http://qdrant-nz:6333 \
uv run python -m newsstack
```

Two tenants must use different `NEWSSTACK_DB_PATH` and `NEWSSTACK_QDRANT_URL` so their articles and clusters don't bleed together.

## Resetting data

On startup, newsstack checks that SQLite and Qdrant are in sync. If one has data and the other is empty (e.g., after a volume was deleted), it automatically resets the stale side so ingestion starts clean.

To fully reset all data:

```bash
# Docker
docker compose down -v   # removes both data volumes
docker compose up --build

# Local development
rm newsstack.db
curl -X DELETE http://localhost:6333/collections/news_articles
uv run python -m newsstack
```

## Development

```bash
# Lint
uv run ruff check src/

# Test
uv run pytest
```
