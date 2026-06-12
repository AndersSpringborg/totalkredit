FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DATA_DIR=/data

WORKDIR /app

RUN groupadd --system --gid 10001 scraper \
    && useradd --system --uid 10001 --gid scraper --home-dir /app scraper

COPY pyproject.toml uv.lock README.md ./
COPY main.py ./
COPY src ./src

RUN uv sync --frozen --no-dev \
    && mkdir -p /data \
    && chown -R scraper:scraper /app /data

USER scraper

CMD ["uv", "run", "--no-sync", "--frozen", "totalkredit-scraper"]
