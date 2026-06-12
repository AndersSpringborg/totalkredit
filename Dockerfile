FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data

WORKDIR /app

RUN addgroup --system --gid 10001 scraper \
    && adduser --system --uid 10001 --ingroup scraper scraper

COPY pyproject.toml README.md ./
COPY main.py ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install . \
    && mkdir -p /data \
    && chown -R scraper:scraper /app /data

USER scraper

CMD ["totalkredit-scraper"]
