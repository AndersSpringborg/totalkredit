"""Totalkredit scraper package."""

from src.scraper import (
    parse_cash_interest_table,
    parse_danish_number,
    parse_danish_percent,
    parse_fixed_rate_table,
    scrape_totalkredit,
)

__all__ = [
    "parse_cash_interest_table",
    "parse_danish_number",
    "parse_danish_percent",
    "parse_fixed_rate_table",
    "scrape_totalkredit",
]
