FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY services/common ./services/common
COPY services/ingest ./services/ingest

RUN uv sync --frozen --package ingest

CMD ["uv", "run", "--frozen", "--package", "ingest", "crawl"]