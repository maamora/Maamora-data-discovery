import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/suppliers",
)

# CHANGED: added contacts.email (filled by contact_info_collect.py /
# email_enrich.py) and other additive columns over time. All migrations
# are ALTER TABLE ... ADD/DROP COLUMN IF [NOT] EXISTS, safe to run
# against an existing database without losing unrelated data.
SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT,
    location     TEXT,
    website      TEXT,
    contact      TEXT,
    price_signal TEXT,
    source       TEXT,
    score        TEXT,
    b2bmap_url   TEXT UNIQUE
);

ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS description  TEXT;
-- external_url: generic unique key so a second source (Europages, etc.)
-- can reuse the same idempotent-insert pattern as b2bmap_url without a
-- schema fork. b2bmap_url stays for backward compatibility with existing
-- rows / the contact_info_collect.py workflow.
ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS external_url TEXT UNIQUE;
-- duplicate_of_id: non-destructive dedup marker. When set, this
-- supplier is considered a duplicate of another row (cross-source
-- match, e.g. same company on both b2bmap.com and kerix.net). Rows
-- are never deleted -- export.py excludes them, but they stay in the
-- DB for debugging/review.
ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS duplicate_of_id INTEGER REFERENCES suppliers(id);

CREATE TABLE IF NOT EXISTS contacts (
    id             SERIAL PRIMARY KEY,
    supplier_id    INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    contact_person TEXT,
    phone          TEXT,
    whatsapp       TEXT,
    email          TEXT,
    address        TEXT,
    zip_code       TEXT,
    state          TEXT,
    city           TEXT,
    country        TEXT,
    UNIQUE (supplier_id)
);

ALTER TABLE contacts ADD COLUMN IF NOT EXISTS email TEXT;

-- CHANGED: review_count abandoned -- confirmed via manual DOM
-- inspection (debug_maps_place_v3.py, tested on Marjane which
-- certainly has thousands of reviews) that the count isn't reliably
-- present in Google Maps' place panel at scrape time.
-- Postgres quirk (found by testing this against a real DB, not
-- assumed): CREATE OR REPLACE VIEW cannot remove a column from an
-- existing view definition ("cannot drop columns from view"), and a
-- column can't be dropped while a view still depends on it. So: drop
-- the view first, then the column, then recreate the view fresh.
DROP VIEW IF EXISTS ranked_suppliers;
ALTER TABLE suppliers DROP COLUMN IF EXISTS review_count;

CREATE VIEW ranked_suppliers AS
SELECT
    s.id, s.name, s.category, s.location, s.website, s.contact,
    s.price_signal, s.source, s.score, s.b2bmap_url,
    s.external_url, s.duplicate_of_id,
    c.contact_person, c.phone AS contact_phone, c.whatsapp, c.email,
    c.address, c.zip_code, c.state, c.city, c.country
FROM suppliers s
LEFT JOIN contacts c ON c.supplier_id = s.id
ORDER BY NULLIF(s.score, '')::float DESC NULLS LAST;
"""


def connect():
    """Open a new Postgres connection with dict rows."""
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_schema():
    """Create the tables + view if they don't already exist, and apply
    additive migrations (ADD COLUMN IF NOT EXISTS) for existing databases."""
    with connect() as c:
        with c.cursor() as cur:
            cur.execute(SCHEMA)
        c.commit()
