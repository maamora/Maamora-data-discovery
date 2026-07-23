import time

import requests
from bs4 import BeautifulSoup

from db import connect, init_schema

BASE = "https://b2bmap.com"
GENERAL_URL = f"{BASE}/morocco/companies"

# CHANGED: the general listing only has 3 pages (~60 suppliers total) --
# verified by hand on b2bmap.com. To get meaningfully more than that we
# also have to walk the 22 category pages. Some overlap with the general
# list and with each other is expected and handled by the DB's
# ON CONFLICT (b2bmap_url) DO NOTHING, so re-scraping the same company
# twice is harmless, just wasted requests.
CATEGORY_SLUGS = [
    "agro-agriculture-product-suppliers",
    "apparel-fashion-product-suppliers",
    "arts-crafts-gifts-product-suppliers",
    "automotive-automobile-product-suppliers",
    "chemicals-product-suppliers",
    "computer-it-product-suppliers",
    "construction-real-estate-product-suppliers",
    "electronics-electrical-product-suppliers",
    "energy-power-product-suppliers",
    "food-beverage-product-suppliers",
    "furniture-decor-product-suppliers",
    "health-medical-product-suppliers",
    "home-appliances-product-suppliers",
    "lights-lighting-product-suppliers",
    "machinery-industrial-product-suppliers",
    "minerals-raw-materials-product-suppliers",
    "office-product-suppliers",
    "paper-printing-packaging-product-suppliers",
    "rubber-plastic-product-suppliers",
    "security-protection-product-suppliers",
    "sports-entertainment-product-suppliers",
    "textiles-leather-jute-product-suppliers",
    "tools-hardware-product-suppliers",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
DELAY = 2
FIELDS = ["name", "category", "location", "website", "contact",
          "price_signal", "source", "score", "b2bmap_url", "description"]


def fetch(url):
    print(f"GET {url}")
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.text


def parse_general(html, fallback_category=""):
    """Parser for the /morocco/companies style listing (original page)."""
    soup = BeautifulSoup(html, "lxml")
    for card in soup.select("li.member-item"):
        name = card.select_one("a.directory-link span")
        if not name:
            continue
        link = card.select_one("a.directory-link")
        href = link.get("href", "") if link else ""
        if href and href.startswith("/"):
            href = f"{BASE}{href}"
        category = fallback_category
        if not category:
            for div in card.select("div.mb-1"):
                if "Business Category" in div.get_text():
                    a = div.select_one("a")
                    category = a.get_text(strip=True) if a else ""
                    break
        loc = card.select_one("div.mb-1.text-muted")
        desc = card.select_one("p") or card.select_one("div.description")
        yield {
            "name": name.get_text(strip=True),
            "category": category,
            "location": loc.get_text(strip=True) if loc else "Morocco",
            "website": "",
            "contact": "",
            "price_signal": "",
            "source": "b2bmap.com",
            "score": "",
            "b2bmap_url": href,
            "description": desc.get_text(strip=True) if desc else "",
        }


# CHANGED: backward-compat alias -- the original function here was named
# `parse` (imported directly as `from collect import parse` by
# tests/test_collect.py). It was renamed to parse_general to distinguish
# it from the new parse_category(), but the test suite still expects the
# name `parse` to exist, so keep this alias rather than breaking it.
parse = parse_general


def parse_category(html, category_name):
    """
    Parser for the per-category listing pages
    (e.g. /morocco/agro-agriculture-product-suppliers). Uses the same
    `li.member-item` container as the general listing — verified July 2026:
    16/23 categories return non-zero rows with these selectors.

    The remaining 7 categories (automotive, chemicals, electronics,
    home-appliances, minerals, paper-printing-packaging, tools-hardware)
    return HTTP 200 with the full site chrome but ZERO card markup — same
    ~37KB rendered size, same 8 script tags as the OK pages. They are
    genuinely empty on B2BMap for Morocco, not a selector bug.
    """
    soup = BeautifulSoup(html, "lxml")
    cards = (soup.select("li.member-item")
             or soup.select("div.company-card")
             or soup.select("article"))
    if not cards:
        # Category is known-empty on B2BMap Morocco (see docstring). One line,
        # not scary — it's an expected outcome for ~30% of the categories.
        print(f"  (empty) {category_name}: 0 suppliers listed")
        return
    for card in cards:
        link = card.select_one("h3 a") or card.select_one("a.directory-link")
        if not link:
            continue
        href = link.get("href", "")
        if href and href.startswith("/"):
            href = f"{BASE}{href}"
        loc = card.select_one("div.mb-1.text-muted") or card.select_one("span.location")
        desc = card.select_one("p")
        yield {
            "name": link.get_text(strip=True),
            "category": category_name,
            "location": loc.get_text(strip=True) if loc else "Morocco",
            "website": "",
            "contact": "",
            "price_signal": "",
            "source": "b2bmap.com",
            "score": "",
            "b2bmap_url": href,
            "description": desc.get_text(strip=True) if desc else "",
        }


def scrape_general(pages=3):
    rows = []
    for p in range(1, pages + 1):
        url = GENERAL_URL if p == 1 else f"{GENERAL_URL}?page={p}"
        rows.extend(parse_general(fetch(url)))
        time.sleep(DELAY)
    return rows


def scrape_categories():
    rows = []
    for slug in CATEGORY_SLUGS:
        category_name = slug.replace("-product-suppliers", "").replace("-", " ").title()
        url = f"{BASE}/morocco/{slug}"
        try:
            html = fetch(url)
        except requests.RequestException as e:
            print(f"  ! {url}: {e}")
            time.sleep(DELAY)
            continue
        rows.extend(parse_category(html, category_name))
        time.sleep(DELAY)
        # NOTE: category pages showed no pagination in manual testing (only
        # ~3 companies, no page 2 link). If a category turns out to have
        # more, add pagination handling here similar to scrape_general().
    return rows


def scrape(pages=3, include_categories=True):
    rows = scrape_general(pages=pages)
    if include_categories:
        rows.extend(scrape_categories())
    return rows


def save(rows):
    """Insert scraped rows into the suppliers table (idempotent on b2bmap_url)."""
    init_schema()
    inserted = 0
    with connect() as c:
        with c.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO suppliers
                        (name, category, location, website, contact,
                         price_signal, source, score, b2bmap_url, description)
                    VALUES
                        (%(name)s, %(category)s, %(location)s, %(website)s,
                         %(contact)s, %(price_signal)s, %(source)s, %(score)s,
                         %(b2bmap_url)s, %(description)s)
                    ON CONFLICT (b2bmap_url) DO NOTHING
                    """,
                    row,
                )
                inserted += cur.rowcount
        c.commit()
    print(f"Inserted {inserted}/{len(rows)} suppliers into DB (dupes skipped)")


if __name__ == "__main__":
    save(scrape(pages=3, include_categories=True))
