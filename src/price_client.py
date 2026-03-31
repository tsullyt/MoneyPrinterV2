"""
Price tracking client with provider abstraction.

Current provider: camelcamelcamel (CCC) — free web scraping, no API key.
Future provider:  amazon_pa_api — Amazon Product Advertising API (requires
                  Associates account). Switch by setting config key:
                  "price_provider": "amazon_pa_api"

Public interface (stable across providers):
    extract_asin(url)           -> str | None
    fetch_price_data(asin)      -> dict | None
    format_price_context(data)  -> str
    get_price_status()          -> str
"""

import re
import time
import json
import requests
from datetime import date

from bs4 import BeautifulSoup

from config import get_price_tracker_enabled, get_price_provider, get_price_tracker_amazon_pa_creds
from cache import get_price_cache_path


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def extract_asin(url: str) -> str | None:
    """
    Extracts the Amazon ASIN from a product URL.

    Args:
        url (str): A resolved Amazon product URL (e.g. from browser.current_url)

    Returns:
        asin (str | None): The 10-character ASIN, or None if not found
    """
    match = re.search(r'/dp/([A-Z0-9]{10})', url)
    if match:
        return match.group(1)
    return None


def _parse_price_text(text: str) -> float | None:
    """Converts a price string like '$49.99' or '49.99' to a float."""
    if not text:
        return None
    cleaned = text.replace(',', '').strip()
    match = re.search(r'[\d]+\.?\d*', cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Local cache helpers (shared across providers)
# ---------------------------------------------------------------------------

def _load_cache() -> dict:
    try:
        with open(get_price_cache_path(), 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"asins": {}}


def _save_cache(data: dict) -> None:
    with open(get_price_cache_path(), 'w') as f:
        json.dump(data, f, indent=4)


def _get_cached(asin: str) -> dict | None:
    """Returns cached price data if still fresh (< 24h), else None."""
    cache = _load_cache()
    entry = cache.get("asins", {}).get(asin)
    if entry and (time.time() - entry.get("cached_at", 0)) < 86400:
        return entry.get("price_data")
    return None


def _store_cached(asin: str, price_data: dict) -> None:
    cache = _load_cache()
    cache.setdefault("asins", {})[asin] = {
        "cached_at": time.time(),
        "price_data": price_data,
    }
    _save_cache(cache)


# ---------------------------------------------------------------------------
# Provider: CamelCamelCamel
# ---------------------------------------------------------------------------

def _fetch_from_ccc(asin: str) -> dict | None:
    """
    Scrapes camelcamelcamel.com for price history on an ASIN.
    Returns a normalised price_data dict, or None on failure.
    """
    url = f"https://camelcamelcamel.com/product/{asin}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
            "Gecko/20100101 Firefox/125.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://camelcamelcamel.com/",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return _parse_ccc_page(response.text, asin)
    except Exception as e:
        print(f"[price_client/ccc] Warning: could not fetch price data for {asin}: {e}")
        return None


def _parse_ccc_page(html: str, asin: str) -> dict | None:
    """
    Parses the CCC product page HTML and extracts Amazon price stats.

    CCC renders a price table with rows per seller type (Amazon, New, Used).
    Each row has columns: Current | Highest | Lowest | Average
    We target the "Amazon" row (sold & fulfilled by Amazon).
    """
    soup = BeautifulSoup(html, "html.parser")

    # CCC uses a table with class "product-price-list" (or similar).
    # Row headers identify the price type: "Amazon", "New", "Used".
    price_data = {}

    # Strategy 1: find table rows where the header text is "Amazon"
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        row_label = cells[0].get_text(strip=True).lower()
        if "amazon" not in row_label:
            continue

        # Columns after the label: Current, Highest, Lowest, [Average]
        values = [_parse_price_text(c.get_text(strip=True)) for c in cells[1:]]
        # Map to known positions if we got at least 3 values
        if len(values) >= 3:
            price_data = {
                "current_price": values[0],
                "high_all": values[1],
                "low_all": values[2],
                "avg": values[3] if len(values) > 3 else None,
                "source": "ccc",
            }
            break

    # Strategy 2: fallback — look for any element with a data-asin or
    # meta og:price if the table structure didn't match
    if not price_data:
        og_price = soup.find("meta", property="og:price:amount")
        if og_price and og_price.get("content"):
            current = _parse_price_text(og_price["content"])
            if current:
                price_data = {
                    "current_price": current,
                    "high_all": None,
                    "low_all": None,
                    "avg": None,
                    "source": "ccc_meta",
                }

    return price_data if price_data else None


# ---------------------------------------------------------------------------
# Provider: Amazon Product Advertising API (stub — implement when available)
# ---------------------------------------------------------------------------

def _fetch_from_amazon_pa(asin: str) -> dict | None:
    """
    Placeholder for Amazon Product Advertising API integration.

    To activate: set "price_provider": "amazon_pa_api" in config.json and
    populate "amazon_pa_api_key", "amazon_pa_secret_key", "amazon_pa_associate_tag".

    The PA API v5 endpoint for GetItems returns:
      - Offers.Listings[].Price.Amount (current price)
      - No built-in price history — pair with your own price log for trends.

    See: https://webservices.amazon.com/paapi5/documentation/
    """
    creds = get_price_tracker_amazon_pa_creds()
    if not creds.get("api_key") or not creds.get("secret_key"):
        print("[price_client/amazon_pa] API credentials not configured.")
        return None

    # TODO: implement PA API v5 signed request (AWS SigV4) once credentials
    # are available. The paapi5-python-sdk package simplifies this.
    print("[price_client/amazon_pa] Amazon PA API integration is not yet implemented.")
    return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def fetch_price_data(asin: str) -> dict | None:
    """
    Fetches price data for an ASIN using the configured provider.
    Results are cached locally for 24 hours.

    Args:
        asin (str): The Amazon ASIN

    Returns:
        price_data (dict | None): Normalised price dict, or None if unavailable
    """
    if not get_price_tracker_enabled():
        return None

    cached = _get_cached(asin)
    if cached is not None:
        return cached

    provider = get_price_provider()
    if provider == "camelcamelcamel":
        data = _fetch_from_ccc(asin)
    elif provider == "amazon_pa_api":
        data = _fetch_from_amazon_pa(asin)
    else:
        print(f"[price_client] Unknown price provider: {provider}")
        data = None

    if data:
        _store_cached(asin, data)

    return data


def format_price_context(price_data: dict | None) -> str:
    """
    Formats price data into a human-readable string for Ollama prompt injection.

    Args:
        price_data (dict | None): Output from fetch_price_data()

    Returns:
        context (str): Compact price summary, or "" if no data
    """
    if not price_data:
        return ""

    current = price_data.get("current_price")
    if current is None:
        return ""

    parts = [f"Current price: ${current:.2f}."]

    low_all = price_data.get("low_all")
    high_all = price_data.get("high_all")

    if low_all is not None and high_all is not None:
        parts.append(f"All-time low: ${low_all:.2f}, all-time high: ${high_all:.2f}.")
        if current <= low_all * 1.05:
            trend = "near all-time low — great time to buy"
        elif current >= high_all * 0.95:
            trend = "near all-time high"
        else:
            trend = "mid-range historically"
        parts.append(f"Price trend: {trend}.")

    avg = price_data.get("avg")
    if avg is not None:
        parts.append(f"Average: ${avg:.2f}.")

    return " ".join(parts)


def get_price_status() -> str:
    """
    Returns a human-readable status string for display in the menu.

    Returns:
        status (str): e.g. "Price tracker: camelcamelcamel | 3 ASINs cached"
    """
    provider = get_price_provider()
    try:
        cache = _load_cache()
        count = len(cache.get("asins", {}))
    except Exception:
        count = 0
    return f"Price tracker: {provider} | {count} ASIN(s) cached"
