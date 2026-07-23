"""
Stage 1c -- Kerix.net scraper (replaces europages_collect.py, which is
blocked by robots.txt -- see project discussion).

robots.txt for kerix.net was checked by hand and is permissive for a
generic bot: User-agent: * has a handful of narrow Disallow rules
(login, addedit, quote-request forms, captcha, cache thumbnails,
double-slash URLs, KerixEmail.asp) followed by a blanket `Allow: /`.
Company profile pages under /en/annuaire-entreprise/<slug> and
/fr/annuaire-entreprise/<slug> are NOT in the disallowed list, so they're
fair game. DO NOT scrape the paths listed in DISALLOWED_PATTERNS below --
that list is transcribed directly from the robots.txt that was checked.

Strategy: read the site's own sitemap(s) instead of guessing pagination.
The sitemap lists both individual company pages (slug, no extension) and
product/category taxonomy pages (slug ending in .html) -- we filter to
keep only the former.

*** TODO VERIFY ***
I fetched one real company page (compass-logistics-international) and
built the label-based parser below from its actual rendered text/labels
("Effectif:", "Chiffre D'affaires:", "Capital:", "Rc:", "Creation:",
"Ice:", "DIRIGEANTS", "ACTIVITES"). This is more reliable than a guess at
CSS classes, but I still only saw ONE example page -- some listings may
be laid out differently (missing fields, different section order).
Spot-check a handful of scraped rows before running the full batch.
"""
import random
import re
import time

import requests
from bs4 import BeautifulSoup

from db import connect, init_schema

BASE = "https://www.kerix.net"
SITEMAPS = [
    f"{BASE}/site_map_kerix_01.txt",
    f"{BASE}/site_map_kerix_02.txt",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}
DELAY_RANGE = (2, 3.5)

# Transcribed from the robots.txt that was manually checked -- any URL
# matching one of these should never be fetched.
DISALLOWED_SUBSTRINGS = [
    "/login", "/addedit", "/inscription", "/editCompanies/",
    "/captcha-handler", "/logos/", "/favicon.ico", "/ads.txt",
    "/app-ads.txt", "/interstitial", "/envoyer-un-devis/",
    "/media/cache/", "KerixEmail.asp",
]


def is_allowed(url):
    if "//annuaire-entreprise" in url.split(BASE, 1)[-1]:
        # matches the /fr/*//* or /en/*//* double-slash disallow pattern
        return False
    return not any(bad in url for bad in DISALLOWED_SUBSTRINGS)


def fetch_sitemap_urls():
    """Download both sitemaps and return company profile URLs only
    (filters out the *.html taxonomy/category pages)."""
    company_urls = []
    for sm_url in SITEMAPS:
        print(f"GET {sm_url}")
        r = requests.get(sm_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        for line in r.text.splitlines():
            line = line.strip()
            if not line or "/annuaire-entreprise/" not in line:
                continue
            if line.endswith(".html"):
                continue  # category/product taxonomy page, not a company
            if not is_allowed(line):
                continue
            company_urls.append(line)
        time.sleep(1)
    # dedupe while preserving order (site publishes both /en/ and
    # possibly /fr/ variants of the same company -- keep first seen)
    seen = set()
    deduped = []
    for u in company_urls:
        slug = u.rsplit("/", 1)[-1]
        if slug in seen:
            continue
        seen.add(slug)
        deduped.append(u)
    return deduped


LABELS = {
    "workforce": "employee_range",
    "turnover": "revenue_range",
    "capital": "capital",
    "trade register": "rc",
    "creation": "creation_year",
    "ice": "ice",
}


def parse_company_page(html, url):
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.select_one("h1")
    name = h1.get_text(strip=True) if h1 else ""
    if not name:
        return None

    lines = [ln.strip() for ln in soup.get_text("\n").splitlines() if ln.strip()]

    # CHANGED: confirmed via debug_kerix_page.py on a real page --
    # labels sit alone on their own line, ending in ':' (e.g.
    # "Workforce:"), with the value on the very next line. Simpler than
    # my previous two attempts, and matches what's actually there.
    data = {"employee_range": "", "revenue_range": "", "capital": "",
            "rc": "", "creation_year": "", "ice": ""}
    activities = ""
    for i, line in enumerate(lines):
        key_label = line.strip().rstrip(":").lower()
        if key_label in LABELS and i + 1 < len(lines) and not data[LABELS[key_label]]:
            data[LABELS[key_label]] = lines[i + 1]
        if key_label == "activities" and i + 1 < len(lines):
            activities = lines[i + 1]

    phones = re.findall(r"\+212[\-\s]?\d[\d\-\s]{6,}", soup.get_text(" "))
    phone = phones[0].strip() if phones else ""

    # CHANGED: the previous approach (grab any external http link on the
    # page) was picking up a shared ad/sponsor banner link that's
    # identical on every Kerix page ("Boost your visibility..."), not
    # the company's actual website. The real website (when present) sits
    # between the "Phone number" line and "COMPANY DETAILS" -- and when
    # absent, that same spot literally says "No website" (confirmed via
    # debug_kerix_page.py). Scan only that narrow window.
    website = ""
    phone_idx = next(
        (i for i, l in enumerate(lines) if l.strip().lower() == "phone number"), None
    )
    details_idx = next(
        (i for i, l in enumerate(lines) if l.strip().upper() == "COMPANY DETAILS"), None
    )
    if phone_idx is not None and details_idx is not None:
        for line in lines[phone_idx:details_idx]:
            if line.strip().lower() == "no website":
                break
            if re.match(r"^https?://", line.strip()):
                website = line.strip()
                break

    # CHANGED: confirmed via debug_kerix_page.py -- the address is
    # spread across SEVERAL separate lines (street, postal code, city,
    # a stray "-", "Morocco"), sitting between the company name repeated
    # a second time (after the breadcrumb / "Correct this card" link)
    # and the "Verified" badge line. Join them back into one string.
    # CHANGED: "Verified" is NOT always present -- confirmed on a real
    # unverified listing ("Abbou et fils") where the address goes
    # straight to "Asking for a Quote" with no badge line at all. That
    # phrase, unlike "Verified", showed up in BOTH real examples seen so
    # far, so use it as the primary end-of-address marker, with
    # Verified/Unverified as a fallback in case some page lacks both.
    location = "Morocco"
    name_positions = [i for i, l in enumerate(lines) if l == name]
    end_markers = ("asking for a quote", "verified", "unverified")
    end_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip().lower() in end_markers), None
    )
    if len(name_positions) >= 2 and end_idx is not None:
        second_name_idx = name_positions[1]
        if end_idx > second_name_idx:
            addr_lines = [
                ln for ln in lines[second_name_idx + 1:end_idx] if ln != "-"
            ]
            if addr_lines:
                location = ", ".join(addr_lines)

    return {
        "name": name,
        "category": activities,
        "location": location,
        "website": website,
        "contact": phone,
        "price_signal": "",
        "source": "kerix.net",
        "score": "",
        "external_url": url,
        "description": f"Effectif: {data['employee_range']} | "
                        f"CA: {data['revenue_range']} | "
                        f"Creation: {data['creation_year']}",
    }


def fetch_and_parse(url):
    print(f"GET {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ! {e}")
        return None
    return parse_company_page(r.text, url)


def existing_external_urls():
    """CHANGED: resume support -- return the set of external_url values
    already in the suppliers table, so scrape() can skip them instead of
    re-fetching pages we already have. One query up front instead of a
    per-URL DB check (cheap, and avoids hundreds of round-trips)."""
    init_schema()
    with connect() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT external_url FROM suppliers WHERE external_url IS NOT NULL"
            )
            return {row["external_url"] for row in cur.fetchall()}


def scrape(limit=2000, resume=True):
    """
    resume=True (default, CHANGED): skip company URLs already in the DB
    (matched on external_url) before applying `limit`, so `limit` means
    "up to N NEW suppliers" rather than "the first N URLs in the sitemap
    regardless of what's already scraped". This avoids re-fetching
    hundreds of already-known pages on every re-run -- the real cost
    here, since collect.py's B2BMap requests are a small fixed number
    (~25 listing pages) but this fetches one page PER company.
    Pass resume=False to force re-fetching everything (e.g. after fixing
    a parsing bug you want to re-apply to already-scraped rows -- combine
    with delete_by_source.py kerix.net first in that case).
    """
    urls = fetch_sitemap_urls()
    if resume:
        known = existing_external_urls()
        before = len(urls)
        urls = [u for u in urls if u not in known]
        print(f"{before} company URLs in sitemaps, {len(urls)} new "
              f"(skipping {before - len(urls)} already in DB)")
    else:
        print(f"{len(urls)} company URLs found in sitemaps (full re-run)")

    print(f"Taking up to {limit}")
    rows = []
    for url in urls[:limit]:
        row = fetch_and_parse(url)
        if row:
            rows.append(row)
        time.sleep(random.uniform(*DELAY_RANGE))
    return rows


def save(rows):
    init_schema()
    inserted = 0
    with connect() as c:
        with c.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO suppliers
                        (name, category, location, website, contact,
                         price_signal, source, score, external_url, description)
                    VALUES
                        (%(name)s, %(category)s, %(location)s, %(website)s,
                         %(contact)s, %(price_signal)s, %(source)s, %(score)s,
                         %(external_url)s, %(description)s)
                    ON CONFLICT (external_url) DO NOTHING
                    """,
                    row,
                )
                inserted += cur.rowcount
        c.commit()
    print(f"Inserted {inserted}/{len(rows)} suppliers into DB (dupes skipped)")


if __name__ == "__main__":
    # CHANGED: was limit=20 (initial spot-check phase, now validated).
    # Raise further toward 2000+ once satisfied with data quality.
    save(scrape(limit=2000))
