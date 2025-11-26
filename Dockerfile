# Multi-architecture build (arm64 and amd64):
#   docker buildx build --platform linux/amd64 -t apantli:latest --push .

#
# Single architecture build:
#   docker build -t apantli:latest .

FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install build dependencies for native packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock
COPY apantli/ apantli/
COPY templates/ templates/

# Install dependencies
RUN uv sync --frozen --no-dev

# Create data directory
RUN mkdir -p /data

# Expose port 4000
EXPOSE 4000

# Default entrypoint with CLI options
CMD ["/app/.venv/bin/python", "-m", "apantli", "--db", "/data/requests.db", "--config", "/data/config.jsonc", "--host", "0.0.0.0", "--port", "4000"]
