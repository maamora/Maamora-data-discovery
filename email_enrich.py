"""
Stage: email_enrich -- fills contacts.email by visiting each supplier's
own website (suppliers.website), for suppliers that don't already have
an email (from any source: B2BMap's /contact-info, or Kerix which
doesn't expose email at all).

Scope, deliberately kept light:
  - Only the homepage + a small set of common contact-page paths
    (/contact, /contact-us, /contactez-nous, /mentions-legales,
    /about, /a-propos). NOT a real crawl.
  - We can't check robots.txt for every individual company site
    up front (unlike b2bmap.com/kerix.net, which were checked once).
    Staying shallow (homepage + a couple of obvious contact pages) is
    the same scope a human would check manually, and stops at the
    first email found rather than harvesting everything on the site.
  - Timeouts and errors on any one site are caught and logged; a bad
    site never stops the run.

Usage:
    python email_enrich.py
"""
import random
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from db import connect, init_schema

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}
DELAY_RANGE = (1.5, 3)
TIMEOUT = 8
CONTACT_PATHS = [
    "", "contact", "contact-us", "contactez-nous", "mentions-legales",
    "about", "a-propos",
]
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Skip obviously-generic placeholder addresses (image hosts, tracking
# pixels, etc. sometimes get matched from JS/CSS by accident)
JUNK_DOMAINS = ("example.com", "sentry.io", "wixpress.com", "godaddy.com")


def extract_email(html):
    soup = BeautifulSoup(html, "lxml")

    mailto = soup.select_one('a[href^="mailto:"]')
    if mailto:
        email = mailto.get("href", "").replace("mailto:", "").split("?")[0].strip()
        if email and not email.lower().endswith(JUNK_DOMAINS):
            return email

    text = soup.get_text(" ")
    for match in EMAIL_RE.findall(text):
        if not match.lower().endswith(JUNK_DOMAINS):
            return match

    return None


def find_email_on_site(base_url):
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    root = f"{parsed.scheme}://{parsed.netloc}"

    for path in CONTACT_PATHS:
        url = urljoin(root + "/", path)
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            email = extract_email(r.text)
            if email:
                return email
        except requests.RequestException:
            continue
        time.sleep(random.uniform(*DELAY_RANGE))
    return None


def main(resume=True):
    """
    resume=True (default): only process suppliers with a website but no
    email yet. Safe to re-run -- won't redo suppliers already resolved.
    """
    init_schema()
    with connect() as c:
        with c.cursor() as cur:
            if resume:
                cur.execute(
                    """
                    SELECT s.id, s.name, s.website FROM suppliers s
                    LEFT JOIN contacts c ON c.supplier_id = s.id
                    WHERE s.website IS NOT NULL AND s.website <> ''
                      AND (c.email IS NULL OR c.email = '')
                    ORDER BY s.id
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT id, name, website FROM suppliers
                    WHERE website IS NOT NULL AND website <> ''
                    ORDER BY id
                    """
                )
            rows = cur.fetchall()

        print(f"{len(rows)} suppliers with a website to check for email "
              f"({'resume mode' if resume else 'full re-run'})")

        found = 0
        for i, row in enumerate(rows, 1):
            email = None
            try:
                email = find_email_on_site(row["website"])
            except Exception as e:
                print(f"  ! {row['name']}: {e}")

            if email:
                found += 1
                with c.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO contacts (supplier_id, email)
                        VALUES (%s, %s)
                        ON CONFLICT (supplier_id) DO UPDATE SET
                            email = COALESCE(contacts.email, EXCLUDED.email)
                        """,
                        (row["id"], email),
                    )
                c.commit()

            print(f"[{i}/{len(rows)}] {row['name']}: email={email or '-'}")

    print(f"Found emails for {found}/{len(rows)} suppliers checked")


if __name__ == "__main__":
    main()
