# Totalkredit scraper

Scrapes Totalkredit Tilpasningslån cash interest rates and fixed-rate loan prices, appends them to `totalkredit_rates.jsonl`, and publishes metrics via OTLP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Logs only the Tilpasningslån summary line to keep k9s output easy to follow.

## Configuration

Copy the example env file and adjust as needed:

```bash
cp .env.example .env
```

Supported variables:

- `DATA_DIR` — output directory for `totalkredit_rates.jsonl`.
- `OTEL_EXPORTER_OTLP_ENDPOINT` — optional OTLP HTTP metrics endpoint. Leave unset/empty locally to skip metric publishing.

## Run locally with uv

```bash
uv sync
DATA_DIR=./data uv run totalkredit-scraper
```

Or load `.env`:

```bash
set -a && source .env && set +a
uv run totalkredit-scraper
```

## Container

```bash
docker build -t totalkredit:local -t totalkredit:latest .
docker run --rm --env-file .env -v "$PWD/data:/data" totalkredit:latest
```

## k3s

Kubernetes manifests are in `kubernetes/totalkredit`. Copy/sync that directory into `~/dev-project/pi-cluster/kubernetes/totalkredit`, update the image tag in `kustomization.yaml`, then apply with kustomize.
