# Totalkredit scraper

Scrapes Totalkredit Tilpasningslån cash interest rates, appends them to `cash_interest_rates.jsonl`, and publishes `totalkredit_cash_interest_percent` metrics via OTLP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.

## Run locally

```bash
pip install .
DATA_DIR=./data totalkredit-scraper
```

## Container

```bash
docker build -t totalkredit:local .
docker run --rm -v "$PWD/data:/data" totalkredit:local
```

## k3s

Kubernetes manifests are in `kubernetes/totalkredit`. Copy/sync that directory into `~/dev-project/pi-cluster/kubernetes/totalkredit`, update the image tag in `kustomization.yaml`, then apply with kustomize.
