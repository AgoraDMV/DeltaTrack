"""x17 -- test `build_frames`. SYNTHETIC + DEVELOPMENT only.

NOT CONFIRMATORY. No holdout document is opened, nothing is scored, and no canonical
`results/frames.json` is produced. The evidence artifact is `results/x17_build_frames.json`.

Every control below records WHAT FACT WOULD MAKE IT FAIL, and the ones that can be injected
ARE injected: a control that only reads back a boolean the code under test just computed
proves nothing, because it cannot distinguish a working rule from a rule that never fires.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

import build_frames as BF  # noqa: E402
import methodology_contracts as MC  # noqa: E402
import run_extended  # noqa: E402
import run_hybrid  # noqa: E402
import x14_anchor_bridge as X14  # noqa: E402
from neutral_identity import Cell, EmittedLine, NeutralLine, build_owner  # noqa: E402

from deltatrack.parsers.pdf_anchors import Anchor, extract_anchors  # noqa: E402
from deltatrack.parsers.pdf_text import Line, Page  # noqa: E402

OUT = EV / "results" / "x17_build_frames.json"
ROWS: list[dict] = []
FAILED: list[str] = []

DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
    ("115-hr-5895/1", REPO / "tests/corpus/115-hr-5895/1_reported-in-house.pdf"),
    ("118-hr-8752/1", REPO / "tests/corpus/118-hr-8752/1_reported-in-house.pdf"),
    ("119-hr-1/1", REPO / "tests/corpus/119-hr-1/1_reported-in-house.pdf"),
    ("118-hr-4366/1", REPO / "tests/corpus/118-hr-4366/1_reported-in-house.pdf"),
]
PAGE_LIMIT = 60
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


def check(name, expected, observed, fails_when="") -> None:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    print(f"[PASS] {name}" if ok else f"[FAIL] {name}\n        expected={expected!r}\n        observed={observed!r}")
    if not ok:
        FAILED.append(name)


# ----------------------------------------------------------------- synthetic fixtures


def nline(page, ordinal, gids):
    return NeutralLine(
        page=page, ordinal=ordinal, baseline=100.0 - ordinal, x0=0.0, y0=0.0, x1=100.0, y1=10.0, gids=frozenset(gids)
    )


def eline(pairs):
    return EmittedLine(cells=[Cell(ngid=g, char=c) for g, c in pairs])


def simple_page(page_number, n_lines, chars_per_line=3, start_gid=0):
    """`n_lines` neutral lines, each with its own emitted line in BOTH arms, all concordant."""
    neutral, h, x, gid = [], [], [], start_gid
    for i in range(n_lines):
        gids = list(range(gid, gid + chars_per_line))
        neutral.append(nline(page_number, i, gids))
        cells = [(g, "A") for g in gids]
        h.append(eline(cells))
        x.append(eline(cells))
        gid += chars_per_line
    return BF.PageInput(page_number=page_number, neutral=neutral, h_emitted=h, x_emitted=x)


def frame_of(pages, population=BF.P_HEAD, sha="devsha"):
    return BF._build_document_frame_from_inputs(sha, "synthetic", population, pages)


def regions_of(frame):
    return [r for pf in frame["pages"] for r in pf["regions"]]


# ------------------------------------------------------------------- synthetic controls


def part_regions() -> None:
    print("\n== region construction (I1, I5, A19 trailing rule) ==")

    # 10. short trailing region KEPT
    page = simple_page(1, 19)
    frame = frame_of([page])
    regions = regions_of(frame)
    check(
        "control 10: a 19-line page yields 3 regions, the last a SHORT TRAILING one",
        [8, 8, 3],
        [r["line_count"] for r in regions],
        "a dropped tail would make the last 1-7 neutral lines of every page unsamplable",
    )
    check("...and the trailing region is flagged as such", [False, False, True], [r["short_trailing"] for r in regions])

    # 2. region partition is TOTAL -- every neutral line in exactly one region
    covered = [tuple(k) for r in regions for k in r["neutral_line_keys"]]
    all_keys = [tuple(ln["key"]) for pf in frame["pages"] for ln in pf["neutral_lines"]]
    check(
        "control 2: every neutral line belongs to exactly one region",
        (sorted(all_keys), len(all_keys)),
        (sorted(covered), len(covered)),
        "a line in zero regions is unsamplable; a line in two would double-count it",
    )

    # 11. region construction RESETS at every page boundary (I5)
    two = frame_of([simple_page(1, 5), simple_page(2, 5, start_gid=1000)])
    rs = regions_of(two)
    check(
        "control 11: each page starts its own region grid at ordinal 0",
        [(1, 0), (2, 0)],
        [(r["page_number"], r["region_ordinal"]) for r in rs],
        "a continuing ordinal would let a region span two pages",
    )
    crossing = [r for r in rs if len({k[0] for k in r["neutral_line_keys"]}) > 1]
    check("control 11b: I5 -- no region contains lines from two pages", [], crossing)

    # 5 short lines on their own page must still form a region
    check("a 5-line page still yields one short trailing region", [5], [r["line_count"] for r in rs[:1]])


def part_d_frame() -> dict:
    print("\n== D-frame membership (I3, I4) ==")
    evidence = {}

    # 4. BOTH_ABSENT-only evidence never creates D membership (I3)
    neutral = [nline(1, i, [i * 3, i * 3 + 1, i * 3 + 2]) for i in range(4)]
    absent = BF.PageInput(page_number=1, neutral=neutral, h_emitted=[], x_emitted=[])
    f_absent = frame_of([absent])
    r_absent = regions_of(f_absent)
    check(
        "control 4: a page neither arm emitted creates NO D-frame membership",
        [False],
        [r["d_frame"] for r in r_absent],
        "counting a shared drop as discordance would flood the D-frame with page furniture",
    )
    check(
        "...and its lines are still IN the artifact and the region grid (I3)",
        4,
        len(f_absent["pages"][0]["neutral_lines"]),
    )
    check(
        "...and are excluded from the M0 comparative risk set (I3)",
        [False] * 4,
        [ln["in_m0_risk_set"] for ln in f_absent["pages"][0]["neutral_lines"]],
    )

    # 6. injected TEXT change on one arm -> D
    page = simple_page(1, 4)
    page.x_emitted = list(page.x_emitted)
    page.x_emitted[1] = eline([(3, "A"), (4, "B"), (5, "A")])  # gid 4 renders differently
    f_text = frame_of([page])
    r_text = regions_of(f_text)[0]
    check(
        "control 6: a text change on ONE arm puts its region in D",
        (True, True),
        (r_text["d_frame"], BF.TEXT_DISCORDANCE in r_text["d_reasons"]),
        "if this passed without the injection, the text predicate would never fire",
    )
    check(
        "...and ONLY the mutated line is recorded as text-discordant (I4)",
        [[1, 1]],
        r_text["discordant_lines"][BF.TEXT_DISCORDANCE],
    )
    # 8. a concordant line inside a D region stays individually concordant
    lines = f_text["pages"][0]["neutral_lines"]
    check(
        "control 8: concordant lines inside a D region are NOT individually qualifying (I4)",
        [False, True, False, False],
        [ln["line_state"]["text_discordance"] for ln in lines],
        "marking the whole region's lines discordant would fabricate M0a numerator entries",
    )
    check(
        "...and a text-only difference does NOT move the segmentation signature",
        [False] * 4,
        [ln["line_state"]["segmentation_discordance"] for ln in lines],
        "the two quantities are deliberately orthogonal; coupling them would corrupt M3",
    )
    evidence["text_injection"] = r_text["d_reasons"]

    # 5. injected MERGE on one arm -> D via segmentation, with text untouched
    page = simple_page(1, 4)
    page.h_emitted = [eline([(0, "A"), (1, "A"), (2, "A"), (3, "A"), (4, "A"), (5, "A")])] + list(page.h_emitted[2:])
    f_seg = frame_of([page])
    r_seg = regions_of(f_seg)[0]
    check(
        "control 5: a merge on ONE arm puts its region in D via SEGMENTATION",
        (True, True),
        (r_seg["d_frame"], BF.SEGMENTATION_DISCORDANCE in r_seg["d_reasons"]),
        "a merge that did not move the signature would make M0b structurally blind",
    )
    seg_lines = f_seg["pages"][0]["neutral_lines"]
    check(
        "...and the merge did NOT move the projected text (grouping vs characters)",
        [False] * 4,
        [ln["line_state"]["text_discordance"] for ln in seg_lines],
        "if a merge moved the text, a segmentation difference would fabricate an M3 boundary error",
    )
    evidence["merge_injection"] = r_seg["d_reasons"]

    # 7. anchor set differs while every line's text is identical -> D
    page = simple_page(1, 4)
    page.h_anchors_by_region = {0: {Anchor(1, 7, "account", "OPERATIONS AND SUPPORT")}}
    page.x_anchors_by_region = {0: set()}
    f_anchor = frame_of([page])
    r_anchor = regions_of(f_anchor)[0]
    check(
        "control 7: an anchor-set difference alone puts the region in D",
        (True, [BF.ANCHOR_DISCORDANCE]),
        (r_anchor["d_frame"], r_anchor["d_reasons"]),
        "PRE-REGISTRATION 5.8 makes a differing emitted anchor set region-level evidence",
    )
    check(
        "...with no line recorded as text- or segmentation-discordant (I4)",
        ([], []),
        (r_anchor["discordant_lines"][BF.TEXT_DISCORDANCE], r_anchor["discordant_lines"][BF.SEGMENTATION_DISCORDANCE]),
    )
    evidence["anchor_injection"] = r_anchor["d_reasons"]

    # the un-injected baseline must be CLEAN, or every injection above proves nothing
    f_clean = frame_of([simple_page(1, 4)])
    check(
        "baseline: with no injection the region is NOT in D",
        [False],
        [r["d_frame"] for r in regions_of(f_clean)],
        "a baseline that was already in D would make all four injections vacuous",
    )

    # 12. the D census is COMPLETE -- never truncated to the A10 60-region budget
    big = [simple_page(p, BF.REGION_SIZE) for p in range(1, 62)]
    for p in big:
        p.x_emitted = list(p.x_emitted)
        p.x_emitted[0] = eline([(p.neutral[0].gids and min(p.neutral[0].gids), "Z")])
    f_big = frame_of(big)
    check(
        "control 12: a 61-region D census is emitted in full, not truncated at 60",
        61,
        f_big["counts"]["d_frame_census"],
        "truncating here would destroy the count A27.3 uses to decide whether Rule 1 may run",
    )
    check("...and the artifact says so explicitly", False, f_big["d_frame_truncated"])
    evidence["d_census_61"] = f_big["counts"]["d_frame_census"]
    return evidence


def part_c_frame() -> dict:
    print("\n== C-frame selection (A27.2, A27.7) ==")
    pages = [simple_page(p, 24, start_gid=p * 1000) for p in range(1, 6)]  # 15 regions
    frame = frame_of(pages)
    regions = regions_of(frame)
    check("the complete region grid is enumerated from the skeleton (I1)", 15, len(regions))

    # 3. a jointly-dropped BODY line -- the shared failure only the C-frame can see. It must
    #    survive into the grid AND land in a region the C-frame draw can reach.
    dropped = simple_page(1, 12)
    dropped.h_emitted = [e for i, e in enumerate(dropped.h_emitted) if i != 5]
    dropped.x_emitted = [e for i, e in enumerate(dropped.x_emitted) if i != 5]
    f_drop = frame_of([dropped])
    target = f_drop["pages"][0]["neutral_lines"][5]
    check(
        "control 3: a body line BOTH arms dropped is still in the grid, in region 0, BOTH_ABSENT",
        ("BOTH_ABSENT", 0, False),
        (target["line_state"]["state"], target["region_ordinal"], target["in_m0_risk_set"]),
        "enumerating regions from EMITTED lines would make this line unsamplable and the "
        "shared failure invisible -- exactly what the C-frame exists to catch",
    )
    drop_ident = [MC.base_stimulus_identity("devsha", 1, r["region_ordinal"]) for r in regions_of(f_drop)]
    check(
        "...and its region is C-frame ELIGIBLE, i.e. reachable by the frozen draw",
        True,
        MC.base_stimulus_identity("devsha", 1, 0) in drop_ident,
    )
    check(
        "...and the drop did not put its region in the D-frame (I3)",
        False,
        regions_of(f_drop)[0]["d_frame"],
        "a shared drop belongs to RQ2 via the C-frame, never to the comparative D-frame",
    )
    check("the C-frame draw is capped at 8 regions per document", 8, frame["counts"]["c_frame_selected"])

    # 9. determinism and order-independence
    ident = [
        MC.base_stimulus_identity("devsha", pf["page_number"], r["region_ordinal"])
        for pf in frame["pages"]
        for r in pf["regions"]
    ]
    a = MC.select("cframe-select", ident, 8)
    b = MC.select("cframe-select", list(reversed(ident)), 8)
    check(
        "control 9: the same identities select the same set AND the same order",
        a,
        b,
        "any listing-order dependence would make the sample irreproducible",
    )
    frame2 = frame_of(list(reversed(pages)))
    check(
        "...and building the document with pages listed in reverse selects the same regions",
        sorted((r["page_number"], r["region_ordinal"]) for r in regions if r["c_frame"]),
        sorted((r["page_number"], r["region_ordinal"]) for r in regions_of(frame2) if r["c_frame"]),
    )

    # selection must not depend on region CONTENT -- no reroll, no replacement
    mutated = [simple_page(p, 24, start_gid=p * 1000) for p in range(1, 6)]
    for p in mutated:
        p.x_emitted = []  # X drops the whole page; the draw must not move
    check(
        "a selected C region stays selected even when an arm drops all of its content",
        sorted((r["page_number"], r["region_ordinal"]) for r in regions if r["c_frame"]),
        sorted((r["page_number"], r["region_ordinal"]) for r in regions_of(frame_of(mutated)) if r["c_frame"]),
        "replacing such a region would delete the shared-failure evidence RQ2 exists to collect",
    )

    # population gate
    robust = frame_of(pages, population="P-robust")
    check(
        "a P-robust document receives NO C-frame selection",
        0,
        robust["counts"]["c_frame_selected"],
        "the C-frame quantity is defined on P-head only",
    )
    check(
        "...but its regions are still enumerated in full",
        15,
        len(regions_of(robust)),
        "if enumeration were skipped too, the D-frame would silently lose the document",
    )
    return {"regions": len(regions), "selected": frame["counts"]["c_frame_selected"]}


# --------------------------------------------------------------------- development run


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fake_arm_page(page_number, texts, gid_base=0, glyph_size=None):
    """A runner-shaped page dict whose print_lines, emitted cells and neutral skeleton agree.

    Built so the anti-drift precondition passes by construction; each control below then
    breaks exactly ONE thing, so a refusal can only be attributed to the injected fault.
    """
    lines = tuple(Line(i + 1, t, glyph_size) for i, t in enumerate(texts))
    page = Page(page_number, lines, lines, tuple((i, i + 1) for i in range(len(texts))))
    emitted, neutral, gid = [], [], gid_base
    for i, t in enumerate(texts):
        cells, gids = [], []
        for ch in t:
            if ch == " ":
                cells.append(Cell(ngid=None, char=" "))
            else:
                cells.append(Cell(ngid=gid, char=ch))
                gids.append(gid)
                gid += 1
        emitted.append(EmittedLine(cells=cells))
        neutral.append(nline(page_number, i, gids))
    return {"page_number": page_number, "page": page, "emitted": emitted, "neutral": neutral}


SEC_TEXTS = ["SEC. 1. The Secretary shall act.", "Second body line of the section."]


def arm_pair(pages=(1,)):
    h = [fake_arm_page(p, SEC_TEXTS, gid_base=p * 1000) for p in pages]
    x = [fake_arm_page(p, SEC_TEXTS, gid_base=p * 1000) for p in pages]
    return h, x


def public_frame(h, x, population=BF.P_HEAD):
    """Every structural control goes through the PUBLIC result-bearing entrypoint.

    Testing the gate helper directly would only prove the helper aborts; what matters is that
    no public call capable of returning a study frame can reach one of these states.
    """
    return BF.build_document_frame("devsha", "synthetic", population, h, x)


def refusal_reason(fn):
    try:
        fn()
    except BF.FrameConstructionError as exc:
        return exc.reason
    except Exception as exc:  # noqa: BLE001 - any other exception is itself a failure
        return f"OTHER:{type(exc).__name__}"
    return None


def part_preconditions() -> dict:
    print("\n== structural preconditions FAIL CLOSED (no caller obligation) ==")

    # --- page-set equality, both directions
    h, x = arm_pair((1, 2))
    check(
        "H carries a page X lacks -> ABORT",
        BF.PAGE_SET_MISMATCH,
        refusal_reason(lambda: public_frame(h, x[:1])),
        "dropping or intersecting the page set would silently shrink every denominator",
    )
    check(
        "X carries a page H lacks -> ABORT",
        BF.PAGE_SET_MISMATCH,
        refusal_reason(lambda: public_frame(h[:1], x)),
    )
    check(
        "matched page sets do NOT abort",
        True,
        refusal_reason(lambda: public_frame(h, x)) is None,
        "if the clean case also aborted, the two controls above would prove nothing",
    )

    # --- neutral skeleton equality
    h, x = arm_pair()
    x[0]["neutral"] = list(x[0]["neutral"])
    bad = x[0]["neutral"][0]
    x[0]["neutral"][0] = NeutralLine(
        page=bad.page,
        ordinal=bad.ordinal,
        baseline=bad.baseline,
        x0=bad.x0,
        y0=bad.y0,
        x1=bad.x1,
        y1=bad.y1,
        gids=frozenset(list(bad.gids)[:-1]),
    )
    check(
        "a one-glyph neutral skeleton difference -> ABORT",
        BF.NEUTRAL_SKELETON_MISMATCH,
        refusal_reason(lambda: public_frame(h, x)),
        "two skeletons would mean the arms' frames are not the same frame",
    )

    # --- A28.5 anti-drift: deletion, and same-length text drift
    h, x = arm_pair()
    x[0]["emitted"] = x[0]["emitted"][:-1]
    check(
        "an emitted line DELETED on one arm -> ABORT",
        BF.PRINT_LINES_EMITTED_DRIFT,
        refusal_reason(lambda: public_frame(h, x)),
        "the bridge reads emitted[i] for print line i; a deletion shifts every later index",
    )

    h, x = arm_pair()
    x[0]["emitted"] = list(x[0]["emitted"])
    x[0]["emitted"][0] = eline([(g, "Z") for g in sorted(x[0]["neutral"][0].gids)])
    check(
        "an emitted line's TEXT altered at equal list length -> ABORT",
        BF.PRINT_LINES_EMITTED_DRIFT,
        refusal_reason(lambda: public_frame(h, x)),
        "equal cardinality is not enough; the texts must correspond index for index",
    )

    # --- anchor placement refusals abort, in EITHER arm, and are NOT anchor discordance
    h, x = arm_pair()
    h[0]["emitted"] = list(h[0]["emitted"])
    h[0]["emitted"][0] = eline_no_ink(SEC_TEXTS[0])
    h_reason = refusal_reason(lambda: public_frame(h, x))
    check(
        "an unplaceable anchor in H -> ABORT",
        BF.ANCHOR_PLACEMENT_REFUSED,
        h_reason,
        "dropping it and comparing the rest would fabricate an ANCHOR_DISCORDANCE",
    )
    check("...and the refusal is NOT interpreted as ANCHOR_DISCORDANCE", True, h_reason != BF.ANCHOR_DISCORDANCE)

    h, x = arm_pair()
    x[0]["emitted"] = list(x[0]["emitted"])
    x[0]["emitted"][0] = eline_foreign_ink(SEC_TEXTS[0])
    x_reason = refusal_reason(lambda: public_frame(h, x))
    check(
        "an unplaceable anchor in X (asymmetric, different refusal class) -> ABORT",
        BF.ANCHOR_PLACEMENT_REFUSED,
        x_reason,
    )
    check("...and it too is NOT interpreted as ANCHOR_DISCORDANCE", True, x_reason != BF.ANCHOR_DISCORDANCE)

    # --- the two remaining silent-reduction paths, closed
    check(
        "an UNRECOGNISED population string -> ABORT, not a quiet empty C-frame",
        BF.UNKNOWN_POPULATION,
        refusal_reason(lambda: frame_of([simple_page(1, 8)], population="P-Head")),
        "'not P-head' would otherwise draw zero C regions and look like a valid frame",
    )
    check(
        "...while the two real populations still build",
        (True, True),
        (
            refusal_reason(lambda: frame_of([simple_page(1, 8)], population=BF.P_HEAD)) is None,
            refusal_reason(lambda: frame_of([simple_page(1, 8)], population=BF.P_ROBUST)) is None,
        ),
    )
    # --- unknown population, through the PUBLIC entrypoint too
    h, x = arm_pair()
    check(
        "an UNRECOGNISED population reaching the PUBLIC entrypoint -> ABORT",
        BF.UNKNOWN_POPULATION,
        refusal_reason(lambda: public_frame(h, x, population="nonsense")),
    )

    # --- duplicate page numbers, per arm. Set equality cannot see these: H=[1,1,2] and
    #     X=[1,2] have equal sets and the page dictionary would collapse the duplicate.
    h, x = arm_pair((1, 2))
    check(
        "a duplicate page record in H -> ABORT",
        BF.DUPLICATE_PAGE_NUMBER,
        refusal_reason(lambda: public_frame(h + [h[0]], x)),
        "set equality is blind to duplicates, and the later page map silently collapses them",
    )
    h, x = arm_pair((1, 2))
    check(
        "a duplicate page record in X -> ABORT",
        BF.DUPLICATE_PAGE_NUMBER,
        refusal_reason(lambda: public_frame(h, x + [x[0]])),
    )

    # --- THE 7-vs-8 HOLE: anchors placed on one grid, regions built on another. It is not
    #     rejected, it is UNSPELLABLE -- no result-bearing signature accepts a region size.
    public_params = sorted(inspect.signature(BF.build_document_frame).parameters)
    inputs_params = sorted(inspect.signature(BF._page_inputs_from_arms).parameters)
    ctor_params = sorted(inspect.signature(BF._build_document_frame_from_inputs).parameters)
    check(
        "no result-bearing signature accepts a region size",
        (False, False, False),
        ("region_size" in public_params, "region_size" in inputs_params, "region_size" in ctor_params),
        "a region_size on any of these lets placement and the grid disagree while both look valid",
    )
    check(
        "the public entrypoint takes RUNNER OUTPUTS, not PageInputs, so gates cannot be skipped",
        ["document_id", "document_sha256", "h_pages", "population", "x_pages"],
        public_params,
    )
    h, x = arm_pair((1, 2))
    built = public_frame(h, x)
    check(
        "...and the public path always yields the frozen 8-line grid",
        (8, True),
        (built["region_size"], all(r["line_count"] <= 8 for pf in built["pages"] for r in pf["regions"])),
    )

    # --- WHY per-page extraction is forbidden, proven on a constructed page collection.
    body = ["The Secretary shall carry out the program.", "Amounts are available until expended."]
    p1 = fake_arm_page(1, body, gid_base=0, glyph_size=10.0)
    p2 = fake_arm_page(2, ["OPERATIONS AND SUPPORT"], gid_base=500, glyph_size=8.0)
    doc_scope = extract_anchors([p1["page"], p2["page"]])
    per_page = extract_anchors([p1["page"]]) + extract_anchors([p2["page"]])
    check(
        "per-page extraction produces a DIFFERENT anchor census than document-scope",
        True,
        doc_scope != per_page,
        "if these agreed, the scope control could not detect the defect it exists to catch",
    )
    check(
        "...specifically, document scope finds the account heading and per-page finds nothing",
        (["account"], []),
        ([a.kind for a in doc_scope], [a.kind for a in per_page]),
        "size bands are derived over the SUPPLIED collection: page 2 alone carries no "
        "body-size prose, so no band exists and the account level vanishes",
    )
    return {
        "synthetic_scope_document": [BF.anchor_repr(a) for a in doc_scope],
        "synthetic_scope_per_page": [BF.anchor_repr(a) for a in per_page],
    }


def eline_no_ink(text):
    """Same characters, no neutral ink -> EMITTED_LINE_CARRIES_NO_NEUTRAL_INK."""
    return EmittedLine(cells=[Cell(ngid=None, char=ch) for ch in text])


def eline_foreign_ink(text):
    """Same characters, ink the skeleton does not own -> FIRST_GID_NOT_OWNED_BY_ANY_NEUTRAL_LINE."""
    return EmittedLine(cells=[Cell(ngid=900000 + i, char=ch) for i, ch in enumerate(text)])


def kind_counts(anchors):
    c = {}
    for a in anchors:
        c[a.kind] = c.get(a.kind, 0) + 1
    return c


def part_development() -> dict:
    print("\n== DEVELOPMENT frames (diagnostics only, never study results) ==")
    rows, scope_rows = [], []
    census_mismatch, placement_mismatch = [], []

    for name, path in DOCS:
        for member in HOLDOUT_GUARD:
            if member in str(path):
                raise SystemExit(f"REFUSED: {path} touches holdout member {member}")
        if not path.exists():
            continue
        h_pages = run_hybrid.run(path, limit=PAGE_LIMIT)
        x_pages, _s = run_extended.run(path, limit=PAGE_LIMIT)

        # Any structural precondition failure RAISES here; reaching the next line is itself
        # the assertion that page sets, skeletons, anti-drift and placement were all clean.
        frame = BF.build_document_frame(sha256_of(path), name, BF.P_HEAD, h_pages, x_pages)

        for arm, arm_pages in (("H", h_pages), ("X", x_pages)):
            ordered = [d["page"] for d in sorted(arm_pages, key=lambda d: d["page_number"])]
            doc_scope = BF.document_scope_anchors(arm_pages)

            # (a) CENSUS fidelity -- what build_frames consumed IS the document-scope census,
            #     and every one of those anchors reached the frame.
            if doc_scope != extract_anchors(ordered):
                census_mismatch.append({"document": name, "arm": arm, "why": "not document-scoped"})
            in_frame = sorted(
                tuple(a) for pf in frame["pages"] for r in pf["regions"] for a in r["anchor_evidence"][arm]
            )
            if in_frame != sorted(BF.anchor_repr(a) for a in doc_scope):
                census_mismatch.append({"document": name, "arm": arm, "why": "frame census != extracted census"})

            # (b) PLACEMENT fidelity -- distinct from (a): the bridge must equal x14's for
            #     every anchor in the DOCUMENT-SCOPE census, not a per-page one.
            by_page = {d["page_number"]: d for d in arm_pages}
            for a in doc_scope:
                d = by_page[a.page_number]
                owner = build_owner(d["neutral"])
                ordinal_by_key = {ln.key: ln.ordinal for ln in d["neutral"]}
                mine = BF.place_anchor(a, d["page"].print_lines, d["emitted"], owner, ordinal_by_key)
                theirs = X14.place_anchor(a, d["page"].print_lines, d["emitted"], d["neutral"], owner)
                if mine != theirs:
                    placement_mismatch.append({"document": name, "arm": arm, "anchor": str(a)})

            # (c) the SCOPE BUG measured: what per-page extraction would have produced
            per_page = []
            for page in ordered:
                per_page.extend(extract_anchors([page]))
            scope_rows.append(
                {
                    "document": name,
                    "arm": arm,
                    "document_scope": len(doc_scope),
                    "per_page_would_have_been": len(per_page),
                    "document_scope_kinds": kind_counts(doc_scope),
                    "per_page_kinds": kind_counts(per_page),
                    "identical": doc_scope == per_page,
                }
            )

        c = frame["counts"]
        print(
            f"  {name}: lines={c['neutral_lines']} regions={c['regions']} "
            f"C={c['c_frame_selected']} D={c['d_frame_census']} "
            f"(text={c['d_text']} seg={c['d_segmentation']} anchor={c['d_anchor']}) "
            f"both_absent={c['both_absent_lines']} short_trailing={c['short_trailing_regions']}"
        )
        rows.append({"document": name, "document_sha256": frame["document_sha256"], **c})

    for r in scope_rows:
        print(
            f"    scope[{r['arm']}] {r['document']}: document={r['document_scope']} "
            f"per-page-would-have-been={r['per_page_would_have_been']} identical={r['identical']}"
        )

    check(
        "H anchor census is document-scoped and reaches the frame intact",
        [],
        [m for m in census_mismatch if m["arm"] == "H"],
        "a per-page census would re-derive size bands per page and cut cross-page runs",
    )
    check(
        "X anchor census is document-scoped and reaches the frame intact",
        [],
        [m for m in census_mismatch if m["arm"] == "X"],
    )
    check(
        "H placement reproduces x14's over the DOCUMENT-SCOPE census",
        [],
        [m for m in placement_mismatch if m["arm"] == "H"],
        "a divergence would mean the frames use a bridge the study never approved",
    )
    check(
        "X placement reproduces x14's over the DOCUMENT-SCOPE census",
        [],
        [m for m in placement_mismatch if m["arm"] == "X"],
    )
    check(
        "every development document retained at least one short trailing region",
        [],
        [r["document"] for r in rows if r["short_trailing_regions"] == 0],
    )
    check(
        "no development document exceeded the 8-region C-frame cap",
        [],
        [r["document"] for r in rows if r["c_frame_selected"] > 8],
    )
    return {
        "documents": rows,
        "anchor_scope_comparison": scope_rows,
        "census_mismatch": census_mismatch,
        "placement_mismatch": placement_mismatch,
    }


def main() -> int:
    part_regions()
    d_evidence = part_d_frame()
    c_evidence = part_c_frame()
    precond = part_preconditions()
    dev = part_development()

    doc = {
        "population": "SYNTHETIC + DEVELOPMENT -- no holdout opened, nothing scored",
        "canonical_frames_json_created": False,
        "d_frame_budget_applied": False,
        "d_frame_sampled_or_truncated": False,
        "region_size": BF.REGION_SIZE,
        "c_frame_max_per_document": BF.C_FRAME_MAX_PER_DOCUMENT,
        "c_frame_namespace": "cframe-select",
        "selection_seed": MC.SELECTION_SEED,
        "anchor_equality": (
            "the WHOLE emitted production Anchor value (page, line, kind, text, division); no "
            "reduced signature is invented for frames"
        ),
        "development_note": (
            "DEVELOPMENT figures are diagnostics that exercise the code paths. They are not "
            "study results and no metric is scored from them."
        ),
        "public_entrypoint": "build_frames.build_document_frame(sha, id, population, h_pages, x_pages)",
        "private_synthetic_constructor": "build_frames._build_document_frame_from_inputs(...)",
        "region_size_is_not_a_parameter_on_any_result_bearing_path": True,
        "structural_preconditions_fail_closed": [
            BF.DUPLICATE_PAGE_NUMBER,
            BF.PAGE_SET_MISMATCH,
            BF.NEUTRAL_SKELETON_MISMATCH,
            BF.PRINT_LINES_EMITTED_DRIFT,
            BF.ANCHOR_PLACEMENT_REFUSED,
            BF.UNKNOWN_POPULATION,
        ],
        "synthetic_precondition_evidence": precond,
        "synthetic_d_evidence": d_evidence,
        "synthetic_c_evidence": c_evidence,
        "development": dev,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
