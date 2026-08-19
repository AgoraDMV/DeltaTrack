"""Apply frozen candidate 4 to a runs/typography/tracking dataset. Shared by the
development check and the holdout scorer so both run the same code."""
from __future__ import annotations
import json, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import frozen_candidate4 as C4  # noqa: E402
from freeze_check4 import verify  # noqa: E402


def load(results_dir: Path, runs_name: str, typo_name: str, track_name: str):
    runs = [json.loads(x) for x in (results_dir / runs_name).open()]
    typo, track, gaps = {}, {}, {}
    for line in (results_dir / typo_name).open():
        r = json.loads(line)
        typo[(r["bill"], r["version"], r["page"], r["line"])] = r["hist"]
    for line in (results_dir / track_name).open():
        r = json.loads(line)
        track[(r["bill"], r["version"], r["page"], r["line"])] = r["tracking_mean"]
        gaps[(r["bill"], r["version"], r["page"], r["line"])] = r["n_gaps"]
    return runs, typo, track, gaps


def truth_of(run):
    g = {}
    for gi, grp in enumerate(run["truth"]):
        for i in grp:
            g[i] = gi
    return [C4.SPLIT if g[i] != g[i + 1] else C4.JOIN for i in range(len(run["texts"]) - 1)]


def track_medians(track, gaps):
    per_doc = defaultdict(dict)
    per_gaps = defaultdict(dict)
    for k, v in track.items():
        per_doc[(k[0], k[1])][k] = v
        per_gaps[(k[0], k[1])][k] = gaps.get(k, 0)
    return {d: C4.document_track_median(per_doc[d], per_gaps[d]) for d in per_doc}


def decide_for(run, i, typo, track, medians):
    b, v = run["bill"], run["version"]

    def prof(k):
        return typo.get((b, v, run["pages"][k], run["lines"][k]))

    return C4.decide(
        run["texts"], run["geoms"], run["column_width"], prof,
        track.get((b, v, run["pages"][i], run["lines"][i])),
        medians.get((b, v)), i,
    )


def score(runs, typo, track, gaps):
    medians = track_medians(track, gaps)
    resolved = [r for r in runs if r["status"] == "resolved" and len(r["texts"]) > 1]
    from collections import Counter
    fj, mj, ship_fj, ship_mj, clauses = set(), set(), set(), set(), Counter()
    for r in resolved:
        for i, t in enumerate(truth_of(r)):
            d, c = decide_for(r, i, typo, track, medians)
            clauses[c] += 1
            key = (r["bill"], r["version"], r["pages"][i], r["lines"][i])
            if t == C4.SPLIT and d == C4.JOIN:
                fj.add(key)
            if t == C4.JOIN and d == C4.SPLIT:
                mj.add(key)
            sd, _sc = C4.shipped_decide(r["texts"], i)
            if t == C4.SPLIT and sd == C4.JOIN:
                ship_fj.add(key)
            if t == C4.JOIN and sd == C4.SPLIT:
                ship_mj.add(key)
    return {
        "digest": verify(), "runs": len(resolved),
        "boundaries": sum(len(r["texts"]) - 1 for r in resolved),
        "false_joins": fj, "missed_joins": mj,
        "shipped_false_joins": ship_fj, "shipped_missed_joins": ship_mj,
        "clauses": clauses, "resolved": resolved, "medians": medians,
    }
