from db import connect, init_schema


def main():
    init_schema()
    with connect() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT name, category, score FROM ranked_suppliers LIMIT 10"
            )
            top = cur.fetchall()
            print("Top 10 overall:")
            for row in top:
                score = row["score"] or "-"
                print(f"  [{score:>4}] {row['name']} ({row['category'] or 'n/a'})")

            cur.execute(
                """
                SELECT category, name, score
                FROM (
                    SELECT category, name, score,
                           ROW_NUMBER() OVER (
                               PARTITION BY category
                               ORDER BY NULLIF(score,'')::float DESC NULLS LAST
                           ) AS rn
                    FROM suppliers
                    WHERE category IS NOT NULL AND category <> ''
                ) t
                WHERE rn <= 3
                ORDER BY category, rn
                """
            )
            rows = cur.fetchall()
            current = None
            print("\nTop 3 per category:")
            for row in rows:
                if row["category"] != current:
                    current = row["category"]
                    print(f"\n  {current}")
                score = row["score"] or "-"
                print(f"    [{score:>4}] {row['name']}")


if __name__ == "__main__":
    main()
