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
CASH_INTEREST_TABLE_ID = os.getenv(
    "CASH_INTEREST_TABLE_ID", "privat-udbetaling-af-laan-kontantrenter-raadgivere-og-kunder"
)
FIXED_RATE_TABLE_ID = os.getenv(
    "FIXED_RATE_TABLE_ID", "privat-udbetaling-af-laan-aktuelle-kurser-kunder"
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


def parse_danish_number(value: str | None) -> float | None:
    """Convert a Danish number string like '103,21' or '2,84%' to a float."""
    if not value or value.strip() == "-":
        return None

    normalized = value.strip().replace("%", "").replace(".", "").replace(",", ".")
    return float(normalized)


def parse_danish_percent(value: str) -> float:
    """Convert a Danish percent string like '2,84%' to 2.84."""
    parsed = parse_danish_number(value)
    if parsed is None:
        raise ValueError(f"Expected percent value, got {value!r}")
    return parsed


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
                    "rate_type": "cash_interest",
                    "group": group_name,
                    "lifetime": lifetime,
                    "loan_type": loan_type,
                    "cash_interest_percent": parse_danish_percent(interest_value),
                    "is_open_for_offer": entry.get("isOpenForOffer"),
                }
            )

    return parsed_data


def parse_fixed_rate_table(payload: dict[str, Any]) -> list[dict[str, str | float | bool | None]]:
    """Parse Totalkredit fixed-rate loan price/rate rows."""
    timestamp = datetime.now(timezone.utc).isoformat()
    last_updated = payload.get("lastUpdatedTimestamp")
    next_update = payload.get("nextUpdateTimestamp")

    parsed_data: list[dict[str, str | float | bool | None]] = []
    for group in payload.get("groups", []):
        group_name = group.get("name", "")
        for entry in group.get("entries", []):
            loan_type = entry.get("name")
            lifetime = entry.get("lifetime")
            fond_code = entry.get("fondCode")

            if not loan_type or not lifetime or not fond_code:
                continue

            parsed_data.append(
                {
                    "timestamp": timestamp,
                    "last_updated": last_updated,
                    "next_update": next_update,
                    "rate_type": "fixed_rate",
                    "group": group_name,
                    "lifetime": lifetime,
                    "loan_type": loan_type,
                    "fond_code": fond_code,
                    "status": entry.get("openForOffer"),
                    "is_open_for_offer": entry.get("isOpenForOffer"),
                    "offer_price": parse_danish_number(entry.get("priceRate")),
                    "current_price": parse_danish_number(entry.get("spotPriceRatePayment")),
                    "effective_rate_percent": parse_danish_number(entry.get("effectiveRate")),
                    "nasdaq_url": entry.get("nasdaqUrl"),
                }
            )

    return parsed_data


def fetch_table(table_id: str) -> dict[str, Any]:
    """Fetch a Totalkredit bond-information table from the public API."""
    url = f"{BASE_URL.rstrip('/')}/api/bondinformation/table"
    params = {"tableId": table_id, "domain": DOMAIN}
    headers = {
        "Accept": "application/json",
        "User-Agent": "totalkredit-scraper/0.1",
    }

    print(f"Scraping {url}?tableId={table_id}&domain={DOMAIN}...")
    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def scrape_totalkredit() -> tuple[
    list[dict[str, str | float | bool | None]],
    list[dict[str, str | float | bool | None]],
]:
    """Scrape cash interest and fixed-rate tables from Totalkredit's public API."""
    cash_interest = parse_cash_interest_table(fetch_table(CASH_INTEREST_TABLE_ID))
    fixed_rates = parse_fixed_rate_table(fetch_table(FIXED_RATE_TABLE_ID))
    return cash_interest, fixed_rates


def save_prices(
    data: list[dict[str, str | float | bool | None]], data_dir: Path = DATA_DIR
) -> Path:
    """Append scraped rows to a JSONL file and return its path."""
    data_dir.mkdir(parents=True, exist_ok=True)
    file_path = data_dir / "totalkredit_rates.jsonl"

    with file_path.open("a", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return file_path


def format_results_line(data: list[dict[str, str | float | bool | None]]) -> str:
    """Format all scraped rates as one compact log line."""
    result_date = data[0].get("last_updated") or data[0].get("timestamp")
    rates = " | ".join(
        f"{item['lifetime']} {item['loan_type']}={float(item['cash_interest_percent']):.2f}%"
        for item in data
    )
    return f"Totalkredit Tilpasningslån date={result_date} | {rates}"


def publish_metrics(meter, data: list[dict[str, str | float | bool | None]]) -> None:
    """Publish scraped Totalkredit rates as OpenTelemetry gauge values."""
    interest_gauge = meter.create_gauge(
        name="totalkredit_cash_interest_percent",
        description="Kontantrente for Totalkredit Tilpasningslån",
        unit="%",
    )
    offer_price_gauge = meter.create_gauge(
        name="totalkredit_fixed_rate_offer_price",
        description="Tilbudskurs for Totalkredit fastforrentede lån",
        unit="1",
    )
    current_price_gauge = meter.create_gauge(
        name="totalkredit_fixed_rate_current_price",
        description="Aktuel kurs for Totalkredit fastforrentede lån",
        unit="1",
    )
    effective_rate_gauge = meter.create_gauge(
        name="totalkredit_fixed_rate_effective_percent",
        description="Effektiv rente for Totalkredit fastforrentede lån",
        unit="%",
    )

    for item in data:
        attributes = {
            "group": str(item["group"]),
            "lifetime": str(item["lifetime"]),
            "loan_type": str(item["loan_type"]),
        }

        if item.get("rate_type") == "cash_interest":
            interest_gauge.set(float(item["cash_interest_percent"]), attributes)
            continue

        fixed_attributes = {
            **attributes,
            "fond_code": str(item["fond_code"]),
            "status": str(item["status"]),
        }
        if item.get("offer_price") is not None:
            offer_price_gauge.set(float(item["offer_price"]), fixed_attributes)
        if item.get("current_price") is not None:
            current_price_gauge.set(float(item["current_price"]), fixed_attributes)
        if item.get("effective_rate_percent") is not None:
            effective_rate_gauge.set(float(item["effective_rate_percent"]), fixed_attributes)


def main() -> None:
    provider, meter = setup_otel()

    try:
        cash_interest, fixed_rates = scrape_totalkredit()
        if not cash_interest:
            raise RuntimeError("No cash interest rows found in Totalkredit API response.")
        if not fixed_rates:
            raise RuntimeError("No fixed-rate rows found in Totalkredit API response.")

        print(format_results_line(cash_interest), flush=True)

        data = [*cash_interest, *fixed_rates]
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
