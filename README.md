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

| Feed | Category |
|------|----------|
| AP News | general |
| NPR World | world |
| NY Times World | world |
| BBC World | world |
| BBC Technology | technology |
| The Guardian World | world |
| Al Jazeera | general |

Additional feeds can be added directly to the `feeds` SQLite table.

### GDELT (fetched every 10 minutes)

The [GDELT DOC API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) is queried for recent English-language articles. No API key required.

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
| `NEWSSTACK_HOST` | `0.0.0.0` | Server bind host |
| `NEWSSTACK_PORT` | `8080` | Server bind port |
| `NEWSSTACK_RETENTION_DAYS` | `180` | Data retention window |

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
