import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/suppliers",
)

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

CREATE TABLE IF NOT EXISTS contacts (
    id             SERIAL PRIMARY KEY,
    supplier_id    INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    contact_person TEXT,
    phone          TEXT,
    whatsapp       TEXT,
    address        TEXT,
    zip_code       TEXT,
    state          TEXT,
    city           TEXT,
    country        TEXT,
    UNIQUE (supplier_id)
);

CREATE OR REPLACE VIEW ranked_suppliers AS
SELECT
    s.id, s.name, s.category, s.location, s.website, s.contact,
    s.price_signal, s.source, s.score, s.b2bmap_url,
    c.contact_person, c.phone AS contact_phone, c.whatsapp,
    c.address, c.zip_code, c.state, c.city, c.country
FROM suppliers s
LEFT JOIN contacts c ON c.supplier_id = s.id
ORDER BY NULLIF(s.score, '')::float DESC NULLS LAST;
"""


def connect():
    """Open a new Postgres connection with dict rows."""
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_schema():
    """Create the tables + view if they don't already exist."""
    with connect() as c:
        with c.cursor() as cur:
            cur.execute(SCHEMA)
        c.commit()
