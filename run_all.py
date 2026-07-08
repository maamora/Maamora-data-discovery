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
