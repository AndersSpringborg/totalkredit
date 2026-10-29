"""Totalkredit scraper package."""

from src.scraper import (
    TABLES,
    parse_cash_interest_table,
    parse_danish_number,
    parse_danish_percent,
    parse_fixed_rate_table,
    parse_table,
    scrape_totalkredit,
)

__all__ = [
    "TABLES",
    "parse_cash_interest_table",
    "parse_danish_number",
    "parse_danish_percent",
    "parse_fixed_rate_table",
    "parse_table",
    "scrape_totalkredit",
]
