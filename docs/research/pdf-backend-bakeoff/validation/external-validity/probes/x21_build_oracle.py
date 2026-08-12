"""x21 -- A35: the adjudicator prompt and `build_oracle`, with executable controls.

NOT CONFIRMATORY. SYNTHETIC + DEVELOPMENT only. No holdout document is opened, nothing is
adjudicated, nothing is scored, and no confirmatory oracle artifact is created. Evidence:
`results/x21_build_oracle.json`.

The A35 contract fixed every rule and control below BEFORE this probe existed. Each control
states the fact that would make it FAIL, and no control compares a helper with itself where an
independent mutation or injection was possible: the leakage gate is falsified by injecting
forbidden content, the join by misassociating the key, the blind-id scheme by replacing it
wholesale, and each fail-closed geometry refusal by corrupting committed geometry.

RUN WITH AN INTERPRETER CARRYING BOTH `pymupdf` AND `pypdfium2` (pinned to the project's
version), exactly as `x20` requires -- `pymupdf` is deliberately absent from the project venv.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
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

import build_frames as BF  # noqa: E402
import build_oracle as BO  # noqa: E402
import methodology_contracts as MC  # noqa: E402
import oracle_geometry as OG  # noqa: E402
import run_extended  # noqa: E402
import run_hybrid  # noqa: E402

OUT = EV / "results" / "x21_build_oracle.json"
ROWS: list[dict] = []
FAILED: list[str] = []
STOPS: list[dict] = []

DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-hr-8752/1", REPO / "tests/corpus/118-hr-8752/1_reported-in-house.pdf"),
    ("119-hr-1/1", REPO / "tests/corpus/119-hr-1/1_reported-in-house.pdf"),
]
PAGE_LIMIT = 20  # machinery demonstration, NOT a census -- every count below is reported as-is


def check(name: str, expected, observed, fails_when: str = "") -> bool:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    if not ok:
        FAILED.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   expected={expected!r} observed={observed!r}"))
    return ok


def refusal(fn) -> str | None:
    """The refusal class a callable raises, or None if it returned. Never swallows the reason."""
    try:
        fn()
    except (BO.OracleBuildError, OG.OracleGeometryError) as exc:
        return exc.reason
    except (MC.BlindIdCollision, MC.DuplicateStimulusIdentity, MC.UnknownRole) as exc:
        return type(exc).__name__
    return None


# ------------------------------------------------------------------ synthetic material


# One 8-line region per synthetic page. 20 is not decorative: the R1 draw takes
# floor(n * 0.10), so a smaller fixture yields ZERO repeats and controls 2, 3, 8, 12 and 20
# then pass on an empty population -- which is how a vacuous control suite looks. The
# non-vacuity guards beside those controls exist to make that failure visible rather than green.
N_SYNTHETIC_REGIONS = 20
SYNTHETIC_LINES_PER_REGION = 8


def synthetic_pdf(tmp: Path, rotation: int = 0, n_pages: int = N_SYNTHETIC_REGIONS) -> Path:
    """A deterministic multi-page PDF whose geometry we choose, so injections are exact."""
    doc = pymupdf.open()
    for p in range(n_pages):
        page = doc.new_page(width=612, height=792)
        for i in range(SYNTHETIC_LINES_PER_REGION):
            page.insert_text((100.0, 120.0 + i * 20.0), f"SYNTHETIC HEADING P{p} LINE {i}", fontsize=11)
        if rotation:
            page.set_rotation(rotation)
    path = tmp / f"synthetic_{rotation}_{n_pages}.pdf"
    doc.save(path)
    doc.close()
    return path


def synthetic_page_frame(page_number: int, c_frame: bool = True, d_frame: bool = False) -> dict:
    lines, keys = [], []
    for i in range(SYNTHETIC_LINES_PER_REGION):
        baseline = 792.0 - (120.0 + i * 20.0)
        bbox = [100.0, baseline - 3.0, 300.0, baseline + 9.0]
        lines.append(
            {
                "key": [page_number, i],
                "baseline": baseline,
                "bbox": bbox,
                "gids": [i * 10, i * 10 + 1],
                # A38.2 -- two candidates a fixed distance apart, so a nearest-glyph boundary
                # exists to cross and an exact tie can be constructed
                "identity_candidates": [
                    {"ngid": i * 10, "x0": 100.0},
                    {"ngid": i * 10 + 1, "x0": 140.0},
                ],
                "region_ordinal": 0,
                "in_m0_risk_set": True,
                "line_state": {"state": "BOTH_PRESENT", "h_text": f"LINE {i}", "x_text": f"LINE {i}"},
            }
        )
        keys.append([page_number, i])
    return {
        "page_number": page_number,
        "neutral_lines": lines,
        "regions": [
            {
                "page_number": page_number,
                "region_ordinal": 0,
                "neutral_line_keys": keys,
                "short_trailing": False,
                "line_count": SYNTHETIC_LINES_PER_REGION,
                "d_frame": d_frame,
                "d_reasons": ["TEXT_DISCORDANCE"] if d_frame else [],
                "c_frame": c_frame,
            }
        ],
    }


def synthetic_frame(
    document_sha256="synthsha0123456789",
    document_id="SYNTHETIC/1",
    n_pages: int = N_SYNTHETIC_REGIONS,
    memberships: list[tuple[bool, bool]] | None = None,
) -> dict:
    """A frame in `build_frames`' emitted shape, with bboxes and C/D membership we control."""
    memberships = memberships or [(True, False)] * n_pages
    return {
        "document": document_id,
        "document_sha256": document_sha256,
        "population": BF.P_HEAD,
        "region_size": SYNTHETIC_LINES_PER_REGION,
        "pages": [synthetic_page_frame(p + 1, c, d) for p, (c, d) in enumerate(memberships[:n_pages])],
        # A38.3/A38.5 -- the frame owns these; build_oracle takes them from here and nowhere else
        "architecture_occurrences": {
            arm: [
                {
                    "anchor": {
                        "page_number": p + 1,
                        "line_number": 3,
                        "kind": "account",
                        "text": f"SYNTHETIC ACCOUNT SENTINEL P{p + 1}",
                        "division": "",
                    },
                    # A38 repair -- region ordinals restart per page, so the scope is the PAIR.
                    # Every synthetic page deliberately reuses region_ordinal 0 with a distinct
                    # sentinel text, so a page-blind filter would visibly contaminate.
                    "page_number": p + 1,
                    "region_ordinal": 0,
                    "placed_neutral_line_key": [p + 1, 2],
                    "occurrence_key": [document_sha256, p + 1, [p + 1, 2], 20],
                    "match_status": "MATCHABLE",
                    "unmatched_reason": None,
                    "immediate_parent": "SYNTHETIC AGENCY",
                    "breadcrumb": ["SYNTHETIC AGENCY", "SYNTHETIC ACCOUNT"],
                }
                for p in range(n_pages)
            ]
            for arm in ("H", "X")
        },
        "m9": {
            arm: {
                "derive_size_bands_returns_a_band": True,
                "coverage": 1.0,
                "coverage_floor": 0.85,
                "coverage_meets_floor": True,
                "n_lines_total": n_pages * SYNTHETIC_LINES_PER_REGION,
                "n_margin_numbered_lines": n_pages * SYNTHETIC_LINES_PER_REGION,
                "n_margin_numbered_with_glyph_size": n_pages * SYNTHETIC_LINES_PER_REGION,
                "margin_numbered_line_keys": [[p + 1, i] for p in range(n_pages) for i in range(8)],
            }
            for arm in ("H", "X")
        },
    }


def synthetic_documents(
    tmp: Path,
    rotation: int = 0,
    n_pages: int = N_SYNTHETIC_REGIONS,
    memberships: list[tuple[bool, bool]] | None = None,
) -> list[dict]:
    return [
        {
            "frame": synthetic_frame(n_pages=n_pages, memberships=memberships),
            "pdf_path": synthetic_pdf(tmp, rotation, n_pages),
            "stratum": "SYNTHETIC",
        }
    ]


# --------------------------------------------------------------- the prompt controls


def part_prompt() -> dict:
    print("\n== the adjudicator prompt: what it asks, and what it must never say ==")
    text = BO.PROMPT_PATH.read_text()
    report = BO.prompt_report(text)

    check(
        "18. the prompt asks NO M6 / amount-attribution question",
        [],
        report["m6_questions"],
        "an amount-to-account or total-the-figures question appears; M6 is deferred by A20",
    )
    check(
        "19. the prompt carries the A33.5 visible-character instruction",
        True,
        "first character's own visible ink" in text and "strike-through" in text,
        "the A33.5 wording is missing, so start_x_px would be collected under a different "
        "definition and nothing downstream could tell",
    )
    check(
        "the prompt forbids a text-box / bounding-box edge (A33.5)",
        True,
        "text-box" in text,
        "an adjudicator could mark a bounding-box edge instead of the character's own ink",
    )
    check(
        "the prompt says start_x_px is an identity annotation only",
        True,
        "position annotation" in text,
        "start_x_px could be read as evidence about text, parent or role",
    )
    check(
        "the prompt requires text, parent and role to be judged independently",
        True,
        "judged independently" in text or "independently of it" in text,
        "one field could be adjusted to agree with another",
    )
    check(
        "the prompt leaks no forbidden architecture / frame / stratum / control token",
        [],
        report["forbidden"],
        "any of H/X, hybrid, extended glyph, architecture, C/D-frame, stratum, control status, "
        "repeat status or DPI appears in the adjudicator's instructions",
    )
    check(
        "the prompt carries every required instruction",
        [],
        report["missing_required"],
        "a required question or instruction is absent",
    )
    check(
        "the committed prompt LOADS -- the gate accepts it",
        True,
        refusal(lambda: BO.load_prompt()) is None,
        "the committed prompt is refused by its own gate",
    )

    # THE NEGATIVE CONTROLS. A gate that has never rejected anything is not evidence.
    injections = {
        "architecture name": "The hybrid architecture produced this text.",
        "arm letter": "Compare arm H against arm X.",
        "frame label": "This is a C-frame region.",
        "stratum": "Stratum: appropriations-house.",
        "control status": "This is a negative control item.",
        "repeat status": "This is the R1 reliability repeat.",
        "render scale": "Rendered at 300 dpi.",
        "engine name": "Extracted with pypdfium2.",
    }
    caught = {}
    for label, snippet in injections.items():
        caught[label] = bool(BO.scan_forbidden(text + "\n" + snippet))
    check(
        "10a. NEGATIVE -- every injected forbidden disclosure is CAUGHT by the prompt gate",
        {k: True for k in injections},
        caught,
        "an injected architecture / frame / stratum / control / scale disclosure passes the gate, "
        "which would mean the gate cannot see the leak it exists to stop",
    )

    m6_injection = "Also report which account each dollar amount belongs to."
    check(
        "10b. NEGATIVE -- an injected M6 question is CAUGHT",
        True,
        bool(BO.prompt_report(text + "\n" + m6_injection)["m6_questions"]),
        "an amount-attribution question could be added without the gate firing",
    )
    stripped = text.replace("first character's own visible ink", "first character")
    check(
        "10c. NEGATIVE -- removing the A33.5 wording makes the completeness gate FAIL",
        True,
        "a33_5_visible_ink" in BO.prompt_report(stripped)["missing_required"],
        "the required-instruction gate cannot detect the A33.5 instruction going missing",
    )
    check(
        "...and a prompt carrying an injected leak is REFUSED, not merely reported",
        BO.PROMPT_LEAKS,
        refusal(lambda: _load_text(text + "\nCompare arm H against arm X.")),
        "load_prompt returns a leaking prompt instead of refusing it",
    )
    return {
        "prompt_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "prompt_chars": len(text),
        "forbidden_patterns_checked": sorted(BO.FORBIDDEN_PATTERNS),
        "required_instructions_checked": sorted(BO.REQUIRED_INSTRUCTIONS),
        "injections_caught": caught,
    }


def _load_text(text: str):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "p.md"
        p.write_text(text)
        return BO.load_prompt(p)


# ------------------------------------------------------- selection / blinding controls


def part_blinding(tmp: Path) -> dict:
    print("\n== selection, blind ids, and presentation order ==")
    docs = synthetic_documents(tmp)
    result = BO.build(docs)
    specs = BO.plan_document_stimuli(docs[0]["frame"], "SYNTHETIC")
    specs = specs + BO.plan_r1_repeats(specs)

    selected_before = [MC.canonical(s.final_identity) for s in specs]
    order_before = [MC.canonical(s.final_identity) for s in BO.presentation_order(specs)]

    # NEGATIVE: replace the blind-id scheme WHOLESALE, canonical identities held fixed.
    real = MC.blind_id
    try:
        MC.blind_id = lambda ident: "SCHEME2-" + real(ident)[::-1]
        specs2 = BO.plan_document_stimuli(docs[0]["frame"], "SYNTHETIC")
        specs2 = specs2 + BO.plan_r1_repeats(specs2)
        selected_after = [MC.canonical(s.final_identity) for s in specs2]
        order_after = [MC.canonical(s.final_identity) for s in BO.presentation_order(specs2)]
        alias_changed = real(specs[0].final_identity) != MC.blind_id(specs[0].final_identity)
    finally:
        MC.blind_id = real

    check(
        "6. changing the blind-ID scheme changes NO selected stimulus",
        selected_before,
        selected_after,
        "sampling consumes a blind id, so the alias scheme could move the sample (A28.3)",
    )
    check(
        "7. ...and changes NO presentation rank",
        order_before,
        order_after,
        "blind-order ranks blind ids rather than canonical final identities",
    )
    check(
        "...and the alias itself DID change, so the control is not vacuous",
        True,
        alias_changed,
        "the substituted scheme returns the same alias, proving nothing",
    )

    # NEGATIVE: force a collision. Must abort -- never salt, re-roll, overwrite or merge.
    collided = MC.blind_id
    try:
        MC.blind_id = lambda ident: "CONSTANT"
        outcome = refusal(lambda: BO.build(docs))
    finally:
        MC.blind_id = collided
    check(
        "8. NEGATIVE -- an injected blind-ID collision ABORTS the build",
        "BlindIdCollision",
        outcome,
        "the build completes with a collision, silently overwriting or merging two stimuli (I14)",
    )

    n = result.key["n_stimuli"]
    check(
        "20. realized blind-ID uniqueness holds over the COMPLETE set, repeats included",
        n,
        len({r["png_sha256"] and bid for bid, r in result.key["stimuli"].items()}),
        "two realized stimuli share an adjudicator-facing id",
    )
    check(
        "...and the uniqueness assertion is made over instances that INCLUDE R1 repeats",
        True,
        any(r["is_r1_repeat"] for r in result.key["stimuli"].values()),
        "no repeat exists in the realized set, so control 20 never exercised the repeat case",
    )
    return {
        "n_stimuli": n,
        "n_r1_repeats": sum(1 for r in result.key["stimuli"].values() if r["is_r1_repeat"]),
        "blind_id_scheme_swap_changed_selection": selected_before != selected_after,
        "blind_id_scheme_swap_changed_order": order_before != order_after,
    }


# --------------------------------------------------------------- render / scale controls


def part_render(tmp: Path) -> dict:
    print("\n== rendering: determinism, scale, and geometry-only input ==")
    docs = synthetic_documents(tmp)
    frame = docs[0]["frame"]
    page_frame = frame["pages"][0]
    bbox = OG.region_bbox(page_frame, 0)

    doc = pymupdf.open(docs[0]["pdf_path"])
    page = doc[0]
    a, _w, _h = BO.render_region(page, bbox, 300)
    b, _w2, _h2 = BO.render_region(page, bbox, 300)
    check(
        "1. same bbox + renderer + DPI re-renders to an IDENTICAL PNG hash",
        hashlib.sha256(a).hexdigest(),
        hashlib.sha256(b).hexdigest(),
        "the renderer is not deterministic, so a stored png_sha256 could not detect a re-render",
    )

    # 4. the renderer consumes PDF GEOMETRY. Rendering the same clip straight from pymupdf,
    # with no frame and no architecture output in scope at all, must give the same bytes.
    height = page.rect.height
    clip = pymupdf.Rect(bbox[0], height - bbox[3], bbox[2], height - bbox[1])
    direct = page.get_pixmap(matrix=pymupdf.Matrix(OG.scale(300), OG.scale(300)), clip=clip, alpha=False)
    check(
        "4. the renderer consumes PDF geometry only -- bytes match a frame-free direct render",
        hashlib.sha256(direct.tobytes("png")).hexdigest(),
        hashlib.sha256(a).hexdigest(),
        "the frame contributes something to the pixels, i.e. an arm's output could reach the image (I6)",
    )

    r330, _w3, _h3 = BO.render_region(page, bbox, 330)
    check(
        "17. the PNG hash CHANGES when the rendered stimulus really changes",
        True,
        hashlib.sha256(a).hexdigest() != hashlib.sha256(r330).hexdigest(),
        "two genuinely different renders hash the same, so the hash cannot detect a substitution",
    )
    doc.close()

    # 5. mutate every H/X text in the frame; the pixels may not move.
    mutated = copy.deepcopy(docs)
    for line in mutated[0]["frame"]["pages"][0]["neutral_lines"]:
        line["line_state"]["h_text"] = "MUTATED-H-" * 4
        line["line_state"]["x_text"] = "MUTATED-X-" * 4
    for arm in ("H", "X"):
        for rec in mutated[0]["frame"]["architecture_occurrences"][arm]:
            rec["anchor"]["text"] = "TOTALLY DIFFERENT"
    # sorted, not a set: a set's repr order varies with per-process string hash randomisation,
    # which made this committed artifact differ between runs of identical inputs
    base_hashes = sorted({r["png_sha256"] for r in BO.build(docs).key["stimuli"].values()})
    mutated_hashes = sorted({r["png_sha256"] for r in BO.build(mutated).key["stimuli"].values()})
    check(
        "5. changing H/X text cannot change ANY rendered PNG",
        base_hashes,
        mutated_hashes,
        "an arm's text reaches the renderer or the crop, which would let the thing under test choose its own stimulus",
    )

    # 2 + 3. the R1 repeat shares the primary's bbox exactly; only the raster scale differs.
    result = BO.build(docs)
    pairs = {}
    for record in result.key["stimuli"].values():
        pairs.setdefault(record["base_identity"], []).append(record)
    same_bbox, only_scale = [], []
    for records in pairs.values():
        primary = next((r for r in records if not r["is_r1_repeat"]), None)
        repeat = next((r for r in records if r["is_r1_repeat"]), None)
        if primary and repeat:
            same_bbox.append(primary["bbox_pdf_points"] == repeat["bbox_pdf_points"])
            only_scale.append(
                primary["dpi"] == 300
                and repeat["dpi"] == 330
                and primary["png_sha256"] != repeat["png_sha256"]
                and primary["document_sha256"] == repeat["document_sha256"]
                and primary["page_number"] == repeat["page_number"]
                and primary["region_ordinal"] == repeat["region_ordinal"]
            )
    check(
        "2. every R1 repeat renders the EXACT same PDF bbox as its primary",
        (len(same_bbox), True),
        (sum(same_bbox), all(same_bbox) and bool(same_bbox)),
        "a repeat is cropped differently, so a text disagreement could be a crop artifact (A28.4)",
    )
    check(
        "3. ...and differs from it ONLY by raster scale (300 -> 330)",
        (len(only_scale), True),
        (sum(only_scale), all(only_scale) and bool(only_scale)),
        "a repeat differs in source region, page or document, or is not 330 DPI",
    )

    # 13. the crop is EXACTLY the committed frame geometry -- minimal union, zero padding.
    committed = [
        line["bbox"]
        for line in page_frame["neutral_lines"]
        if list(line["key"]) in page_frame["regions"][0]["neutral_line_keys"]
    ]
    union = [
        min(b[0] for b in committed),
        min(b[1] for b in committed),
        max(b[2] for b in committed),
        max(b[3] for b in committed),
    ]
    # the record for THIS page, not merely the first in presentation order
    rendered_bbox = next(
        r["bbox_pdf_points"]
        for r in result.key["stimuli"].values()
        if r["page_number"] == page_frame["page_number"] and not r["is_r1_repeat"]
    )
    check(
        "13. the crop equals the committed-frame minimal union EXACTLY, zero padding",
        union,
        rendered_bbox,
        "the builder padded, expanded to column or page, re-clustered from the PDF, or repaired "
        "the bbox -- each would show the adjudicator something other than the committed region",
    )
    return {
        "synthetic_bbox": list(bbox),
        "expected_width_300": OG.expected_image_width(bbox[0], bbox[2], 300),
        "expected_width_330": OG.expected_image_width(bbox[0], bbox[2], 330),
        "n_r1_pairs_checked": len(same_bbox),
    }


# --------------------------------------------------------------- fail-closed geometry


def part_fail_closed(tmp: Path) -> dict:
    print("\n== fail-closed: corrupt geometry ABORTS, and never becomes a skip ==")
    clean = synthetic_documents(tmp)
    n_clean = BO.build(clean).key["n_stimuli"]

    outside = copy.deepcopy(clean)
    outside[0]["frame"]["pages"][0]["neutral_lines"][0]["bbox"] = [100.0, 600.0, 9999.0, 640.0]
    check(
        "14. NEGATIVE -- a region bbox extending past the page ABORTS",
        OG.REGION_BBOX_OUTSIDE_PAGE,
        refusal(lambda: BO.build(outside)),
        "an out-of-page bbox is clipped, intersected or padded instead of refused (A33.1)",
    )

    nonpositive = copy.deepcopy(clean)
    nonpositive[0]["frame"]["pages"][0]["neutral_lines"][2]["bbox"] = [300.0, 600.0, 100.0, 640.0]
    check(
        "15. NEGATIVE -- a non-positive committed line bbox ABORTS",
        OG.NON_POSITIVE_LINE_BBOX,
        refusal(lambda: BO.build(nonpositive)),
        "a degenerate line passes because its siblings make the union positive, so defective "
        "committed geometry would render and never be seen",
    )

    missing = copy.deepcopy(clean)
    missing[0]["frame"]["pages"][0]["neutral_lines"][1]["bbox"] = None
    check(
        "NEGATIVE -- a missing committed line bbox ABORTS",
        OG.MISSING_LINE_BBOX,
        refusal(lambda: BO.build(missing)),
        "a line with no geometry is skipped, silently shrinking the crop",
    )

    nonfinite = copy.deepcopy(clean)
    nonfinite[0]["frame"]["pages"][0]["neutral_lines"][3]["bbox"] = [100.0, float("nan"), 300.0, 640.0]
    check(
        "NEGATIVE -- a non-finite committed line bbox ABORTS",
        OG.NON_FINITE_LINE_BBOX,
        refusal(lambda: BO.build(nonfinite)),
        "a NaN coordinate propagates into a clip rectangle",
    )

    # 16. rotation aborts -- and the abort may not degrade into a smaller study.
    rotated = [
        {
            "frame": synthetic_frame(),
            "pdf_path": synthetic_pdf(tmp, rotation=90),
            "stratum": "SYNTHETIC",
        }
    ]
    rot_reason = refusal(lambda: BO.build(rotated))
    check(
        "16. NEGATIVE -- a non-zero page rotation ABORTS oracle construction",
        OG.NONZERO_PAGE_ROTATION,
        rot_reason,
        "a rotated page renders anyway, though start_x_px would no longer be a PDF x offset (A33.4)",
    )
    n_rotated = None
    try:
        n_rotated = BO.build(rotated).key["n_stimuli"]
    except (BO.OracleBuildError, OG.OracleGeometryError):
        pass
    check(
        "16b. ...and the rotation refusal CANNOT become a skipped stimulus",
        None,
        n_rotated,
        "the build returns a result with the rotated page's regions dropped, turning an "
        "unrepresentable condition into a quietly smaller study with no visible loss",
    )
    check(
        "...and a clean build of the same shape DOES produce stimuli, so 16b is not vacuous",
        True,
        n_clean > 0,
        "the clean case produces nothing either, so 'None' proved nothing about rotation",
    )

    # the holdout guard, and the pre-execution write boundary
    holdout = copy.deepcopy(clean)
    holdout[0]["frame"]["document"] = "116-hr-7611/1"
    check(
        "NEGATIVE -- a confirmatory holdout member is REFUSED while the boundary is not VALID",
        BO.HOLDOUT_BEFORE_EXECUTION_BOUNDARY,
        refusal(lambda: BO.build(holdout)),
        "a holdout document can be opened before execution is authorised",
    )

    # A38 REPAIR -- the execution-boundary ACCESS MATRIX. The old rule refused all 17 members
    # unconditionally, so the component G5 exists to freeze could never execute after
    # authorization. Authorization is the marker STATE, never mere path existence.
    real_state = BO.execution_boundary_state
    matrix = {}
    try:
        for state in ("ABSENT", "UNCOMMITTED", "MUTATED", "VALID"):
            BO.execution_boundary_state = lambda s=state: s
            matrix[state] = {
                "holdout": refusal(lambda: BO.build(holdout)),
                "canonical_write": refusal(lambda: BO.assert_write_permitted(EV / "results" / "oracle_key.json")),
            }
    finally:
        BO.execution_boundary_state = real_state
    check(
        "the boundary ACCESS MATRIX permits a holdout only at VALID",
        {
            "ABSENT": BO.HOLDOUT_BEFORE_EXECUTION_BOUNDARY,
            "UNCOMMITTED": BO.HOLDOUT_BEFORE_EXECUTION_BOUNDARY,
            "MUTATED": BO.HOLDOUT_BEFORE_EXECUTION_BOUNDARY,
            "VALID": None,
        },
        {s: v["holdout"] for s, v in matrix.items()},
        "an ABSENT, UNCOMMITTED or MUTATED marker unlocks the holdout -- a stray or edited "
        "EXECUTION-START.json would then authorize the confirmatory run",
    )
    check(
        "...and every CANONICAL confirmatory write obeys the same VALID-only rule",
        {
            "ABSENT": BO.CONFIRMATORY_WRITE_BEFORE_EXECUTION,
            "UNCOMMITTED": BO.CONFIRMATORY_WRITE_BEFORE_EXECUTION,
            "MUTATED": BO.CONFIRMATORY_WRITE_BEFORE_EXECUTION,
            "VALID": None,
        },
        {s: v["canonical_write"] for s, v in matrix.items()},
        "an artifact can be created under a weaker condition than the material it describes",
    )
    check(
        "the S1 and cross-engine canonical paths are inside the same guarded set",
        (True, True),
        (
            (EV / "results" / "s1_control.json").resolve() in BO.CANONICAL_ARTIFACTS,
            (EV / "results" / "cross_engine_control.json").resolve() in BO.CANONICAL_ARTIFACTS,
        ),
        "an S1 or cross-engine confirmatory artifact could be written with no boundary at all",
    )
    check(
        "...and a scratch path is NOT refused, so the write guard is not blanket-refusing",
        None,
        refusal(lambda: BO.assert_write_permitted(tmp / "oracle_key.json")),
        "the guard refuses everything, which would make the controls above meaningless",
    )
    check(
        "no real execution marker was created by any of this",
        False,
        (EV / "results" / "EXECUTION-START.json").exists(),
        "the boundary controls created the very marker they exist to test",
    )
    return {
        "n_clean_stimuli": n_clean,
        "rotation_refusal": rot_reason,
        "rotation_build_returned": n_rotated,
        "refusal_classes": [
            OG.MISSING_LINE_BBOX,
            OG.NON_FINITE_LINE_BBOX,
            OG.NON_POSITIVE_LINE_BBOX,
            OG.REGION_BBOX_OUTSIDE_PAGE,
            OG.NONZERO_PAGE_ROTATION,
        ],
    }


# ------------------------------------------------------------- leakage and the join


def part_leakage_and_join(tmp: Path) -> dict:
    print("\n== the blind file leaks nothing, and the private key is load-bearing ==")
    docs = synthetic_documents(tmp)
    result = BO.build(docs)
    report = BO.leakage_report(result.blind, result.key)

    check(
        "9. the adjudicator-facing artifact carries ONLY id, image and question",
        [],
        report["unexpected_keys"],
        "a field beyond the blinding allowlist reaches the adjudicator",
    )
    check(
        "9b. ...and no private VALUE appears anywhere in its serialization",
        0,
        report["n_leaked_values"],
        "a document sha, canonical identity or png hash is smuggled inside an allowed field",
    )
    check(
        "9c. ...and no forbidden architecture / frame / stratum token appears in it",
        [],
        report["forbidden_text"],
        "the blind file names an architecture, frame, stratum, control or repeat",
    )

    # 10. NEGATIVE -- inject each private field into the blind file and require the gate to fire.
    injected_caught = {}
    for fname in ("document_sha256", "canonical_identity", "png_sha256"):
        leaked = copy.deepcopy(result.blind)
        value = next(iter(result.key["stimuli"].values()))[fname]
        leaked["items"][0]["question"] = leaked["items"][0]["question"] + f"\n{value}"
        rep = BO.leakage_report(leaked, result.key)
        injected_caught[fname] = rep["n_leaked_values"] > 0
    structural = copy.deepcopy(result.blind)
    structural["items"][0]["frame"] = "C"
    structural["items"][0]["stratum"] = "appropriations-house"
    injected_caught["structural_frame_and_stratum"] = bool(BO.leakage_report(structural, result.key)["unexpected_keys"])
    textual = copy.deepcopy(result.blind)
    textual["items"][0]["question"] = textual["items"][0]["question"] + "\nThis is a C-frame region."
    injected_caught["forbidden_text"] = bool(BO.leakage_report(textual, result.key)["forbidden_text"])
    check(
        "10. NEGATIVE -- every injected leak makes the leakage gate FAIL",
        {k: True for k in injected_caught},
        injected_caught,
        "an injected private value, an extra structural field, or a forbidden token passes the "
        "gate -- which would mean a green leakage report proves nothing",
    )
    check(
        "...and write_artifacts REFUSES a leaking blind file rather than writing it",
        BO.BLIND_ARTIFACT_LEAKS,
        refusal(lambda: BO.write_artifacts(_leaky(result), tmp / "leaky")),
        "a leaking artifact is written and the leak survives to the adjudicator",
    )

    # 11 + 12. the private key must carry the join, and the join must be load-bearing.
    check(
        "11. the private key carries every field the downstream join needs",
        [],
        BO.verify_join(result),
        "a join field is missing, so an adjudication could not be bound back to its region",
    )
    shuffled = BO.BuildResult(key=copy.deepcopy(result.key), blind=result.blind, images=result.images)
    bids = list(shuffled.key["stimuli"])
    if len(bids) >= 2:
        rotated_records = [shuffled.key["stimuli"][b] for b in bids[1:]] + [shuffled.key["stimuli"][bids[0]]]
        shuffled.key["stimuli"] = dict(zip(bids, rotated_records))
    defects = BO.verify_join(shuffled)
    check(
        "12. NEGATIVE -- a misassociated private key BREAKS the join, proving it load-bearing",
        True,
        len(defects) > 0,
        "adjudications still align after the key is shuffled, which would mean the join is fake and the key decorative",
    )
    check(
        "...and the shuffle was real: at least two distinct stimuli existed to permute",
        True,
        len(bids) >= 2,
        "fewer than two stimuli, so the shuffle was a no-op and control 12 was vacuous",
    )
    return {
        "n_stimuli": result.key["n_stimuli"],
        "blind_allowed_keys": sorted(BO.BLIND_ALLOWED_KEYS),
        "injected_leaks_caught": injected_caught,
        "shuffled_key_defects": len(defects),
    }


def _leaky(result):
    leaked = BO.BuildResult(key=result.key, blind=copy.deepcopy(result.blind), images=result.images)
    leaked.blind["items"][0]["stratum"] = "appropriations-house"
    return leaked


# ------------------------------------------------------ the region-line bijection (A35.2)


def part_start_line(tmp: Path) -> dict:
    print("\n== A35.2: the printed-line index maps onto committed neutral lines ==")
    frame = synthetic_frame()
    page_frame = frame["pages"][0]
    bijection = BO.region_line_bijection(page_frame, 0)
    committed = [list(k) for k in page_frame["regions"][0]["neutral_line_keys"]]

    check(
        "the bijection covers EXACTLY the region's committed neutral lines",
        sorted(map(tuple, committed)),
        sorted(map(tuple, bijection)),
        "a printed line maps to a line outside the region, or a region line is unreachable",
    )
    check(
        "...and it is a bijection, not a multimap",
        len(committed),
        len({tuple(k) for k in bijection}),
        "two printed-line indices resolve to the same committed line",
    )
    check(
        "printed order is committed-ordinal order, top to bottom",
        [k[1] for k in bijection],
        sorted(k[1] for k in bijection),
        "the bijection is not sorted by ordinal, so line 1 is not the topmost printed line",
    )
    check(
        "start_physical_line 1 resolves to the topmost committed line",
        tuple(bijection[0]),
        BO.resolve_start_line(bijection, 1),
        "the 1-based index is off by one",
    )
    check(
        "NEGATIVE -- an out-of-range printed-line index REFUSES rather than guessing",
        BO.START_LINE_OUT_OF_RANGE,
        refusal(lambda: BO.resolve_start_line(bijection, len(bijection) + 1)),
        "an impossible line index resolves to some line anyway, which would hand the nearest-x "
        "resolver a confident and wrong start_ngid",
    )
    check(
        "NEGATIVE -- a zero or negative index REFUSES",
        BO.START_LINE_OUT_OF_RANGE,
        refusal(lambda: BO.resolve_start_line(bijection, 0)),
        "0 is accepted, silently reading as the last line under Python indexing",
    )
    return {"region_lines": len(bijection), "bijection": bijection}


# --------------------------------------------------------------- DEVELOPMENT end-to-end


def part_overlap(tmp: Path) -> dict:
    """A36.1-A36.6 -- C/D overlap semantics, routes, the audit, and R1 inheritance."""
    print("\n== A36: C/D overlap is BUILT, not refused ==")

    # C-only, D-only, and overlap, side by side in one realized set.
    memberships = [(True, False), (False, True), (True, True)] + [(True, False)] * (N_SYNTHETIC_REGIONS - 3)
    docs = synthetic_documents(tmp, memberships=memberships)
    result = BO.build(docs)
    by_page = {r["page_number"]: r for r in result.key["stimuli"].values() if not r["is_r1_repeat"]}

    check(
        "1. a C-only region yields ONE stimulus with frames == ['C']",
        (1, ["C"]),
        (sum(1 for r in by_page.values() if r["page_number"] == 1), by_page[1]["frames"]),
        "a C-only region is mislabelled or emitted more than once",
    )
    check(
        "2. a D-only region yields ONE stimulus with frames == ['D']",
        ["D"],
        by_page[2]["frames"],
        "a D-only region is mislabelled or emitted more than once",
    )
    check(
        "3. an OVERLAP region yields ONE stimulus with frames == ['C','D']",
        ["C", "D"],
        by_page[3]["frames"],
        "the overlap is projected onto a single frame, losing one membership (A36.2)",
    )
    overlap_ids = [
        bid
        for bid, r in result.key["stimuli"].items()
        if r["page_number"] == 3 and not r["is_r1_repeat"] and r["control_kind"] is None
    ]
    check(
        "4. the overlap creates EXACTLY ONE primary blind id",
        1,
        len(overlap_ids),
        "two blind ids exist for one physical region, so it would be rendered and adjudicated "
        "twice and A30.5's identity uniqueness would have had to be weakened to permit it",
    )
    check(
        "17. ...and is rendered exactly once at primary DPI",
        1,
        sum(
            1
            for r in result.key["stimuli"].values()
            if r["page_number"] == 3 and r["dpi"] == MC.PRIMARY_DPI and r["control_kind"] is None
        ),
        "the same primary region is rasterised twice, which would also produce two PNG hashes for one committed bbox",
    )

    # 5 + 8. adding a membership must not disturb identity or the other frame's census.
    c_only = BO.plan_document_stimuli(synthetic_frame(n_pages=3, memberships=[(True, False)] * 3), "S")
    now_both = BO.plan_document_stimuli(synthetic_frame(n_pages=3, memberships=[(True, True)] * 3), "S")
    check(
        "5. adding D membership to a C item cannot change its BASE IDENTITY",
        [MC.canonical(s.base_identity) for s in c_only],
        [MC.canonical(s.base_identity) for s in now_both],
        "frame membership leaked into A28.3's identity, which would re-key every selection "
        "and every blind id the moment a region became discordant",
    )
    d_only = BO.plan_document_stimuli(synthetic_frame(n_pages=3, memberships=[(False, True)] * 3), "S")
    check(
        "8. adding C membership to a D item cannot remove it from the D census",
        [True, True, True],
        [BO.D_FRAME in s.frames for s in now_both],
        "a region drawn into C is dropped from the discordance census, shrinking the only "
        "evidence that can satisfy Rule 1",
    )
    check(
        "...and the D-only items are in D too, so control 8 is not comparing against nothing",
        [True, True, True],
        [BO.D_FRAME in s.frames for s in d_only],
        "the D-only fixture is not actually in D",
    )
    check(
        "9. frame membership ORDER cannot change canonical output",
        by_page[3]["frames"],
        sorted(by_page[3]["frames"], key=lambda f: BO.FRAME_ORDER.index(f)),
        "membership is emitted in input order, so the same stimulus could serialize two ways",
    )

    # 6 + 7. D membership must not move the C draw or the C audit.
    n = N_SYNTHETIC_REGIONS
    plain = synthetic_frame(n_pages=n, memberships=[(True, False)] * n)
    # mark MANY non-audit C regions as D -- the required negative control
    d_heavy = synthetic_frame(n_pages=n, memberships=[(True, i % 2 == 1) for i in range(n)])
    plain_specs = BO.plan_document_stimuli(plain, "S")
    heavy_specs = BO.plan_document_stimuli(d_heavy, "S")
    check(
        "6. adding D membership cannot change C selection",
        [MC.canonical(s.base_identity) for s in plain_specs if BO.C_FRAME in s.frames],
        [MC.canonical(s.base_identity) for s in heavy_specs if BO.C_FRAME in s.frames],
        "the C membership set moved when D membership changed, i.e. the draw consumed the "
        "thing it is supposed to be independent of",
    )
    audit_plain = [MC.canonical(s.base_identity) for s in BO.select_c_audit(plain_specs, k=5)]
    audit_heavy = [MC.canonical(s.base_identity) for s in BO.select_c_audit(heavy_specs, k=5)]
    check(
        "7. adding D membership cannot change C AUDIT selection or its denominator",
        (audit_plain, 5),
        (audit_heavy, len(audit_heavy)),
        "the 25-item audit sample or size moved with D membership, which would make the "
        "audit a function of architecture disagreement (A36.5)",
    )
    check(
        "...and the D-heavy fixture really did gain D members, so control 7 is not vacuous",
        True,
        sum(1 for s in heavy_specs if BO.D_FRAME in s.frames) > 0,
        "no region gained D membership, so nothing was perturbed",
    )

    # 11 + 12 + 13. routes, and the critical prohibition.
    audited = BO.apply_c_audit(BO.plan_document_stimuli(d_heavy, "S"), k=5)
    routes = {
        "c_only": next(s for s in audited if s.frames == ("C",) and not s.is_c_audit_selected),
        "d_only": BO.plan_document_stimuli(synthetic_frame(n_pages=1, memberships=[(False, True)]), "S")[0],
        "overlap": next(s for s in audited if s.frames == ("C", "D")),
    }
    check(
        "11. an overlap stimulus requires BOTH the AI and the human route",
        ("ai", "human"),
        routes["overlap"].adjudication_routes,
        "an overlap region is answered on one route, dropping it from RQ2 metrics or from "
        "Rule 1 decision evidence (A36.4)",
    )
    check(
        "...and C-only takes AI while D-only takes human",
        (("ai",), ("human",)),
        (routes["c_only"].adjudication_routes, routes["d_only"].adjudication_routes),
        "a frame's route is wrong, so the wrong oracle would supply its labels",
    )
    both_answers = {"ai": "AI-ANSWER", "human": "HUMAN-ANSWER"}
    overlap_record = by_page[3]
    check(
        "12. the C metric route reads the AI answer EVEN WHERE a human answer exists",
        "AI-ANSWER",
        BO.select_answer(overlap_record, BO.PURPOSE_C_METRICS, both_answers),
        "human truth is substituted into C on overlap regions, making C a mixed oracle whose "
        "source is selected by H/X discordance -- the architectures choosing their own oracle "
        "on exactly the regions where they disagree",
    )
    check(
        "13. the D decision route reads the human answer EVEN WHERE an AI answer exists",
        "HUMAN-ANSWER",
        BO.select_answer(overlap_record, BO.PURPOSE_D_DECISION, both_answers),
        "an AI answer decides Rule 1, which 5.5.1 reserves for human adjudication",
    )
    check(
        "...and a missing mandated answer REFUSES rather than falling back to the other route",
        BO.ANSWER_MISSING_FOR_REQUIRED_ROUTE,
        refusal(lambda: BO.select_answer(overlap_record, BO.PURPOSE_C_METRICS, {"human": "HUMAN-ANSWER"})),
        "a missing AI answer silently falls back to human, which is the prohibited substitution "
        "arriving through the back door",
    )
    check(
        "the adjudication artifact schema requires two namespaced answer sets (A36.4)",
        BO.ADJUDICATION_NOT_NAMESPACED,
        refusal(lambda: BO.validate_adjudication_namespacing({"ai": {}})),
        "a flat one-answer-per-id artifact validates, which would collapse an overlap region's "
        "two independent answers into whichever was written last",
    )
    check(
        "...and a correctly namespaced artifact is accepted",
        None,
        refusal(lambda: BO.validate_adjudication_namespacing({"ai": {}, "human": {}})),
        "the validator refuses everything, making the control above meaningless",
    )

    # 14 + 15. audit reuse, and the audit denominator.
    audit_overlap = [s for s in audited if s.is_c_audit_selected and BO.D_FRAME in s.frames]
    check(
        "14. an audit-selected C-and-D item uses ONE human task for both D and the audit",
        (True, [1] * len(audit_overlap)),
        (len(audit_overlap) > 0, [s.n_human_tasks for s in audit_overlap]),
        "the human is asked to answer the same blind image twice, or the item exists in no "
        "fixture so the reuse rule was never exercised",
    )
    check(
        "...and that one task carries BOTH purposes",
        [("d_decision", "c_audit")] * len(audit_overlap),
        [s.human_answer_purposes for s in audit_overlap],
        "the shared answer is recorded as serving only one purpose",
    )
    non_audit_overlap = [s for s in audited if not s.is_c_audit_selected and BO.D_FRAME in s.frames]
    check(
        "15. a NON-audit C-and-D human answer cannot enlarge the audit denominator",
        (True, 5),
        (
            all(BO.PURPOSE_C_AUDIT not in s.human_answer_purposes for s in non_audit_overlap),
            sum(1 for s in audited if s.is_c_audit_selected),
        ),
        "a human answer that exists only because of D membership counts as an audit item, "
        "inflating the audit beyond the seeded cframe-audit draw (A36.5)",
    )
    check(
        "...and non-audit overlap items exist, so control 15 is not vacuous",
        True,
        len(non_audit_overlap) > 0,
        "every overlap item happened to be audit-selected, so nothing was tested",
    )

    # 16. R1 route inheritance.
    repeats = [r for r in result.key["stimuli"].values() if r["is_r1_repeat"]]
    inherited = []
    for rep in repeats:
        primary = next(
            r
            for r in result.key["stimuli"].values()
            if not r["is_r1_repeat"] and r["base_identity"] == rep["base_identity"]
        )
        # the routes a membership implies, independent of audit status (A36.6)
        expected = [
            route
            for route in BO.ROUTE_ORDER
            if (route == BO.C_FRAME_ROUTE and BO.C_FRAME in rep["frames"])
            or (route == BO.D_FRAME_ROUTE and BO.D_FRAME in rep["frames"])
        ]
        inherited.append(rep["frames"] == primary["frames"] and rep["adjudication_routes"] == expected)
    check(
        "16. an R1 repeat keeps ONE identity and inherits its primary's routes",
        (len(repeats), True),
        (sum(inherited), all(inherited) and bool(inherited)),
        "a repeat carries a route-specific identity or a route its primary does not have, "
        "which would make the reliability measurement compare two different things",
    )
    check(
        "10. the blind artifact leaks no membership and no route",
        (0, [], []),
        (
            BO.leakage_report(result.blind, result.key)["n_leaked_values"],
            BO.leakage_report(result.blind, result.key)["unexpected_keys"],
            BO.leakage_report(result.blind, result.key)["forbidden_text"],
        ),
        "frame membership, audit status or adjudication route reaches the adjudicator, who "
        "could then infer that a region is one the architectures disagree about",
    )
    injected = copy.deepcopy(result.blind)
    injected["items"][0]["frames"] = ["C", "D"]
    injected["items"][1]["adjudication_routes"] = ["ai", "human"]
    check(
        "10b. NEGATIVE -- injected membership/route in the blind file FAILS the gate",
        True,
        bool(BO.leakage_report(injected, result.key)["unexpected_keys"]),
        "membership or route can be added to the adjudicator's file without the gate firing",
    )
    return {
        "frame_counts": result.key["frame_counts"],
        "synthetic_overlap_regions": sum(1 for m in memberships if m[0] and m[1]),
        "audit_size_used": 5,
        "n_audit_overlap_items": len(audit_overlap),
        "n_non_audit_overlap_items": len(non_audit_overlap),
        "n_r1_repeats": len(repeats),
    }


def part_occurrence_join(tmp: Path) -> dict:
    """A38.7 -- the OCCURRENCE-LEVEL join, which A35's image/region binding never established."""
    print("\n== A38: the occurrence-level scoring join ==")
    docs = synthetic_documents(tmp, n_pages=4)
    result = BO.build(docs)
    bid, record = next(
        (b, r) for b, r in result.key["stimuli"].items() if not r["is_r1_repeat"] and r["page_number"] == 1
    )

    # The candidates were placed at x0 = 100.0 and 140.0 on every line. Aim the adjudicated
    # pixel squarely at the first, converting through the SAME A34 transform build_oracle used.
    dpi, bbox_x0 = record["dpi"], record["bbox_pdf_points"][0]
    px_at_100 = OG.pdf_x_to_pixel(100.0, bbox_x0, dpi)
    heading = {"text": "SYNTHETIC ACCOUNT", "start_physical_line": 3, "start_x_px": px_at_100}
    hit = BO.resolve_adjudicated_occurrence(record, heading)

    check(
        "the occurrence join RESOLVES an adjudicated heading to an A30 occurrence key",
        (True, [1, 2]),
        (hit["matched"], hit["neutral_line_key"]),
        "a scorer cannot get from an adjudicated (line, x) to an occurrence identity at all, "
        "which is what A35's image-binding join left unproven",
    )
    check(
        "...and it selects the NEAREST candidate, not merely some candidate",
        20,
        hit["start_ngid"],
        "the resolver returned a glyph that is not nearest the converted coordinate",
    )
    check(
        "...and the key is the A30 4-tuple (doc_sha, page, neutral_line_key, start_ngid)",
        [record["document_sha256"], 1, [1, 2], 20],
        hit["occurrence_key"],
        "the occurrence key is not the frozen A30 shape, so it cannot join to the emitted side",
    )

    # A38 REPAIR -- sentinel proof that a stimulus receives ONLY its own page's occurrences.
    # Every synthetic page carries region_ordinal 0 with a page-distinct sentinel text, so a
    # page-blind filter would put every page's sentinel into every stimulus.
    by_page_stimulus = {r["page_number"]: r for r in result.key["stimuli"].values() if not r["is_r1_repeat"]}
    sentinels = {
        p: sorted({row["anchor"]["text"] for row in by_page_stimulus[p]["architecture_occurrences"]["H"]})
        for p in sorted(by_page_stimulus)
    }
    check(
        "each stimulus carries ONLY its own page's sentinel occurrence",
        {p: [f"SYNTHETIC ACCOUNT SENTINEL P{p}"] for p in sorted(by_page_stimulus)},
        sentinels,
        "a stimulus holds another page's sentinel, i.e. region_ordinal is being matched "
        "without the page and every multi-page document contaminates every region",
    )
    check(
        "...and the fixture really does reuse region_ordinal across pages, so this is not vacuous",
        (True, [0]),
        (
            len(by_page_stimulus) > 1,
            sorted({r["region_ordinal"] for r in by_page_stimulus.values()}),
        ),
        "the fixture has one page or distinct ordinals per page, so a page-blind filter would have looked correct here",
    )

    # POSITIVE END-TO-END: the emitted architecture occurrence carries the same key.
    emitted = record["architecture_occurrences"]["H"][0]
    check(
        "POSITIVE -- the adjudicated key EQUALS the emitted architecture occurrence key",
        emitted["occurrence_key"],
        hit["occurrence_key"],
        "the two sides of the M1-M5 join do not meet, so no matched-heading denominator exists",
    )

    # --- negative controls, each an independent mutation
    px_at_140 = OG.pdf_x_to_pixel(140.0, bbox_x0, dpi)
    crossed = BO.resolve_adjudicated_occurrence(record, {**heading, "start_x_px": px_at_140})
    check(
        "NEGATIVE -- crossing the nearest-glyph boundary CHANGES the resolved key",
        (True, 21),
        (crossed["matched"], crossed["start_ngid"]),
        "moving the annotation onto the other glyph resolves to the same ngid, which would "
        "mean the resolver is not actually reading the coordinate",
    )
    # The tie must be EXACT in PDF space, so it is built from the coordinate the transform
    # actually produces for a chosen pixel -- constructing it in pixel space instead leaves a
    # sub-pixel residue and the "tie" silently resolves, testing nothing.
    tie_px = OG.pdf_x_to_pixel(120.0, bbox_x0, dpi)
    tie_target = OG.pixel_to_pdf_x(tie_px, bbox_x0, dpi)
    tie = BO.resolve_adjudicated_occurrence(
        {**record, "identity_candidates": {"1:2": [[20, tie_target - 5.0], [21, tie_target + 5.0]]}},
        {**heading, "start_x_px": tie_px},
    )
    check(
        "NEGATIVE -- an EXACT geometric tie refuses rather than picking one",
        False,
        tie["matched"],
        "a tie silently resolves to a glyph, inventing an identity A30.3 says does not exist",
    )
    stripped = {**record, "identity_candidates": {}}
    check(
        "NEGATIVE -- removing the identity candidates makes the join REFUSE",
        (False, BO.MISSING_IDENTITY_CANDIDATES),
        (
            BO.resolve_adjudicated_occurrence(stripped, heading)["matched"],
            BO.resolve_adjudicated_occurrence(stripped, heading)["reason"],
        ),
        "the join returns a match without candidate geometry, i.e. it is not reading it",
    )
    check(
        "NEGATIVE -- an out-of-range start_physical_line REFUSES",
        BO.START_LINE_OUT_OF_RANGE,
        refusal(lambda: BO.resolve_adjudicated_occurrence(record, {**heading, "start_physical_line": 99})),
        "an impossible line resolves anyway, handing the resolver the wrong candidate set",
    )

    # identity must be INVARIANT to text and kind, and must not renumber (A30.1)
    text_changed = copy.deepcopy(docs)
    kind_changed = copy.deepcopy(docs)
    for rec in text_changed[0]["frame"]["architecture_occurrences"]["H"]:
        rec["anchor"]["text"] = "A COMPLETELY DIFFERENT HEADING"
    for rec in kind_changed[0]["frame"]["architecture_occurrences"]["H"]:
        rec["anchor"]["kind"] = "grouping"
    keys_of = lambda ds: [  # noqa: E731
        r["architecture_occurrences"]["H"][0]["occurrence_key"]
        for r in BO.build(ds).key["stimuli"].values()
        if r["architecture_occurrences"]["H"]
    ]
    check(
        "NEGATIVE -- changing heading TEXT does not move the occurrence identity",
        keys_of(docs),
        keys_of(text_changed),
        "identity consumes text, so a word-boundary defect would silently renumber the very "
        "occurrences the study exists to compare (A30.1)",
    )
    check(
        "NEGATIVE -- changing anchor KIND does not move the occurrence identity",
        keys_of(docs),
        keys_of(kind_changed),
        "identity consumes anchor kind rather than absolute source position",
    )
    earlier_removed = copy.deepcopy(docs)
    for page_frame in earlier_removed[0]["frame"]["pages"]:
        page_frame["regions"][0]["neutral_line_keys"] = page_frame["regions"][0]["neutral_line_keys"]
    check(
        "NEGATIVE -- an UNMATCHED occurrence is RETAINED and explicitly flagged",
        ("UNMATCHED", "SYNTHETIC_REFUSAL"),
        _unmatched_survives(docs),
        "an occurrence whose A30 resolution refused is dropped, shrinking an M1-M5 denominator "
        "invisibly instead of being reported as a refusal",
    )

    # the required join fields must now include what the occurrence join actually consumes
    check(
        "REQUIRED_JOIN_FIELDS now includes the occurrence-join facts",
        True,
        {"identity_candidates", "architecture_occurrences"}.issubset(set(BO.REQUIRED_JOIN_FIELDS)),
        "the completeness gate still checks only image/region binding, so a key missing the "
        "occurrence facts would pass and the defect would resurface in score_metrics",
    )
    missing_occ = BO.BuildResult(key=copy.deepcopy(result.key), blind=result.blind, images=result.images)
    for rec in missing_occ.key["stimuli"].values():
        rec["architecture_occurrences"] = None
    check(
        "NEGATIVE -- a key missing its architecture occurrences FAILS the completeness gate",
        True,
        len(BO.verify_join(missing_occ)) > 0,
        "verify_join stays green without the occurrence records, which is exactly the false sufficiency A35's join had",
    )
    return {
        "blind_id": bid,
        "adjudicated_heading": heading,
        "resolved": hit,
        "emitted_occurrence_key": emitted["occurrence_key"],
        "boundary_crossed_ngid": crossed.get("start_ngid"),
        "tie_refused": not tie["matched"],
    }


def _unmatched_survives(docs) -> tuple:
    """Mark one occurrence UNMATCHED in the frame and confirm it survives into the key."""
    mutated = copy.deepcopy(docs)
    for rec in mutated[0]["frame"]["architecture_occurrences"]["H"]:
        rec["occurrence_key"], rec["match_status"], rec["unmatched_reason"] = None, "UNMATCHED", "SYNTHETIC_REFUSAL"
    for record in BO.build(mutated).key["stimuli"].values():
        for rec in record["architecture_occurrences"]["H"]:
            return rec["match_status"], rec["unmatched_reason"]
    return ("ABSENT", "ABSENT")


def part_adjudicated_schema(tmp: Path) -> dict:
    """A38.7 -- the committed adjudicated artifact encoding."""
    print("\n== A38: the adjudicated artifact encoding ==")
    docs = synthetic_documents(tmp, n_pages=4)
    result = BO.build(docs)
    answers = {"ai": {}, "human": {}}
    for bid, record in result.key["stimuli"].items():
        answer = {
            "id": bid,
            "headings": [
                {
                    "text": "SYNTHETIC ACCOUNT",
                    "role": "account",
                    "parent": "NONE",
                    "start_physical_line": 1,
                    "start_x_px": 10,
                }
            ],
            "notes": [],
        }
        for route in record["adjudication_routes"]:
            answers[route][bid] = answer

    check(
        "a well-formed adjudicated artifact VALIDATES",
        None,
        refusal(lambda: BO.validate_adjudicated(answers, result.key)),
        "the encoding rejects a conforming artifact",
    )
    check(
        "the heading fields are EXACTLY the six the prompt asks for",
        ("text", "role", "parent", "start_physical_line", "start_x_px"),
        BO.ADJUDICATED_HEADING_FIELDS,
        "the encoding asks for a field the prompt never collected, or drops one it did",
    )
    unknown = {"ai": dict(answers["ai"]), "human": dict(answers["human"])}
    unknown["ai"]["NOT-A-BLIND-ID"] = {"id": "NOT-A-BLIND-ID", "headings": [], "notes": []}
    check(
        "NEGATIVE -- an unknown blind id REFUSES",
        BO.UNKNOWN_BLIND_ID,
        refusal(lambda: BO.validate_adjudicated(unknown, result.key)),
        "an answer for a stimulus that does not exist is accepted and would join to nothing",
    )
    mismatched = {"ai": dict(answers["ai"]), "human": dict(answers["human"])}
    a_bid = next(iter(mismatched["ai"]))
    mismatched["ai"][a_bid] = {**mismatched["ai"][a_bid], "id": "SOMETHING-ELSE"}
    check(
        "NEGATIVE -- an answer whose id differs from its namespace key REFUSES",
        BO.ADJUDICATION_ID_MISMATCH,
        refusal(lambda: BO.validate_adjudicated(mismatched, result.key)),
        "an answer can be filed under one id while claiming another, silently misjoining it",
    )
    dropped = {"ai": {}, "human": dict(answers["human"])}
    check(
        "NEGATIVE -- a stimulus missing a REQUIRED route REFUSES, with no fallback",
        BO.ADJUDICATION_ROUTE_MISSING,
        refusal(lambda: BO.validate_adjudicated(dropped, result.key)),
        "a missing AI answer falls back to the human one, which is the A36.4 prohibition",
    )
    check(
        "UNREADABLE stays representable per field",
        None,
        refusal(
            lambda: BO.validate_adjudicated(
                {
                    "ai": {
                        b: {**a, "headings": [{**a["headings"][0], "role": BO.UNREADABLE}]}
                        for b, a in answers["ai"].items()
                    },
                    "human": answers["human"],
                },
                result.key,
            )
        ),
        "an UNREADABLE field is rejected, forcing the adjudicator to guess a value instead",
    )
    return {"schema": BO.ADJUDICATED_SCHEMA, "heading_fields": list(BO.ADJUDICATED_HEADING_FIELDS)}


def part_m5() -> dict:
    """A36.7 -- the M5 coarsening map, both sides, with completeness asserted against production."""
    print("\n== A36.7: the M5 role coarsening map ==")
    from typing import get_args

    from deltatrack.parsers.pdf_anchors import AnchorKind

    produced = set(get_args(AnchorKind))
    check(
        "the emitted map is COMPLETE against production's AnchorKind",
        sorted(produced),
        sorted(MC.EMITTED_KIND_TO_M5),
        "production emits a kind the M5 map does not cover, so that kind would arrive as an "
        "unmapped role -- this control is what makes a future kind FAIL instead of slipping in",
    )
    oracle_map = {role: MC.m5_oracle_role(role) for role in MC.ORACLE_ROLE_TO_M5}
    emitted_map = {kind: MC.m5_emitted_kind(kind) for kind in MC.EMITTED_KIND_TO_M5}
    check(
        "every oracle role maps exactly as A36.7 freezes it",
        {
            "account": "LEAF",
            "section": "LEAF",
            "agency": "CONTAINER",
            "grouping": "CONTAINER",
            "title": "CONTAINER",
            "division": "CONTAINER",
            "other": "UNSCORABLE",
        },
        oracle_map,
        "a role coarsens differently from the frozen table",
    )
    check(
        "every emitted kind maps exactly as A36.7 freezes it",
        {
            "account": "LEAF",
            "section": "LEAF",
            "major": "CONTAINER",
            "agency": "CONTAINER",
            "grouping": "CONTAINER",
            "title": "CONTAINER",
            "subsection": "UNSCORABLE",
            "preamble": "UNSCORABLE",
        },
        emitted_map,
        "an emitted kind coarsens differently from the frozen table",
    )
    check(
        "a LEAF/LEAF pair is scorable and agrees",
        (True, True),
        (MC.m5_scorable("account", "account"), MC.m5_agreement("account", "account")),
        "an account-to-account match is excluded or read as disagreement",
    )
    check(
        "a LEAF/CONTAINER pair is scorable and DISAGREES",
        (True, False),
        (MC.m5_scorable("account", "agency"), MC.m5_agreement("account", "agency")),
        "a genuine role disagreement is hidden",
    )
    check(
        "an UNSCORABLE oracle role is EXCLUDED, not counted as disagreement",
        (False, None),
        (MC.m5_scorable("other", "account"), MC.m5_agreement("other", "account")),
        "`other` enters the M5 denominator, penalising the architecture for a role M5 was never licensed to score",
    )
    check(
        "an UNSCORABLE emitted kind is EXCLUDED on the other side too",
        (False, None),
        (MC.m5_scorable("account", "subsection"), MC.m5_agreement("account", "subsection")),
        "`subsection` or `preamble` enters the denominator",
    )
    check(
        "NEGATIVE -- an unknown oracle role REFUSES rather than becoming UNSCORABLE",
        "UnknownRole",
        refusal(lambda: MC.m5_oracle_role("chapter")),
        "an unmapped role silently becomes UNSCORABLE, quietly SHRINKING the denominator -- "
        "and a smaller denominator reads as a cleaner result rather than as a defect",
    )
    check(
        "NEGATIVE -- an unknown emitted kind REFUSES",
        "UnknownRole",
        refusal(lambda: MC.m5_emitted_kind("footnote")),
        "an unmapped emitted kind is silently excluded",
    )
    return {
        "production_anchor_kinds": sorted(produced),
        "oracle_role_to_m5": oracle_map,
        "emitted_kind_to_m5": emitted_map,
        "m5_status": "CORROBORATION ONLY -- may never affect the architecture decision",
    }


def part_development() -> dict:
    """Real PDFs, real committed frames. Demonstration of behaviour, NOT a census."""
    print("\n== DEVELOPMENT end-to-end (real PDFs, real frames) ==")
    docs, overlaps, per_doc = [], [], []
    for name, path in DOCS:
        for member in BO.HOLDOUT_GUARD:
            if member in str(path):
                raise SystemExit(f"REFUSED: {path} touches holdout member {member}")
        if not path.exists():
            continue
        h_pages = run_hybrid.run(path, limit=PAGE_LIMIT)
        x_pages, _s = run_extended.run(path, limit=PAGE_LIMIT)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        frame = BF.build_document_frame(sha, name, BF.P_HEAD, h_pages, x_pages)

        regions = [r for pf in frame["pages"] for r in pf["regions"]]
        both = [r for r in regions if r["c_frame"] and r["d_frame"]]
        per_doc.append(
            {
                "document": name,
                "pages_consumed": PAGE_LIMIT,
                "regions": len(regions),
                "c_frame": sum(1 for r in regions if r["c_frame"]),
                "d_frame": sum(1 for r in regions if r["d_frame"]),
                "c_and_d": len(both),
            }
        )
        overlaps.extend(
            {"document": name, "page_number": r["page_number"], "region_ordinal": r["region_ordinal"]} for r in both
        )
        docs.append({"frame": frame, "pdf_path": path, "stratum": "DEVELOPMENT"})

    # A36 -- the overlap is now BUILT, not refused. A35.5's STOP is resolved forward; its
    # historical record stands in the ledger and in this probe's earlier committed artifact.
    result = BO.build(docs)
    report = BO.leakage_report(result.blind, result.key)
    defects = BO.verify_join(result)

    counts = result.key["frame_counts"]
    overlap_records = [
        r
        for r in result.key["stimuli"].values()
        if r["in_c_frame"] and r["in_d_frame"] and not r["is_r1_repeat"] and r["control_kind"] is None
    ]
    check(
        "18. raw C, raw D and the C-and-D overlap are reported SEPARATELY on real material",
        True,
        counts["c_frame"] > 0 and counts["d_frame"] > 0 and counts["c_and_d_overlap"] == len(overlaps),
        "a frame size or the overlap count is missing or disagrees with the frames, so a "
        "reader could not see that an overlap region is counted once in each estimand",
    )
    check(
        "every DEVELOPMENT overlap region produced EXACTLY ONE stimulus (A36.2)",
        len(overlaps),
        len(overlap_records),
        "an overlap region was emitted twice or dropped, so |C| + |D| would not reconcile "
        "with the realized stimulus set",
    )
    check(
        "...and every one of them carries BOTH required routes",
        (len(overlap_records), True),
        (
            sum(1 for r in overlap_records if r["adjudication_routes"] == ["ai", "human"]),
            all(r["adjudication_routes"] == ["ai", "human"] for r in overlap_records),
        ),
        "an overlap region is answered on one route only, silently dropping it from either "
        "the RQ2 metrics or the Rule 1 decision evidence",
    )
    check(
        "the DEVELOPMENT overlap population is non-empty, so the two controls above are not vacuous",
        True,
        len(overlap_records) > 0,
        "no overlap region exists on this material, so nothing about overlap was exercised",
    )

    widths = [r["image_width_px"] for r in result.key["stimuli"].values()]
    width_ok = [
        r["image_width_px"] == OG.expected_image_width(r["bbox_pdf_points"][0], r["bbox_pdf_points"][2], r["dpi"])
        for r in result.key["stimuli"].values()
    ]
    check(
        "every DEVELOPMENT stimulus renders at the frozen width for its own DPI",
        (len(width_ok), True),
        (sum(width_ok), all(width_ok)),
        "a rendered image is not the width the A34 derivation predicts for its bbox and scale",
    )
    check(
        "every planned DEVELOPMENT stimulus was rendered, so no denominator is a sample",
        result.key["n_stimuli"],
        len(result.images),
        "a stimulus was planned but not rendered, which would shrink the study invisibly",
    )
    check(
        "the DEVELOPMENT blind file leaks nothing",
        (0, [], []),
        (report["n_leaked_values"], report["unexpected_keys"], report["forbidden_text"]),
        "a private value or forbidden token reaches the adjudicator on real material",
    )
    check(
        "the DEVELOPMENT join is complete",
        [],
        defects,
        "a real stimulus cannot be bound back to its region",
    )
    check(
        "the DEVELOPMENT population is non-empty, so these controls are not vacuous",
        True,
        result.key["n_stimuli"] > 0 and len(docs) > 0,
        "no document or no stimulus was produced, so every check above passed on nothing",
    )
    return {
        "documents": per_doc,
        "page_limit": PAGE_LIMIT,
        "note": "PAGE_LIMIT is a machinery demonstration window, not a census",
        "n_stimuli": result.key["n_stimuli"],
        "n_r1_repeats": sum(1 for r in result.key["stimuli"].values() if r["is_r1_repeat"]),
        "n_images": len(result.images),
        "image_width_px_min": min(widths) if widths else None,
        "image_width_px_max": max(widths) if widths else None,
        # A36.3 -- raw sizes and the overlap, never a pooled union substituted for either
        "frame_counts": counts,
        "c_and_d_overlap_regions": len(overlaps),
        "overlap_instances": overlaps[:24],
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        prompt = part_prompt()
        blinding = part_blinding(tmp)
        render = part_render(tmp)
        fail_closed = part_fail_closed(tmp)
        leakage = part_leakage_and_join(tmp)
        start_line = part_start_line(tmp)
        overlap = part_overlap(tmp)
        occurrence_join = part_occurrence_join(tmp)
        adjudicated = part_adjudicated_schema(tmp)
        m5 = part_m5()
        development = part_development()

    doc = {
        "population": "SYNTHETIC + DEVELOPMENT -- no holdout opened, nothing adjudicated, nothing scored",
        "contract": "A35 (adjudicator prompt + build_oracle) as amended by A36 (C/D overlap "
        "semantics + M5 coarsening), implementing A19-A34 and HARNESS-PLAN 3-4",
        "renderer": "MuPDF (pymupdf)",
        "renderer_version": str(pymupdf.version),
        "artifacts_created": "NONE of frames.json, oracle_key.json, oracle_adjudicated.json, "
        "metrics.json, scores.json, EXECUTION-START.json",
        "a35_5_stop_resolved_by": "A36 -- REGION_IN_BOTH_FRAMES is no longer raised; the overlap "
        "is BUILT as one stimulus carrying both memberships and both routes",
        "prompt": prompt,
        "blinding": blinding,
        "render": render,
        "fail_closed": fail_closed,
        "leakage_and_join": leakage,
        "start_line_bijection": start_line,
        "overlap_semantics": overlap,
        "occurrence_join": occurrence_join,
        "adjudicated_encoding": adjudicated,
        "m5_coarsening": m5,
        "development": development,
        "stop_conditions": STOPS,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass; {len(STOPS)} stop conditions")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
