"""Pre-registered selection of a genuinely unseen bill-level holdout for #524.

Written and digest-recorded BEFORE the pool was enumerated, and before any PDF was
parsed. The point is that "we did not pick bills that would pass" is checkable rather
than asserted.

================================================================================
SELECTION RULE  (frozen; the seed and every threshold are stated here)
================================================================================
1. FRAME. For Congresses 113-119, sessions 1-2, bill types `hr` and `s`, read the
   govinfo BILLS bulkdata listing. Each entry names
   `BILLS-{congress}{type}{number}{version}.xml` and carries a byte `size`.

2. LENGTH PREFILTER. Keep a bill when its LARGEST version XML is >= 300_000 bytes.
   Document length is an a-priori attribute of the artifact, known before any parse,
   and independent of heading correctness and of the candidate. It exists only to
   keep step 3 affordable.

3. IN-SCOPE TEST (XML-side, independent of the candidate). Download the largest
   version XML and keep the bill iff it contains an `<appropriations-major>` or
   `<appropriations-small>` element. This asks "does this document have an
   appropriations account hierarchy at all", which is what puts it in the population
   the account-terminated heading path serves. It reads the XML only -- never the
   PDF, never a boundary, never a candidate decision.

4. EXCLUSION (the SEEN set). Drop every bill id that appears in `tests/corpus/` or in
   the repository's gitignored `/bills` download directory. The unit is the BILL:
   if any version of a bill was available to the discovery work, every version of
   that bill is excluded. `/bills` is included in the exclusion even though the
   development measurements iterated `tests/corpus/` only, because `CORPUS_SWEEP=1`
   can reach it and a conservative exclusion costs nothing here.

5. PAIRING. Keep a bill only if at least one version has BOTH a PDF and an XML on
   govinfo.

6. SAMPLE. Sort the survivors by bill id, then draw with `random.Random(SEED)`,
   stratified to at most `PER_CONGRESS` bills per Congress so the sample cannot
   collapse onto one Congress or one appropriations cycle. SEED = 20260819.

No step consults heading correctness, segmentation, caps-per-word, fullness, or any
candidate output. Steps 2 and 3 are inclusion criteria on the artifact; step 4 is the
independence constraint; step 6 is blind.

    uv run python docs/research/pdf-heading-identity/holdout/select_holdout.py
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
OUT = HERE / "pool.json"

CONGRESSES = range(113, 120)
SESSIONS = (1, 2)
BILL_TYPES = ("hr", "s")
MIN_XML_BYTES = 300_000
SEED = 20260819
PER_CONGRESS = 3

_FILE = re.compile(
    r"<name>BILLS-(?P<congress>\d+)(?P<type>[a-z]+)(?P<number>\d+)(?P<version>[a-z]+)\.xml</name>.*?<size>(?P<size>\d+)</size>",
    re.DOTALL,
)


def listing(client, congress, session, bill_type):
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"listing-{congress}-{session}-{bill_type}.xml"
    if path.exists():
        return path.read_text()
    url = f"https://www.govinfo.gov/bulkdata/BILLS/{congress}/{session}/{bill_type}"
    r = client.get(url, headers={"Accept": "application/xml"}, timeout=120, follow_redirects=True)
    if r.status_code != 200:
        return ""
    path.write_text(r.text)
    return r.text


def bill_trees() -> list[Path]:
    """Every tree that could have supplied a bill to the discovery work.

    `bills/` is per-working-tree and gitignored, so in a worktree it is empty while the
    real downloads sit in the MAIN checkout. Reading only `ROOT / "bills"` here silently
    admitted bills that discovery could have swept (`116-hr-133`, `115-hr-880`,
    `118-s-2302`), which is a selection-integrity defect, not a cosmetic one -- it is
    exactly the leak that would make a "holdout" not a holdout. `git rev-parse
    --git-common-dir` resolves the shared repository, whose parent is the main checkout.
    """
    import subprocess

    trees = [ROOT / "tests" / "corpus", ROOT / "bills"]
    try:
        common = Path(
            subprocess.run(
                ["git", "rev-parse", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
        )
        main_root = (ROOT / common).resolve().parent
        trees += [main_root / "tests" / "corpus", main_root / "bills"]
    except Exception:
        pass
    return trees


def seen_bill_ids() -> set[str]:
    seen = set()
    for d in bill_trees():
        if not d.is_dir():
            continue
        for child in d.iterdir():
            if child.is_dir() and re.fullmatch(r"\d+-[a-z]+-\d+", child.name):
                seen.add(child.name)
    return seen


def main() -> None:
    seen = seen_bill_ids()
    print(f"SEEN (excluded) bills: {len(seen)}")

    versions: dict[str, dict[str, int]] = defaultdict(dict)
    with httpx.Client() as client:
        for congress in CONGRESSES:
            for session in SESSIONS:
                for bill_type in BILL_TYPES:
                    text = listing(client, congress, session, bill_type)
                    if not text:
                        continue
                    n = 0
                    for m in _FILE.finditer(text):
                        bid = f"{m['congress']}-{m['type']}-{int(m['number'])}"
                        versions[bid][m["version"]] = int(m["size"])
                        n += 1
                    print(f"  listing {congress}/{session}/{bill_type}: {n} files")

    print(f"\nframe: {len(versions)} bills with at least one XML")
    long_bills = {b: v for b, v in versions.items() if max(v.values()) >= MIN_XML_BYTES}
    print(f"after length prefilter (>= {MIN_XML_BYTES} bytes): {len(long_bills)}")
    unseen = {b: v for b, v in long_bills.items() if b not in seen}
    print(f"after excluding SEEN bills: {len(unseen)}")
    excluded_by_seen = sorted(set(long_bills) - set(unseen))
    print(f"  excluded as seen: {excluded_by_seen}")

    OUT.write_text(
        json.dumps(
            {
                "seed": SEED,
                "min_xml_bytes": MIN_XML_BYTES,
                "per_congress": PER_CONGRESS,
                "congresses": list(CONGRESSES),
                "bill_types": list(BILL_TYPES),
                "seen_excluded": sorted(seen),
                "frame_size": len(versions),
                "after_length": len(long_bills),
                "after_exclusion": len(unseen),
                "excluded_by_seen": excluded_by_seen,
                "candidates": {b: v for b, v in sorted(unseen.items())},
            },
            indent=2,
        )
    )
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
