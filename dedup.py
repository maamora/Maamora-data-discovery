"""
Stage: dedup -- finds suppliers that appear on BOTH b2bmap.com and
kerix.net (same real company, two different source rows), and marks
the weaker copy as a duplicate via suppliers.duplicate_of_id.

Rule (deliberately simple and defensible, no manual negotiation done on
it -- flag this to the encadrant/Abdelhamid as the rule used):
  1. Normalize names: lowercase, strip accents, remove common legal
     suffixes (sarl, sarl au, sa, sasu, ste, societe...), remove
     punctuation, collapse whitespace.
  2. EXACT match on normalized name, across two DIFFERENT sources
     -> auto-marked as a duplicate pair. Low false-positive risk.
  3. CLOSE match (similarity >= 0.88, difflib) on normalized name,
     across two different sources, NOT already an exact match
     -> printed as a candidate for manual review, NOT auto-marked.
     Merging on a "looks similar" basis risks merging two genuinely
     different companies (e.g. "Atlas Trading" vs "Atlas Textile").
  4. When marking a duplicate pair, the row kept as primary is the one
     with more non-empty fields filled in (a simple completeness
     score) -- ties broken by preferring kerix.net (richer data:
     turnover, employee range, creation year).

Usage:
    python dedup.py
"""
import re
import unicodedata
from difflib import SequenceMatcher

from db import connect, init_schema

LEGAL_SUFFIXES = [
    "sarl", "au", "sasu", "sas", "sa", "ste", "societe", "société",
    "trading", "maroc", "morocco", "group", "groupe",
]

FUZZY_THRESHOLD = 0.88


def normalize_name(name):
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = text.split()
    words = [w for w in words if w not in LEGAL_SUFFIXES]
    return " ".join(words).strip()


def completeness_score(row):
    fields = ["category", "location", "website", "contact", "price_signal",
              "score", "email"]
    return sum(1 for f in fields if row.get(f))


def fetch_all():
    init_schema()
    with connect() as c:
        with c.cursor() as cur:
            cur.execute(
                """
                SELECT s.id, s.name, s.source, s.category, s.location,
                       s.website, s.contact, s.price_signal, s.score,
                       c.email
                FROM suppliers s
                LEFT JOIN contacts c ON c.supplier_id = s.id
                WHERE s.duplicate_of_id IS NULL
                ORDER BY s.id
                """
            )
            return cur.fetchall()


def mark_duplicate(loser_id, winner_id):
    with connect() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE suppliers SET duplicate_of_id = %s WHERE id = %s",
                (winner_id, loser_id),
            )
        c.commit()


def main():
    rows = fetch_all()
    for r in rows:
        r["_norm"] = normalize_name(r["name"])

    exact_marked = 0
    fuzzy_candidates = []

    seen = {}  # normalized name -> row, only for names seen so far
    for r in rows:
        if not r["_norm"]:
            continue
        key = r["_norm"]
        if key in seen:
            other = seen[key]
            if other["source"] != r["source"]:
                # exact match across two different sources -> auto-mark
                winner, loser = (
                    (other, r) if completeness_score(other) >= completeness_score(r)
                    else (r, other)
                )
                # prefer kerix.net on ties
                if completeness_score(other) == completeness_score(r):
                    winner = other if other["source"] == "kerix.net" else r
                    loser = r if winner is other else other
                mark_duplicate(loser["id"], winner["id"])
                exact_marked += 1
                print(f"[EXACT] '{loser['name']}' ({loser['source']}) "
                      f"-> duplicate of '{winner['name']}' ({winner['source']})")
                continue
        else:
            seen[key] = r

    # Fuzzy pass: only across different sources, only among names not
    # already exact-matched (i.e. still no duplicate_of_id set)
    remaining = [r for r in rows if r["_norm"]]
    for i, a in enumerate(remaining):
        for b in remaining[i + 1:]:
            if a["source"] == b["source"]:
                continue
            ratio = SequenceMatcher(None, a["_norm"], b["_norm"]).ratio()
            if ratio >= FUZZY_THRESHOLD and ratio < 1.0:
                fuzzy_candidates.append((ratio, a, b))

    print(f"\n{exact_marked} exact cross-source duplicates auto-marked.")
    print(f"{len(fuzzy_candidates)} close-but-not-exact candidates found "
          f"(NOT auto-marked -- review manually):\n")
    for ratio, a, b in sorted(fuzzy_candidates, key=lambda x: -x[0]):
        print(f"  [{ratio:.2f}] '{a['name']}' ({a['source']}, id={a['id']}) "
              f"<-> '{b['name']}' ({b['source']}, id={b['id']})")


if __name__ == "__main__":
    main()
