"""
Scrapes Amazon's Today's Deals page for top electronics/tech products.
Uses Selenium with the user's existing Firefox profile (which has an Amazon session).
Falls back to the Electronics Best Sellers page if the deals page yields nothing.
"""

import re
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from webdriver_manager.firefox import GeckoDriverManager

from config import get_headless

AMAZON_DEALS_URL = (
    "https://www.amazon.com/deals"
    "?deals-widget=%7B%22version%22%3A1%2C%22viewIndex%22%3A0"
    "%2C%22presetId%22%3A%22deals-collection-all-deals%22"
    "%2C%22sorting%22%3A%22BY_SCORE%22%7D"
)
AMAZON_BESTSELLERS_URL = "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics/"


def scrape_top_deals(firefox_profile: str, limit: int = 5) -> list:
    """
    Scrapes Amazon for top electronics deals or best sellers.

    Args:
        firefox_profile (str): Path to Firefox profile with an active Amazon session.
        limit (int): Maximum number of deals to return.

    Returns:
        list of dicts with keys: title, price, url
    """
    options = Options()
    if get_headless():
        options.add_argument("--headless")
    options.add_argument("-profile")
    options.add_argument(firefox_profile)

    service = Service(GeckoDriverManager().install())
    browser = webdriver.Firefox(service=service, options=options)

    try:
        # Try the deals page first
        browser.get(AMAZON_DEALS_URL)
        time.sleep(5)  # Allow JS to render deal cards
        deals = _parse_product_links(browser.page_source, limit * 3)

        if len(deals) < 2:
            # Fallback to Electronics Best Sellers
            browser.get(AMAZON_BESTSELLERS_URL)
            time.sleep(3)
            deals = _parse_product_links(browser.page_source, limit * 3)

        return deals[:limit]
    finally:
        browser.quit()


def _parse_product_links(page_source: str, limit: int) -> list:
    """
    Extracts unique product entries from Amazon page HTML.
    Looks for links pointing to /dp/<ASIN> product pages.

    Returns list of dicts: {title, price, url}
    """
    soup = BeautifulSoup(page_source, "html.parser")
    seen_asins = set()
    results = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        asin_match = re.search(r"/dp/([A-Z0-9]{10})", href)
        if not asin_match:
            continue

        asin = asin_match.group(1)
        if asin in seen_asins:
            continue
        seen_asins.add(asin)

        # Get title text — prefer the link's own text; fall back to parent block
        title = link.get_text(" ", strip=True)
        if not title or len(title) < 8:
            parent = link.parent
            title = parent.get_text(" ", strip=True)[:200] if parent else ""

        if not title or len(title) < 8:
            continue

        # Grab first dollar-amount string visible near this link
        price = ""
        price_match = re.search(r"\$[\d,]+(?:\.\d{2})?", link.get_text())
        if not price_match and link.parent:
            price_match = re.search(r"\$[\d,]+(?:\.\d{2})?", link.parent.get_text())
        if price_match:
            price = price_match.group(0)

        results.append({
            "title": title[:150].strip(),
            "price": price,
            "url": f"https://www.amazon.com/dp/{asin}",
        })

        if len(results) >= limit:
            break

    return results
