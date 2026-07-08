"""
Stage 1b of the supplier-discovery pipeline.

Reads `data/raw_suppliers.csv`, and for each supplier appends `/contact-info`
to its `b2bmap_url` and scrapes the resulting page. Writes one row per
supplier to `data/contacts.csv` with:

    name, contact_person, phone, whatsapp, address,
    zip_code, state, city, country, b2bmap_url

The parser is line-based rather than assuming a `<table>` layout — it works
whether B2BMap uses `<table>`, `<dl>`, or plain divs, as long as each label
appears near its value in the rendered text. Missing fields stay empty
rather than failing the row.

Runs before `enrich.py`. Uses only `requests` + BeautifulSoup — no browser.
"""

import csv
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

INPUT = Path("data/raw_suppliers.csv")
OUTPUT = Path("data/contacts.csv")
DELAY = 1
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

CONTACT_LABELS = {
    "contact person": "contact_person",
    "phone": "phone",
    "whatsapp": "whatsapp",
    "address": "address",
    "zip code": "zip_code",
    "state": "state",
    "city": "city",
    "country": "country",
}
FIELDS = ["name", "contact_person", "phone", "whatsapp",
          "address", "zip_code", "state", "city", "country",
          "b2bmap_url"]


def parse_contact_info(html):
    """
    Extract labelled fields from a B2BMap contact-info page.

    Works with any HTML layout — scans the rendered text line by line and
    for each known label picks either the value on the same line after
    "Label:" or the next non-empty line if the label is alone.
    """
    soup = BeautifulSoup(html, "lxml")
    lines = [ln.strip() for ln in soup.get_text("\n").splitlines() if ln.strip()]
    data = {}
    for i, line in enumerate(lines):
        low = line.lower().rstrip(":").strip()
        if low in CONTACT_LABELS and i + 1 < len(lines):
            data[CONTACT_LABELS[low]] = lines[i + 1]
            continue
        m = re.match(r"([A-Za-z ]+?)\s*:\s*(.+)", line)
        if m:
            label = m.group(1).strip().lower()
            if label in CONTACT_LABELS:
                data[CONTACT_LABELS[label]] = m.group(2).strip()
    return data


def fetch_contact_info(b2bmap_url):
    """GET <b2bmap_url>/contact-info and return the parsed fields as a dict."""
    if not b2bmap_url:
        return {}
    url = b2bmap_url.rstrip("/") + "/contact-info"
    print(f"GET {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ! {e}")
        return {}
    return parse_contact_info(r.text)


def main():
    rows = list(csv.DictReader(INPUT.open(encoding="utf-8")))
    contacts = []
    for i, row in enumerate(rows, 1):
        info = fetch_contact_info(row.get("b2bmap_url", ""))
        contact = {"name": row["name"], "b2bmap_url": row.get("b2bmap_url", "")}
        contact.update(info)
        contacts.append(contact)
        print(f"[{i}/{len(rows)}] {row['name']}: "
              f"tel={contact.get('phone', '-') or '-'} | "
              f"wa={contact.get('whatsapp', '-') or '-'}")
        time.sleep(DELAY)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(contacts)
    print(f"Saved {len(contacts)} contact rows to {OUTPUT}")


if __name__ == "__main__":
    main()
