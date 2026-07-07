import csv
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://b2bmap.com/morocco/companies"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
DELAY = 2
OUTPUT = Path("data/raw_suppliers.csv")
FIELDS = ["name", "category", "location", "website", "contact",
          "price_signal", "source", "score"]


def fetch(page):
    url = URL if page == 1 else f"{URL}?page={page}"
    print(f"GET {url}")
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.text


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    for card in soup.select("li.member-item"):
        name = card.select_one("a.directory-link span")
        if not name:
            continue
        category = ""
        for div in card.select("div.mb-1"):
            if "Business Category" in div.get_text():
                a = div.select_one("a")
                category = a.get_text(strip=True) if a else ""
                break
        loc = card.select_one("div.mb-1.text-muted")
        yield {
            "name": name.get_text(strip=True),
            "category": category,
            "location": loc.get_text(strip=True) if loc else "Morocco",
            "website": "",
            "contact": "",
            "price_signal": "",
            "source": "b2bmap.com",
            "score": 0,
        }


def scrape(pages=1):
    rows = []
    for p in range(1, pages + 1):
        rows.extend(parse(fetch(p)))
        time.sleep(DELAY)
    return rows


def save(rows):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {len(rows)} suppliers to {OUTPUT}")


if __name__ == "__main__":
    save(scrape(pages=3))
