import json
import os
from dataclasses import dataclass
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
DOMAIN = os.getenv("DOMAIN", "totalkredit")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")


@dataclass(frozen=True)
class TableConfig:
    section_key: str
    table_id: str
    metric_prefix: str


TABLES: dict[str, TableConfig] = {
    "fixed_rate_payout": TableConfig(
        section_key="fixed_rate_payout",
        table_id=os.getenv(
            "FIXED_RATE_TABLE_ID", "privat-udbetaling-af-laan-aktuelle-kurser-kunder"
        ),
        metric_prefix="fixed_rate",
    ),
    "variable_rate_payout": TableConfig(
        section_key="variable_rate_payout",
        table_id=os.getenv(
            "VARIABLE_RATE_TABLE_ID", "privat-udbetaling-af-variabel-laan-aktuelle-kurser-kunder"
        ),
        metric_prefix="variable_rate",
    ),
    "cash_interest_payout": TableConfig(
        section_key="cash_interest_payout",
        table_id=os.getenv(
            "CASH_INTEREST_TABLE_ID", "privat-udbetaling-af-laan-kontantrenter-raadgivere-og-kunder"
        ),
        metric_prefix="cash_interest",
    ),
    "redemption": TableConfig(
        section_key="redemption",
        table_id=os.getenv(
            "REDEMPTION_TABLE_ID", "indfrielse-af-laan-aktuelle-kurser-og-terminstillaeg-kunder"
        ),
        metric_prefix="redemption",
    ),
}

NUMERIC_FIELDS: dict[str, tuple[str, str, str]] = {
    "cash_interest_percent": (
        "totalkredit_cash_interest_percent",
        "Kontantrente for Totalkredit Tilpasningslån",
        "%",
    ),
    "offer_price": ("totalkredit_offer_price", "Tilbudskurs for Totalkredit-lån", "1"),
    "current_price": ("totalkredit_current_price", "Aktuel kurs for Totalkredit-lån", "1"),
    "effective_rate_percent": (
        "totalkredit_effective_rate_percent",
        "Effektiv rente for Totalkredit-lån",
        "%",
    ),
    "interest_margin_percent": ("totalkredit_interest_margin_percent", "Rentetillæg", "%"),
    "calculation_rate_percent": (
        "totalkredit_calculation_rate_percent",
        "Dagens beregningsrente",
        "%",
    ),
    "redemption_rate": (
        "totalkredit_redemption_rate",
        "Kurs ved opsigelse til termin",
        "1",
    ),
}


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


def _add_number(row: dict[str, Any], field_name: str, value: str | None) -> None:
    parsed = parse_danish_number(value)
    if parsed is not None:
        row[field_name] = parsed


def parse_table(payload: dict[str, Any], table: TableConfig) -> list[dict[str, Any]]:
    """Parse any Totalkredit bond-information API table into normalized rows."""
    timestamp = datetime.now(timezone.utc).isoformat()
    last_updated = payload.get("lastUpdatedTimestamp")
    next_update = payload.get("nextUpdateTimestamp")
    title = payload.get("title") or table.section_key

    parsed_data: list[dict[str, Any]] = []
    for group in payload.get("groups", []):
        group_name = (group.get("name") or "").strip()
        for entry in group.get("entries", []):
            loan_type = entry.get("name")
            if not loan_type:
                continue

            row: dict[str, Any] = {
                "timestamp": timestamp,
                "last_updated": last_updated,
                "next_update": next_update,
                "section_key": table.section_key,
                "section_title": title,
                "rate_type": table.section_key,
                "group": group_name,
                "loan_type": loan_type,
                "is_open_for_offer": entry.get("isOpenForOffer"),
            }

            if entry.get("lifetime"):
                row["lifetime"] = entry.get("lifetime")
            if entry.get("fondCode"):
                row["fond_code"] = entry.get("fondCode")
            if entry.get("openForOffer"):
                row["status"] = entry.get("openForOffer")
            if entry.get("green"):
                row["green"] = entry.get("green")
            if entry.get("isGreen") is not None:
                row["is_green"] = entry.get("isGreen")
            if entry.get("nasdaqUrl"):
                row["nasdaq_url"] = entry.get("nasdaqUrl")

            _add_number(row, "cash_interest_percent", entry.get("innerInterestGrossValue"))
            _add_number(row, "offer_price", entry.get("priceRate"))
            _add_number(row, "current_price", entry.get("spotPriceRatePayment"))
            _add_number(row, "current_price", entry.get("spotPriceRateRedemption"))
            _add_number(row, "effective_rate_percent", entry.get("effectiveRate"))
            _add_number(row, "interest_margin_percent", entry.get("interestMarginRate"))
            _add_number(row, "calculation_rate_percent", entry.get("expectedRate"))
            _add_number(row, "redemption_rate", entry.get("redemptionRate"))

            if any(field in row for field in NUMERIC_FIELDS):
                parsed_data.append(row)

    return parsed_data


def parse_cash_interest_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Totalkredit Tilpasningslån cash interest rows."""
    return parse_table(payload, TABLES["cash_interest_payout"])


def parse_fixed_rate_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Totalkredit fixed-rate loan price/rate rows."""
    return parse_table(payload, TABLES["fixed_rate_payout"])


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


def scrape_totalkredit() -> dict[str, list[dict[str, Any]]]:
    """Scrape every Totalkredit table shown on the kurs-og-priser page."""
    sections: dict[str, list[dict[str, Any]]] = {}
    for table in TABLES.values():
        sections[table.section_key] = parse_table(fetch_table(table.table_id), table)
    return sections


def save_prices(data: list[dict[str, Any]], data_dir: Path = DATA_DIR) -> Path:
    """Append scraped rows to a JSONL file and return its path."""
    data_dir.mkdir(parents=True, exist_ok=True)
    file_path = data_dir / "totalkredit_rates.jsonl"

    with file_path.open("a", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return file_path


def format_results_line(data: list[dict[str, Any]]) -> str:
    """Format a compact log line with section counts and freshness."""
    counts: dict[str, int] = {}
    freshness: dict[str, Any] = {}
    for item in data:
        section_key = str(item["section_key"])
        counts[section_key] = counts.get(section_key, 0) + 1
        freshness.setdefault(section_key, item.get("last_updated"))

    sections = " | ".join(
        f"{section_key}={counts[section_key]} rows updated={freshness.get(section_key)}"
        for section_key in sorted(counts)
    )
    return f"Totalkredit scrape | {sections}"


def publish_metrics(meter, data: list[dict[str, Any]]) -> None:
    """Publish scraped Totalkredit data as OpenTelemetry gauge values."""
    gauges = {
        field: meter.create_gauge(name=name, description=description, unit=unit)
        for field, (name, description, unit) in NUMERIC_FIELDS.items()
    }

    # Backwards-compatible metric names used by the original dashboard.
    legacy_cash_interest_gauge = meter.create_gauge(
        name="totalkredit_legacy_cash_interest_percent",
        description="Deprecated alias for totalkredit_cash_interest_percent",
        unit="%",
    )
    legacy_fixed_offer_price_gauge = meter.create_gauge(
        name="totalkredit_fixed_rate_offer_price",
        description="Tilbudskurs for Totalkredit fastforrentede lån",
        unit="1",
    )
    legacy_fixed_current_price_gauge = meter.create_gauge(
        name="totalkredit_fixed_rate_current_price",
        description="Aktuel kurs for Totalkredit fastforrentede lån",
        unit="1",
    )
    legacy_fixed_effective_rate_gauge = meter.create_gauge(
        name="totalkredit_fixed_rate_effective_percent",
        description="Effektiv rente for Totalkredit fastforrentede lån",
        unit="%",
    )

    for item in data:
        attributes = {
            "section_key": str(item.get("section_key", "")),
            "section_title": str(item.get("section_title", "")),
            "group": str(item.get("group", "")),
            "lifetime": str(item.get("lifetime", "")),
            "loan_type": str(item.get("loan_type", "")),
            "fond_code": str(item.get("fond_code", "")),
            "status": str(item.get("status", "")),
            "green": str(item.get("green", "")),
        }

        for field, gauge in gauges.items():
            if item.get(field) is not None:
                gauge.set(float(item[field]), attributes)

        if item.get("section_key") == "cash_interest_payout" and item.get("cash_interest_percent") is not None:
            legacy_cash_interest_gauge.set(float(item["cash_interest_percent"]), attributes)
        if item.get("section_key") == "fixed_rate_payout":
            if item.get("offer_price") is not None:
                legacy_fixed_offer_price_gauge.set(float(item["offer_price"]), attributes)
            if item.get("current_price") is not None:
                legacy_fixed_current_price_gauge.set(float(item["current_price"]), attributes)
            if item.get("effective_rate_percent") is not None:
                legacy_fixed_effective_rate_gauge.set(float(item["effective_rate_percent"]), attributes)


def main() -> None:
    provider, meter = setup_otel()

    try:
        sections = scrape_totalkredit()
        empty_sections = [section for section, rows in sections.items() if not rows]
        if empty_sections:
            raise RuntimeError(f"No rows found in Totalkredit API response for: {', '.join(empty_sections)}")

        data = [row for rows in sections.values() for row in rows]
        print(format_results_line(data), flush=True)

        file_path = save_prices(data)
        print(f"Saved {len(data)} records to {file_path}")

        if provider:
            publish_metrics(meter, data)
            print(f"Published {len(data)} rows of metrics to OTel endpoint: {OTEL_ENDPOINT}")
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
