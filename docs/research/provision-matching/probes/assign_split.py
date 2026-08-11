"""Assign each candidate a dev / held-out split BY BILL (protocol §6).

Pairs from one bill share vocabulary and drafting style, so a pair-level holdout leaks; the
split is by whole bill (the leave-one-bill-out discipline the paper validated). The single
most important overfitting guard: cutoffs are fit on dev bills only and the held-out set is
touched once, at the end.

Rule (deterministic, no RNG state — reproducible from the bill name alone):
  a bill is HELD-OUT iff  sha256(bill + SALT) mod 3 == 0   (~1/3 of bills).
For a cross-bill candidate (high-containment-different pairs span two bills), the pair is:
  - held-out  iff BOTH endpoint bills are held-out,
  - dev       iff BOTH endpoint bills are dev,
  - cross     otherwise -> excluded from BOTH metrics and logged (never leak across the line).

Corpus constraints this encodes (protocol §6, updated for the bills_corpus pool):
  - high-containment-different CAN be held out (its pairs are built from arbitrary corpus
    bills), so both dev and held-out get candidates.
  - consolidation exists only in 119-hr-1 (a Pass-1 seen bill forced to dev), so it is
    dev-only with no held-out counterpart until a second consolidation-bearing bill is
    validated (NDAA candidates flagged by the census, not yet mined).

Run (from repo root, repo venv):
    .venv/bin/python docs/research/provision-matching/probes/assign_split.py
Writes `split_assignment.json` and prints the partition per stratum.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).parent
SALT = "deltatrack-pass2-v1"  # fixed; bump only to deliberately reshuffle the split
_POOLS = [
    "candidates_high_containment_different.json",
    "candidates_consolidation.json",
    "candidates_financial_lines.json",
]
_FORCE_DEV = {"119-hr-1"}  # Pass-1 seen bills must not launder into held-out (§6)


def bill_split(bill: str) -> str:
    if bill in _FORCE_DEV:
        return "dev"
    h = int(hashlib.sha256(f"{bill}{SALT}".encode()).hexdigest(), 16)
    return "held-out" if h % 3 == 0 else "dev"


def pair_split(bill_old: str, bill_new: str) -> str:
    so, sn = bill_split(bill_old), bill_split(bill_new)
    if so == sn:
        return so
    return "cross"  # spans the split line -> excluded from both


def main() -> None:
    assignments = {}
    bills_seen = set()
    for pool_name in _POOLS:
        path = _HERE / pool_name
        if not path.exists():
            print(f"SKIP {pool_name} (not mined yet)")
            continue
        pool = json.loads(path.read_text())
        stratum = pool["stratum"]
        by_split = Counter()
        for c in pool["candidates"]:
            s = pair_split(c["bill_old"], c["bill_new"])
            assignments[c["id"]] = {
                "split": s,
                "stratum": stratum,
                "bill_old": c["bill_old"],
                "bill_new": c["bill_new"],
            }
            by_split[s] += 1
            bills_seen.update((c["bill_old"], c["bill_new"]))
        print(f"{stratum:28} {dict(by_split)}")

    held = sorted(b for b in bills_seen if bill_split(b) == "held-out")
    dev = sorted(b for b in bills_seen if bill_split(b) == "dev")
    print(f"\nbills touched: {len(bills_seen)}  ->  dev: {len(dev)}  held-out: {len(held)}")
    (_HERE / "split_assignment.json").write_text(
        json.dumps(
            {
                "_about": "By-bill dev/held-out split for Pass 2 challenge candidates (protocol §6). "
                "Deterministic from bill name + SALT; cross-line pairs excluded from both metrics.",
                "salt": SALT,
                "force_dev": sorted(_FORCE_DEV),
                "held_out_bills": held,
                "dev_bills": dev,
                "assignments": assignments,
            },
            indent=2,
        )
    )
    print(f"wrote {len(assignments)} split assignments -> split_assignment.json")


if __name__ == "__main__":
    main()
