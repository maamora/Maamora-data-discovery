import random
import re
import time
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

from db import connect, init_schema

DELAY_RANGE = (2.5, 4.5)  # randomized instead of a fixed 3s.
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
    # CHANGED: review_count extraction removed. Confirmed via
    # debug_maps_place_v3.py on multiple real listings (including
    # Marjane, which certainly has thousands of reviews) that the count
    # is genuinely not present in div.F7nice, its ancestors, or the
    # visible/aria-label text of the open place panel at this stage of
    # the page load. Not a regex bug -- the data isn't there to extract.
    # score/website/contact are unaffected and continue to work.
    rating = website = phone = ""
    node = page.query_selector('div.F7nice')
    if node:
        text = node.inner_text() or ""
        m = re.search(r"([\d.,]+)", text)
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


def main(resume=True):
    """
    resume=True (default): only process suppliers that don't already
    have a score. This is the fix for "re-scrapes everything on every
    run" -- at hundreds of Google Maps lookups, a CAPTCHA partway
    through used to mean losing all progress on the next run.
    CHANGED: dropped the "OR review_count IS NULL" condition that used
    to be here -- since review_count is never populated anymore, that
    condition was always true, silently forcing a full re-run every
    single time regardless of what score already had. Pass resume=False
    to force a full re-run on purpose.
    """
    init_schema()
    with connect() as c:
        with c.cursor() as cur:
            if resume:
                cur.execute(
                    """
                    SELECT id, name, location, website, contact FROM suppliers
                    WHERE score IS NULL OR score = ''
                    ORDER BY id
                    """
                )
            else:
                cur.execute(
                    "SELECT id, name, location, website, contact FROM suppliers ORDER BY id"
                )
            rows = cur.fetchall()

        print(f"{len(rows)} suppliers to enrich "
              f"({'resume mode' if resume else 'full re-run'})")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            for i, row in enumerate(rows, 1):
                rating = website = phone = ""
                try:
                    if open_place(page, row["name"], row["location"]):
                        rating, website, phone = extract(page)
                except Exception as e:
                    # don't let one bad lookup (timeout, CAPTCHA
                    # redirect, detached frame, ...) kill the whole run --
                    # log it and move on. Combined with resume=True this
                    # row will simply be retried on the next invocation.
                    print(f"  ! {row['name']}: {e}")

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
                time.sleep(random.uniform(*DELAY_RANGE))
            browser.close()
    print(f"Enriched {len(rows)} suppliers")


if __name__ == "__main__":
    main()
