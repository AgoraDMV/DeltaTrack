"""V5 — score every path against the independently adjudicated boundaries.

Joins `v04_adjudication.json` (written and committed first) to `v04_key.json`.

The four columns `RESULTS-HYBRID.md` implicitly compares, made explicit:

    pdfium      did PDFium put a space between these two glyphs (read or generated)?
    hybrid      what `reconstruct_hybrid.py` emits. This is PDFium's answer BY
                CONSTRUCTION -- the hybrid layer applies no spacing rule of its own, it
                joins the engine's characters in engine order. Reported as its own column
                only so that the identity is visible rather than implied.
    glyph       the shipped rule, ink-gap > 0.25 x font size, as `reconstruct.py` applies it.
    pdfminer    did pdfminer put a space there (an `LTAnno` or a literal space `LTChar`)?

Also re-runs §4's separability question against the INDEPENDENT labels rather than
against PDFium's, which is the substitution the review asked for: if the two class
distributions of gap/size overlap under adjudicated labels too, then the supported claim
is "no single global gap/size threshold can perfectly classify these independently
adjudicated boundaries" -- and no more than that.

UNREADABLE items are excluded from accuracy and reported separately. An item nobody could
adjudicate is not evidence for or against any path.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

PATHS = ("pdfium", "hybrid", "glyph", "pdfminer")


def path_decision(item: dict, path: str) -> bool | None:
    if path == "pdfium":
        return item["pdfium_space"]
    if path == "hybrid":
        # Identical to pdfium by construction: reconstruct_hybrid._line_text joins the
        # engine's characters and applies no spacing rule.
        return item["pdfium_space"]
    if path == "glyph":
        return item["glyph_threshold_space"]
    if path == "pdfminer":
        return item["pdfminer_space"]
    raise ValueError(path)


def main() -> None:
    key = json.loads((RESULTS / "v04_key.json").read_text())
    adj = json.loads((RESULTS / "v04_adjudication.json").read_text())["answers"]
    items = {it["id"]: it for it in key["items"]}

    scored, unreadable = [], []
    for cid, a in adj.items():
        if a["v"] == "UNREADABLE":
            unreadable.append((cid, items[cid]["stratum"], a.get("note", "")))
            continue
        scored.append((cid, items[cid], a["v"] == "BOUNDARY", a["c"]))

    # ---- intra-adjudicator consistency, checked before anything is concluded ----------
    # A stimulus is the same stimulus when the two characters, the gap, the size and the
    # font are all identical. If the same stimulus got different answers, the adjudicator
    # is demonstrably unreliable on that class and the primary score inherits the noise.
    # This is computed from the adjudication and the pair geometry only -- no path's
    # answer is consulted to define it.
    def stim(it: dict) -> tuple:
        return (
            it["prev_ch"],
            it["next_ch"],
            round(it["gap"], 3),
            round(it["size"], 2),
            it["prev_font"],
            it["next_font"],
        )

    groups: dict[tuple, list] = defaultdict(list)
    for cid, it, truth, _q in scored:
        groups[stim(it)].append((cid, truth))
    inconsistent = {k: v for k, v in groups.items() if len({t for _c, t in v}) > 1}
    inconsistent_ids = {cid for v in inconsistent.values() for cid, _t in v}

    out: dict = {
        "adjudicated": len(adj),
        "scored": len(scored),
        "unreadable": [{"id": c, "stratum": s, "note": n} for c, s, n in unreadable],
        "truth_boundaries": sum(1 for _c, _i, t, _q in scored if t),
        "truth_non_boundaries": sum(1 for _c, _i, t, _q in scored if not t),
        "overall": {},
        "by_stratum": {},
        "high_confidence_only": {},
        "disagreements": [],
    }

    def tally(rows, path):
        tp = fp = tn = fn = na = 0
        for _cid, it, truth, _q in rows:
            d = path_decision(it, path)
            if d is None:
                na += 1
                continue
            if d and truth:
                tp += 1
            elif d and not truth:
                fp += 1
            elif not d and truth:
                fn += 1
            else:
                tn += 1
        n = tp + fp + tn + fn
        return {
            "n": n,
            "not_available": na,
            "correct": tp + tn,
            "accuracy": round((tp + tn) / n, 4) if n else None,
            "missed_boundaries": fn,
            "spurious_boundaries": fp,
            "boundary_recall": round(tp / (tp + fn), 4) if (tp + fn) else None,
            "non_boundary_precision": round(tn / (tn + fp), 4) if (tn + fp) else None,
        }

    for p in PATHS:
        out["overall"][p] = tally(scored, p)
        out["high_confidence_only"][p] = tally([r for r in scored if r[3] == "high"], p)

    # Two sensitivity analyses on the inconsistent class. Both are POST-HOC -- computed
    # after the key was opened -- and both are labelled as such, because both move the
    # numbers in the same direction and that is exactly when a post-hoc adjustment needs
    # to be visible rather than folded in.
    #
    #   dropped   the class is declared unadjudicated. Requires choosing no answer, so it
    #             cannot express a preference for any path. This is the honest default.
    #   resolved  the class is resolved to NO_BOUNDARY on the stated reading that a margin
    #             line number's two digits are one token. Stronger, and more assailable.
    out["intra_adjudicator_consistency"] = {
        "repeated_stimuli_groups": len([g for g in groups.values() if len(g) > 1]),
        "inconsistent_groups": len(inconsistent),
        "inconsistent_items": sorted(inconsistent_ids),
        "detail": [
            {
                "stimulus": f"{k[0]!r}|{k[1]!r} gap={k[2]} size={k[3]} font={k[4]}",
                "answers": {cid: ("BOUNDARY" if t else "NO_BOUNDARY") for cid, t in v},
            }
            for k, v in inconsistent.items()
        ],
    }
    out["sensitivity_inconsistent_dropped"] = {
        "n": len([r for r in scored if r[0] not in inconsistent_ids]),
        **{p: tally([r for r in scored if r[0] not in inconsistent_ids], p) for p in PATHS},
    }
    resolved = [(c, i, (False if c in inconsistent_ids else t), q) for c, i, t, q in scored]
    out["sensitivity_inconsistent_resolved_to_no_boundary"] = {
        "n": len(resolved),
        "post_hoc": True,
        **{p: tally(resolved, p) for p in PATHS},
    }

    by_s: dict[str, list] = defaultdict(list)
    for row in scored:
        by_s[row[1]["stratum"]].append(row)
    for s, rows in sorted(by_s.items()):
        out["by_stratum"][s] = {
            "n": len(rows),
            "truth_boundaries": sum(1 for r in rows if r[2]),
            **{p: tally(rows, p) for p in PATHS},
        }

    for cid, it, truth, q in scored:
        d = {p: path_decision(it, p) for p in PATHS}
        if len({v for v in d.values() if v is not None}) > 1 or any(
            v is not truth for v in d.values() if v is not None
        ):
            out["disagreements"].append(
                {
                    "id": cid,
                    "stratum": it["stratum"],
                    "doc": it["doc"],
                    "page": it["page"],
                    "pair": f"{it['prev_ch']}|{it['next_ch']}",
                    "gap": round(it["gap"], 3),
                    "ratio": round(it["ratio"], 4),
                    "truth": "BOUNDARY" if truth else "NO_BOUNDARY",
                    "confidence": q,
                    **{p: d[p] for p in PATHS},
                }
            )

    # ---- §4's separability question, re-asked against the independent labels -----------
    bnd = sorted(it["ratio"] for _c, it, t, _q in scored if t)
    intra = sorted(it["ratio"] for _c, it, t, _q in scored if not t)
    best = None
    if bnd and intra:
        for tv in sorted({round(r, 6) for r in bnd + intra}):
            miss = sum(1 for r in bnd if r <= tv)
            spur = sum(1 for r in intra if r > tv)
            if best is None or miss + spur < best[1]:
                best = (tv, miss + spur, miss, spur)
    out["separability_under_independent_labels"] = {
        "n_boundary": len(bnd),
        "n_intra": len(intra),
        "boundary_ratio_min": round(bnd[0], 4) if bnd else None,
        "boundary_ratio_median": round(statistics.median(bnd), 4) if bnd else None,
        "intra_ratio_median": round(statistics.median(intra), 4) if intra else None,
        "intra_ratio_max": round(intra[-1], 4) if intra else None,
        "distributions_overlap": bool(bnd and intra and bnd[0] <= intra[-1]),
        "best_threshold": round(best[0], 4) if best else None,
        "best_threshold_errors": best[1] if best else None,
        "shipped_0.25_errors": (
            sum(1 for r in bnd if r <= 0.25) + sum(1 for r in intra if r > 0.25) if bnd and intra else None
        ),
    }

    (RESULTS / "v05_boundary_scores.json").write_text(json.dumps(out, indent=1))

    print(
        f"scored {out['scored']} of {out['adjudicated']} "
        f"({out['truth_boundaries']} true boundaries, {out['truth_non_boundaries']} true non-boundaries); "
        f"{len(out['unreadable'])} unreadable\n"
    )
    print(f"{'path':<10} {'acc':>7} {'missed':>7} {'spurious':>9} {'recall':>7}   (n)")
    for p in PATHS:
        t = out["overall"][p]
        print(
            f"{p:<10} {str(t['accuracy']):>7} {t['missed_boundaries']:>7} {t['spurious_boundaries']:>9} "
            f"{str(t['boundary_recall']):>7}   ({t['n']}, n/a {t['not_available']})"
        )
    print("\nby stratum (accuracy):")
    print(f"{'stratum':<22} {'n':>3} {'true bnd':>9} " + " ".join(f"{p:>9}" for p in PATHS))
    for s, d in out["by_stratum"].items():
        print(
            f"{s:<22} {d['n']:>3} {d['truth_boundaries']:>9} " + " ".join(f"{str(d[p]['accuracy']):>9}" for p in PATHS)
        )
    ic = out["intra_adjudicator_consistency"]
    print(
        f"\nintra-adjudicator consistency: {ic['inconsistent_groups']} inconsistent repeated stimuli, "
        f"items {ic['inconsistent_items']}"
    )
    for d in ic["detail"]:
        print(f"   {d['stimulus']}  ->  {d['answers']}")
    for tag in ("sensitivity_inconsistent_dropped", "sensitivity_inconsistent_resolved_to_no_boundary"):
        print(f"\n{tag} (POST-HOC, n={out[tag]['n']}):")
        for p in PATHS:
            t = out[tag][p]
            print(
                f"   {p:<10} acc={str(t['accuracy']):>7} missed={t['missed_boundaries']} "
                f"spurious={t['spurious_boundaries']}"
            )
    print("\nseparability under INDEPENDENT labels:")
    print(json.dumps(out["separability_under_independent_labels"], indent=1))
    print(f"\ndisagreements ({len(out['disagreements'])}):")
    for d in out["disagreements"]:
        print(
            f"  {d['id']} {d['stratum']:<20} {d['pair']!r:<12} ratio={d['ratio']:<8} truth={d['truth']:<12} "
            f"pdfium={d['pdfium']} glyph={d['glyph']} pdfminer={d['pdfminer']}"
        )
    print(f"\nwrote {RESULTS / 'v05_boundary_scores.json'}")


if __name__ == "__main__":
    main()
