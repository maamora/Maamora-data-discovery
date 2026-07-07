"""
Stage 3 of the supplier-discovery pipeline.

Reads `data/enriched_suppliers.csv`, sorts by `score` descending, and writes:
    data/ranked/all.csv          -- every supplier, ranked
    data/ranked/<category>.csv   -- one file per B2BMap category, ranked

Rows with an empty or non-numeric `score` sink to the bottom of every table.
Category filenames are slugified: lowercased, non-word chars stripped,
spaces/hyphens collapsed to `_` (e.g. "Machinery & Industrial Supplies" ->
`machinery_industrial_supplies.csv`).
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

INPUT = Path("data/enriched_suppliers.csv")
OUTPUT_DIR = Path("data/ranked")


def sort_key(row):
    try:
        return -float(row.get("score") or 0)
    except ValueError:
        return 0.0


def slug(category):
    s = re.sub(r"[^\w\s-]", "", category).strip().lower()
    return re.sub(r"[\s-]+", "_", s) or "uncategorised"


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    rows = list(csv.DictReader(INPUT.open(encoding="utf-8")))
    fields = list(rows[0].keys())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows.sort(key=sort_key)
    write_csv(OUTPUT_DIR / "all.csv", fields, rows)
    print(f"all: {len(rows)} -> {OUTPUT_DIR / 'all.csv'}")

    by_category = defaultdict(list)
    for row in rows:
        by_category[row.get("category") or "Uncategorised"].append(row)

    for category, items in by_category.items():
        path = OUTPUT_DIR / f"{slug(category)}.csv"
        write_csv(path, fields, items)
        print(f"{category}: {len(items)} -> {path}")


if __name__ == "__main__":
    main()
