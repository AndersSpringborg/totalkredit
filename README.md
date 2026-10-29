# Totalkredit scraper

Scrapes all Totalkredit data shown on `kurser-og-priser`: fixed-rate payout prices, variable-rate/F-kort payout prices, Tilpasningslån cash interest, and all redemption groups (Fast rente, F-kort, RenteMax, CIBOR3, CIBOR6, Tilpasningslån). Rows are appended to `totalkredit_rates.jsonl`, and numeric values can be published as OTLP metrics.

## Configuration

Copy the example env file and adjust as needed:

```bash
cp .env.example .env
```

Supported variables:

- `DATA_DIR` — output directory for `totalkredit_rates.jsonl`.
- `OTEL_EXPORTER_OTLP_ENDPOINT` — optional OTLP HTTP metrics endpoint. Leave unset/empty to skip metric publishing.

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
docker build -t totalkredit:local .
docker run --rm --env-file .env -v "$PWD/data:/data" totalkredit:local
```

## Kubernetes

Kustomize manifests are in `kubernetes/`.

The default Kustomize config points at the public image for this repository:

```yaml
images:
  - name: totalkredit
    newName: ghcr.io/andersspringborg/totalkredit
    newTag: latest
```

If you fork the project or publish your own image, update `images[].newName` in `kubernetes/kustomization.yaml`.

OTEL metrics are configured in `kubernetes/kustomization.yaml` too:

- Set `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` if you want metric publishing.
- Leave the OTEL endpoint values empty to run without metrics.

Render and apply:

```bash
kubectl kustomize kubernetes
kubectl apply -k kubernetes
```

The default PersistentVolumeClaim uses your cluster's default storage class. Add `storageClassName` to `kubernetes/01-pvc.yaml` if your cluster requires one.

## Grafana

A Grafana dashboard example is available at `grafana/dashboard.json`. Import it into Grafana and point the panels at the Prometheus-compatible datasource that receives the scraper's OTLP metrics.

The dashboard has a graph plus an adjacent latest-value table for each scraped section/subsection, including F-kort and the redemption groups.
