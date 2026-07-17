"""
Stage: export -- the missing final step. Reads the `ranked_suppliers`
view (already sorted by score, defined in db.py) and writes clean CSVs a
human can actually open and act on, plus a draft outreach message per
supplier (per the original brief's Definition of Done -- this was never
implemented by any prior stage).

Output:
  data/ranked/all.csv                -- every supplier, best-to-worst
  data/ranked/<category-slug>.csv    -- one file per category

The outreach message is a template, not personalized copywriting -- it's
meant as a starting point a human edits before sending, per the project's
ground rules ("drafts only, a human always sends").
"""
import csv
import os
import re

from db import connect, init_schema

OUT_DIR = os.path.join("data", "ranked")


def slugify(text):
    text = (text or "uncategorized").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "uncategorized"


def draft_outreach(row):
    name = row.get("name") or "there"
    category = row.get("category") or "your products"
    contact_person = row.get("contact_person")
    greeting = f"Bonjour {contact_person}," if contact_person else f"Bonjour,"
    return (
        f"{greeting}\n\n"
        f"Nous avons trouvé {name} en recherchant des fournisseurs pour "
        f"{category}, et votre profil correspond à ce que nous recherchons.\n\n"
        f"Seriez-vous disponible pour échanger sur une éventuelle "
        f"collaboration ? Nous serions ravis d'en savoir plus sur vos "
        f"produits/services et vos conditions.\n\n"
        f"Cordialement,"
    )


FIELDNAMES = [
    "name", "category", "location", "website", "contact", "email",
    "price_signal", "score", "review_count", "source", "b2bmap_url",
    "external_url", "outreach_draft",
]


def fetch_rows():
    init_schema()
    with connect() as c:
        with c.cursor() as cur:
            cur.execute("SELECT * FROM ranked_suppliers")
            return cur.fetchall()


def to_export_row(row):
    return {
        "name": row.get("name") or "",
        "category": row.get("category") or "",
        "location": row.get("location") or "",
        "website": row.get("website") or "",
        "contact": row.get("contact") or row.get("contact_phone") or "",
        "email": row.get("email") or "",
        "price_signal": row.get("price_signal") or "",
        "score": row.get("score") or "",
        "review_count": row.get("review_count") if row.get("review_count") is not None else "",
        "source": row.get("source") or "",
        "b2bmap_url": row.get("b2bmap_url") or "",
        "external_url": row.get("external_url") or "",
        "outreach_draft": draft_outreach(row),
    }


def write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = fetch_rows()
    export_rows = [to_export_row(r) for r in rows]

    all_path = os.path.join(OUT_DIR, "all.csv")
    write_csv(all_path, export_rows)
    print(f"Wrote {len(export_rows)} suppliers to {all_path}")

    by_category = {}
    for r, export_r in zip(rows, export_rows):
        slug = slugify(r.get("category"))
        by_category.setdefault(slug, []).append(export_r)

    for slug, cat_rows in by_category.items():
        path = os.path.join(OUT_DIR, f"{slug}.csv")
        write_csv(path, cat_rows)
        print(f"Wrote {len(cat_rows)} suppliers to {path}")

    print(f"\nExport complete: {len(export_rows)} suppliers across "
          f"{len(by_category)} category files, in {OUT_DIR}/")


if __name__ == "__main__":
    main()
