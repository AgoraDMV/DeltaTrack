"""Candidate 3 evaluation and its negative controls.

CANDIDATE 3, complete (no document-local learned state anywhere):

    C1  upper line ends in a wrap hyphen                       -> JOIN
    C2  caps_per_word(upper) >= T and caps_per_word(lower) < T -> SPLIT
    C3  fullness slack is None (geometry absent)               -> SPLIT   (fail closed)
    C4  fullness slack >= 0                                    -> SPLIT
    C5  otherwise                                              -> JOIN

T = 0.5. Differences from frozen candidate 1: the vocabulary clauses D1/D2/D3 are gone
entirely, and the unconditional "both sides even small caps -> JOIN" clause (D6) is gone,
so those boundaries now reach the fullness test instead of short-circuiting past it.

Controls (each must turn a known case red):
    M1  remove the fullness test (C3/C4 -> JOIN)      the OIG confounders must false-join
    M2  invert the fullness comparison               known wraps must split
    M3  restore D6 ahead of fullness                 the OIG confounders must false-join
    M4  remove C2                                    caps-and-small-caps containers must merge
    M5  make C3 fail OPEN (missing geometry -> JOIN) must be inert here, and is reported so
"""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "docs" / "research" / "pdf-heading-identity" / "frozen"))
import frozen_candidate as FC  # noqa: E402
from freeze_check import verify  # noqa: E402

RES = Path(__file__).resolve().parents[1] / "results"
T = FC.T


def load():
    runs = []
    for rn, tag in (("heading-runs.jsonl", "dev"), ("holdout-runs.jsonl", "holdout")):
        for line in (RES / rn).open():
            r = json.loads(line); r["corpus"] = tag; runs.append(r)
    typo = {}
    for tn in ("within-line-typography.jsonl", "holdout-typography.jsonl"):
        for line in (RES / tn).open():
            r = json.loads(line); typo[(r["bill"], r["version"], r["page"], r["line"])] = r["hist"]
    return runs, typo


runs, typo = load()


def truth(run):
    g = {}
    for gi, grp in enumerate(run["truth"]):
        for i in grp: g[i] = gi
    return [FC.SPLIT if g[i] != g[i + 1] else FC.JOIN for i in range(len(run["texts"]) - 1)]


def caps(run, k):
    return FC.caps_per_word(run["texts"][k], typo.get((run["bill"], run["version"], run["pages"][k], run["lines"][k])))


def decide(run, i, mutation="none"):
    cu, cl = caps(run, i), caps(run, i + 1)
    sl = FC.slack(run["geoms"][i], run["geoms"][i + 1], run["column_width"])
    if run["texts"][i].rstrip().endswith(FC.WRAP_HYPHENS):
        return FC.JOIN, "C1_hyphen"
    if mutation != "M4" and cu is not None and cl is not None and cu >= T and cl < T:
        return FC.SPLIT, "C2_caps_container"
    if mutation == "M3" and cu is not None and cl is not None and cu < T and cl < T:
        return FC.JOIN, "M3_restored_D6"
    if mutation == "M1":
        return FC.JOIN, "M1_no_fullness"
    if sl is None:
        return (FC.JOIN, "M5_fail_open") if mutation == "M5" else (FC.SPLIT, "C3_no_geometry")
    if mutation == "M2":
        return (FC.JOIN, "M2_inverted") if sl >= 0.0 else (FC.SPLIT, "M2_inverted")
    return (FC.SPLIT, "C4_fullness_split") if sl >= 0.0 else (FC.JOIN, "C5_fullness_join")


resolved = [r for r in runs if r["status"] == "resolved" and len(r["texts"]) > 1]
sv = defaultdict(set)
for r in resolved: sv[r["bill"]].add(r["version"])
multi = {b for b, s in sv.items() if len(s) > 1}


def ident(r, i): return (r["bill"], r["version"], r["pages"][i], r["lines"][i])


def score(mutation="none"):
    fj, mj, clauses = set(), set(), Counter()
    for r in resolved:
        for i, t in enumerate(truth(r)):
            d, c = decide(r, i, mutation); clauses[c] += 1
            if t == FC.SPLIT and d == FC.JOIN: fj.add(ident(r, i))
            if t == FC.JOIN and d == FC.SPLIT: mj.add(ident(r, i))
    return fj, mj, clauses


def instability(mutation="none"):
    occ = defaultdict(list)
    for r in resolved:
        if r["bill"] not in multi: continue
        ts = r["texts"]; groups, cur = [], [0]
        for i in range(len(ts) - 1):
            d, _ = decide(r, i, mutation)
            if d == FC.SPLIT: groups.append(cur); cur = [i + 1]
            else: cur.append(i + 1)
        groups.append(cur)
        idx = {}
        for g in groups:
            t = FC.join_lines([ts[k] for k in g])
            for k in g: idx[k] = t
        for g in r["truth"]:
            key = FC.normalize_text(FC.join_lines([ts[k] for k in g]))
            occ[(r["bill"], key)].append((r["version"], r["pages"][g[0]], r["lines"][g[0]], idx[g[-1]]))
    comparable = unstable = 0; bad = []
    for (b, key), rows in occ.items():
        if len({v for v, _, _, _ in rows}) < 2: continue
        comparable += 1
        if len({FC.normalize_text(e) for _, _, _, e in rows}) > 1:
            unstable += 1; bad.append((b, key, rows))
    return comparable, unstable, bad


def confounders():
    out = []
    for r in resolved:
        for i, t in enumerate(truth(r)):
            cu, cl = caps(r, i), caps(r, i + 1)
            if cu is None or cl is None or not (cu < T and cl < T): continue
            if r["texts"][i].rstrip().endswith(FC.WRAP_HYPHENS): continue
            out.append((r, i, t))
    return out


def main() -> None:
    print(f"frozen-candidate-1 digest (reference): {verify()}")
    ship_fj, ship_mj = set(), set()
    for r in resolved:
        for i, t in enumerate(truth(r)):
            d, _ = FC.shipped_decide(r, i)
            if t == FC.SPLIT and d == FC.JOIN: ship_fj.add(ident(r, i))
            if t == FC.JOIN and d == FC.SPLIT: ship_mj.add(ident(r, i))
    n = sum(len(r["texts"]) - 1 for r in resolved)
    print(f"combined development evidence: {n} boundaries, {len(resolved)} runs, {len(multi)} multi-version bills")
    print(f"shipped: false_joins={len(ship_fj)} missed_joins={len(ship_mj)}")

    fj, mj, clauses = score()
    cmp_, uns, bad = instability()
    print(f"\nCANDIDATE 3: false_joins={len(fj)} (novel {len(fj - ship_fj)}) "
          f"missed_joins={len(mj)} (novel {len(mj - ship_mj)})")
    print(f"             cross-version comparable={cmp_} UNSTABLE={uns}")
    print(f"             clause usage: {clauses.most_common()}")

    pop = confounders()
    conf = [(r, i) for r, i, t in pop if t == FC.SPLIT]
    wrap = [(r, i) for r, i, t in pop if t == FC.JOIN]
    ok_conf = sum(1 for r, i in conf if decide(r, i)[0] == FC.SPLIT)
    ok_wrap = sum(1 for r, i in wrap if decide(r, i)[0] == FC.JOIN)
    print(f"\nCONFOUNDER CLASS (both lines even small caps):")
    print(f"  containers correctly SPLIT : {ok_conf}/{len(conf)}")
    print(f"  at-risk wraps preserved    : {ok_wrap}/{len(wrap)}")

    print(f"\n=== every candidate-3 false join ({len(fj)}) ===")
    for r in resolved:
        for i, t in enumerate(truth(r)):
            if ident(r, i) not in fj: continue
            d, c = decide(r, i)
            sl = FC.slack(r["geoms"][i], r["geoms"][i + 1], r["column_width"])
            print(f"  {r['bill']}/{r['version']} p{r['pages'][i]}L{r['lines'][i]} [{c}]  "
                  f"caps={caps(r,i)}/{caps(r,i+1)} slack={sl:.1f}")
            print(f"     {r['texts'][i]!r} + {r['texts'][i+1]!r}")

    print(f"\n=== cross-version instabilities ({uns}) ===")
    for b, key, rows in bad:
        print(f"  {b} {key!r}")
        for v, p, l, e in sorted(rows):
            mark = "OK " if FC.normalize_text(e) == key else "***"
            print(f"     {mark} {v} p{p}L{l} -> {e!r}")

    print("\n=== NEGATIVE CONTROLS ===")
    print(f"{'mutation':<22}{'falseJ':>8}{'missedJ':>9}{'UNSTABLE':>10}{'  confounders SPLIT'}")
    for m, label in (("none", "none (candidate 3)"), ("M1", "M1 no fullness"), ("M2", "M2 inverted fullness"),
                     ("M3", "M3 D6 restored"), ("M4", "M4 no caps clause"), ("M5", "M5 fail OPEN")):
        f2, m2, _ = score(m)
        _c, u2, _b = instability(m)
        okc = sum(1 for r, i in conf if decide(r, i, m)[0] == FC.SPLIT)
        print(f"{label:<22}{len(f2):>8}{len(m2):>9}{u2:>10}      {okc}/{len(conf)}")


if __name__ == "__main__":
    main()
