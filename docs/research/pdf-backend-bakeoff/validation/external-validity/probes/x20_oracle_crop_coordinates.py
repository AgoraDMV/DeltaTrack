"""x20 -- A33: the region crop, and how MuPDF maps a fractional clip onto integer pixels.

NOT CONFIRMATORY. SYNTHETIC + DEVELOPMENT only. No holdout document is opened, nothing is
scored, and no oracle artifact is created. Evidence: `results/x20_oracle_crop_coordinates.json`.

The A33 contract fixed every rule and control below BEFORE this probe existed. The mapping is
reported because the renderer does it, never because it flatters x18.

RUN WITH AN INTERPRETER CARRYING BOTH `pymupdf` AND `pypdfium2` (pinned to the project's
version). `pymupdf` is deliberately absent from the project venv -- shared across worktrees, and
PyMuPDF is a rejected EXTRACTOR under ADR 0002. Here it is only the renderer PRE-REGISTRATION
5.2 already names.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

import anchor_provenance as AP  # noqa: E402
import build_frames as BF  # noqa: E402
import oracle_geometry as OG  # noqa: E402
import run_extended  # noqa: E402
import run_hybrid  # noqa: E402

OUT = EV / "results" / "x20_oracle_crop_coordinates.json"
ROWS: list[dict] = []
FAILED: list[str] = []
STOPS: list[dict] = []

PRIMARY_DPI, R1_DPI = 300, 330
DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-hr-8752/1", REPO / "tests/corpus/118-hr-8752/1_reported-in-house.pdf"),
    ("119-hr-1/1", REPO / "tests/corpus/119-hr-1/1_reported-in-house.pdf"),
]
# 95, not 12: the known same-line collisions sit at 114-hr-2029 p66/p136 and 118-hr-8752 p92,
# so a 12-page window left population C EMPTY and its recovery claim vacuous -- which the
# non-vacuity control below caught. Widening the window is required by the contract (C must be
# exercised), not a selection of favourable data: every metric is fixed and every region in
# range is measured.
PAGE_LIMIT = 95
HOLDOUT_GUARD = {
    "116-hr-7611",
    "115-hr-5961",
    "115-hr-6147",
    "115-s-2976",
    "115-s-1609",
    "114-s-3001",
    "115-hr-6157",
    "117-hr-3237",
    "119-hr-6938",
    "119-hr-7148",
    "CRPT-114HRPT215",
    "CRPT-119HRPT632",
    "CRPT-114HRPT605",
    "117-s-4663",
    "119-hr-8469",
    "116-hr-7617",
    "113-hr-933",
}


def check(name, expected, observed, fails_when=""):
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


def stop(kind, detail):
    STOPS.append({"condition": kind, "detail": detail})
    print(f"[STOP CONDITION] {kind}: {detail}")


def raised(fn):
    try:
        fn()
    except OG.OracleGeometryError as exc:
        return exc.reason
    except Exception as exc:  # noqa: BLE001
        return f"OTHER:{type(exc).__name__}"
    return None


def leftmost_ink(pix):
    n, w, h = pix.n, pix.width, pix.height
    b = pix.samples
    for x in range(w):
        for y in range(h):
            if b[(y * w + x) * n + (n - 1)]:
                return x
    return None


# ------------------------------------------------------------------ synthetic frames


def synth_page_frame(lines, region_ordinal=0):
    """A committed-frame-shaped page object. Only geometry matters here."""
    return {
        "page_number": 1,
        "neutral_lines": [{"key": [1, i], "bbox": b} for i, b in enumerate(lines)],
        "regions": [{"region_ordinal": region_ordinal, "neutral_line_keys": [[1, i] for i in range(len(lines))]}],
    }


def part_bbox() -> dict:
    print("\n== A33.1/A33.2 region bbox: minimal union of committed line bboxes, zero padding ==")
    lines = [[100.0, 700.0, 500.0, 712.0], [102.0, 686.0, 495.0, 698.0], [98.5, 672.0, 505.5, 684.0]]
    bbox = OG.region_bbox(synth_page_frame(lines), 0)

    check(
        "1. bbox is exactly the min/max union of the committed line bboxes",
        (98.5, 672.0, 505.5, 712.0),
        bbox,
        "any other rectangle means padding, a column, or a re-derivation crept in",
    )
    check(
        "2. input line ORDER cannot change the bbox", bbox, OG.region_bbox(synth_page_frame(list(reversed(lines))), 0)
    )

    # 3/4 -- text and anchor content are not inputs; adding them to the frame changes nothing
    noisy = synth_page_frame(lines)
    for ln in noisy["neutral_lines"]:
        ln["line_state"] = {"h_text": "FAMILY HOUSING", "x_text": "FAMILYHOUSING"}
    noisy["regions"][0]["anchor_evidence"] = {"differ": True, "H": [["a"]], "X": []}
    check(
        "3+4. H/X text and anchor content cannot change the bbox",
        bbox,
        OG.region_bbox(noisy, 0),
        "if either moved it, the renderer would be reading architecture output",
    )

    check(
        "5. no padding is added on any side",
        (0.0, 0.0, 0.0, 0.0),
        (bbox[0] - 98.5, bbox[1] - 672.0, bbox[2] - 505.5, bbox[3] - 712.0),
        "a non-zero delta is a free parameter the protocol never froze",
    )
    contained = all(b[0] >= bbox[0] and b[1] >= bbox[1] and b[2] <= bbox[2] and b[3] <= bbox[3] for b in lines)
    check("6. every region line bbox is contained by the region bbox", True, contained)

    # 7 -- a neighbouring line NOT in the region must not expand the crop
    withneighbour = synth_page_frame([*lines, [10.0, 600.0, 600.0, 612.0]])
    withneighbour["regions"][0]["neutral_line_keys"] = [[1, 0], [1, 1], [1, 2]]
    check(
        "7. a neighbouring line outside the region does not expand the crop",
        bbox,
        OG.region_bbox(withneighbour, 0),
        "the crop would otherwise show content the frozen region does not claim",
    )

    short = synth_page_frame([lines[0]])
    check("8. a short trailing region follows the identical rule", tuple(lines[0]), OG.region_bbox(short, 0))

    # 9 -- invalid committed geometry aborts, and is never repaired with padding
    bad = synth_page_frame([[100.0, 700.0, float("nan"), 712.0]])
    check("9a. non-finite committed geometry ABORTS", OG.NON_FINITE_LINE_BBOX, raised(lambda: OG.region_bbox(bad, 0)))
    missing = synth_page_frame([lines[0]])
    missing["neutral_lines"][0].pop("bbox")
    check("9b. a missing line bbox ABORTS", OG.MISSING_LINE_BBOX, raised(lambda: OG.region_bbox(missing, 0)))
    # 9c -- a degenerate SOLE line now trips the per-line check first, which is stricter and
    # correct. NON_POSITIVE_REGION_BBOX is therefore UNREACHABLE through `region_bbox`: a union
    # of positive-area lines is always positive. It is retained as a defensive backstop for any
    # future caller that constructs a bbox another way, and this control asserts the reason the
    # code ACTUALLY returns rather than one that can no longer fire.
    degenerate = synth_page_frame([[100.0, 700.0, 100.0, 712.0]])
    check(
        "9c. a degenerate sole line ABORTS via the stricter per-line check",
        OG.NON_POSITIVE_LINE_BBOX,
        raised(lambda: OG.region_bbox(degenerate, 0)),
        "the region-union guard alone would not have caught a single degenerate line",
    )
    check(
        "9d. ...while the clean frame does NOT abort, so 9a-9c prove something",
        None,
        raised(lambda: OG.region_bbox(synth_page_frame(lines), 0)),
    )

    # 9e -- an INDIVIDUAL degenerate line must abort even when its siblings make the union
    # positive. Checking only the union would let the defective committed geometry through
    # unseen, because the region would still render.
    eight = [[100.0 + i, 700.0 - 14 * i, 500.0, 712.0 - 14 * i] for i in range(8)]
    check(
        "9e. one degenerate line among eight valid ones ABORTS (union alone would pass)",
        OG.NON_POSITIVE_LINE_BBOX,
        raised(lambda: OG.region_bbox(synth_page_frame([[300.0, 650.0, 300.0, 662.0], *eight[1:]]), 0)),
        "a union-only check passes here, so the bad line would be rendered and never reported",
    )
    check(
        "9f. ...and a zero-HEIGHT line aborts the same way",
        OG.NON_POSITIVE_LINE_BBOX,
        raised(lambda: OG.region_bbox(synth_page_frame([[300.0, 650.0, 400.0, 650.0], *eight[1:]]), 0)),
    )
    check(
        "9g. ...while the eight valid lines alone do NOT abort",
        None,
        raised(lambda: OG.region_bbox(synth_page_frame(eight), 0)),
    )

    # A33.1 page-bound refusal: no clipping, no intersection, no repair. Each side separately.
    pw, phh = 612.0, 792.0
    sides = {
        "left": (-0.5, 10.0, 100.0, 20.0),
        "bottom": (10.0, -0.5, 100.0, 20.0),
        "right": (10.0, 10.0, pw + 0.5, 20.0),
        "top": (10.0, 10.0, 100.0, phh + 0.5),
    }
    for side, bb in sides.items():
        check(
            f"a region bbox past the {side} page edge is REFUSED, not clipped",
            OG.REGION_BBOX_OUTSIDE_PAGE,
            raised(lambda bb=bb: OG.validate_region_bbox_for_page(bb, pw, phh)),
            "clipping to the page would hand the adjudicator a stimulus that is not the region the frame committed to",
        )
    check(
        "...while a bbox inside the page passes, so the four refusals prove something",
        None,
        raised(lambda: OG.validate_region_bbox_for_page((10.0, 10.0, 100.0, 20.0), pw, phh)),
    )
    return {"synthetic_bbox": list(bbox)}


# --------------------------------------------------- MuPDF device mapping, measured
def part_mapping() -> dict:
    print("\n== A33.3 MuPDF fractional-clip mapping (measured, not assumed) ==")
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    phases = [0.0, 0.05, 0.1, 0.25, 0.37, 0.5, 0.63, 0.75, 0.9, 0.99]
    widths = [10.0, 10.37, 12.5, 40.0]
    origin_ok, width_ok, rows = [], [], []
    for dpi in (PRIMARY_DPI, R1_DPI):
        for ph in phases:
            for w in widths:
                x0, x1 = 100.0 + ph, 100.0 + ph + w
                pix = page.get_pixmap(
                    matrix=pymupdf.Matrix(OG.scale(dpi), OG.scale(dpi)),
                    clip=pymupdf.Rect(x0, 100.0, x1, 120.0),
                    alpha=True,
                )
                origin_ok.append(pix.x == OG.device_origin_px(x0, dpi))
                width_ok.append(pix.width == OG.expected_image_width(x0, x1, dpi))
                rows.append(
                    {
                        "dpi": dpi,
                        "x0": x0,
                        "x1": x1,
                        "pix_x": pix.x,
                        "pix_width": pix.width,
                        "predicted_origin": OG.device_origin_px(x0, dpi),
                        "predicted_width": OG.expected_image_width(x0, x1, dpi),
                    }
                )
    doc.close()
    check(
        "image column 0 is floor(bbox_x0 * DPI/72 + eps), on EVERY fractional phase and both scales",
        (len(origin_ok), True),
        (sum(origin_ok), all(origin_ok)),
        "A30.3 sketched column 0 == bbox_x0; if that were right this control would fail",
    )
    check(
        "the returned width is ceil(x1*s - eps) - floor(x0*s + eps), so it needs no extra metadata",
        len(width_ok),
        sum(width_ok),
    )
    n_mismatch = sum(1 for r in rows if abs((r["x1"] - r["x0"]) * OG.scale(r["dpi"]) - r["pix_width"]) > 0.5)
    return {
        "n_cases": len(rows),
        "origin_rule": "pix.x == floor(bbox_x0 * DPI/72 + MUPDF_ROUND_EPS)  [A34]",
        "width_rule": "pix.width == ceil(bbox_x1*s - eps) - floor(bbox_x0*s + eps)  [A34]",
        "n_cases_where_width_differs_from_bbox_width_times_scale": n_mismatch,
        "metadata_needed_beyond_bbox_and_dpi": None,
        "cases": rows[:12],
    }


def part_epsilon() -> dict:
    """A34 -- prove MuPDF's 0.001 px device-rectangle epsilon is REAL and LOAD-BEARING.

    The constant can move `device_x0` by a whole pixel and therefore the PDF coordinate handed
    to the nearest-ngid resolver, so it may not be frozen from prose. Coordinates are derived
    MATHEMATICALLY from a target device coordinate -- `x0 = (n - delta)/s` -- not found by
    searching until something passed, and the boundary is BRACKETED either side.
    """
    print("\n== A34 epsilon: the renderer's device-rectangle rounding, falsified ==")
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    n = 500
    inside, outside = (0.0005, 0.001), (0.0011, 0.002)
    origin_rows, width_rows = [], []
    eps_only, both_agree = [], []

    for dpi in (PRIMARY_DPI, R1_DPI):
        s = OG.scale(dpi)
        # --- LEFT EDGE / device origin
        for delta in inside + outside:
            x0 = (n - delta) / s
            pix = page.get_pixmap(
                matrix=pymupdf.Matrix(s, s), clip=pymupdf.Rect(x0, 100.0, x0 + 20.0, 120.0), alpha=True
            )
            plain = math.floor(x0 * s)
            withe = math.floor(x0 * s + OG.MUPDF_ROUND_EPS)
            row = {
                "dpi": dpi,
                "target_device_x": n,
                "delta_px": delta,
                "bbox_x0": x0,
                "x0_times_s": x0 * s,
                "mupdf_pix_x": pix.x,
                "zero_epsilon_prediction": plain,
                "epsilon_aware_prediction": withe,
                "inside_epsilon_band": delta in inside,
            }
            origin_rows.append(row)
            (eps_only if delta in inside else both_agree).append(row)

        # --- RIGHT EDGE, the operation `expected_image_width` performs
        m = 600
        x0_exact = n / s
        for delta in inside + outside:
            x1 = (m + delta) / s
            pix = page.get_pixmap(
                matrix=pymupdf.Matrix(s, s), clip=pymupdf.Rect(x0_exact, 100.0, x1, 120.0), alpha=True
            )
            right = pix.x + pix.width
            width_rows.append(
                {
                    "dpi": dpi,
                    "target_device_x1": m,
                    "delta_px": delta,
                    "bbox_x1": x1,
                    "x1_times_s": x1 * s,
                    "mupdf_right_edge": right,
                    "bbox_x0": x0_exact,
                    "mupdf_width": pix.width,
                    "zero_epsilon_prediction": math.ceil(x1 * s),
                    "epsilon_aware_prediction": math.ceil(x1 * s - OG.MUPDF_ROUND_EPS),
                    "inside_epsilon_band": delta in inside,
                }
            )
    doc.close()

    check(
        "INSIDE the epsilon band the renderer matches the EPSILON-AWARE origin, not floor",
        (len(eps_only), 0),
        (
            sum(1 for r in eps_only if r["mupdf_pix_x"] == r["epsilon_aware_prediction"]),
            sum(1 for r in eps_only if r["mupdf_pix_x"] == r["zero_epsilon_prediction"]),
        ),
        "if the renderer agreed with plain floor here, MUPDF_ROUND_EPS would be unfounded "
        "and device_origin_px must be reverted",
    )
    check(
        "...and the two predictions genuinely DIFFER there, so the case is discriminating",
        len(eps_only),
        sum(1 for r in eps_only if r["epsilon_aware_prediction"] != r["zero_epsilon_prediction"]),
    )
    check(
        "OUTSIDE the band both predictions agree and match the renderer (boundary bracketed)",
        (len(both_agree), len(both_agree)),
        (
            sum(1 for r in both_agree if r["mupdf_pix_x"] == r["epsilon_aware_prediction"]),
            sum(1 for r in both_agree if r["mupdf_pix_x"] == r["zero_epsilon_prediction"]),
        ),
        "without the outside bracket this would show one favourable coordinate, not a threshold",
    )

    w_in = [r for r in width_rows if r["inside_epsilon_band"]]
    w_out = [r for r in width_rows if not r["inside_epsilon_band"]]
    check(
        "RIGHT edge: inside the band the renderer matches the epsilon-aware ceil, not ceil",
        (len(w_in), 0),
        (
            sum(1 for r in w_in if r["mupdf_right_edge"] == r["epsilon_aware_prediction"]),
            sum(1 for r in w_in if r["mupdf_right_edge"] == r["zero_epsilon_prediction"]),
        ),
        "the code claims the epsilon applies symmetrically; this is that claim's evidence",
    )
    check(
        "RIGHT edge: outside the band both agree, bracketing the threshold",
        (len(w_out), len(w_out)),
        (
            sum(1 for r in w_out if r["mupdf_right_edge"] == r["epsilon_aware_prediction"]),
            sum(1 for r in w_out if r["mupdf_right_edge"] == r["zero_epsilon_prediction"]),
        ),
    )

    # THE NEGATIVE CONTROL the ruling requires: zero the constant and the boundary cases must
    # stop matching. Executed, not argued.
    real_eps = OG.MUPDF_ROUND_EPS
    try:
        OG.MUPDF_ROUND_EPS = 0.0
        broken = [r for r in eps_only if OG.device_origin_px(r["bbox_x0"], r["dpi"]) == r["mupdf_pix_x"]]
        broken_w = [
            r for r in w_in if OG.expected_image_width(r["bbox_x0"], r["bbox_x1"], r["dpi"]) == r["mupdf_width"]
        ]
    finally:
        OG.MUPDF_ROUND_EPS = real_eps
    check(
        "with MUPDF_ROUND_EPS = 0 the origin boundary control FAILS on every band case",
        0,
        len(broken),
        "if it still matched, the constant would not be load-bearing and should be dropped",
    )
    check(
        "with MUPDF_ROUND_EPS = 0 the WIDTH derivation also stops matching in the band",
        0,
        len(broken_w),
        "this is the symmetry claim's negative control, not an argument from the code comment",
    )
    check("...and the epsilon is restored afterwards, so the injection did not leak", 0.001, OG.MUPDF_ROUND_EPS)
    return {
        "epsilon_px": OG.MUPDF_ROUND_EPS,
        "origin_boundary": origin_rows,
        "right_edge_boundary": width_rows,
        "zero_epsilon_origin_matches": len(broken),
    }


def part_roundtrip() -> dict:
    """12/13 -- the arithmetic roundtrip, then the renderer's agreement with it."""
    print("\n== A33.3 roundtrip across fractional origins, and a wrong-origin control ==")

    # (a) PURE ARITHMETIC. No renderer, so antialiasing cannot confound it: for a known PDF x,
    #     the forward map to an integer column and the frozen inverse must land within one
    #     pixel, at every fractional origin phase and both scales.
    exact, sketch_ok, rows = [], [], []
    for dpi in (PRIMARY_DPI, R1_DPI):
        px_pt = 72.0 / dpi
        for ph in [0.0, 0.07, 0.13, 0.29, 0.41, 0.5, 0.61, 0.77, 0.88, 0.96]:
            bx0 = 100.0 + ph
            bx1 = bx0 + 40.0
            width = OG.expected_image_width(bx0, bx1, dpi)
            for frac in (0.0, 17.3, 39.4):
                mark = bx0 + frac
                col = OG.pdf_x_to_pixel(mark, bx0, dpi)
                est = OG.pixel_to_pdf_x(col, bx0, dpi)
                exact.append(abs(est - mark) <= px_pt)
                # the DELIBERATELY WRONG convention A30.3 sketched: linear across the bbox
                wrong = bx0 + (col / width) * (bx1 - bx0)
                sketch_ok.append(abs(wrong - mark) <= px_pt)
                rows.append(
                    {
                        "dpi": dpi,
                        "bbox_x0": bx0,
                        "mark_x": mark,
                        "col": col,
                        "frozen_inverse": est,
                        "frozen_err_pt": est - mark,
                        "a30_3_sketch_inverse": wrong,
                        "sketch_err_pt": wrong - mark,
                    }
                )
    check(
        "12. the frozen inverse recovers the source position at every fractional origin",
        (len(exact), True),
        (sum(exact), all(exact)),
        "a failure means the encoded transform is not the renderer's actual mapping",
    )
    check(
        "13. the deliberately wrong (linear-across-bbox) convention does NOT always recover it",
        False,
        all(sketch_ok),
        "if the wrong convention also passed, control 12 would prove nothing",
    )

    # (b) THE RENDERER AGREES with the forward map. Marks are FILL-ONLY: draw_rect(color=...)
    #     strokes the path with a default ~1pt pen, which puts ink ~0.5pt (2px at 300 DPI) left
    #     of the intended x and would look exactly like a broken transform.
    render_rows, agree = [], []
    for dpi in (PRIMARY_DPI, R1_DPI):
        for ph in (0.0, 0.29, 0.5, 0.77):
            bx0 = 100.0 + ph
            mark = bx0 + 17.3
            doc = pymupdf.open()
            page = doc.new_page(width=612, height=792)
            page.draw_rect(pymupdf.Rect(mark, 100.0, mark + 0.6, 120.0), color=None, fill=(0, 0, 0))
            pix = page.get_pixmap(
                matrix=pymupdf.Matrix(OG.scale(dpi), OG.scale(dpi)),
                clip=pymupdf.Rect(bx0, 100.0, bx0 + 40.0, 120.0),
                alpha=True,
            )
            col = leftmost_ink(pix)
            doc.close()
            predicted = OG.pdf_x_to_pixel(mark, bx0, dpi)
            delta = None if col is None else col - predicted
            agree.append(delta is not None and abs(delta) <= 1)
            render_rows.append(
                {
                    "dpi": dpi,
                    "bbox_x0": bx0,
                    "mark_x": mark,
                    "leftmost_inked_col": col,
                    "predicted_col": predicted,
                    "delta_col": delta,
                }
            )
    check(
        "the RENDERER's leftmost inked column matches the forward map within 1 px",
        (len(agree), True),
        (sum(agree), all(agree)),
        "a larger gap would mean the device origin rule is wrong, not merely antialiased",
    )
    # (c) THE RESOLVER ITSELF IS LOAD-BEARING. Arithmetic error only matters if it can cross a
    #     nearest-x decision boundary and change the identity. Searched deterministically over
    #     a grid rather than hand-picked, so the case is found, not constructed to order.
    crossings = []
    for dpi in (PRIMARY_DPI, R1_DPI):
        px_pt = 72.0 / dpi
        for width in (200.0, 320.0, 460.0):
            for ph in (0.0, 0.11, 0.23, 0.37, 0.5, 0.61, 0.79, 0.93):
                bx0 = 100.0 + ph
                bx1 = bx0 + width
                img = OG.expected_image_width(bx0, bx1, dpi)
                # Locate the column where the two transforms disagree MOST rather than guessing
                # a position: the disagreement is linear in the column, so its extreme sits at
                # one end, but WHICH end depends on the rounding phase.
                best_col, best_err = None, 0.0
                for col in (0, img // 4, img // 2, (3 * img) // 4, max(img - 1, 0)):
                    true_x = OG.pixel_to_pdf_x(col, bx0, dpi)
                    err = (bx0 + (col / img) * (bx1 - bx0)) - true_x
                    if abs(err) > abs(best_err):
                        best_col, best_err = col, err
                if best_col is None or abs(best_err) < 1e-9:
                    continue
                true_x = OG.pixel_to_pdf_x(best_col, bx0, dpi)
                # Place the competitor so the true start sits inside its own cell while the
                # wrong transform's drift carries the estimate across the midpoint.
                sep = abs(best_err) * 1.6
                comp = true_x + sep if best_err > 0 else true_x - sep
                cands = [(1, true_x), (2, comp)]
                right = AP.resolve_oracle_start_ngid(cands, true_x)
                wrong = AP.resolve_oracle_start_ngid(cands, bx0 + (best_col / img) * (bx1 - bx0))
                if right[0] == 1 and wrong[0] != 1:
                    crossings.append(
                        {
                            "dpi": dpi,
                            "bbox_width": width,
                            "phase": ph,
                            "col": best_col,
                            "drift_pt": best_err,
                            "drift_px": best_err / px_pt,
                            "separation_pt": sep,
                            "correct_transform_ngid": right[0],
                            "wrong_transform_ngid": wrong[0],
                            "wrong_refusal": wrong[1],
                        }
                    )
    check(
        "the wrong transform can cross a nearest-x boundary and change the IDENTITY",
        True,
        len(crossings) > 0,
        "without this the wrong-transform control only shows arithmetic drift, never that the "
        "resolver would return a different ngid",
    )
    worst = max((abs(r["sketch_err_pt"]) for r in rows), default=0.0)
    return {
        "n_identity_crossings_under_wrong_transform": len(crossings),
        "identity_crossing_examples": crossings[:5],
        "n_arithmetic_cases": len(rows),
        "frozen_inverse_ok": sum(exact),
        "sketch_ok": sum(sketch_ok),
        "worst_sketch_error_pt": worst,
        "worst_sketch_error_px_300": worst * PRIMARY_DPI / 72.0,
        "renderer_agreement": render_rows,
        "cases": rows[:10],
    }


def part_rotation() -> dict:
    print("\n== A33.4 rotation: exact clip carry, but start_x_px loses its meaning ==")
    findings = []
    for rot in (0, 90, 180, 270):
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        page.set_rotation(rot)
        page.draw_rect(pymupdf.Rect(200, 300, 210, 310), color=(0, 0, 0), fill=(0, 0, 0))
        clip = pymupdf.Rect(195, 295, 215, 315)
        naive = page.get_pixmap(
            matrix=pymupdf.Matrix(OG.scale(PRIMARY_DPI), OG.scale(PRIMARY_DPI)), clip=clip, alpha=True
        )
        rclip = clip * page.rotation_matrix
        fixed = page.get_pixmap(
            matrix=pymupdf.Matrix(OG.scale(PRIMARY_DPI), OG.scale(PRIMARY_DPI)), clip=rclip, alpha=True
        )
        findings.append(
            {
                "rotation": rot,
                "naive_clip_has_ink": leftmost_ink(naive) is not None,
                "rotated_clip_has_ink": leftmost_ink(fixed) is not None,
                "image_x_axis_is_pdf_x": rot in (0, 180),
                "image_x_axis_direction": "same" if rot == 0 else ("mirrored" if rot == 180 else "pdf_y"),
            }
        )
        doc.close()
    check(
        "a clip in UNROTATED pdf space renders no ink on a rotated page",
        [True, False, False, False],
        [f["naive_clip_has_ink"] for f in findings],
        "if it did render, rotation would be a non-issue and the refusal unnecessary",
    )
    check(
        "...the rotation matrix carries the clip exactly, at every rotation",
        [True] * 4,
        [f["rotated_clip_has_ink"] for f in findings],
    )
    check(
        "14. a non-zero rotation is REFUSED, fail-closed",
        OG.NONZERO_PAGE_ROTATION,
        raised(lambda: OG.check_rotation(90)),
    )
    check("14b. ...and rotation 0 is not refused", None, raised(lambda: OG.check_rotation(0)))
    return {
        "synthetic": findings,
        "ruling": "RATIFIED fail-closed NONZERO_PAGE_ROTATION -- ABORTS oracle construction and "
        "may never skip a page/region, drop a stimulus or reduce a denominator. "
        "The clip carries exactly, "
        "but at 90/270 the image x axis is the PDF y axis and at 180 it is "
        "mirrored, so start_x_px stops corresponding to a neutral glyph x0",
    }


# ----------------------------------------------------------------- DEVELOPMENT crops


def part_development() -> dict:
    """DEVELOPMENT diagnostics, and the END-TO-END resolver recovery the contract required."""
    print("\n== DEVELOPMENT crop diagnostics + end-to-end resolver recovery ==")
    from x18_start_x_discriminability import glyph_map  # one implementation, not a copy

    widths, heights, rows = [], [], []
    n_regions = n_rendered = n_short = n_invalid = n_outside = n_empty = n_determinism = n_width_fail = 0
    rotations, clipped = {}, []
    recov = {("H", 300): [0, 0], ("H", 330): [0, 0], ("C", 300): [0, 0], ("C", 330): [0, 0]}
    recovery_failures = []

    for name, path in DOCS:
        for member in HOLDOUT_GUARD:
            if member in str(path):
                raise SystemExit(f"REFUSED: {path} touches holdout member {member}")
        if not path.exists():
            continue
        h_pages = run_hybrid.run(path, limit=PAGE_LIMIT)
        x_pages, _s = run_extended.run(path, limit=PAGE_LIMIT)
        frame = BF.build_document_frame("devsha", name, BF.P_HEAD, h_pages, x_pages)

        # A30 starts on exactly these pages, from the A30 machinery -- never from heading text
        ordered = [d["page"] for d in sorted(h_pages, key=lambda d: d["page_number"])]
        occurrences, _ref = AP.instrumented_extract_anchors(ordered)
        starts, by_line = {}, {}
        for occ in occurrences:
            d = next((q for q in h_pages if q["page_number"] == occ.page_number), None)
            if d is None:
                continue
            ngid, reason = AP.resolve_start_ngid(d["page"], d["emitted"], occ.merged_index, occ.start_offset)
            if reason:
                continue
            starts.setdefault(occ.page_number, set()).add(ngid)
            by_line.setdefault((occ.anchor.page_number, occ.anchor.line_number), []).append(ngid)
        collisions = {(p, n) for (p, _ln), gs in by_line.items() if len(gs) > 1 for n in gs}

        doc = pymupdf.open(path)
        try:
            for pf in frame["pages"]:
                page = doc[pf["page_number"] - 1]
                rotations[page.rotation] = rotations.get(page.rotation, 0) + 1
                d_h = next(q for q in h_pages if q["page_number"] == pf["page_number"])
                xmap = glyph_map(d_h["chars"])
                region_of = {}
                for region in pf["regions"]:
                    for k in region["neutral_line_keys"]:
                        region_of[tuple(k)] = region["region_ordinal"]

                for region in pf["regions"]:
                    n_regions += 1
                    n_short += bool(region["short_trailing"])
                    try:
                        bbox = OG.region_bbox(pf, region["region_ordinal"])
                    except OG.OracleGeometryError:
                        n_invalid += 1
                        continue
                    widths.append(bbox[2] - bbox[0])
                    heights.append(bbox[3] - bbox[1])
                    if raised(lambda b=bbox: OG.validate_region_bbox_for_page(b, page.rect.width, page.rect.height)):
                        n_outside += 1
                    keys = {tuple(k) for k in region["neutral_line_keys"]}
                    for line in pf["neutral_lines"]:
                        if tuple(line["key"]) in keys:
                            lb = line["bbox"]
                            if lb[0] < bbox[0] or lb[2] > bbox[2] or lb[1] < bbox[1] or lb[3] > bbox[3]:
                                clipped.append({"document": name, "page": pf["page_number"], "line": line["key"]})

                    # EVERY region is rendered, so the denominators below are 1:1 with n_regions
                    ph = page.rect.height
                    clip = pymupdf.Rect(bbox[0], ph - bbox[3], bbox[2], ph - bbox[1])
                    mat = pymupdf.Matrix(OG.scale(PRIMARY_DPI), OG.scale(PRIMARY_DPI))
                    a = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
                    b = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
                    n_rendered += 1
                    if hashlib.sha256(a.tobytes("png")).hexdigest() != hashlib.sha256(b.tobytes("png")).hexdigest():
                        n_determinism += 1
                    if a.width == 0 or a.height == 0:
                        n_empty += 1
                    c330 = page.get_pixmap(
                        matrix=pymupdf.Matrix(OG.scale(R1_DPI), OG.scale(R1_DPI)), clip=clip, alpha=False
                    )
                    if a.width != OG.expected_image_width(
                        bbox[0], bbox[2], PRIMARY_DPI
                    ) or c330.width != OG.expected_image_width(bbox[0], bbox[2], R1_DPI):
                        n_width_fail += 1
                    if len(rows) < 12:
                        rows.append(
                            {
                                "document": name,
                                "page": pf["page_number"],
                                "region": region["region_ordinal"],
                                "bbox": list(bbox),
                                "w300": a.width,
                                "w330": c330.width,
                            }
                        )

                # --- END-TO-END: known start -> pixel -> A33 inverse -> ACTUAL A30 resolver
                for line in pf["neutral_lines"]:
                    gids = [g for g in line["gids"] if g in xmap]
                    if not gids:
                        continue
                    ro = region_of.get(tuple(line["key"]))
                    if ro is None:
                        continue
                    try:
                        bbox = OG.region_bbox(pf, ro)
                    except OG.OracleGeometryError:
                        continue
                    cands = [(g, xmap[g].x0) for g in gids]
                    for g in gids:
                        pops = []
                        if g in starts.get(pf["page_number"], set()):
                            pops.append("H")
                        if (pf["page_number"], g) in collisions:
                            pops.append("C")
                        if not pops:
                            continue
                        for dpi in (PRIMARY_DPI, R1_DPI):
                            col = OG.pdf_x_to_pixel(xmap[g].x0, bbox[0], dpi)
                            est = OG.pixel_to_pdf_x(col, bbox[0], dpi)
                            got, why = AP.resolve_oracle_start_ngid(cands, est)
                            for pop in pops:
                                recov[(pop, dpi)][1] += 1
                                if got == g:
                                    recov[(pop, dpi)][0] += 1
                                else:
                                    recovery_failures.append(
                                        {
                                            "population": pop,
                                            "dpi": dpi,
                                            "document": name,
                                            "page": pf["page_number"],
                                            "ngid": g,
                                            "got": got,
                                            "refusal": why,
                                        }
                                    )
        finally:
            doc.close()

    for (pop, dpi), (ok, tot) in sorted(recov.items()):
        print(f"  {pop}_{dpi} recovered {ok}/{tot}")
    check(
        "end-to-end: every H/C start recovers its own ngid through the A33 transform + A30 resolver",
        [],
        recovery_failures[:10],
        "a failure means the frozen transform and the frozen resolver do not compose",
    )
    check(
        "...and the end-to-end population is non-empty at both scales, so it is not vacuous",
        True,
        all(tot > 0 for _k, (_o, tot) in recov.items()),
    )
    check("10. every rendered region matches the frozen width derivation at BOTH scales", 0, n_width_fail)
    check("11. re-rendering the same bbox/renderer/DPI reproduces the PNG hash", 0, n_determinism)
    check(
        "no committed neutral line is clipped by the zero-padding union",
        [],
        clipped[:10],
        "if the union clipped committed content, A33.1 would need review -- padding is NOT tuned",
    )
    check("no DEVELOPMENT region produced an empty render", 0, n_empty)
    check("every region enumerated was also rendered, so render denominators are not a sample", n_regions, n_rendered)
    check("every DEVELOPMENT page consumed has rotation 0", [0], sorted(rotations))
    if clipped:
        stop("ZERO_PADDING_UNION_CLIPS_COMMITTED_CONTENT", clipped[:10])
    if recovery_failures:
        stop("END_TO_END_RESOLVER_RECOVERY_FAILED", recovery_failures[:10])
    return {
        "n_regions": n_regions,
        "n_regions_rendered": n_rendered,
        "render_sample_rule": "none -- all regions rendered",
        "n_short_trailing": n_short,
        "n_invalid_bbox": n_invalid,
        "n_out_of_page_bbox": n_outside,
        "n_empty_render": n_empty,
        "n_render_determinism_failures": n_determinism,
        "n_width_derivation_failures": n_width_fail,
        "page_rotation_census": rotations,
        "end_to_end_recovery": {f"{p}_{d}": {"recovered": o, "n": t} for (p, d), (o, t) in sorted(recov.items())},
        "end_to_end_failures": recovery_failures[:10],
        "bbox_width_pt": (
            {"min": min(widths), "median": statistics.median(widths), "max": max(widths)} if widths else None
        ),
        "bbox_height_pt": (
            {"min": min(heights), "median": statistics.median(heights), "max": max(heights)} if heights else None
        ),
        "clipped_lines": clipped[:10],
        "sampled_renders": rows,
    }


def main() -> int:
    bbox = part_bbox()
    mapping = part_mapping()
    epsilon = part_epsilon()
    roundtrip = part_roundtrip()
    rotation = part_rotation()
    dev = part_development()
    doc = {
        "population": "SYNTHETIC + DEVELOPMENT -- no holdout opened, nothing scored",
        "contract": "A33 (crop + transform), corrected forward by A34 (renderer epsilon)",
        "renderer": "MuPDF (pymupdf)",
        "renderer_version": str(pymupdf.version),
        "region_bbox_rule": "minimal axis-aligned union of COMMITTED neutral-line bboxes, zero padding",
        "mupdf_round_eps_px": OG.MUPDF_ROUND_EPS,
        "frozen_inversion": (
            "s = DPI/72; eps = 0.001 px; device_x0 = floor(bbox_x0*s + eps); pdf_x = (device_x0 + start_x_px) / s"
        ),
        "frozen_width_validation": "ceil(bbox_x1*s - eps) - floor(bbox_x0*s + eps)",
        "a33_stated_was": "device_x0 = floor(bbox_x0 * DPI/72)  -- epsilon-free, corrected by A34",
        "a30_3_sketch_was": "pdf_x = bbox_x0 + (start_x_px / image_width) * (bbox_x1 - bbox_x0)",
        "metadata_insufficient": False,
        "bbox": bbox,
        "mupdf_mapping": mapping,
        "epsilon_boundary": epsilon,
        "roundtrip": roundtrip,
        "rotation": rotation,
        "development": dev,
        "stop_conditions": STOPS,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass; {len(STOPS)} stop conditions")
    print(f"wrote {OUT}")
    return 1 if FAILED or STOPS else 0


if __name__ == "__main__":
    sys.exit(main())
