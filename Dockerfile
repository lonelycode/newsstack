FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock .python-version ./
COPY src/ src/
RUN uv sync --frozen --no-dev

# Pre-download GLiNER model into the image so first startup is fast
RUN /app/.venv/bin/python -c "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_medium-v2.1')"

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app /app
COPY --from=builder /root/.cache/huggingface /root/.cache/huggingface

EXPOSE 8080

CMD ["/app/.venv/bin/python", "-m", "newsstack"]
