"""x09 -- cross-engine control on the NEUTRAL SKELETON, with a frozen acceptance rule.

NOT CONFIRMATORY. DEVELOPMENT documents only.

A19 re-pointed the protocol's 10 % PyMuPDF cross-check at "per-page neutral line counts".
That is insufficient: two engines can both report 30 lines while disagreeing about which
baselines and which glyphs belong to each. A21 replaced counting with a GEOMETRIC
CORRESPONDENCE but adopted no threshold, which left a methodological degree of freedom open
before execution. This file closes it.

THE PROPERTY. The skeleton is PDFium-derived. Both architectures inherit it together, so a
PDFium geometry error cannot bias H against X -- but it CAN move the adjudication unit, and
a reader is entitled to know whether an independent engine sees substantially the same
physical lines.

THE MATCHING RULE (unchanged from A21)

    A PDFium line P matches a PyMuPDF line M iff
        |baseline(P) - baseline(M)| <= 0.5 * median ink height of the PDFium page   and
        x-span overlap / min(span(P), span(M)) >= 0.5
    Greedy by ascending baseline distance, each line used at most once, ties on the lower
    PDFium ordinal. NO TEXT is used anywhere.

WHICH PARTS OF THIS ARE ACTUALLY LIKE-FOR-LIKE. This matters, and phase 3 already measured
it rather than leaving it to inference:

  baseline        LIKE FOR LIKE. Both are pen origins -- PDFium's
                  `FPDFText_GetCharOrigin` y and MuPDF's `char[2]` origin. This is the
                  discriminating half of the rule.
  x extent        NOT identical quantities. PDFium's x0/x1 are INK box edges;
                  `get_texttrace()`'s bbox is CONSTRUCTED from the glyph advance at the pen
                  origin -- `h01` measured `bbox[0] == origin[0]` to 0.0 pt on every
                  character of every sampled document, which no ink box can satisfy, and
                  `h08` traced it to `jm_trace_text_span`'s `x1 = x0 + adv`. So a PyMuPDF
                  line's span starts at the first pen origin and ends at the last advance,
                  while PDFium's starts at the first ink edge and ends at the last. The
                  PyMuPDF span therefore CONTAINS the PDFium span in the ordinary case,
                  and since the overlap denominator is the SMALLER span, the ratio pins to
                  1.0. Observed: `x_overlap_min` is exactly 1.0 on every matched line of
                  both development documents -- the criterion never binds.
                  It is therefore reported as a COARSE GUARD, not as evidence of fine
                  geometric agreement: its real job is to stop two horizontally disjoint
                  lines that happen to share a baseline (the two-column case) from matching.
  vertical box    NOT comparable and NOT compared. PDFium's is a tight ink box; MuPDF's
                  rect uses the span's ascender/descender. Only PDFium's height is used,
                  and only to set the baseline tolerance, so the mismatch cannot leak in.
  count, order    comparable, and both are reported.

No better PyMuPDF field is pursued here. `Font.glyph_bbox` would give ink extents, but
obtaining them means re-deriving each glyph's transform from the trace and is a second
backend study; the baseline comparison already carries the control's weight.
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

from neutral_identity import SPACE, SourceGlyph, cluster, eligible  # noqa: E402

OUT = EV / "results" / "x09_skeleton_cross_engine.json"
DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
]
OVERLAP_MIN = 0.5

# ------------------------------------------------------------------- THE FROZEN GATE
#
# METRIC       per document, over the sampled pages:
#                  matched_fraction = one-to-one matched lines / max(pdfium, pymupdf) lines
#              The denominator is the LARGER count, so over-segmentation by EITHER engine
#              lowers the score. Scoring against PDFium alone would read 1.0 while PyMuPDF
#              saw 300 lines to PDFium's 256.
#
# THRESHOLD    PASS(document) iff  matched_fraction >= 0.95
#                             and  every sampled page has page matched_fraction >= 0.75
#
# WHY THERE.   Development observes 514 of 515 lines matched across two documents, i.e. a
#              disagreement rate of 0.2 %. The document gate permits 5 % -- roughly 25x the
#              observed rate -- and that looseness is deliberate, for a reason that is not
#              statistical modesty alone: the development material is TWO GPO BILLS, while
#              the holdout contains three COMMITTEE REPORTS, a class with two-column pages.
#              A19 already records that a two-column page merges its columns into one
#              neutral line, so on that class the two engines can disagree for a reason
#              internal to the skeleton's design rather than because PDFium is wrong. A gate
#              tuned to bills would fire there and be read as an engine fault. Calibrating a
#              tight threshold on 20 pages of one document class would be pretending this
#              sample establishes a population error rate; it does not.
#
#              The per-page floor exists because a document-level fraction hides exactly the
#              failure that matters: on a 300-line document, one completely divergent
#              26-line page still scores 0.91 and would pass a document gate alone. 0.75 of
#              a ~26-line GPO page means about 6 unmatched lines on one page -- far above
#              anything observed, far below a page-scale frame shift.
#
# WHAT IT PERMITS, PLAINLY. Up to 5 % of a document's lines unmatched, and up to 25 % of any
#              single page's, with no label at all. It is a coarse guard against a frame
#              that has moved, not a precision instrument.
#
# CONSEQUENCE (frozen; execution is NEVER blocked by this gate)
#   PASS everywhere        the skeleton is reported as cross-engine corroborated.
#   FAIL on document d     every RQ1 **and** RQ2 result or table computed on d carries
#                          "PDFIUM-CONDITIONED FRAME". Both are still reported and the
#                          decision rule is unchanged.
#   FAIL on more than a
#   third of sampled docs  the headline qualification applies to BOTH RQ1 and RQ2.
#
# WHY RQ1 IS NOT EXEMPT. An earlier version of this rule said RQ1 was "unaffected" because
# both arms inherit the same frame. That is too strong, and x10 part 9 measured why rather
# than arguing it. A common frame cannot DIRECTLY favour H or X -- and the per-line
# comparative verdict did in fact survive every partition tried, so the overclaim was not
# that a verdict flips. The conditioning enters through the DENOMINATOR AND POPULATION: the
# frame decides how many neutral lines exist, which are in M0's comparative risk set, and
# -- through the 8-line region grid -- which regions enter the D-frame and which are drawn
# into the C-frame. Identical architecture output scored against two different neutral
# partitions of the same glyphs gives different M0 rates. So RQ1's NUMBERS are conditional
# on the PDFium frame even though its DIRECTION is not, and the label belongs on both.
DOC_MIN = 0.95
PAGE_MIN = 0.75


def gate(pages: list[dict]) -> dict:
    """Apply the frozen rule to one document's per-page records."""
    tot_k = sum(p["matched"] for p in pages)
    tot_d = sum(max(p["pdfium"], p["pymupdf"]) for p in pages)
    frac = (tot_k / tot_d) if tot_d else None
    page_fracs = [
        (p["page"], p["matched"] / max(p["pdfium"], p["pymupdf"])) for p in pages if max(p["pdfium"], p["pymupdf"]) > 0
    ]
    worst = min(page_fracs, key=lambda t: t[1]) if page_fracs else None
    ok = frac is not None and frac >= DOC_MIN and (worst is None or worst[1] >= PAGE_MIN)
    return {
        "matched_fraction": round(frac, 4) if frac is not None else None,
        "worst_page": worst[0] if worst else None,
        "worst_page_fraction": round(worst[1], 4) if worst else None,
        "document_threshold": DOC_MIN,
        "page_threshold": PAGE_MIN,
        "pass": bool(ok),
        "failed_on": (
            []
            if ok
            else ([f"document {frac:.4f} < {DOC_MIN}"] if frac is not None and frac < DOC_MIN else [])
            + ([f"page {worst[0]} {worst[1]:.4f} < {PAGE_MIN}"] if worst and worst[1] < PAGE_MIN else [])
        ),
    }


def pdfium_lines(path: Path, limit: int):
    import pdfium_hybrid
    from contract_hybrid import CP, GEN, UPRIGHT, VBOX, X0, X1

    pages, _ = pdfium_hybrid.extract(path, limit=limit)
    out: dict[int, list] = {}
    for p in pages:
        for i, c in enumerate(p.chars):
            box = None if c[X0] is None or c[X1] is None or c[VBOX] is None else (c[X0], c[VBOX][0], c[X1], c[VBOX][1])
            gid = None if c[GEN] else i
            if eligible(gid, box, bool(c[UPRIGHT]), c[CP]):
                out.setdefault(p.page_number, []).append(SourceGlyph(gid, c[2], box[0], box[1], box[2], box[3]))
    return {pg: cluster(gs, pg) for pg, gs in out.items()}


def pymupdf_lines(path: Path, limit: int):
    import pymupdf

    doc = pymupdf.open(str(path))
    out = {}
    try:
        for pno in range(min(limit, doc.page_count)):
            page = doc[pno]
            height = page.rect.height
            glyphs = []
            gid = 0
            for span in page.get_texttrace():
                d = span.get("dir", (1.0, 0.0))
                if not (abs(d[1]) < 1e-6 and d[0] > 0):
                    continue  # non-upright spans, the rule every adapter here applies
                for ch in span.get("chars", ()):
                    # (cp, gid, origin, bbox) -- and MuPDF is y-DOWN from the page top,
                    # so every y is flipped against the page height to reach PDF page
                    # space. Getting this wrong silently produces a skeleton that matches
                    # nothing, which reads like engine disagreement rather than a bug.
                    origin, bx = ch[2], ch[3]
                    if bx is None or origin is None:
                        continue
                    # A24.2, applied to BOTH engines. `get_texttrace()` gives the codepoint
                    # as ch[0], so PyMuPDF's skeleton excludes U+0020 by exactly the rule
                    # the PDFium side uses. Without this the control would compare two
                    # differently DEFINED frames and report the definition gap as engine
                    # disagreement.
                    if ch[0] == SPACE:
                        continue
                    x0, y0, x1, y1 = bx
                    if (x1 - x0) <= 0 or (y1 - y0) <= 0:
                        continue
                    glyphs.append(SourceGlyph(gid, height - origin[1], x0, height - y1, x1, height - y0))
                    gid += 1
            out[pno + 1] = cluster(glyphs, pno + 1)
    finally:
        doc.close()
    return out


def match_page(p_lines, m_lines) -> dict:
    base = {"pdfium": len(p_lines), "pymupdf": len(m_lines), "matched": 0, "deltas": [], "overlaps": []}
    if not p_lines or not m_lines:
        return {**base, "x0_deltas": [], "x1_deltas": []}
    tol = 0.5 * (statistics.median([ln.y1 - ln.y0 for ln in p_lines]) or 1.0)
    cands = []
    for p in p_lines:
        for m in m_lines:
            d = abs(p.baseline - m.baseline)
            if d > tol:
                continue
            lo, hi = max(p.x0, m.x0), min(p.x1, m.x1)
            span = min(p.x1 - p.x0, m.x1 - m.x0)
            ov = (hi - lo) / span if span > 0 and hi > lo else 0.0
            if ov >= OVERLAP_MIN:
                cands.append((d, p.ordinal, m.ordinal, ov, p.x0 - m.x0, p.x1 - m.x1))
    cands.sort()
    used_p, used_m, deltas, overlaps, dx0, dx1 = set(), set(), [], [], [], []
    for d, po, mo, ov, a, b in cands:
        if po in used_p or mo in used_m:
            continue
        used_p.add(po)
        used_m.add(mo)
        deltas.append(round(d, 4))
        overlaps.append(round(ov, 4))
        dx0.append(round(a, 4))
        dx1.append(round(b, 4))
    return {**base, "matched": len(used_p), "deltas": deltas, "overlaps": overlaps, "x0_deltas": dx0, "x1_deltas": dx1}


def measure(pl, ml) -> list[dict]:
    rows = []
    for pg in sorted(set(pl) | set(ml)):
        r = match_page(pl.get(pg, []), ml.get(pg, []))
        rows.append({"page": pg, **r})
    return rows


# ----------------------------------------------------------------- fault injection
#
# A gate that has never produced a FAIL cannot distinguish "the frames agree" from "this
# check cannot see disagreement". Each fault below is applied to the PyMuPDF skeleton only,
# and the gate must reject it. The permitted case is included too, so what the rule lets
# through is stated by measurement rather than by claim.


def page_tol(lines: list) -> float:
    """The page's own baseline tolerance: the same 0.5 x median ink height the matcher uses."""
    return 0.5 * (statistics.median([ln.y1 - ln.y0 for ln in lines]) or 1.0)


def fault_frame_displaced(ml: dict, page: int, dy: float = 200.0) -> dict:
    """One page's frame moved clean off its baselines, by far more than any line pitch.

    Scale-free ON PURPOSE. A first attempt shifted a fixed 6 pt and did NOT fire on
    `118-s-4795/1`: its page 1 is a large-type title page, so `0.5 x median ink height` is
    itself about 6 pt and the shift stayed inside the tolerance that DEFINES a line. That is
    correct behaviour rather than a gate defect -- `fault_subtolerance_shift` keeps the case
    as an explicitly permitted one -- but it makes a fixed offset useless as a probe.
    """
    return {
        pg: ([replace(ln, baseline=ln.baseline + dy) for ln in lns] if pg == page else lns) for pg, lns in ml.items()
    }


def fault_split_every_line(ml: dict) -> dict:
    """Every line cut in two at its x-midpoint -- systematic OVER-segmentation.

    This is the fault the denominator choice exists for. Scored against PDFium's count
    alone the result would read 1.0, because every PDFium line still finds a partner; the
    max() denominator is what makes doubling PyMuPDF's line count visible.
    """
    out = {}
    for pg, lns in ml.items():
        split = []
        for ln in lns:
            mid = (ln.x0 + ln.x1) / 2.0
            split.append(replace(ln, ordinal=len(split), x1=mid))
            split.append(replace(ln, ordinal=len(split) + 1, x0=mid))
        out[pg] = split
    return out


def fault_subtolerance_shift(ml: dict, pl: dict, factor: float = 0.4) -> dict:
    """Every baseline nudged by a FRACTION of the page's own tolerance -- permitted by design.

    A displacement smaller than the tolerance that defines a line is not a line-structure
    disagreement: the same clustering rule would place those glyphs on the same line.
    """
    return {
        pg: ([replace(ln, baseline=ln.baseline + factor * page_tol(pl[pg])) for ln in lns] if pg in pl else lns)
        for pg, lns in ml.items()
    }


def fault_pairwise_merge(ml: dict) -> dict:
    """Every adjacent pair of lines merged -- a systematic over-merge across the document."""
    out = {}
    for pg, lns in ml.items():
        merged = []
        for i in range(0, len(lns), 2):
            pair = lns[i : i + 2]
            merged.append(
                replace(
                    pair[0],
                    baseline=round(statistics.median([p.baseline for p in pair]), 4),
                    x0=min(p.x0 for p in pair),
                    x1=max(p.x1 for p in pair),
                    gids=frozenset().union(*(p.gids for p in pair)),
                )
            )
        out[pg] = merged
    return out


def fault_drop_tenth(ml: dict, page: int) -> dict:
    """A tenth of one page's lines missing -- inside what the rule deliberately permits."""
    return {pg: ([ln for i, ln in enumerate(lns) if i % 10] if pg == page else lns) for pg, lns in ml.items()}


def main(limit: int = 10) -> int:
    out = []
    faults = []
    failed: list[str] = []
    for name, path in DOCS:
        if not path.exists():
            continue
        pl, ml = pdfium_lines(path, limit), pymupdf_lines(path, limit)
        pages = measure(pl, ml)
        g = gate(pages)
        all_d = [d for p in pages for d in p["deltas"]]
        all_o = [o for p in pages for o in p["overlaps"]]
        all_x0 = [v for p in pages for v in p["x0_deltas"]]
        all_x1 = [v for p in pages for v in p["x1_deltas"]]
        rec = {
            "document": name,
            "pages": limit,
            "pdfium_neutral_lines": sum(p["pdfium"] for p in pages),
            "pymupdf_neutral_lines": sum(p["pymupdf"] for p in pages),
            "one_to_one_matched": sum(p["matched"] for p in pages),
            "gate": g,
            "baseline_delta_median": round(statistics.median(all_d), 4) if all_d else None,
            "baseline_delta_max": max(all_d) if all_d else None,
            "x_overlap_median": round(statistics.median(all_o), 4) if all_o else None,
            "x_overlap_min": min(all_o) if all_o else None,
            # the ink-vs-advance residue, so the x-overlap is not over-read
            "x0_delta_median_pdfium_minus_pymupdf": round(statistics.median(all_x0), 4) if all_x0 else None,
            "x1_delta_median_pdfium_minus_pymupdf": round(statistics.median(all_x1), 4) if all_x1 else None,
            "per_page": [{k: p[k] for k in ("page", "pdfium", "pymupdf", "matched")} for p in pages],
        }
        out.append(rec)
        print(
            f"  {name:16} pdfium={rec['pdfium_neutral_lines']:5} pymupdf={rec['pymupdf_neutral_lines']:5} "
            f"matched={rec['one_to_one_matched']:5} frac={g['matched_fraction']} "
            f"worst_page={g['worst_page_fraction']} GATE={'PASS' if g['pass'] else 'FAIL'}"
        )
        if not g["pass"]:
            failed.append(f"{name} unperturbed gate FAILED")

        # --- the gate must be shown capable of failing, on known-bad frames
        target = pages[0]["page"]
        for label, bad_ml, must_pass in (
            ("one page's frame displaced 200 pt", fault_frame_displaced(ml, target), False),
            ("every line pairwise-merged", fault_pairwise_merge(ml), False),
            ("every line split in two", fault_split_every_line(ml), False),
            ("a tenth of one page's lines dropped", fault_drop_tenth(ml, target), True),
            ("every baseline nudged 0.4 x tolerance", fault_subtolerance_shift(ml, pl), True),
        ):
            bg = gate(measure(pl, bad_ml))
            faults.append(
                {
                    "document": name,
                    "fault": label,
                    "matched_fraction": bg["matched_fraction"],
                    "worst_page_fraction": bg["worst_page_fraction"],
                    "gate_pass": bg["pass"],
                    "expected_gate_pass": must_pass,
                    "failed_on": bg["failed_on"],
                }
            )
            ok = bg["pass"] == must_pass
            print(
                f"     fault: {label:36} frac={bg['matched_fraction']} "
                f"worst={bg['worst_page_fraction']} -> {'PASS' if bg['pass'] else 'FAIL'} "
                f"[{'as expected' if ok else 'UNEXPECTED'}]"
            )
            if not ok:
                failed.append(f"{name}: {label} gave pass={bg['pass']}, expected {must_pass}")

    doc = {
        "population": "DEVELOPMENT -- not a holdout",
        "property": "do two independent engines see substantially the same physical line skeleton?",
        "rule": {
            "baseline_tolerance": "0.5 * median PDFium ink height on the page",
            "x_overlap_min": OVERLAP_MIN,
            "matching": "greedy by ascending baseline distance, one-to-one, ties on lower PDFium ordinal",
            "text_used": False,
        },
        "gate": {
            "metric": "one-to-one matched neutral lines / max(pdfium, pymupdf) lines, per document",
            "document_threshold": DOC_MIN,
            "page_threshold": PAGE_MIN,
            "consequence": (
                "FAIL on a document labels every RQ1 AND RQ2 result computed on it PDFIUM-CONDITIONED "
                "FRAME; FAIL on more than a third of sampled documents applies that qualification to "
                "BOTH RQ1's and RQ2's headline. RQ1 is NOT exempt: a common frame cannot directly "
                "favour either arm, but it sets M0's denominator and the D/C-frame populations, so "
                "RQ1's numbers are frame-conditional even where its direction is not. Execution is "
                "never blocked by this gate."
            ),
        },
        "geometry_caveat": (
            "baseline is like-for-like (both are pen origins) and carries the control. The x extent is "
            "NOT: PyMuPDF's texttrace bbox is constructed from the glyph advance at the pen origin "
            "(phase3 h01 measured bbox[0] == origin[0] to 0.0 pt; h08 traced it to jm_trace_text_span), "
            "so the PyMuPDF span contains the PDFium ink span and the overlap ratio pins to 1.0. The "
            "x-overlap is a coarse guard against horizontally disjoint lines, not fine agreement. The "
            "vertical box is not comparable and is not compared."
        ),
        "documents": out,
        "fault_injection": faults,
        "failures": failed,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\nwrote {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
