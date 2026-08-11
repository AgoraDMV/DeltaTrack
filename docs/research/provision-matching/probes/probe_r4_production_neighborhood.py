"""R4: how often does the high-containment false-keep shape arise where production can see it?

`probe_review_gameability.py` and `mine_high_containment_different.py` build SHORT(cited) x LONG
pairs across DIFFERENT bills and measure how often containment >= 0.70 fires. That is a valid
failure-EXISTENCE result and a good hard-negative mine. It is not an operational false-positive
rate, because production never compares two different bills: a move candidate is only ever drawn
from the removed/added sets of ONE adjacent version pair of ONE bill.

This probe runs the IDENTICAL construction inside the production neighbourhood, so the two rates
are directly comparable and differ only in where the candidates come from:

  adversarial   short(cited) in bill A  x  long in bill B      (B != A)     -- existing probes
  production    short(cited) removed    x  long added          same bill, adjacent versions

It also reports the size of the neighbourhood, because the false-keep risk scales with how many
long provisions a short one is compared against: a corpus-wide sweep offers tens of thousands of
chances for a coincidental rare-token hit, one version pair offers a few hundred.

Nothing here is a labeled false positive. A same-bill short-vs-long pair at high containment may
be a genuine consolidation ("absorbed into"). The probe reports RATES and SUPPORT, and says which
pairs a human would have to rule.

Run (from a normal checkout, repo venv; needs idf_cache.json from mine_idf.py):
    .venv/bin/python docs/research/provision-matching/probes/probe_r4_production_neighborhood.py
"""

from __future__ import annotations

import random
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

from corpus_roots import adjacent_pairs  # noqa: E402
from mine_common import containment, vec  # noqa: E402

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import _normalize_text, diff_bills  # noqa: E402

_cite = re.compile(r"u\.s\.c\.|\bsection\s+\d|\bact of \d{4}|\bpublic law", re.I)
SHORT_MAX = 200
LONG_MIN = 800
KEEP = 0.70


def main() -> None:
    random.seed(42)
    n_pairs = 0
    comparisons = hits = 0
    shorts_total = shorts_with_hit = 0
    neighbourhood_sizes = []
    examples = []
    per_bill_hits = {}

    for bill, xa, xb in adjacent_pairs():
        try:
            d = diff_bills(normalize_bill(xa), normalize_bill(xb))
        except Exception:
            continue
        n_pairs += 1

        shorts, longs = [], []
        for c in d.changes:
            if c.change_type == "removed" and c.old_text:
                t = _normalize_text(c.old_text)
                if len(t) <= SHORT_MAX and _cite.search(t):
                    shorts.append((c, t))
            elif c.change_type == "added" and c.new_text:
                t = _normalize_text(c.new_text)
                if len(t) >= LONG_MIN:
                    longs.append((c, t))
        if not shorts or not longs:
            continue
        neighbourhood_sizes.append(len(longs))
        long_vecs = [(c, t, vec(t)) for c, t in longs]

        for sc, st in shorts:
            sv = vec(st)
            shorts_total += 1
            hit_here = 0
            for lc, lt, lv in long_vecs:
                comparisons += 1
                if containment(sv, lv) >= KEEP:
                    hits += 1
                    hit_here += 1
                    if len(examples) < 8:
                        examples.append((bill, round(containment(sv, lv), 3), st[:70], lt[:70]))
            if hit_here:
                shorts_with_hit += 1
                per_bill_hits[bill] = per_bill_hits.get(bill, 0) + 1

    print("=" * 100)
    print("PRODUCTION NEIGHBOURHOOD: short(cited) removed x long added, SAME bill, adjacent versions")
    print("=" * 100)
    print(f"  adjacent version pairs scanned                     : {n_pairs}")
    print(f"  version pairs offering both a short(cited) and a long : {len(neighbourhood_sizes)}")
    if neighbourhood_sizes:
        avg = sum(neighbourhood_sizes) / len(neighbourhood_sizes)
        print(f"  long provisions a short is compared against (mean)  : {avg:.1f}")
        print(f"                                              (max)  : {max(neighbourhood_sizes)}")
    print()
    print(f"  short(cited) removed provisions examined           : {shorts_total}")
    print(f"  short x long comparisons made                      : {comparisons}")
    print(f"  comparisons reaching containment >= {KEEP}          : {hits}")
    rate = hits / comparisons if comparisons else 0.0
    print(f"  PER-COMPARISON hit rate                            : {rate:.2%}")
    pr = shorts_with_hit / shorts_total if shorts_total else 0.0
    print(f"  PER-PROVISION rate (a short with >=1 such partner)  : {shorts_with_hit}/{shorts_total} = {pr:.1%}")
    print()
    print("  by bill (shorts with at least one >= 0.70 partner):")
    for b in sorted(per_bill_hits, key=lambda k: -per_bill_hits[k]):
        print(f"    {b:<16} {per_bill_hits[b]}")
    print()
    print("  sample pairs a human would have to rule (absorbed vs coincidental -- NOT labels):")
    for b, c, s, ln in examples:
        print(f"    {b:<14} contain={c}")
        print(f"        SHORT: {s}")
        print(f"        LONG:  {ln}")
    print()
    print("  READ THIS AS: the per-PROVISION rate is the operationally meaningful one -- it is the")
    print("  share of short cited provisions for which a spurious keep is even available. The")
    print("  per-COMPARISON rate is what the cross-bill probes report, and it is not comparable")
    print("  across the two because the denominators are different populations.")


if __name__ == "__main__":
    main()
