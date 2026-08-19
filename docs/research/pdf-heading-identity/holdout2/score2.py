"""Score frozen candidate 4 on the second holdout. Once.

PRIMARY GATE: no oracle-established SPLIT boundary may be joined.
SECONDARY: missed joins, reported as a quality metric and NOT driven to zero.
"""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "frozen"))
import apply4  # noqa: E402
import frozen_candidate4 as C4  # noqa: E402

RES = Path(__file__).resolve().parents[1] / "results"


def main() -> None:
    runs, typo, track, gaps = apply4.load(
        RES, "holdout2-runs.jsonl", "holdout2-typography.jsonl", "holdout2-tracking.jsonl")
    s = apply4.score(runs, typo, track, gaps)
    fj, mj = s["false_joins"], s["missed_joins"]
    sfj, smj = s["shipped_false_joins"], s["shipped_missed_joins"]
    resolved = s["resolved"]

    print(f"frozen candidate 4 digest : {s['digest']}")
    print(f"holdout 2                 : {len({r['bill'] for r in resolved})} bills, "
          f"{len({(r['bill'], r['version']) for r in resolved})} documents")
    print(f"boundaries scored         : {s['boundaries']} over {s['runs']} resolved multi-line runs")
    tw = sum(1 for r in resolved for t in apply4.truth_of(r) if t == C4.JOIN)
    ts = sum(1 for r in resolved for t in apply4.truth_of(r) if t == C4.SPLIT)
    print(f"true wraps / true stacks  : {tw} / {ts}")
    print()
    print(f"shipped        false_joins={len(sfj):<4} missed_joins={len(smj)}")
    print(f"CANDIDATE 4    false_joins={len(fj):<4} missed_joins={len(mj)}")
    print(f"               novel false joins  = {len(fj - sfj)}")
    print(f"               novel missed joins = {len(mj - smj)}")
    print(f"               clause usage: {s['clauses'].most_common()}")
    missing = [d for d, m in s["medians"].items() if m is None]
    print(f"               documents hitting the fail-open (no tracking median): {len(missing)}")

    print(f"\n*** PRIMARY GATE: no oracle SPLIT joined -> "
          f"{'PASS' if len(fj) == 0 else 'FAIL (' + str(len(fj)) + ')'} ***")
    if fj:
        print("\n=== every false join ===")
        medians = s["medians"]
        for r in resolved:
            for i, t in enumerate(apply4.truth_of(r)):
                key = (r["bill"], r["version"], r["pages"][i], r["lines"][i])
                if key not in fj:
                    continue
                d, c = apply4.decide_for(r, i, typo, track, medians)
                novel = key not in sfj
                print(f"  {'*** NOVEL ***' if novel else '(shipped errs too)'} "
                      f"{r['bill']}/{r['version']} p{r['pages'][i]}L{r['lines'][i]} [{c}]")
                print(f"     {r['texts'][i]!r} + {r['texts'][i + 1]!r}")
                print(f"     XML truth: {[C4.join_lines([r['texts'][k] for k in g]) for g in r['truth']]}")

    print("\n=== PER BILL ===")
    print(f"{'bill':<14}{'docs':>5}{'wraps':>7}{'stacks':>7}{'shipFJ':>8}{'candFJ':>8}"
          f"{'shipMJ':>8}{'candMJ':>8}")
    per = defaultdict(list)
    for r in resolved:
        per[r["bill"]].append(r)
    for bill in sorted(per):
        rs = per[bill]
        w = sum(1 for r in rs for t in apply4.truth_of(r) if t == C4.JOIN)
        st = sum(1 for r in rs for t in apply4.truth_of(r) if t == C4.SPLIT)
        keys = {(r["bill"], r["version"], r["pages"][i], r["lines"][i])
                for r in rs for i in range(len(r["texts"]) - 1)}
        print(f"{bill:<14}{len({r['version'] for r in rs}):>5}{w:>7}{st:>7}"
              f"{len(sfj & keys):>8}{len(fj & keys):>8}{len(smj & keys):>8}{len(mj & keys):>8}")

    print("\n=== BY STAGE ===")
    per_s = defaultdict(list)
    for r in resolved:
        per_s[r["version"]].append(r)
    print(f"{'stage':<8}{'bounds':>8}{'shipFJ':>8}{'candFJ':>8}{'shipMJ':>8}{'candMJ':>8}")
    for st in sorted(per_s):
        rs = per_s[st]
        keys = {(r["bill"], r["version"], r["pages"][i], r["lines"][i])
                for r in rs for i in range(len(r["texts"]) - 1)}
        print(f"{st:<8}{len(keys):>8}{len(sfj & keys):>8}{len(fj & keys):>8}"
              f"{len(smj & keys):>8}{len(mj & keys):>8}")


if __name__ == "__main__":
    main()
