"""10B + 10C: the actual final segmentation through the real pipeline, on every
production-accepted adjacent pair, with the PR #639 move cards re-adjudicated.

Every consequential downstream delta must trace to an oracle-confirmed corrected
heading boundary. `src/` untouched; `extract_anchors` monkeypatched and restored.
"""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "confounder"))
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "frozen"))
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-matching-convergence" / "probes"))

import pipeline_consequence as PC  # noqa: E402
from freeze_check4 import verify  # noqa: E402
from corpus import accepted_pdf_pairs, pages_for  # noqa: E402
from deltatrack.bill_tree import normalize_header  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"
TRACK = defaultdict(dict)
for _f in ("tracking.jsonl", "holdout2-tracking.jsonl"):
    p = RESULTS / _f
    if p.exists():
        for line in p.open():
            r = json.loads(line)
            TRACK[(r["bill"], r["version"])][(r["page"], r["line"])] = r["tracking_mean"]


def move_class(o, n):
    if o is None or n is None:
        return "relocated"
    no, nn = normalize_header(o), normalize_header(n)
    if no == nn:
        return "labels_equal"
    fo, fn = "".join(no.split()), "".join(nn.split())
    return "FALSE_fragment" if (fo in fn or fn in fo) else "distinct"


def main() -> None:
    print(f"frozen candidate 4 digest: {verify()}\n")
    totals = Counter()
    no_track = []
    for bill, old, new in accepted_pdf_pairs():
        p1, p2 = pages_for(old), pages_for(new)
        pr1, pr2 = PC.profiles_for(old), PC.profiles_for(new)
        t1, t2 = TRACK.get((bill, old.stem), {}), TRACK.get((bill, new.stem), {})
        if not t1:
            no_track.append(f"{bill}/{old.stem}")
        if not t2:
            no_track.append(f"{bill}/{new.stem}")

        def ex(pages, _a=pr1, _b=pr2, _t1=t1, _t2=t2, _p1=p1):
            return PC.candidate3_extract_anchors(
                pages, _a if pages is _p1 else _b, _t1 if pages is _p1 else _t2, True)

        base = PC.stages(p1, p2, PC.ORIGINAL)
        alt = PC.stages(p1, p2, ex)
        bm = [c for c in base["_canon"]["changes"] if c.get("move")]
        am = [c for c in alt["_canon"]["changes"] if c.get("move")]
        bc = Counter(move_class(m["move"].get("old_label"), m["move"].get("new_label")) for m in bm)
        ac = Counter(move_class(m["move"].get("old_label"), m["move"].get("new_label")) for m in am)
        totals["ship_moves"] += len(bm); totals["cand_moves"] += len(am)
        totals["ship_false"] += bc["FALSE_fragment"]; totals["cand_false"] += ac["FALSE_fragment"]
        totals["ship_distinct"] += bc["distinct"]; totals["cand_distinct"] += ac["distinct"]
        changed = [f for f in PC.FIELDS if base[f] != alt[f]]
        print(f"### {bill} {old.stem} -> {new.stem}")
        print(f"    anchors {base['n_anchors']} -> {alt['n_anchors']}   "
              f"summary {base['summary']} -> {alt['summary']}")
        print(f"    moves {len(bm)} -> {len(am)}   false-fragment {bc['FALSE_fragment']} -> "
              f"{ac['FALSE_fragment']}   distinct {bc['distinct']} -> {ac['distinct']}")
        print(f"    stages changed: {changed or 'NONE'}")

    print("\n=== TOTALS over the production-accepted pairs ===")
    print(f"  canonical moves            : {totals['ship_moves']} -> {totals['cand_moves']}")
    print(f"  FALSE-fragment Renumbered  : {totals['ship_false']} -> {totals['cand_false']}")
    print(f"  distinct-label moves       : {totals['ship_distinct']} -> {totals['cand_distinct']}")
    print(f"  documents with no tracking (fail-open): {len(set(no_track))} {sorted(set(no_track))[:6]}")


if __name__ == "__main__":
    main()
