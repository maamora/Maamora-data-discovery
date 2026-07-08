"""
Orchestrator: run the full pipeline in order.

    python run_all.py

Runs collect -> contact_info_collect -> enrich -> rank. Each stage reads
the previous stage's CSV from `data/`. Produces:
    data/raw_suppliers.csv        (collect)
    data/contacts.csv             (contact_info_collect, B2BMap /contact-info)
    data/enriched_suppliers.csv   (enrich, Google Maps rating/website)
    data/ranked/all.csv           (rank)
    data/ranked/<category>.csv    (rank)
"""

import time

import collect
import contact_info_collect
import enrich
import rank


def stage(name, fn):
    print(f"\n=== {name} ===")
    t0 = time.time()
    fn()
    print(f"=== {name} done in {time.time() - t0:.1f}s ===")


def main():
    t0 = time.time()
    stage("collect", lambda: collect.save(collect.scrape(pages=3)))
    stage("contact-info", contact_info_collect.main)
    stage("enrich", enrich.main)
    stage("rank", rank.main)
    print(f"\nPipeline complete in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
