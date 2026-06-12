import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

# --- Configuration ---
BASE_URL = os.getenv("BASE_URL", "https://www.totalkredit.dk")
TABLE_ID = os.getenv(
    "TABLE_ID", "privat-udbetaling-af-laan-kontantrenter-raadgivere-og-kunder"
)
DOMAIN = os.getenv("DOMAIN", "totalkredit")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")


def setup_otel():
    """Configure OpenTelemetry to push metrics via OTLP when an endpoint is set."""
    if not OTEL_ENDPOINT:
        return None, metrics.get_meter("totalkredit_scraper")

    exporter = OTLPMetricExporter(endpoint=OTEL_ENDPOINT)
    reader = PeriodicExportingMetricReader(exporter)
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    return provider, metrics.get_meter("totalkredit_scraper")


def parse_danish_percent(value: str) -> float:
    """Convert a Danish percent string like '2,84%' to 2.84."""
    normalized = value.strip().replace("%", "").replace(".", "").replace(",", ".")
    return float(normalized)


def parse_cash_interest_table(payload: dict[str, Any]) -> list[dict[str, str | float | bool | None]]:
    """Parse Totalkredit's bond-information API response."""
    timestamp = datetime.now(timezone.utc).isoformat()
    last_updated = payload.get("lastUpdatedTimestamp")
    next_update = payload.get("nextUpdateTimestamp")

    parsed_data: list[dict[str, str | float | bool | None]] = []
    for group in payload.get("groups", []):
        group_name = group.get("name", "")
        for entry in group.get("entries", []):
            interest_value = entry.get("innerInterestGrossValue")
            loan_type = entry.get("name")
            lifetime = entry.get("lifetime")

            if not interest_value or not loan_type or not lifetime:
                continue

            parsed_data.append(
                {
                    "timestamp": timestamp,
                    "last_updated": last_updated,
                    "next_update": next_update,
                    "group": group_name,
                    "lifetime": lifetime,
                    "loan_type": loan_type,
                    "cash_interest_percent": parse_danish_percent(interest_value),
                    "is_open_for_offer": entry.get("isOpenForOffer"),
                }
            )

    return parsed_data


def scrape_totalkredit() -> list[dict[str, str | float | bool | None]]:
    """Scrape cash interest rates for Tilpasningslån from Totalkredit's public API."""
    url = f"{BASE_URL.rstrip('/')}/api/bondinformation/table"
    params = {"tableId": TABLE_ID, "domain": DOMAIN}
    headers = {
        "Accept": "application/json",
        "User-Agent": "totalkredit-scraper/0.1",
    }

    print(f"Scraping {url}?tableId={TABLE_ID}&domain={DOMAIN}...")
    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return parse_cash_interest_table(response.json())


def save_prices(
    data: list[dict[str, str | float | bool | None]], data_dir: Path = DATA_DIR
) -> Path:
    """Append scraped rows to a JSONL file and return its path."""
    data_dir.mkdir(parents=True, exist_ok=True)
    file_path = data_dir / "cash_interest_rates.jsonl"

    with file_path.open("a", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return file_path


def format_results_line(data: list[dict[str, str | float | bool | None]]) -> str:
    """Format all scraped rates as one log line for k9s."""
    result_date = data[0].get("last_updated") or data[0].get("timestamp")
    rates = " | ".join(
        f"{item['lifetime']} {item['loan_type']}={float(item['cash_interest_percent']):.2f}%"
        for item in data
    )
    return f"Totalkredit Tilpasningslån date={result_date} | {rates}"


def publish_metrics(meter, data: list[dict[str, str | float | bool | None]]) -> None:
    """Publish cash interest rates as OpenTelemetry gauge values."""
    interest_gauge = meter.create_gauge(
        name="totalkredit_cash_interest_percent",
        description="Kontantrente for Totalkredit Tilpasningslån",
        unit="%",
    )

    for item in data:
        interest_gauge.set(
            float(item["cash_interest_percent"]),
            {
                "group": str(item["group"]),
                "lifetime": str(item["lifetime"]),
                "loan_type": str(item["loan_type"]),
            },
        )


def main() -> None:
    provider, meter = setup_otel()

    try:
        data = scrape_totalkredit()
        if not data:
            raise RuntimeError("No cash interest rows found in Totalkredit API response.")

        print(format_results_line(data), flush=True)

        file_path = save_prices(data)
        print(f"Saved {len(data)} records to {file_path}")

        if provider:
            publish_metrics(meter, data)
            print(f"Published {len(data)} metrics to OTel endpoint: {OTEL_ENDPOINT}")
        else:
            print("OTEL_EXPORTER_OTLP_ENDPOINT is not set; skipped metric publishing")

    except Exception as e:
        print(f"Scraper failed: {e}")
        raise
    finally:
        if provider:
            provider.force_flush()
            provider.shutdown()
            print("Metrics flushed. Exiting.")


if __name__ == "__main__":
    main()
