"""Score shipped behaviour and the FROZEN candidate on the holdout. Once.

Refuses to run if the frozen specification digest moved (`freeze_check`), so a number
reported here cannot have come from a tuned rule.

Reports counts AND error identities: a better aggregate can still hide a newly
fabricated hierarchy, so every candidate false join is printed individually with the
evidence that produced it, and the two error sets are compared against shipped
behaviour rather than merely counted.

    uv run python docs/research/pdf-heading-identity/holdout/score_holdout.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "frozen"))

import frozen_candidate as FC  # noqa: E402
from freeze_check import verify  # noqa: E402

RES = HERE.parent / "results"


def load():
    runs = [json.loads(x) for x in (RES / "holdout-runs.jsonl").open()]
    typo = {}
    for line in (RES / "holdout-typography.jsonl").open():
        r = json.loads(line)
        typo[(r["bill"], r["version"], r["page"], r["line"])] = r["hist"]
    return runs, typo


def truth_of(run):
    g = {}
    for gi, grp in enumerate(run["truth"]):
        for i in grp:
            g[i] = gi
    return [FC.SPLIT if g[i] != g[i + 1] else FC.JOIN for i in range(len(run["texts"]) - 1)]


def main() -> None:
    digest = verify()
    runs, typo = load()

    by_doc = defaultdict(list)
    for r in runs:
        by_doc[(r["bill"], r["version"])].append(r)
    vocab = {doc: FC.bootstrap(rs) for doc, rs in by_doc.items()}

    resolved = [r for r in runs if r["status"] == "resolved" and len(r["texts"]) > 1]
    rows = []
    for r in resolved:
        acc, con = vocab[(r["bill"], r["version"])]

        def prof(k, _r=r):
            return typo.get((_r["bill"], _r["version"], _r["pages"][k], _r["lines"][k]))

        for i, t in enumerate(truth_of(r)):
            cand, clause = FC.decide(r, i, acc, con, prof)
            ship, sclause = FC.shipped_decide(r, i)
            rows.append(
                {
                    "run": r,
                    "i": i,
                    "truth": t,
                    "cand": cand,
                    "clause": clause,
                    "ship": ship,
                    "sclause": sclause,
                    "cu": FC.caps_per_word(r["texts"][i], prof(i)),
                    "cl": FC.caps_per_word(r["texts"][i + 1], prof(i + 1)),
                    "slack": FC.slack(r["geoms"][i], r["geoms"][i + 1], r["column_width"]),
                }
            )

    def err(row, key):
        if row["truth"] == FC.SPLIT and row[key] == FC.JOIN:
            return "false_join"
        if row["truth"] == FC.JOIN and row[key] == FC.SPLIT:
            return "missed_join"
        return "correct"

    print(f"frozen digest : {digest}")
    print(f"T             : {FC.T}")
    print(f"documents     : {len(by_doc)}   bills: {len({d[0] for d in by_doc})}")
    unresolved = [r for r in runs if r["status"] != "resolved" and len(r["texts"]) > 1]
    print(f"boundaries scored : {len(rows)}   (unresolved multi-line runs excluded: {len(unresolved)})")
    print(f"true wraps  : {sum(1 for r in rows if r['truth'] == FC.JOIN)}")
    print(f"true stacks : {sum(1 for r in rows if r['truth'] == FC.SPLIT)}")

    for key, label in (("ship", "shipped"), ("cand", "frozen candidate")):
        c = Counter(err(r, key) for r in rows)
        tw = sum(1 for r in rows if r["truth"] == FC.JOIN)
        ts = sum(1 for r in rows if r["truth"] == FC.SPLIT)
        cj, cs = tw - c["missed_join"], ts - c["false_join"]
        prec = cj / (cj + c["false_join"]) if (cj + c["false_join"]) else float("nan")
        rec = cj / tw if tw else float("nan")
        print(
            f"\n{label:<18} correct_joins={cj:<5} correct_stacks={cs:<5} "
            f"false_joins={c['false_join']:<5} missed_joins={c['missed_join']:<5}"
        )
        print(f"{'':<18} join precision={prec:.4f}  join recall={rec:.4f}")

    print("\n=== deciding clause, frozen candidate ===")
    for k, v in Counter(r["clause"] for r in rows).most_common():
        print(f"   {k:<34}{v:>6}")

    print("\n=== PER BILL ===")
    hdr = (
        f"{'bill':<14}{'vers':>5}{'wraps':>7}{'stacks':>7}"
        f"{'shipFJ':>8}{'candFJ':>8}{'shipMJ':>8}{'candMJ':>8}{'unres':>7}"
    )
    print(hdr)
    per_bill = defaultdict(list)
    for r in rows:
        per_bill[r["run"]["bill"]].append(r)
    unres_bill = Counter(r["bill"] for r in unresolved)
    vers_bill = defaultdict(set)
    for d in by_doc:
        vers_bill[d[0]].add(d[1])
    for bill in sorted(per_bill):
        rs = per_bill[bill]
        sc = Counter(err(r, "ship") for r in rs)
        cc = Counter(err(r, "cand") for r in rs)
        print(
            f"{bill:<14}{len(vers_bill[bill]):>5}"
            f"{sum(1 for r in rs if r['truth'] == FC.JOIN):>7}{sum(1 for r in rs if r['truth'] == FC.SPLIT):>7}"
            f"{sc['false_join']:>8}{cc['false_join']:>8}{sc['missed_join']:>8}{cc['missed_join']:>8}"
            f"{unres_bill[bill]:>7}"
        )

    print("\n=== BY LEGISLATIVE STAGE ===")
    per_stage = defaultdict(list)
    for r in rows:
        per_stage[r["run"]["version"]].append(r)
    print(f"{'stage':<8}{'bounds':>8}{'wraps':>7}{'stacks':>7}{'shipFJ':>8}{'candFJ':>8}{'shipMJ':>8}{'candMJ':>8}")
    for stage in sorted(per_stage):
        rs = per_stage[stage]
        sc = Counter(err(r, "ship") for r in rs)
        cc = Counter(err(r, "cand") for r in rs)
        print(
            f"{stage:<8}{len(rs):>8}{sum(1 for r in rs if r['truth'] == FC.JOIN):>7}"
            f"{sum(1 for r in rs if r['truth'] == FC.SPLIT):>7}"
            f"{sc['false_join']:>8}{cc['false_join']:>8}{sc['missed_join']:>8}{cc['missed_join']:>8}"
        )

    # ---- TASK 6: error identities -------------------------------------------
    def ident(r):
        return (r["run"]["bill"], r["run"]["version"], r["run"]["pages"][r["i"]], r["run"]["lines"][r["i"]])

    ship_fj = {ident(r) for r in rows if err(r, "ship") == "false_join"}
    cand_fj = {ident(r) for r in rows if err(r, "cand") == "false_join"}
    ship_mj = {ident(r) for r in rows if err(r, "ship") == "missed_join"}
    cand_mj = {ident(r) for r in rows if err(r, "cand") == "missed_join"}

    print("\n=== ERROR-SET IDENTITIES ===")
    print(f"1. novel false joins (candidate errs, shipped correct) : {len(cand_fj - ship_fj)}")
    print(f"2. novel missed joins (candidate errs, shipped correct): {len(cand_mj - ship_mj)}")
    print(f"3. candidate false joins subset of shipped false joins : {cand_fj <= ship_fj}")
    print(f"4. candidate missed joins subset of shipped missed joins: {cand_mj <= ship_mj}")
    print(f"   shipped FJ={len(ship_fj)} candFJ={len(cand_fj)} shipMJ={len(ship_mj)} candMJ={len(cand_mj)}")

    print(f"\n=== EVERY CANDIDATE FALSE JOIN ({len(cand_fj)}) ===")
    for r in rows:
        if err(r, "cand") != "false_join":
            continue
        run, i = r["run"], r["i"]
        novel = ident(r) not in ship_fj
        print(f"\n  {'*** NOVEL ***' if novel else '(shipped errs here too)'}")
        print(f"  {run['bill']}/{run['version']}  p{run['pages'][i]} L{run['lines'][i]}")
        print(f"    upper : {run['texts'][i]!r}")
        print(f"    lower : {run['texts'][i + 1]!r}")
        print(f"    XML truth : {run['truth']}  -> two logical headings (STACK)")
        print(f"    shipped   : {r['ship']} ({r['sclause']})")
        print(f"    candidate : {r['cand']} ({r['clause']})")
        cu = f"{r['cu']:.3f}" if r["cu"] is not None else "None"
        cl = f"{r['cl']:.3f}" if r["cl"] is not None else "None"
        sl = f"{r['slack']:.1f}" if r["slack"] is not None else "None"
        print(f"    evidence  : caps/word upper={cu} lower={cl} (T={FC.T})  slack={sl}")

    novel_mj = [r for r in rows if err(r, "cand") == "missed_join" and ident(r) not in ship_mj]
    print(f"\n=== NOVEL MISSED JOINS ({len(novel_mj)}) ===")
    for r in novel_mj[:20]:
        run, i = r["run"], r["i"]
        print(f"  {run['bill']}/{run['version']} p{run['pages'][i]}L{run['lines'][i]} [{r['clause']}]")
        print(f"    {run['texts'][i]!r} + {run['texts'][i + 1]!r}")

    (RES / "holdout-score.json").write_text(
        json.dumps(
            {
                "frozen_digest": digest,
                "T": FC.T,
                "boundaries": len(rows),
                "shipped": dict(Counter(err(r, "ship") for r in rows)),
                "candidate": dict(Counter(err(r, "cand") for r in rows)),
                "novel_false_joins": len(cand_fj - ship_fj),
                "novel_missed_joins": len(cand_mj - ship_mj),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
