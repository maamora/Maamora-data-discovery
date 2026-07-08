import re
import time
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

from db import connect, init_schema

DELAY = 3
MAPS_URL = "https://www.google.com/maps/search/{q}?hl=en"


def open_place(page, name, location):
    """Navigate to the Google Maps place-details panel for the top result."""
    query = quote_plus(f"{name} {location}")
    page.goto(MAPS_URL.format(q=query), timeout=30000)
    try:
        page.wait_for_selector('div[role="feed"], div[role="main"]', timeout=10000)
    except Exception:
        return False
    first = page.query_selector('div[role="feed"] a.hfpxzc')
    if first:
        first.click()
        try:
            page.wait_for_selector(
                'button[data-item-id="phone:tel:"], a[data-item-id="authority"], div.F7nice',
                timeout=8000,
            )
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
    init_schema()
    with connect() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT id, name, location, website, contact FROM suppliers ORDER BY id"
            )
            rows = cur.fetchall()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            for i, row in enumerate(rows, 1):
                rating = website = phone = ""
                if open_place(page, row["name"], row["location"]):
                    rating, website, phone = extract(page)

                updates = {}
                if rating:
                    updates["score"] = rating
                if website and not row["website"]:
                    updates["website"] = website
                if phone and not row["contact"]:
                    updates["contact"] = phone

                if updates:
                    sets = ", ".join(f"{k} = %({k})s" for k in updates)
                    params = {**updates, "id": row["id"]}
                    with c.cursor() as cur:
                        cur.execute(
                            f"UPDATE suppliers SET {sets} WHERE id = %(id)s",
                            params,
                        )
                    c.commit()

                print(f"[{i}/{len(rows)}] {row['name']}: "
                      f"score={updates.get('score') or row.get('score') or '-'} | "
                      f"web={updates.get('website') or row['website'] or '-'} | "
                      f"tel={updates.get('contact') or row['contact'] or '-'}")
                time.sleep(DELAY)
            browser.close()
    print(f"Enriched {len(rows)} suppliers")


if __name__ == "__main__":
    main()
