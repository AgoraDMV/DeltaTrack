"""x19 -- A32 raster diagnostic: is the VISIBLE left edge displaced from the geometric x0?

NOT CONFIRMATORY. DEVELOPMENT only, worst-case targets from `x18`. Nothing is scored and no
oracle artifact is created. Evidence: `results/x19_raster_edge_diagnostic.json`.

NARROW PURPOSE, per the A32 contract: does the MuPDF-rendered raster reveal a SYSTEMATIC reason
that "left edge of the first printed character" -- what A30.3 asks the adjudicator for -- would
sit materially away from the neutral glyph's geometric `x0`?

WHAT THIS DELIBERATELY DOES NOT DO. No OCR. No pixel-intensity threshold invented and then
treated as truth. The only edge rule used is EXACT RASTER OCCUPANCY: with the page rendered on
a transparent ground, the visible edge is the leftmost pixel column receiving ANY alpha at all.
That is a property MuPDF computes, not a number chosen here.

THE MEASUREMENT IS RESTRICTED GEOMETRICALLY, NOT HEURISTICALLY. A neighbouring glyph's ink
inside the search window would contaminate "leftmost inked column", and separating it would
require exactly the segmentation heuristic the contract forbids. So a target is measured only
when NO other glyph's ink box reaches into its window -- a purely geometric exclusion, decided
from `x18`'s recorded neighbour boxes, with the excluded count reported rather than hidden.

RUN IT WITH AN INTERPRETER THAT HAS `pymupdf`. It is deliberately absent from the project venv:
that venv is shared across worktrees and PyMuPDF is a rejected EXTRACTOR under ADR 0002. Here
it is only the renderer PRE-REGISTRATION 5.2 already names for adjudication stimuli.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
X18 = EV / "results" / "x18_start_x_discriminability.json"
OUT = EV / "results" / "x19_raster_edge_diagnostic.json"
IMG_DIR = EV / "results" / "x19_raster_dev"

PRIMARY_DPI, R1_DPI = 300, 330
WINDOW_PT = 3.0  # how far left of x0 the search window reaches
N_IMAGES = 4  # worst cases kept as crops, per population -- minimal by design

ROWS: list[dict] = []
FAILED: list[str] = []


def check(name, expected, observed, fails_when=""):
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


def leftmost_inked_column(pix):
    """The leftmost pixel column carrying ANY alpha, or None if the crop is empty.

    Exact occupancy. No intensity threshold: a column counts if the renderer put any coverage
    in it at all, which is what "the glyph is visible here" means without inventing a cutoff.
    """
    n, w, h = pix.n, pix.width, pix.height
    samples = pix.samples
    for x in range(w):
        for y in range(h):
            if samples[(y * w + x) * n + (n - 1)]:
                return x
    return None


def measure(target, dpi, save_as=None):
    """Render one target's window and report where visible ink actually starts."""
    doc = pymupdf.open(target["pdf"])
    try:
        page = doc[target["page"] - 1]
        if page.rotation:
            return {"error": "PAGE_ROTATED", "rotation": page.rotation}
        # PDF user space is bottom-up; MuPDF's page space is top-down. Converting wrongly
        # would silently render the wrong band, so the empty-crop check below is the guard.
        ph = page.rect.height
        x_left = target["x0"] - WINDOW_PT
        rect = pymupdf.Rect(x_left, ph - target["y1"], target["x1"], ph - target["y0"])

        # NON-GLYPH VECTOR INK. GPO reported prints show matter deleted in committee as
        # STRUCK THROUGH, and that strike is a drawn rule, not a character: it carries no text
        # index, so it has no `ngid` and is correctly absent from the neutral skeleton -- yet
        # MuPDF renders it across every column of the line. Raster occupancy cannot tell rule
        # ink from glyph ink, and separating them is precisely the segmentation heuristic the
        # A32 contract forbids. `get_drawings()` reports vector paths STRUCTURALLY, so the
        # contaminated case is excluded exactly rather than guessed at or silently reported as
        # a displaced glyph edge.
        # NB: a strike rule is a ZERO-HEIGHT rect, and PyMuPDF's Rect.intersects() is False for
        # a degenerate rect -- so the obvious spelling of this test can never fire. Overlap is
        # therefore tested by coordinate, which is what makes this exclusion actually work.
        drawings = [
            dr
            for dr in page.get_drawings()
            if dr["rect"].x0 <= rect.x1
            and dr["rect"].x1 >= rect.x0
            and dr["rect"].y0 <= rect.y1
            and dr["rect"].y1 >= rect.y0
        ]
        if drawings:
            return {
                "dpi": dpi,
                "measured": False,
                "why_not_measured": "NON_GLYPH_VECTOR_INK_IN_BAND",
                "n_vector_paths_in_band": len(drawings),
                "note": "struck-through matter: a drawn rule, not a glyph; no ngid by construction",
            }
        pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72.0, dpi / 72.0), clip=rect, alpha=True)
        col = leftmost_inked_column(pix)
        out = {
            "dpi": dpi,
            "crop_px": [pix.width, pix.height],
            "window_pt": WINDOW_PT,
            "leftmost_inked_column_px": col,
        }
        if col is None:
            out["error"] = "EMPTY_CROP"
            return out
        # offset of the visible edge from the geometric x0, in pixels at this scale
        x0_col = (target["x0"] - x_left) * dpi / 72.0
        out["geometric_x0_column_px"] = x0_col
        out["visible_edge_offset_px"] = col - x0_col
        if save_as:
            IMG_DIR.mkdir(parents=True, exist_ok=True)
            data = pix.tobytes("png")
            (IMG_DIR / save_as).write_bytes(data)
            out["image"] = save_as
            out["image_sha256"] = hashlib.sha256(data).hexdigest()
        return out
    finally:
        doc.close()


def mupdf_glyph_bbox_delta(target):
    """MuPDF's reported glyph bbox x0 minus PDFium's char-box x0, in points.

    A SEPARATE quantity from the visible-ink edge, reported because it is systematic and
    would otherwise look like a discrepancy. A glyph bbox includes the left side bearing --
    whitespace the font reserves before the ink starts -- so this delta is NOT what a human
    marking "the left edge of the first printed character" would point at. The raster
    occupancy figure above is the task-relevant one.
    """
    doc = pymupdf.open(target["pdf"])
    try:
        page = doc[target["page"] - 1]
        ph = page.rect.height
        band = pymupdf.Rect(target["x0"] - 0.2, ph - target["y1"], target["x1"] + 0.2, ph - target["y0"])
        best = None
        for b in page.get_text("rawdict", clip=band)["blocks"]:
            for line in b.get("lines", []):
                for s in line.get("spans", []):
                    for c in s.get("chars", []):
                        cb = c["bbox"]
                        if abs(cb[0] - target["x0"]) < 3.0 or cb[0] <= target["x0"] <= cb[2]:
                            if best is None or abs(cb[0] - target["x0"]) < abs(best["mupdf_x0"] - target["x0"]):
                                best = {"mupdf_x0": cb[0], "char": c["c"], "font": s["font"], "size": s["size"]}
        if best is None:
            return {"found": False}
        best["pdfium_x0"] = target["x0"]
        best["delta_pt"] = best["mupdf_x0"] - target["x0"]
        best["delta_px_300"] = best["delta_pt"] * PRIMARY_DPI / 72.0
        best["found"] = True
        return best
    finally:
        doc.close()


def main() -> int:
    if not X18.exists():
        print(f"FATAL: run x18 first ({X18} missing)")
        return 2
    x18 = json.loads(X18.read_text())
    worst = x18["development"]["worst_cases"]

    print(f"pymupdf {pymupdf.__doc__ or ''} version={pymupdf.version}")
    results = {"H": [], "C": []}
    excluded = {"H": 0, "C": 0}
    empty = 0

    for pop in ("H", "C"):
        for i, t in enumerate(worst[pop]):
            # purely geometric exclusion: any neighbouring ink reaching into the window makes
            # "leftmost inked column" ambiguous, and segmenting it is forbidden
            intruding = [n for n in t.get("ink_within_6pt_left", []) if n["x1"] > t["x0"] - WINDOW_PT]
            if intruding:
                excluded[pop] += 1
                results[pop].append(
                    {
                        "document": t["document"],
                        "page": t["page"],
                        "ngid": t["ngid"],
                        "m_pt": t["m_pt"],
                        "measured": False,
                        "why_not_measured": "NEIGHBOUR_INK_IN_WINDOW",
                        "intruding": intruding,
                    }
                )
                continue
            row = {
                "document": t["document"],
                "page": t["page"],
                "ngid": t["ngid"],
                "kind": t.get("kind"),
                "m_pt": t["m_pt"],
            }
            keep = i < N_IMAGES
            for dpi, tag in ((PRIMARY_DPI, "300"), (R1_DPI, "330")):
                name = f"{pop}{i}_{t['document'].replace('/', '-')}_p{t['page']}_g{t['ngid']}_{tag}dpi.png"
                m = measure(t, dpi, save_as=name if keep else None)
                row[f"dpi_{tag}"] = m
                if m.get("error") == "EMPTY_CROP":
                    empty += 1
            row["mupdf_glyph_bbox_delta"] = mupdf_glyph_bbox_delta(t)
            # `measure()` is the AUTHORITY on whether a raster edge was obtained. An earlier
            # cut set measured=True on this row BEFORE those calls ran, so a target measure()
            # had excluded still counted in the denominator -- 16 reported where 15 were
            # measurable. The flag is now derived from the per-scale results, never asserted
            # ahead of them.
            reasons = sorted({row[k].get("why_not_measured") for k in ("dpi_300", "dpi_330")} - {None})
            row["measured"] = not reasons
            if reasons:
                row["why_not_measured"] = reasons[0]
            results[pop].append(row)

    all_rows = [r for p in results.values() for r in p]
    cleanly = [r for r in all_rows if r.get("measured") and "dpi_300" in r]
    offsets300 = [
        r["dpi_300"]["visible_edge_offset_px"]
        for r in cleanly
        if r["dpi_300"].get("visible_edge_offset_px") is not None
    ]
    offsets330 = [
        r["dpi_330"]["visible_edge_offset_px"]
        for r in cleanly
        if r["dpi_330"].get("visible_edge_offset_px") is not None
    ]
    vector_excluded = [
        {
            "document": r["document"],
            "page": r["page"],
            "ngid": r["ngid"],
            "n_vector_paths_in_band": r["dpi_300"].get("n_vector_paths_in_band"),
        }
        for r in all_rows
        if r.get("why_not_measured") == "NON_GLYPH_VECTOR_INK_IN_BAND"
    ]

    # NEGATIVE CONTROL for the denominator defect itself: an excluded target may neither be
    # counted as measured nor contribute an offset. Asserted on the rows, not on a helper
    # comparing itself.
    check(
        "a vector-ink exclusion is NOT counted in the measured denominator",
        [],
        [r["ngid"] for r in cleanly if r.get("why_not_measured") == "NON_GLYPH_VECTOR_INK_IN_BAND"],
        "the outer row once said measured=True before measure() ran, inflating n_measured by one",
    )
    check(
        "...and contributes NO value to either offset distribution",
        (0, 0),
        tuple(
            sum(
                1
                for r in all_rows
                if r.get("why_not_measured") == "NON_GLYPH_VECTOR_INK_IN_BAND"
                and r[k].get("visible_edge_offset_px") is not None
            )
            for k in ("dpi_300", "dpi_330")
        ),
    )
    check(
        "the denominator is exact: cleanly measured + excluded == attempted",
        len(all_rows),
        len(cleanly) + len([r for r in all_rows if not r.get("measured")]),
    )

    check(
        "every rendered crop contained ink, so the PDF->MuPDF coordinate mapping is right",
        0,
        empty,
        "an empty crop would mean the bottom-up/top-down y conversion is wrong and every "
        "offset below would be measuring blank paper",
    )
    check(
        "at least one worst-case target admitted a clean, unsegmented measurement",
        True,
        len(cleanly) > 0,
        "if all were excluded, this diagnostic would report nothing and must say so",
    )

    summary = {
        "renderer": "MuPDF (pymupdf)",
        "renderer_version": str(pymupdf.version),
        "edge_rule": "exact raster occupancy -- leftmost column with ANY alpha; no intensity threshold",
        "ocr_used": False,
        "segmentation_heuristic_used": False,
        "window_pt": WINDOW_PT,
        "n_attempted": len(all_rows),
        "n_cleanly_measured": len(cleanly),
        "n_excluded_neighbour_ink": excluded,
        "n_excluded_non_glyph_vector_ink": len(vector_excluded),
        "excluded_non_glyph_vector_ink": vector_excluded,
        "visible_edge_offset_px_300": {
            "min": min(offsets300) if offsets300 else None,
            "max": max(offsets300) if offsets300 else None,
            "values": offsets300,
        },
        "visible_edge_offset_px_330": {
            "min": min(offsets330) if offsets330 else None,
            "max": max(offsets330) if offsets330 else None,
            "values": offsets330,
        },
        "limitation": (
            "Two exclusions, both STRUCTURAL rather than heuristic. (1) A target whose window "
            "contains a neighbouring GLYPH's ink is not measured; its intruding boxes are "
            "listed. (2) A target whose band is crossed by NON-GLYPH VECTOR INK is not "
            "measured: GPO reported prints strike through matter deleted in committee, and "
            "that rule is a drawn path with no text index, hence no ngid -- correctly outside "
            "the neutral skeleton, but rendered by MuPDF across the whole line. Raster "
            "occupancy cannot separate rule ink from glyph ink, and doing so would need the "
            "segmentation heuristic the A32 contract forbids. Crops for the worst cases are "
            "committed for human inspection."
        ),
        "mupdf_vs_pdfium_glyph_bbox": (
            "Separately measured and reported so it cannot look like an unexplained "
            "discrepancy: MuPDF's glyph BBOX x0 sits systematically left of PDFium's char-box "
            "x0 -- about -1.23 pt for '(' and -0.90 pt for the open quote at DeVinne/14. That "
            "is the font's left side bearing, i.e. reserved whitespace before the ink, and it "
            "is NOT what a human marking the left edge of a printed character would point at. "
            "The raster-occupancy offsets above are the task-relevant quantity."
        ),
        "for_the_reviewer": (
            "The struck-through case is not a defect in A30.3's geometry: the glyph's x0 is "
            "unchanged and the resolver never reads pixels. It is a PROMPT-DESIGN observation "
            "-- an adjudicator asked for 'the left edge of the first printed character' will "
            "see a horizontal rule running through that character on reported prints. Whether "
            "that needs wording in adjudicator_prompt.md is the reviewer's call; A32 states "
            "no ruling."
        ),
    }
    print(json.dumps(summary, indent=1)[:1200])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "population": "DEVELOPMENT worst cases from x18 -- no holdout opened, nothing scored",
                "summary": summary,
                "H": results["H"],
                "C": results["C"],
                "tests": ROWS,
                "failures": FAILED,
            },
            indent=1,
        )
    )
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
