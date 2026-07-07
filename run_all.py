"""
Orchestrator: run the full pipeline in order.

    python run_all.py

Runs collect -> enrich -> rank. Each stage reads the previous stage's CSV
from `data/`, so the effect is the same as running the three scripts by hand.
Any exception in a stage aborts the run (the later stages would just fail
on missing input anyway).
"""

import time

import collect
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
    stage("enrich", enrich.main)
    stage("rank", rank.main)
    print(f"\nPipeline complete in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
