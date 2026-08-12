"""H7 — two arithmetic corrections to H3, neither of which needs new extraction.

**A. The engine-change cost was an UNPAIRED subtraction.** H3 reported pdfminer's own text
decision at 0.8065 and the extended rule at 0.9683 and called the gap 16.2 points. Those
were scored on different populations: pdfminer's own column covers 62 pairs, because phase
1 could not locate the other 7, while the extended column covers all 69. A difference of
differences across different denominators is not a cost of changing engines, and the sign
of the bias is unknown without checking. This probe scores both paths on **exactly the
pairs where both have a decision**, and reports the discordant counts, which is the
quantity a paired comparison actually licenses.

PyMuPDF already had equal coverage, so its number should not move. Presenting it the same
way is the control: if the paired machinery changed PyMuPDF's delta, the machinery is wrong.

**B. N1 claimed more than it demonstrated.** H3 described N1 as reproducing phase 2's
extended result "item by item". But `g04_boundary_scores.json` persists only the
extended-vs-PDFium DISAGREEMENTS, and there were none, so H3 reconstructed the expected
value as "equal to `pdfium_own`" and compared against that. That tests agreement with
PDFium's engine-space decision. It does not compare against a stored phase-2 vector,
because no such vector exists on disk.

The fix here is the one that costs least and proves most: **re-run phase 2's own `g04`
code path** and materialise the complete 72-decision vector it computes in memory, then
compare that against phase 3's adapter-derived vector. The two are genuinely different
implementations of the extraction (`g04._page_pairs` reads the text page inline;
`pdfium_extended.extract` is the adapter), so this is a real replication.

`g04_boundary_scores.json` is NOT modified. `g04.main()` is additionally run to a scratch
path and its published blocks compared with the frozen artifact, so that a drift between
the imported functions and the committed entry point would surface rather than hide.

Read-only apart from a scratch file under the system temp directory. Writes JSON only
under `validation/phase3/results/`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
P1 = HERE.parents[0] / "results"
P2 = HERE.parents[0] / "phase2"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(P2))

import g04_score_boundaries as G4  # noqa: E402
from reconstruct_extended import wants_space  # noqa: E402

INCONSISTENT = {"B30", "B32", "B36", "B42", "B55", "B60"}


# --------------------------------------------------------------------------- A: paired


def _tally(rows: list[tuple[bool, bool]]) -> dict:
    """rows are (decision, truth)."""
    tp = sum(1 for d, t in rows if d and t)
    tn = sum(1 for d, t in rows if not d and not t)
    fp = sum(1 for d, t in rows if d and not t)
    fn = sum(1 for d, t in rows if not d and t)
    n = len(rows)
    return {
        "n": n,
        "accuracy": round((tp + tn) / n, 4) if n else None,
        "errors": fp + fn,
        "missed_boundaries": fn,
        "spurious_boundaries": fp,
    }


def paired(per_pair: dict, truth: dict, backend: str, drop_inconsistent: bool) -> dict:
    own_col, ext_col = f"{backend}_own", f"{backend}_ext"
    ids = []
    for cid, d in per_pair.items():
        if cid not in truth:
            continue
        if drop_inconsistent and cid in INCONSISTENT:
            continue
        if d.get(own_col) is None or d.get(ext_col) is None:
            continue
        ids.append(cid)

    own_rows = [(per_pair[c][own_col], truth[c]) for c in ids]
    ext_rows = [(per_pair[c][ext_col], truth[c]) for c in ids]
    own_t, ext_t = _tally(own_rows), _tally(ext_rows)

    # The discordant counts are what a paired comparison is FOR. A delta of +N points can
    # come from N one-way corrections or from 5N corrections against 4N regressions, and
    # those are different claims about the risk of changing engines.
    own_right_ext_wrong = [c for c in ids if (per_pair[c][own_col] == truth[c]) and (per_pair[c][ext_col] != truth[c])]
    ext_right_own_wrong = [c for c in ids if (per_pair[c][ext_col] == truth[c]) and (per_pair[c][own_col] != truth[c])]
    return {
        "paired_n": len(ids),
        "own": own_t,
        "extended": ext_t,
        "paired_delta_points": (
            round((ext_t["accuracy"] - own_t["accuracy"]) * 100, 2)
            if own_t["accuracy"] is not None and ext_t["accuracy"] is not None
            else None
        ),
        "discordant": {
            "extended_right_own_wrong": len(ext_right_own_wrong),
            "own_right_extended_wrong": len(own_right_ext_wrong),
            "ids_extended_fixed": sorted(ext_right_own_wrong),
            "ids_extended_broke": sorted(own_right_ext_wrong),
        },
        "excluded_for_no_paired_decision": sorted(
            c
            for c, d in per_pair.items()
            if c in truth
            and (not drop_inconsistent or c not in INCONSISTENT)
            and (d.get(own_col) is None or d.get(ext_col) is None)
        ),
    }


# ------------------------------------------------------------------ B: g04 replication


def replicate_g04() -> dict:
    """Re-run phase 2's g04 path and materialise the full 72-decision extended vector."""
    key = json.loads((P1 / "v04_key.json").read_text())
    items = key["items"]
    by_doc_page: dict[tuple, list] = {}
    for it in items:
        by_doc_page.setdefault((it["doc"], it["page"]), []).append(it)

    vector: dict[str, bool] = {}
    engine: dict[str, bool] = {}
    missing = []
    for (rel, page_no), its in sorted(by_doc_page.items()):
        pairs = G4._page_pairs(REPO / rel, page_no)
        for it in its:
            k = (round(it["prev_x1"], 2), round(it["next_x0"], 2))
            p = pairs.get(k)
            if p is None:
                missing.append(it["id"])
                continue
            # Exactly the expression in g04.main.
            vector[it["id"]] = wants_space(G4._ext_glyph(p["a"]), G4._ext_glyph(p["b"]))
            engine[it["id"]] = p["pdfium_space"]
    return {"extended": vector, "pdfium_own": engine, "missing": missing}


def frozen_artifact_still_reproduces() -> dict:
    """Run g04's committed entry point to a scratch path and diff its published blocks.

    Guards the replication above: if `g04.main()` no longer reproduced its own frozen
    result, the imported functions would be reproducing something else too, and the
    "different implementation" claim would be worthless.
    """
    frozen = json.loads((P2 / "results" / "g04_boundary_scores.json").read_text())
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "g04_rerun.json"
        r = subprocess.run(
            [sys.executable, str(P2 / "g04_score_boundaries.py"), "--out", str(out)],
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )
        if r.returncode != 0:
            return {"ran": False, "stderr": r.stderr[-400:]}
        fresh = json.loads(out.read_text())
    blocks = ("overall", "inconsistent_class_dropped_POST_HOC", "by_stratum", "extended_vs_pdfium_disagreements")
    return {
        "ran": True,
        "frozen_artifact_modified": False,
        "blocks_identical": {b: frozen.get(b) == fresh.get(b) for b in blocks},
        "all_identical": all(frozen.get(b) == fresh.get(b) for b in blocks),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=HERE / "results" / "h07_paired_and_replication.json")
    args = ap.parse_args()

    h03 = json.loads((HERE / "results" / "h03_cross_backend_scores.json").read_text())
    adj = json.loads((P1 / "v04_adjudication.json").read_text())["answers"]
    per_pair = h03["per_pair"]
    truth = {cid: a["v"] == "BOUNDARY" for cid, a in adj.items() if a["v"] != "UNREADABLE"}

    out: dict = {
        "A_paired_own_vs_extended": {
            "why": "H3's 16.2-point figure subtracted accuracies computed on different denominators",
            "primary_adjudication": {b: paired(per_pair, truth, b, False) for b in ("pdfminer", "pymupdf")},
            "POST_HOC_inconsistent_class_dropped": {
                b: paired(per_pair, truth, b, True) for b in ("pdfminer", "pymupdf")
            },
        }
    }

    rep = replicate_g04()
    assert not rep["missing"], f"g04 path could not relocate {rep['missing']}"
    mismatch_ext = [
        {"id": cid, "g04_path": v, "phase3_adapter": per_pair[cid]["pdfium_ext"]}
        for cid, v in rep["extended"].items()
        if per_pair[cid]["pdfium_ext"] != v
    ]
    mismatch_eng = [cid for cid, v in rep["pdfium_own"].items() if per_pair[cid]["pdfium_own"] != v]
    out["B_N1_replication"] = {
        "what_it_now_is": (
            "phase 2's g04 code path re-run and its COMPLETE 72-decision extended vector compared, "
            "item by item, against phase 3's adapter-derived vector"
        ),
        "what_it_was": (
            "a comparison against a value reconstructed as 'equal to pdfium_own', because "
            "g04_boundary_scores.json persists only disagreements and there were none"
        ),
        "vector_length": len(rep["extended"]),
        "extended_mismatches": mismatch_ext,
        "engine_decision_mismatches": mismatch_eng,
        "true_count": sum(1 for v in rep["extended"].values() if v),
        "false_count": sum(1 for v in rep["extended"].values() if not v),
        "full_vector": {cid: rep["extended"][cid] for cid in sorted(rep["extended"])},
        "frozen_g04_entry_point": frozen_artifact_still_reproduces(),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))

    print("A. PAIRED own vs extended\n")
    for label, key in (
        ("PRIMARY adjudication", "primary_adjudication"),
        ("POST-HOC, inconsistent class dropped", "POST_HOC_inconsistent_class_dropped"),
    ):
        print(f"  {label}")
        print(f"    {'backend':<10} {'path':<10} {'paired n':>9} {'accuracy':>9} {'errors':>7}")
        for b in ("pdfminer", "pymupdf"):
            d = out["A_paired_own_vs_extended"][key][b]
            for path in ("own", "extended"):
                t = d[path]
                print(f"    {b:<10} {path:<10} {d['paired_n']:>9} {str(t['accuracy']):>9} {t['errors']:>7}")
            print(
                f"    {'':<10} {'DELTA':<10} {'':>9} {str(d['paired_delta_points']) + ' pts':>9}"
                f"   discordant +{d['discordant']['extended_right_own_wrong']}"
                f"/-{d['discordant']['own_right_extended_wrong']}"
            )
        print()

    b = out["B_N1_replication"]
    print("B. N1 REPLICATION")
    print(f"    vector length          {b['vector_length']}")
    print(f"    extended mismatches    {len(b['extended_mismatches'])}  (must be 0)")
    print(f"    engine decision diffs  {len(b['engine_decision_mismatches'])}  (must be 0)")
    print(f"    vector true/false      {b['true_count']}/{b['false_count']}")
    print(f"    frozen g04 re-run      {b['frozen_g04_entry_point']}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
