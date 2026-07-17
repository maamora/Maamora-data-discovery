import time

# CHANGED: europages_collect removed -- blocked by robots.txt
# (Disallow: / for generic bots)
import collect
import contact_info_collect
import enrich
import export
import kerix_collect
import price_signal
import rank


def stage(name, fn):
    print(f"\n=== {name} ===")
    t0 = time.time()
    fn()
    print(f"=== {name} done in {time.time() - t0:.1f}s ===")


def main():
    t0 = time.time()
    # CHANGED: two collect sources now instead of one.
    stage("collect (b2bmap)", lambda: collect.save(collect.scrape(pages=3, include_categories=True)))
    # NOTE: start small (limit=20) the first time to spot-check the
    # parser against real Kerix pages before raising this toward 2000.
    stage("collect (kerix)", lambda: kerix_collect.save(kerix_collect.scrape(limit=20)))
    # CHANGED: price_signal is a new stage -- was never actually run before.
    stage("price_signal", price_signal.main)
    # CHANGED: resume=True by default now on both of these -- safe to
    # re-run run_all.py after a crash without losing prior progress.
    stage("contact-info", lambda: contact_info_collect.main(resume=True))
    stage("enrich", lambda: enrich.main(resume=True))
    stage("rank", rank.main)
    # CHANGED: new final stage -- writes the actual CSV deliverable the
    # brief's Definition of Done requires (this never existed before).
    stage("export", export.main)
    print(f"\nPipeline complete in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
