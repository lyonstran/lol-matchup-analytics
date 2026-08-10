FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Workspace root config + shared lockfile
COPY pyproject.toml uv.lock ./

# Packages the API needs
COPY services/common ./services/common
COPY services/api ./services/api

# Install the api member (and its workspace dep, common)
RUN uv sync --frozen --package api

EXPOSE 8000
CMD ["uv", "run", "--frozen", "--package", "api", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]