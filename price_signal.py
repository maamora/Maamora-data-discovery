"""
Stage: price_signal -- fills the `price_signal` column, which existed in
the schema from day one but was never actually populated by any stage.

IMPORTANT: neither b2bmap.com nor Google Maps expose real *unit* price
data for suppliers. This stays a HEURISTIC, not a source of truth --
flag this explicitly to the encadrant so it's not mistaken for real
pricing in the final export.

Two-tier rule, per supplier:
  1. PRIMARY (kerix.net suppliers): use the real disclosed turnover
     ("CA: ..." in `description`, sourced from Kerix's "Turnover" field).
     Larger turnover -> more likely a bulk/wholesale-scale operation ->
     "low" per-unit pricing. Smaller turnover -> more likely a small/
     boutique operation -> "high" per-unit pricing. This is real
     disclosed financial data, not a guess -- the more reliable signal
     when available.
  2. FALLBACK (b2bmap.com suppliers, or anyone with no turnover data):
     keyword heuristic on name/category/description, as before. Only
     used when step 1 finds nothing to work with.
"""
import re

LOW_KEYWORDS = [
    "wholesale", "manufacturer", "exporter", "bulk", "gros", "grossiste",
    "fabricant", "producteur", "export",
]
HIGH_KEYWORDS = [
    "premium", "luxury", "luxe", "artisanal", "handmade", "hand-made",
    "boutique", "organic", "bio", "natural", "naturel", "haut de gamme",
]

# Thresholds (Moroccan Dirhams) for the turnover-based rule. Deliberately
# round numbers, easy to explain/defend/adjust with the encadrant.
LOW_THRESHOLD_DH = 50_000_000   # above this -> "low" (bulk/wholesale scale)
HIGH_THRESHOLD_DH = 5_000_000   # below this -> "high" (small/boutique scale)


def extract_turnover_dh(description):
    """Pull the 'CA: ...' segment out of our own generated description
    text (see kerix_collect.py) and return its upper bound in Dirhams,
    or None if no turnover info is present (e.g. b2bmap.com suppliers,
    or a Kerix listing that didn't disclose it)."""
    if not description:
        return None
    m = re.search(r"CA:\s*([^|]+)", description)
    if not m:
        return None
    numbers = [int(n.replace(",", "")) for n in re.findall(r"[\d,]{4,}", m.group(1))]
    if not numbers:
        return None
    return max(numbers)  # upper bound of the disclosed range


def infer_price_signal(name, category, description):
    # 1. PRIMARY: real turnover, when we have it.
    turnover = extract_turnover_dh(description)
    if turnover is not None:
        if turnover >= LOW_THRESHOLD_DH:
            return "low"
        if turnover < HIGH_THRESHOLD_DH:
            return "high"
        return "mid"

    # 2. FALLBACK: keyword heuristic.
    text = " ".join(filter(None, [name, category, description])).lower()
    if any(kw in text for kw in HIGH_KEYWORDS):
        return "high"
    if any(kw in text for kw in LOW_KEYWORDS):
        return "low"
    return "mid"


def main():
    from db import connect, init_schema

    init_schema()
    with connect() as c:
        with c.cursor() as cur:
            # CHANGED: no longer filters on "already has a value" --
            # this stage is cheap/local (no external requests to spare),
            # and the rule itself just changed, so existing "mid" values
            # need to be recomputed, not skipped.
            cur.execute("SELECT id, name, category, description FROM suppliers")
            rows = cur.fetchall()

        print(f"{len(rows)} suppliers to score for price_signal")
        for row in rows:
            signal = infer_price_signal(row["name"], row["category"], row["description"])
            with c.cursor() as cur:
                cur.execute(
                    "UPDATE suppliers SET price_signal = %s WHERE id = %s",
                    (signal, row["id"]),
                )
        c.commit()
    print(f"Set price_signal for {len(rows)} suppliers")


if __name__ == "__main__":
    main()
