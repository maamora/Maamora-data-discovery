import random
import re
import time

import requests
from bs4 import BeautifulSoup

from db import connect, init_schema

DELAY_RANGE = (1, 2)  # CHANGED: randomized instead of a fixed 1s -- a fixed
# delay is an easy pattern for anti-bot systems to fingerprint at volume.
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
    "email": "email",  # CHANGED: added -- this is the field the internship
    "e-mail": "email",  # supervisor asked for.
    "address": "address",
    "zip code": "zip_code",
    "state": "state",
    "city": "city",
    "country": "country",
}
COLS = ["contact_person", "phone", "whatsapp", "email", "address",
        "zip_code", "state", "city", "country"]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# B2BMap masks contact data for anonymous users:
#   phone/whatsapp are served as e.g. "+212669xxxxx" (last 5 digits = literal x)
#   email is served as "*" (single asterisk)
# Verified July 2026 by fetching /contact-info without a session. These are
# NOT real values — dropping them here so the DB never stores "+212661xxxxx"
# as if it were a phone. To get real values we'd have to register + log in
# (and re-check ToS). Address / contact_person / city / state / country are
# NOT masked and remain useful.
MASK_RE = re.compile(r"x{3,}", re.IGNORECASE)


def _looks_masked(value):
    if not value:
        return True
    v = value.strip()
    return v in ("*", "-", "") or bool(MASK_RE.search(v))


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

    # CHANGED: fallback email extraction. Contact-info pages often don't
    # label the email explicitly (or show it as a mailto: link / inside a
    # "protected" span), so if the labelled scan above didn't find one,
    # fall back to (a) any mailto: href, then (b) a regex scan of the
    # visible text.
    if not data.get("email") or _looks_masked(data.get("email")):
        data.pop("email", None)
        mailto = soup.select_one('a[href^="mailto:"]')
        if mailto:
            data["email"] = mailto.get("href", "").replace("mailto:", "").split("?")[0].strip()
    if not data.get("email"):
        m = EMAIL_RE.search(soup.get_text(" "))
        if m:
            data["email"] = m.group(0)

    # Drop any field whose value is B2BMap's anon-user mask (see MASK_RE
    # comment). Do this last so the mailto/regex email fallbacks above got a
    # chance to fill in a real value first.
    for f in ("phone", "whatsapp", "email"):
        if _looks_masked(data.get(f)):
            data.pop(f, None)

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


def main(resume=True):
    """
    resume=True (default, CHANGED): only process suppliers that don't
    already have a contacts row with an email filled in. This is the fix
    for the "re-scrapes everything on every run" issue -- at ~1000 rows,
    a crash/CAPTCHA partway through used to mean starting over from zero.
    Pass resume=False to force a full re-run (e.g. after fixing a parsing
    bug you want to re-apply to already-processed rows).
    """
    init_schema()
    with connect() as c:
        with c.cursor() as cur:
            if resume:
                cur.execute(
                    """
                    SELECT s.id, s.name, COALESCE(s.b2bmap_url, s.external_url) AS url
                    FROM suppliers s
                    LEFT JOIN contacts c ON c.supplier_id = s.id
                    WHERE s.b2bmap_url IS NOT NULL
                      AND (c.email IS NULL OR c.email = '')
                    ORDER BY s.id
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT id, name, b2bmap_url AS url FROM suppliers
                    WHERE b2bmap_url IS NOT NULL ORDER BY id
                    """
                )
            suppliers = cur.fetchall()

        print(f"{len(suppliers)} suppliers to process "
              f"({'resume mode' if resume else 'full re-run'})")

        for i, s in enumerate(suppliers, 1):
            info = fetch_contact_info(s["url"])
            params = {"supplier_id": s["id"]}
            for col in COLS:
                params[col] = info.get(col) or None

            with c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO contacts
                        (supplier_id, contact_person, phone, whatsapp, email,
                         address, zip_code, state, city, country)
                    VALUES
                        (%(supplier_id)s, %(contact_person)s, %(phone)s, %(whatsapp)s,
                         %(email)s, %(address)s, %(zip_code)s, %(state)s, %(city)s,
                         %(country)s)
                    ON CONFLICT (supplier_id) DO UPDATE SET
                        contact_person = COALESCE(EXCLUDED.contact_person, contacts.contact_person),
                        phone          = COALESCE(EXCLUDED.phone, contacts.phone),
                        whatsapp       = COALESCE(EXCLUDED.whatsapp, contacts.whatsapp),
                        email          = COALESCE(EXCLUDED.email, contacts.email),
                        address        = COALESCE(EXCLUDED.address, contacts.address),
                        zip_code       = COALESCE(EXCLUDED.zip_code, contacts.zip_code),
                        state          = COALESCE(EXCLUDED.state, contacts.state),
                        city           = COALESCE(EXCLUDED.city, contacts.city),
                        country        = COALESCE(EXCLUDED.country, contacts.country)
                    """,
                    params,
                )
            c.commit()
            print(f"[{i}/{len(suppliers)}] {s['name']}: "
                  f"tel={params.get('phone') or '-'} | "
                  f"email={params.get('email') or '-'}")
            time.sleep(random.uniform(*DELAY_RANGE))
    print(f"Upserted contacts for {len(suppliers)} suppliers")


if __name__ == "__main__":
    main()
