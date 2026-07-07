"""
Stage 2 of the supplier-discovery pipeline.

Reads `data/raw_suppliers.csv`, and for each supplier searches Google Maps for
`"{name} {location}"` in headless Chromium (Playwright). If a matching place
panel opens, it back-fills:
    score    <- star rating (as a string, e.g. "4.5")
    website  <- link on the panel (only if empty)
    contact  <- phone number (only if empty)

Writes `data/enriched_suppliers.csv` with the same schema — no new columns.
Rows that Maps can't resolve are kept as-is (empty fields, not dropped).
A 3-second sleep between lookups keeps the request rate polite.

Setup once:
    pip install -r requirements.txt
    python -m playwright install chromium

Note: Google Maps' DOM changes often. If a whole run comes back empty, the
selectors in `extract()` — `div.F7nice`, `a[data-item-id="authority"]`,
`button[data-item-id^="phone:tel:"]` — are the first thing to check.
"""

import csv
import re
import time
from pathlib import Path
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

INPUT = Path("data/raw_suppliers.csv")
OUTPUT = Path("data/enriched_suppliers.csv")
DELAY = 3
MAPS_URL = "https://www.google.com/maps/search/{q}?hl=en"


def open_place(page, name, location):
    """Navigate to the place-details panel for the top result."""
    query = quote_plus(f"{name} {location}")
    page.goto(MAPS_URL.format(q=query), timeout=30000)
    try:
        page.wait_for_selector('div[role="feed"], div[role="main"]', timeout=10000)
    except Exception:
        return False

    # If a list of results came back, click the first card to open its panel.
    first = page.query_selector('div[role="feed"] a.hfpxzc')
    if first:
        first.click()
        try:
            page.wait_for_selector('button[data-item-id="phone:tel:"], a[data-item-id="authority"], div.F7nice', timeout=8000)
        except Exception:
            pass
    return True


def extract(page):
    rating = website = phone = ""

    node = page.query_selector('div.F7nice')
    if node:
        m = re.search(r"([\d.,]+)", node.inner_text() or "")
        if m:
            rating = m.group(1).replace(",", ".")

    site = page.query_selector('a[data-item-id="authority"]')
    if site:
        website = site.get_attribute("href") or ""

    tel = page.query_selector('button[data-item-id^="phone:tel:"]')
    if tel:
        item_id = tel.get_attribute("data-item-id") or ""
        phone = item_id.replace("phone:tel:", "").strip()

    return rating, website, phone


def main():
    rows = list(csv.DictReader(INPUT.open(encoding="utf-8")))
    fields = list(rows[0].keys())

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for i, row in enumerate(rows, 1):
            rating = website = phone = ""
            if open_place(page, row["name"], row["location"]):
                rating, website, phone = extract(page)
            if rating:
                row["score"] = rating
            if website and not row.get("website"):
                row["website"] = website
            if phone and not row.get("contact"):
                row["contact"] = phone
            print(f"[{i}/{len(rows)}] {row['name']}: "
                  f"score={row['score'] or '-'} | "
                  f"{row['website'] or '-'} | {row['contact'] or '-'}")
            time.sleep(DELAY)
        browser.close()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {len(rows)} enriched suppliers to {OUTPUT}")


if __name__ == "__main__":
    main()
