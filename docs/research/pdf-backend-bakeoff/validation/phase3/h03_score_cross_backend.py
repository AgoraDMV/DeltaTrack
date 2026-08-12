"""H3 — does the SAME segmentation rule, fed each engine's OWN facts, give the same answer?

Phase 2 built one extended-glyph path (PDFium's) and scored it. From that it inferred a
portability property:

    "word quality if the backend changes: fixed -- the rule is ours"

That is a hypothesis, not a result. Phase 2 measured field AVAILABILITY on three backends
(`g03`) and ACCURACY on one (`g04`). This probe closes the gap by running the identical
`reconstruct_extended.wants_space` over each backend's own `origin_x` and `advance`, on the
frozen phase-1 sample, and scoring all of them against the same adjudication.

WHAT IS AND IS NOT REUSED.

  reused unchanged   `validation/results/v04_key.json` (the frozen 72 pairs)
                     `validation/results/v04_adjudication.json` (never reopened)
                     `phase2/reconstruct_extended.wants_space` (one rule, all backends)
                     the frozen `pdfminer_space` column, which is pdfminer's OWN text
                     decision as phase 1 recorded it
  new here           `pdfminer_extended.py`, `pymupdf_extended.py` -- each answering from
                     its own API only. No PDFium value crosses into either.

HOW A FROZEN PAIR IS LOCATED IN ANOTHER ENGINE. Not by character index, which is not
comparable across extractors. By PEN ORIGIN: `h01` measured that the three engines agree
on a character's origin to under 2e-4 pt, because all three are reading the same content
stream. So the join is (codepoint, |dx| <= 0.05 pt, |d baseline| <= 0.6 pt) and a pair is
mapped only when BOTH endpoints resolve uniquely. Anything else is reported as UNMAPPED
and is never scored as agreement or as disagreement.

NEGATIVE CONTROLS. Every one of these exists because the expected result here is a tie,
and a tie is exactly what a broken harness also produces.

  N1  PDFium-extended is recomputed here through the ADAPTER, and asserted equal, item by
      item, to phase 2's `g04` column, which was computed by different code. A harness
      that silently scored something else would break this.
  N2  each backend's advances are perturbed +-25 % and rescored. If the decisions do not
      move, the rule is not reading the advance at all and every rate above is vacuous.
  N3  pdfminer is rescored with `.adv` (the TEXT-space advance) in place of `.width`. h01
      showed those differ by the text-matrix scale, 8-14x on this corpus, so this must
      collapse. If it does not, the harness cannot see the field it claims to test.
  N4  coverage is asserted, not assumed: all 72 pairs must relocate in PDFium, and every
      backend's mapped/unmapped split is reported per stratum.
  N5  the FACTS are compared, not only the decisions: max |d origin_x| and max |d advance|
      between engines on the mapped pairs. If the answers agree because the inputs are
      numerically identical, that is the mechanism and it belongs in the finding.

Read-only. Writes JSON only under `validation/phase3/results/`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
P1 = HERE.parents[0] / "results"
P2 = HERE.parents[0] / "phase2"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(P2))

import pdfium_extended  # noqa: E402
import pdfminer_extended  # noqa: E402
import pymupdf_extended  # noqa: E402
from contract_extended import ADVANCE, BASELINE, CP, ORIGIN_X, SIZE, UPRIGHT  # noqa: E402
from g04_score_boundaries import _page_pairs  # noqa: E402
from reconstruct_extended import wants_space  # noqa: E402

ORIGIN_TOL = 0.05
BASELINE_TOL = 0.6
MAX_PAGE = 24  # the frozen sample never reaches beyond page 24 of any document


# ------------------------------------------------------------------ per-backend glyphs


def _glyphs_by_page(backend: str, rel: str, pages: list[int]) -> dict[int, list]:
    path = REPO / rel
    if backend == "pdfium":
        out, _ = pdfium_extended.extract(path, limit=max(pages))
        return {p.page_number: p.glyphs for p in out if p.page_number in pages}
    if backend == "pdfminer":
        out, _ = pdfminer_extended.extract(path, pages=pages)
        return {p.page_number: p.glyphs for p in out}
    if backend == "pymupdf":
        out, _ = pymupdf_extended.extract(path, pages=pages)
        return {p.page_number: p.glyphs for p in out}
    raise ValueError(backend)


def _locate(glyphs: list, cp: int, ox: float, baseline: float):
    """The unique upright glyph at this pen origin on this baseline, or None.

    Returns None both when nothing matches and when more than one does -- an ambiguous
    match is not evidence and must not be scored.
    """
    hits = [
        g
        for g in glyphs
        if g[CP] == cp
        and g[UPRIGHT]
        and abs(g[ORIGIN_X] - ox) <= ORIGIN_TOL
        and abs(g[BASELINE] - baseline) <= BASELINE_TOL
    ]
    return hits[0] if len(hits) == 1 else None


# --------------------------------------------------- PyMuPDF's OWN text decision


def _pymupdf_own_spaces(rel: str, page: int) -> list[dict]:
    """MuPDF's assembled structured text: ink chars in order, with a preceding-space flag.

    This is the counterpart of phase 1's `_pdfminer_page_spaces` and it deliberately uses
    a DIFFERENT API from the extended adapter. `get_texttrace()` is the raw device trace
    and inserts nothing; `get_text("rawdict")` is MuPDF's own text assembly and is where
    its word-boundary decision lives. Comparing the extended rule against the trace would
    compare the rule with itself.
    """
    import pymupdf

    d = pymupdf.open(str(REPO / rel))
    out: list[dict] = []
    try:
        pg = d[page - 1]
        h = pg.rect.height
        raw = pg.get_text("rawdict")
        for block in raw.get("blocks", ()):
            for line in block.get("lines", ()):
                pending = False
                for span in line.get("spans", ()):
                    for ch in span.get("chars", ()):
                        c = ch.get("c", "")
                        if not c:
                            continue
                        if not c.strip():
                            pending = True
                            continue
                        cp = ord(c)
                        if cp < 0x20:
                            cp = 0xFFFD
                        out.append(
                            {
                                "cp": cp,
                                "ox": ch["origin"][0],
                                "baseline": h - ch["origin"][1],
                                "space_before": pending,
                            }
                        )
                        pending = False
    finally:
        d.close()
    return out


def _pymupdf_own_decision(chars: list[dict], a, b) -> bool | None:
    hits = [
        c
        for c in chars
        if c["cp"] == b[CP] and abs(c["ox"] - b[ORIGIN_X]) <= 0.2 and abs(c["baseline"] - b[BASELINE]) <= BASELINE_TOL
    ]
    if len(hits) != 1:
        return None
    if not any(
        c["cp"] == a[CP] and abs(c["ox"] - a[ORIGIN_X]) <= 0.2 and abs(c["baseline"] - a[BASELINE]) <= BASELINE_TOL
        for c in chars
    ):
        return None
    return bool(hits[0]["space_before"])


# ----------------------------------------------------------------------- perturbation


def _scaled(g, factor: float):
    if g[ADVANCE] is None:
        return g
    return tuple(v * factor if i == ADVANCE else v for i, v in enumerate(g))


def _with_field(g, value):
    return tuple(value if i == ADVANCE else v for i, v in enumerate(g))


# ------------------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=HERE / "results" / "h03_cross_backend_scores.json")
    args = ap.parse_args()

    key = json.loads((P1 / "v04_key.json").read_text())
    adj = json.loads((P1 / "v04_adjudication.json").read_text())["answers"]
    g04 = json.loads((P2 / "results" / "g04_boundary_scores.json").read_text())
    items = key["items"]

    by_doc: dict[str, list] = defaultdict(list)
    for it in items:
        by_doc[it["doc"]].append(it)

    decided: dict[str, dict] = {}
    facts: dict[str, dict] = {}
    missing_pdfium = []

    for rel, its in sorted(by_doc.items()):
        pages = sorted({it["page"] for it in its})
        assert max(pages) <= MAX_PAGE, f"{rel} reaches page {max(pages)}"
        print(f"  {rel}: {len(its)} pairs over pages {pages}")

        glyphs = {b: _glyphs_by_page(b, rel, pages) for b in ("pdfium", "pdfminer", "pymupdf")}
        own_mu = {p: _pymupdf_own_spaces(rel, p) for p in pages}
        pdfium_pairs = {p: _page_pairs(REPO / rel, p) for p in pages}

        for it in its:
            k = (round(it["prev_x1"], 2), round(it["next_x0"], 2))
            pp = pdfium_pairs[it["page"]].get(k)
            if pp is None:
                missing_pdfium.append(it["id"])
                continue
            a_raw, b_raw = pp["a"], pp["b"]
            cp_a = 0xFFFD if a_raw["cp"] < 0x20 else a_raw["cp"]
            cp_b = 0xFFFD if b_raw["cp"] < 0x20 else b_raw["cp"]

            rec: dict = {
                "stratum": it["stratum"],
                "doc": rel,
                "page": it["page"],
                "chars": f"{chr(cp_a)}|{chr(cp_b)}",
                "pdfium_own": pp["pdfium_space"],
                "pdfminer_own": it["pdfminer_space"],
            }
            fact: dict = {}
            for backend in ("pdfium", "pdfminer", "pymupdf"):
                gl = glyphs[backend][it["page"]]
                ga = _locate(gl, cp_a, a_raw["ox"], a_raw["oy"])
                gb = _locate(gl, cp_b, b_raw["ox"], b_raw["oy"])
                if ga is None or gb is None:
                    rec[f"{backend}_ext"] = None
                    rec[f"{backend}_unmapped_why"] = "prev" if ga is None else "next"
                    continue
                rec[f"{backend}_ext"] = wants_space(ga, gb)
                rec[f"{backend}_ext_adv25"] = wants_space(_scaled(ga, 1.25), _scaled(gb, 1.25))
                rec[f"{backend}_ext_adv75"] = wants_space(_scaled(ga, 0.75), _scaled(gb, 0.75))
                fact[backend] = {
                    "ox_a": ga[ORIGIN_X],
                    "ox_b": gb[ORIGIN_X],
                    "adv_a": ga[ADVANCE],
                    "adv_b": gb[ADVANCE],
                    "size_a": ga[SIZE],
                    "size_b": gb[SIZE],
                }
                if backend == "pymupdf":
                    rec["pymupdf_own"] = _pymupdf_own_decision(own_mu[it["page"]], ga, gb)
                if backend == "pdfminer":
                    # N3: the same rule fed the WRONG FIELD. h01 measured `.adv` =
                    # `.width` / text-matrix a, and on this corpus GPO sets Tf 1 so the
                    # text-matrix scale IS the effective font size. Dividing each advance
                    # by its own size therefore reconstructs what `.adv` would have given.
                    rec["pdfminer_ext_WRONG_FIELD"] = wants_space(
                        _with_field(ga, None if ga[ADVANCE] is None else ga[ADVANCE] / max(ga[SIZE], 1e-6)),
                        _with_field(gb, None if gb[ADVANCE] is None else gb[ADVANCE] / max(gb[SIZE], 1e-6)),
                    )
            decided[it["id"]] = rec
            facts[it["id"]] = fact

    assert not missing_pdfium, f"{len(missing_pdfium)} frozen pairs could not be re-located: {missing_pdfium}"
    assert len(decided) == 72, f"expected all 72 frozen pairs, got {len(decided)}"

    # ---- N1: the adapter must reproduce phase 2's independently-written g04 column ------
    g04_ext = {d["id"]: d for d in g04["extended_vs_pdfium_disagreements"]}
    n1_mismatch = []
    for cid, rec in decided.items():
        # g04 only lists disagreements, so reconstruct its extended value: equal to its
        # pdfium value unless the pair is in the disagreement list.
        expect = (g04_ext[cid]["extended"]) if cid in g04_ext else rec["pdfium_own"]
        if rec["pdfium_ext"] != expect:
            n1_mismatch.append({"id": cid, "here": rec["pdfium_ext"], "g04": expect})

    # ---- scoring -----------------------------------------------------------------------
    scored, unreadable = [], []
    for cid, a in adj.items():
        if a["v"] == "UNREADABLE":
            unreadable.append(cid)
            continue
        scored.append((cid, decided[cid], a["v"] == "BOUNDARY"))

    inconsistent = {"B30", "B32", "B36", "B42", "B55", "B60"}
    dropped = [r for r in scored if r[0] not in inconsistent]

    COLUMNS = [
        "pdfium_own",
        "pdfium_ext",
        "pdfminer_own",
        "pdfminer_ext",
        "pymupdf_own",
        "pymupdf_ext",
        "pdfminer_ext_WRONG_FIELD",
        "pdfium_ext_adv25",
        "pdfium_ext_adv75",
        "pdfminer_ext_adv25",
        "pdfminer_ext_adv75",
        "pymupdf_ext_adv25",
        "pymupdf_ext_adv75",
    ]

    def tally(rows, col):
        tp = fp = tn = fn = na = 0
        for _cid, d, truth in rows:
            v = d.get(col)
            if v is None:
                na += 1
                continue
            if v and truth:
                tp += 1
            elif v:
                fp += 1
            elif truth:
                fn += 1
            else:
                tn += 1
        n = tp + fp + tn + fn
        return {
            "scored": n,
            "unavailable": na,
            "coverage": round(n / len(rows), 4) if rows else None,
            "accuracy": round((tp + tn) / n, 4) if n else None,
            "missed_boundaries": fn,
            "spurious_boundaries": fp,
        }

    out: dict = {
        "sample": "phase 1 frozen v04 sample; adjudication unchanged and not reopened",
        "relocated_in_pdfium": len(decided),
        "unreadable_excluded": unreadable,
        "join": {
            "rule": "codepoint + |d pen origin_x| <= 0.05 pt + |d baseline| <= 0.6 pt, unique match required",
            "ambiguous_or_absent_are_reported_not_scored": True,
        },
        "overall": {c: tally(scored, c) for c in COLUMNS},
        "inconsistent_class_dropped_POST_HOC": {c: tally(dropped, c) for c in COLUMNS},
        "by_stratum": {},
        "unmapped": {},
        "pairwise_disagreement": {},
        "N1_adapter_vs_g04_mismatches": n1_mismatch,
        "N5_fact_agreement": {},
    }

    by_s: dict[str, list] = defaultdict(list)
    for row in scored:
        by_s[row[1]["stratum"]].append(row)
    for s, rows in sorted(by_s.items()):
        out["by_stratum"][s] = {
            "n": len(rows),
            **{c: tally(rows, c)["accuracy"] for c in ("pdfium_ext", "pdfminer_ext", "pymupdf_ext", "pdfminer_own")},
            "coverage": {
                c: tally(rows, c)["coverage"] for c in ("pdfium_ext", "pdfminer_ext", "pymupdf_ext", "pymupdf_own")
            },
        }

    for backend in ("pdfium", "pdfminer", "pymupdf"):
        miss = [
            {"id": cid, "stratum": d["stratum"], "chars": d["chars"], "why": d.get(f"{backend}_unmapped_why")}
            for cid, d in decided.items()
            if d.get(f"{backend}_ext") is None
        ]
        out["unmapped"][backend] = {"count": len(miss), "items": miss}

    def disagree(col_a: str, col_b: str) -> dict:
        both = [(cid, d) for cid, d in decided.items() if d.get(col_a) is not None and d.get(col_b) is not None]
        diff = [
            {"id": cid, "stratum": d["stratum"], "chars": d["chars"], col_a: d[col_a], col_b: d[col_b]}
            for cid, d in both
            if d[col_a] != d[col_b]
        ]
        return {"comparable_pairs": len(both), "disagreements": len(diff), "items": diff[:20]}

    for pair in (
        ("pdfium_ext", "pdfminer_ext"),
        ("pdfium_ext", "pymupdf_ext"),
        ("pdfminer_ext", "pymupdf_ext"),
        ("pdfium_ext", "pdfium_own"),
        ("pdfminer_ext", "pdfminer_own"),
        ("pymupdf_ext", "pymupdf_own"),
    ):
        out["pairwise_disagreement"][f"{pair[0]} vs {pair[1]}"] = disagree(*pair)

    # ---- N5: how far apart are the FACTS themselves? ------------------------------------
    for x, y in (("pdfium", "pdfminer"), ("pdfium", "pymupdf")):
        dox, dadv = [], []
        for f in facts.values():
            if x not in f or y not in f:
                continue
            for side in ("a", "b"):
                dox.append(abs(f[x][f"ox_{side}"] - f[y][f"ox_{side}"]))
                if f[x][f"adv_{side}"] is not None and f[y][f"adv_{side}"] is not None:
                    dadv.append(abs(f[x][f"adv_{side}"] - f[y][f"adv_{side}"]))
        out["N5_fact_agreement"][f"{x} vs {y}"] = {
            "endpoints_compared": len(dox),
            "max_abs_d_origin_x_pt": round(max(dox), 6) if dox else None,
            "advances_compared": len(dadv),
            "max_abs_d_advance_pt": round(max(dadv), 6) if dadv else None,
            "median_abs_d_advance_pt": round(sorted(dadv)[len(dadv) // 2], 6) if dadv else None,
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({**out, "per_pair": decided}, indent=1))

    # ------------------------------------------------------------------------ report ---
    print(f"\nrelocated {out['relocated_in_pdfium']}/72; {len(unreadable)} unreadable excluded")
    print(f"\nN1 adapter vs phase-2 g04: {len(n1_mismatch)} mismatches (must be 0)")
    print("\n{:<28} {:>7} {:>9} {:>8} {:>7} {:>9}".format("column", "scored", "coverage", "acc", "missed", "spurious"))
    for c in COLUMNS:
        t = out["overall"][c]
        print(
            f"{c:<28} {t['scored']:>7} {str(t['coverage']):>9} {str(t['accuracy']):>8} "
            f"{t['missed_boundaries']:>7} {t['spurious_boundaries']:>9}"
        )
    print("\ninconsistent class dropped (POST-HOC):")
    for c in ("pdfium_ext", "pdfminer_ext", "pymupdf_ext", "pdfium_own", "pdfminer_own", "pymupdf_own"):
        t = out["inconsistent_class_dropped_POST_HOC"][c]
        print(f"  {c:<26} acc={t['accuracy']}  scored={t['scored']}  unavailable={t['unavailable']}")
    print("\nunmapped:")
    for b, d in out["unmapped"].items():
        print(f"  {b:<10} {d['count']}  {[i['id'] for i in d['items']]}")
    print("\npairwise disagreement:")
    for k, v in out["pairwise_disagreement"].items():
        print(f"  {k:<34} {v['disagreements']}/{v['comparable_pairs']}")
    print("\nby stratum (accuracy):")
    print("  {:<22} {:>3} {:>9} {:>10} {:>9} {:>10}".format("stratum", "n", "pdfium", "pdfminer", "pymupdf", "pm_own"))
    for s, d in out["by_stratum"].items():
        print(
            f"  {s:<22} {d['n']:>3} {str(d['pdfium_ext']):>9} {str(d['pdfminer_ext']):>10} "
            f"{str(d['pymupdf_ext']):>9} {str(d['pdfminer_own']):>10}"
        )
    print("\nN5 fact agreement:")
    for k, v in out["N5_fact_agreement"].items():
        print(f"  {k:<22} max|d origin_x|={v['max_abs_d_origin_x_pt']}  max|d advance|={v['max_abs_d_advance_pt']}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
