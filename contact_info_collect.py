import re
import time

import requests
from bs4 import BeautifulSoup

from db import connect, init_schema

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
COLS = ["contact_person", "phone", "whatsapp", "address",
        "zip_code", "state", "city", "country"]


def parse_contact_info(html):
    """Extract labelled fields from a B2BMap contact-info page (layout-agnostic)."""
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
    init_schema()
    with connect() as c:
        with c.cursor() as cur:
            cur.execute("SELECT id, name, b2bmap_url FROM suppliers ORDER BY id")
            suppliers = cur.fetchall()

        for i, s in enumerate(suppliers, 1):
            info = fetch_contact_info(s["b2bmap_url"])
            params = {"supplier_id": s["id"]}
            for col in COLS:
                params[col] = info.get(col) or None

            with c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO contacts
                        (supplier_id, contact_person, phone, whatsapp, address,
                         zip_code, state, city, country)
                    VALUES
                        (%(supplier_id)s, %(contact_person)s, %(phone)s, %(whatsapp)s,
                         %(address)s, %(zip_code)s, %(state)s, %(city)s, %(country)s)
                    ON CONFLICT (supplier_id) DO UPDATE SET
                        contact_person = EXCLUDED.contact_person,
                        phone          = EXCLUDED.phone,
                        whatsapp       = EXCLUDED.whatsapp,
                        address        = EXCLUDED.address,
                        zip_code       = EXCLUDED.zip_code,
                        state          = EXCLUDED.state,
                        city           = EXCLUDED.city,
                        country        = EXCLUDED.country
                    """,
                    params,
                )
            c.commit()
            print(f"[{i}/{len(suppliers)}] {s['name']}: "
                  f"tel={params.get('phone') or '-'} | "
                  f"wa={params.get('whatsapp') or '-'}")
            time.sleep(DELAY)
    print(f"Upserted contacts for {len(suppliers)} suppliers")


if __name__ == "__main__":
    main()
