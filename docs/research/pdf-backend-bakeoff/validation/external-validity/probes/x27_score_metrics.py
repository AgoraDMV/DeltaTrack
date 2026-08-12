"""x27 -- HARNESS-PLAN section 5's control table, executed against `score_metrics`.

NOT CONFIRMATORY. SYNTHETIC + DEVELOPMENT only. No holdout document is opened, nothing is
adjudicated by a human or an AI, no architecture decision is taken, and none of
`results/frames.json`, `oracle_key.json`, `oracle_blind.json`, `oracle_adjudicated.json`,
`s1_control.json`, `cross_engine_control.json`, `metrics.json`, `scores.json` or
`EXECUTION-START.json` is created. Evidence: `results/x27_score_metrics.json`.

RUN WITH AN INTERPRETER CARRYING BOTH `pymupdf` AND `pypdfium2`, as `x21`/`x22` require.

WHAT THIS PROBE EXISTS TO PROVE, and what would make each half FALSE:

    the scorer computes section 6 / section 8 from committed facts     -- every control below
    each frozen quantity can go RED                                   -- the negatives
    a malformed or incomplete input REFUSES rather than scoring        -- part_refusals
    the scorer never reads a summary it could have trusted             -- the corrupted-`counts`
                                                                         attack
    the same inputs give the same numbers                             -- part_reproducibility

THE SYNTHETIC ADJUDICATIONS ARE A MECHANISM FIXTURE, NEVER AN ACCURACY MEASUREMENT. Their
"oracle" text is taken from one arm's own emitted output, so agreement proves the JOIN works and
says nothing about whether either architecture is correct. Real adjudication is human/AI, does
not exist, and cannot exist before the execution boundary. Every number this probe prints is a
property of a fixture built here.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import inspect
import json
import re
import subprocess
import sys
import tempfile
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
import build_oracle as BO  # noqa: E402
import control_fixtures as CF  # noqa: E402
import m3_boundaries as M3  # noqa: E402
import methodology_contracts as MC  # noqa: E402
import oracle_geometry as OG  # noqa: E402
import pymupdf  # noqa: E402
import score_metrics as SM  # noqa: E402
from neutral_identity import Cell, EmittedLine, NeutralLine  # noqa: E402

from deltatrack.parsers.pdf_anchors import Anchor  # noqa: E402

OUT = EV / "results" / "x27_score_metrics.json"
ROWS: list[dict] = []
FAILED: list[str] = []

#: section 5 control-table rows, so the evidence file states which row each check discharges.
SECTION5_ROWS = (
    "S1 liveness",
    "M3 weld/space fixture",
    "M3 insulation",
    "negative: delete agency anchors",
    "negative: shift heading baselines one line-height",
    "negative: inject an R E P O R T page",
    "M0 denominator",
    "vacuity",
    "section 8 independence",
    "section 8 zero-event",
    "section 8 pairing",
)
COVERED: dict[str, list[str]] = {row: [] for row in SECTION5_ROWS}


def check(name: str, expected, observed, fails_when: str = "", row: str = "") -> bool:
    ok = expected == observed
    ROWS.append(
        {"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when, "row": row}
    )
    if not ok:
        FAILED.append(name)
    if row:
        COVERED.setdefault(row, []).append(name)
    print(
        f"[{'PASS' if ok else 'FAIL'}] {name}"
        + ("" if ok else f"\n        expected={expected!r}\n        observed={observed!r}")
    )
    return ok


def refusal(fn) -> str | None:
    """The refusal class a callable raises, or None if it returned. Never swallows the reason."""
    return refusal_detail(fn)[1]


def first_failure(kind_block: dict) -> tuple:
    """`(status, first failure reason or None)` for one control kind.

    Indexing `failures[0]` directly makes a control CRASH when an injected fault turns the
    expected failure into a pass -- the fault is still detected, but by a traceback rather than by
    the named check, which is weaker evidence: a crash cannot distinguish "the rule broke" from
    "the probe has a bug". Returning None keeps the red inside `check`.
    """
    failures = kind_block.get("failures") or []
    return (kind_block.get("status"), failures[0]["reason"] if failures else None)


def refusal_any(fn) -> tuple:
    """`(exception type, reason or None)` for ANY exception -- used where a fault would otherwise
    escape as an unrelated crash (a KeyError deep inside `qualification`, say) and the control
    needs to distinguish a DETERMINISTIC refusal from an accidental one."""
    try:
        fn()
    except SM.ScoreInputError as exc:
        return (type(exc).__name__, exc.reason)
    except Exception as exc:  # noqa: BLE001 -- the point is to name whatever came out
        return (type(exc).__name__, None)
    return (None, None)


def refusal_detail(fn) -> tuple:
    """`(exception type name, reason)` -- WHICH LAYER refused, not only that something did.

    The reason alone is not always enough. `score_metrics` and `methodology_contracts` both
    define `DUPLICATE_DOCUMENT_IDENTITY` with the SAME string, and the frozen section 8 helper
    validates its document vector one layer below the scorer's own check. A control asserting the
    reason alone therefore passes whether or not the scorer's guard exists -- which the injection
    sweep found by deleting that guard and watching the suite stay green. Pinning the exception
    CLASS distinguishes the layers, so the control can fail.
    """
    try:
        fn()
    except SM.ScoreInputError as exc:
        return (type(exc).__name__, exc.reason)
    except (BO.OracleBuildError, MC.BootstrapInputError) as exc:
        return (type(exc).__name__, exc.reason)
    except MC.UnknownRole as exc:
        return (type(exc).__name__, type(exc).__name__)
    return (None, None)


# ============================================================ synthetic fixture material
#
# The frames come from `build_frames._build_document_frame_from_inputs` -- the private synthetic
# seam `x17` uses -- so every `line_state`, region grid, C/D membership and count below is REAL
# producer output rather than a hand-written dict resembling one. Only `architecture_occurrences`
# and `m9` are attached by hand, because the real producer derives them from live `Page` objects;
# `part_development` closes that gap by running the whole chain on a real DEVELOPMENT PDF.

LINES_PER_REGION = BF.REGION_SIZE
DOC_SHA = hashlib.sha256(b"x27-synthetic").hexdigest()
#: A second source SHA. A28.3's base stimulus identity is (sha, page, region_ordinal), so any
#: fixture with two documents needs two SHAs or the realized stimulus set collides.
DOC_SHA_B = hashlib.sha256(b"x27-synthetic-b").hexdigest()
#: x21's synthetic-PDF geometry, so a frame built here can be rendered by the REAL `build_oracle`.
LEFT_X, RIGHT_X = 100.0, 300.0
CANDIDATE_XS = (100.0, 140.0)


def nline(page: int, ordinal: int, gids) -> NeutralLine:
    baseline = 792.0 - (120.0 + ordinal * 20.0)
    ordered = sorted(gids)
    return NeutralLine(
        page=page,
        ordinal=ordinal,
        baseline=baseline,
        x0=LEFT_X,
        y0=baseline - 3.0,
        x1=RIGHT_X,
        y1=baseline + 9.0,
        gids=frozenset(ordered),
        # A38.2 -- two candidates a fixed distance apart, so a nearest-glyph boundary exists
        candidates=tuple((g, CANDIDATE_XS[i % len(CANDIDATE_XS)]) for i, g in enumerate(ordered)),
    )


def eline(pairs) -> EmittedLine:
    return EmittedLine(cells=[Cell(ngid=g, char=c) for g, c in pairs])


def page_input(
    page_number: int,
    n_lines: int = LINES_PER_REGION,
    *,
    start_gid: int = 0,
    text_differs=(),
    merge=(),
    both_absent=(),
    h_anchors=None,
    x_anchors=None,
) -> BF.PageInput:
    """One page of neutral lines, with the arms' emitted lines under our control.

    text_differs  ordinals where X emits a DIFFERENT character for the same glyph
    merge         ordinals X merges with the NEXT line (a pure segmentation difference)
    both_absent   ordinals NEITHER arm emits (chrome both correctly drop)
    """
    neutral, h, x, gid = [], [], [], start_gid
    for i in range(n_lines):
        gids = list(range(gid, gid + 2))
        neutral.append(nline(page_number, i, gids))
        gid += 2
    skip_x: set[int] = set()
    for i, line in enumerate(neutral):
        gids = sorted(line.gids)
        if i in both_absent:
            continue
        h.append(eline([(g, "A") for g in gids]))
        if i in skip_x:
            continue
        if i in merge and i + 1 < n_lines and (i + 1) not in both_absent:
            nxt = sorted(neutral[i + 1].gids)
            x.append(eline([(g, "A") for g in gids + nxt]))
            skip_x.add(i + 1)
            continue
        char = "Z" if i in text_differs else "A"
        x.append(eline([(g, char) for g in gids]))
    return BF.PageInput(
        page_number=page_number,
        neutral=neutral,
        h_emitted=h,
        x_emitted=x,
        h_anchors_by_region=h_anchors or {},
        x_anchors_by_region=x_anchors or {},
    )


def anchor(page: int, line: int, kind: str = "account", text: str = "SALARIES AND EXPENSES") -> Anchor:
    return Anchor(page_number=page, line_number=line, kind=kind, text=text, division="")


def occurrence(
    page: int,
    line_ordinal: int,
    ngid: int,
    *,
    kind: str = "account",
    text: str = "SALARIES AND EXPENSES",
    parent: str | None = "DEPARTMENTAL MANAGEMENT",
    region_ordinal: int = 0,
    line_number: int | None = None,
    matchable: bool = True,
    sha: str = DOC_SHA,
) -> dict:
    """One emitted occurrence record in `build_frames`' committed A38.3 shape."""
    key = [sha, page, [page, line_ordinal], ngid] if matchable else None
    return {
        "anchor": {
            "page_number": page,
            "line_number": line_ordinal if line_number is None else line_number,
            "kind": kind,
            "text": text,
            "division": "",
        },
        "page_number": page,
        "region_ordinal": region_ordinal,
        "placed_neutral_line_key": [page, line_ordinal],
        "occurrence_key": key,
        "match_status": "MATCHABLE" if matchable else "UNMATCHED",
        "unmatched_reason": None if matchable else "START_NGID_NOT_OWNED_BY_NEUTRAL_LINE",
        "immediate_parent": parent,
        "breadcrumb": [p for p in (parent, text) if p is not None],
    }


def m9_facts(*, band: bool = True, coverage: float = 1.0, margin: int = 120, lines: int = 140) -> dict:
    return {
        "derive_size_bands_returns_a_band": band,
        "coverage": coverage,
        "coverage_floor": 0.85,
        "coverage_meets_floor": coverage >= 0.85,
        "n_lines_total": lines,
        "n_margin_numbered_lines": margin,
        "n_margin_numbered_with_glyph_size": margin,
        "margin_numbered_line_keys": [[1, i] for i in range(margin)],
        "rule0_comparison": "RAW FACTS ONLY",
    }


def frame(
    pages,
    *,
    document: str = "SYNTHETIC/1",
    sha: str = DOC_SHA,
    population: str = BF.P_HEAD,
    occurrences=None,
    m9_h=None,
    m9_x=None,
) -> dict:
    built = BF._build_document_frame_from_inputs(sha, document, population, list(pages))
    built["architecture_occurrences"] = occurrences or {"H": [], "X": []}
    built["m9"] = {"H": m9_h or m9_facts(), "X": m9_x or m9_facts()}
    return built


EMPTY_KEY = {"schema": "oracle_key/3", "stimuli": {}}
EMPTY_ADJUDICATED = {"schema": BO.ADJUDICATED_SCHEMA, BO.ROUTE_AI: {}, BO.ROUTE_HUMAN: {}}


def s1_artifact(fires: bool = True) -> dict:
    return {"schema": "s1_control/1", "advance_scale": 1.25, "fires": fires, "n_firing": 1 if fires else 0}


def cross_engine_artifact(documents, failed=()) -> dict:
    return {
        "schema": "cross_engine_control/1",
        "per_document": [
            {"document": d, "passed": d not in failed, "qualification": None if d not in failed else "Q"}
            for d in documents
        ],
        "n_documents": len(list(documents)),
    }


def inputs(
    frames,
    *,
    key=None,
    adjudicated=None,
    s1=None,
    cross_engine=None,
    strata=None,
) -> SM.ScoreInputs:
    docs = [f["document"] for f in frames]
    return SM.ScoreInputs(
        frames=tuple(frames),
        oracle_key=key or EMPTY_KEY,
        oracle_adjudicated=adjudicated or EMPTY_ADJUDICATED,
        cross_engine=cross_engine or cross_engine_artifact(docs),
        s1=s1 or s1_artifact(),
        document_strata=strata if strata is not None else {d: 1 for d in docs},
    )


# ================================================================= M0, its denominator, vacuity


def part_m0() -> dict:
    print("\n== M0: the risk set, BOTH_ABSENT, and the region-level M0c ==")
    clean = frame([page_input(1)])
    block = SM.m0_block(clean)
    check(
        "a fully concordant page yields a full risk set and zero discordance",
        (LINES_PER_REGION, 0, 0, 0),
        (block["risk_set"], block["M0a_text"], block["M0b_segmentation"], block["both_absent"]),
        "the fixture is not concordant, so every comparison below starts from a moving baseline",
    )

    # --- section 5 row: M0 denominator. BOTH_ABSENT must appear in NO M0 denominator.
    with_chrome = frame([page_input(1, both_absent={5, 6, 7})])
    chrome_block = SM.m0_block(with_chrome)
    denominators = {
        name: chrome_block[name]["denominator"] for name in ("M0a_text_rate", "M0b_segmentation_rate", "M0_any_rate")
    }
    check(
        "3 BOTH_ABSENT lines leave the risk set at 5 and are reported as a raw count",
        (5, 3, LINES_PER_REGION),
        (chrome_block["risk_set"], chrome_block["both_absent"], chrome_block["neutral_lines_in_scope"]),
        "a jointly-dropped line entered the risk set, which would make the rate a function of "
        "how much page furniture GPO set rather than of the seam",
        row="M0 denominator",
    )
    check(
        "every M0 line-rate denominator IS the risk set, never the line count",
        {name: 5 for name in denominators},
        denominators,
        "a BOTH_ABSENT line appears in an M0 denominator, i.e. a shared drop is scored as agreement",
        row="M0 denominator",
    )
    check(
        "...and M0b's DEFINED denominator is reported separately (A23's reporting rule)",
        5,
        chrome_block["M0b_rate_on_defined"]["denominator"],
        "the defined-population rate shares the risk-set denominator, so a zero M0b could be read "
        "as 'the arms grouped identically' when it means 'there was nothing to compare'",
    )

    # --- NEGATIVE: BOTH_ABSENT counted as agreement. The two denominators must DIFFER here, or
    # the control above passed on a fixture that could not tell them apart.
    discordant_with_chrome = frame([page_input(1, text_differs={0}, both_absent={5, 6, 7})])
    b = SM.m0_block(discordant_with_chrome)
    check(
        "NEGATIVE -- the all-lines denominator gives a DIFFERENT rate, so the fixture is decisive",
        (1 / 5, 1 / 8),
        (b["M0_any_rate"]["value"], b["M0_any_rate_ALL_LINES_superseded"]),
        "both denominators agree on this fixture, so 'BOTH_ABSENT is excluded' was never tested",
        row="M0 denominator",
    )
    check(
        "...and the REPORTED headline is the risk-set rate, not the superseded one",
        1 / 5,
        b["M0a_text_rate"]["value"],
        "the scorer reports the all-lines rate, which counts a shared drop as agreement",
        row="M0 denominator",
    )

    # --- section 5 row: vacuity. A zero content-bearing denominator is VACUOUS, never a rate.
    all_absent = frame([page_input(1, both_absent=set(range(LINES_PER_REGION)))])
    vac = SM.m0_block(all_absent)
    check(
        "a page neither arm emitted reports VACUOUS, not 0.0 and not agreement",
        (0, None, SM.VACUOUS, None, SM.VACUOUS),
        (
            vac["risk_set"],
            vac["M0a_text_rate"]["value"],
            vac["M0a_text_rate"]["status"],
            vac["M0_any_rate"]["value"],
            vac["M0_any_rate"]["status"],
        ),
        "a zero-denominator metric is printed as a rate -- 0.0 reads as perfect agreement and "
        "1.0 as total failure, and neither was measured",
        row="vacuity",
    )

    # --- M0b vs M0a: a pure segmentation difference must move M0b and NOT M0a.
    merged = frame([page_input(1, merge={2})])
    m = SM.m0_block(merged)
    check(
        "a pure segmentation difference moves M0b and leaves M0a at zero",
        (0, 2, 2, 0),
        (m["M0a_text"], m["M0b_segmentation"], m["M0b_only_segmentation"], m["M0a_only_text"]),
        "grouping and characters are conflated, which is the exact defect A23 corrected",
    )

    # --- M0c is REGION-level and is never pooled with the line rates.
    differing = frame(
        [
            page_input(
                1,
                h_anchors={0: {anchor(1, 3)}},
                x_anchors={0: {anchor(1, 3, text="SALARIESAND EXPENSES")}},
            )
        ]
    )
    c = SM.m0_block(differing)
    check(
        "an anchor-set difference is counted as M0c over REGIONS, with the line rates untouched",
        (1, 1, 1.0, 0, 0),
        (
            c["M0c_anchor_regions"],
            c["M0c_rate"]["denominator"],
            c["M0c_rate"]["value"],
            c["M0a_text"],
            c["M0b_segmentation"],
        ),
        "M0c is pooled into or averaged with the per-line rates, which section 5 forbids",
    )
    return {
        "concordant": {k: block[k] for k in ("risk_set", "M0a_text", "M0b_segmentation")},
        "with_chrome": {k: chrome_block[k] for k in ("risk_set", "both_absent", "neutral_lines_in_scope")},
        "vacuous": {"risk_set": vac["risk_set"], "status": vac["M0a_text_rate"]["status"]},
        "segmentation_only": {k: m[k] for k in ("M0a_text", "M0b_segmentation")},
        "m0c": {"regions": c["M0c_anchor_regions"], "rate": c["M0c_rate"]["value"]},
    }


def part_i9() -> dict:
    """I9 -- M0's eligibility set and the D-frame's are ONE set, and drift REFUSES."""
    print("\n== I9: one eligibility set for M0 and the D-frame ==")
    good = frame([page_input(1, text_differs={0})])
    check(
        "a text-discordant line puts its region in the D-frame (same predicate, one set)",
        (True, [BF.TEXT_DISCORDANCE]),
        (good["pages"][0]["regions"][0]["d_frame"], good["pages"][0]["regions"][0]["d_reasons"]),
        "M0 and the D-frame would be reading different eligibility sets, so Rule 1's census and "
        "M0 would be measuring different things",
    )
    check(
        "the clean input SCORES, so the refusals below are not refusing everything",
        None,
        refusal(lambda: SM.score(inputs([good]))),
        "the scorer refuses valid input, making every negative control meaningless",
    )

    stripped = copy.deepcopy(good)
    stripped["pages"][0]["regions"][0]["d_frame"] = False
    stripped["pages"][0]["regions"][0]["d_reasons"] = []
    check(
        "NEGATIVE -- a discordant line in a NON-D region REFUSES (I9)",
        SM.D_FRAME_ELIGIBILITY_DRIFT,
        refusal(lambda: SM.score(inputs([stripped]))),
        "two eligibility sets are accepted silently, and the D-frame census that Rule 1 reads "
        "would exclude regions M0 counted as discordant",
    )

    # COHERENT with the flag invariant (`d_frame == bool(d_reasons)` holds), so that check cannot
    # fire first and this control still measures what it names: a region claiming D membership with
    # no predicate actually satisfied.
    invented = copy.deepcopy(frame([page_input(1)]))
    invented["pages"][0]["regions"][0]["d_frame"] = True
    invented["pages"][0]["regions"][0]["d_reasons"] = [BF.TEXT_DISCORDANCE]
    check(
        "NEGATIVE -- a D-frame region with NO qualifying predicate REFUSES",
        SM.D_FRAME_ELIGIBILITY_DRIFT,
        refusal(lambda: SM.score(inputs([invented]))),
        "a region can be in the adjudication census for no recorded reason, which would spend "
        "human adjudication budget on regions nothing selected",
    )

    lied = copy.deepcopy(good)
    lied["pages"][0]["neutral_lines"][0]["line_state"]["text_discordance"] = False
    check(
        "NEGATIVE -- a committed predicate that disagrees with the frozen rule REFUSES",
        SM.LINE_STATE_PREDICATE_DRIFT,
        refusal(lambda: SM.score(inputs([lied]))),
        "the scorer trusts a committed boolean over `neutral_identity`'s own predicate, so a "
        "frame could report agreement its own texts contradict",
    )

    unknown = copy.deepcopy(good)
    unknown["pages"][0]["neutral_lines"][0]["line_state"]["state"] = "PROBABLY_FINE"
    check(
        "NEGATIVE -- an unknown line state REFUSES rather than defaulting into the risk set",
        SM.UNKNOWN_LINE_STATE,
        refusal(lambda: SM.score(inputs([unknown]))),
        "an unrecognised state falls through to 'not BOTH_ABSENT' and silently enlarges the M0 denominator",
    )

    # --- THE EXACT FLAG INVARIANT, with a fixture chosen so no OTHER check can catch it first.
    # A CONCORDANT region given a reason while `d_frame` stays False satisfies every per-predicate
    # check: there is no discordant line (so the line-level rule is silent), `d_frame` is False (so
    # the "D with no predicate" rule is silent), and ANCHOR_DISCORDANCE is absent from both the
    # reasons and the evidence (so the anchor rule agrees). Only `d_frame == bool(d_reasons)` sees it.
    flag_drift = copy.deepcopy(frame([page_input(1)]))
    region = flag_drift["pages"][0]["regions"][0]
    region["d_reasons"] = [BF.TEXT_DISCORDANCE]
    region["d_frame"] = False
    check(
        "NEGATIVE -- a region whose d_frame contradicts its own d_reasons REFUSES",
        SM.D_FRAME_FLAG_DRIFT,
        refusal(lambda: SM.score(inputs([flag_drift]))),
        "`d_frame` and `d_reasons` can disagree, so a region carrying a recorded reason can sit "
        "outside the census that reason exists to put it in -- and every per-predicate check above "
        "passes on this fixture, which is why the exact invariant is needed",
    )
    check(
        "...and the fixture really is invisible to the other checks, so this is not a duplicate",
        (False, False, False),
        (
            any(ln["line_state"]["text_discordance"] for ln in flag_drift["pages"][0]["neutral_lines"]),
            any(ln["line_state"]["segmentation_discordance"] for ln in flag_drift["pages"][0]["neutral_lines"]),
            region["anchor_evidence"]["differ"],
        ),
        "the fixture also carries a line-level or anchor discordance, so an existing check would "
        "have caught it and the new invariant is unproven",
    )
    check(
        "the producer really does emit d_frame == bool(d_reasons), so the invariant is its own",
        [(True, True), (False, False)],
        [
            (bool(r["d_frame"]), bool(r["d_reasons"]))
            for r in (
                frame([page_input(1, text_differs={0})])["pages"][0]["regions"][0],
                frame([page_input(1)])["pages"][0]["regions"][0],
            )
        ],
        "`build_frames` does not maintain the relationship this check enforces, so the check would "
        "be asserting something the producer never promised",
    )
    return {"d_reasons": good["pages"][0]["regions"][0]["d_reasons"]}


def part_s1() -> dict:
    """Section 5's first row: if S1 does not fire, M0 is NOT REPORTABLE."""
    print("\n== section 5 row 1: S1 liveness gates M0's reportability ==")
    f = frame([page_input(1, text_differs={0})])
    live = SM.score(inputs([f], s1=s1_artifact(True)))
    dead = SM.score(inputs([f], s1=s1_artifact(False)))
    live_m0 = live["per_document"]["SYNTHETIC/1"]["M0"]
    dead_m0 = dead["per_document"]["SYNTHETIC/1"]["M0"]
    check(
        "S1 FIRING leaves M0 reportable",
        (True, "REPORTED", 1 / LINES_PER_REGION),
        (live["s1"]["m0_reportable"], live_m0["M0a_text_rate"]["status"], live_m0["M0a_text_rate"]["value"]),
        "a live comparator still suppresses M0, so the control cannot distinguish live from dead",
        row="S1 liveness",
    )
    check(
        "S1 NOT firing makes every M0 rate NOT REPORTABLE",
        (False, SM.NOT_REPORTABLE_S1_DEAD, None),
        (dead["s1"]["m0_reportable"], dead_m0["M0a_text_rate"]["status"], dead_m0["M0a_text_rate"]["value"]),
        "M0 is reported from a comparator that cannot be shown to move -- exactly the phase-1 "
        "defect S1 exists to catch",
        row="S1 liveness",
    )
    check(
        "...and the RAW counts survive the suppression, so evidence is not destroyed",
        (1, LINES_PER_REGION),
        (dead_m0["M0a_text"], dead_m0["risk_set"]),
        "withholding the rate also deleted the counts, so a reader cannot see what was measured",
        row="S1 liveness",
    )
    check(
        "NEGATIVE -- an S1 artifact with no verdict at all REFUSES",
        SM.S1_ARTIFACT_MISSING,
        refusal(lambda: SM.score(inputs([f], s1={"schema": "s1_control/1"}))),
        "a missing liveness verdict is read as firing, so M0 is reported with no live comparator",
        row="S1 liveness",
    )
    return {"live": live["s1"], "dead": dead["s1"]}


# ============================================================== the M1-M5 heading join, on a
# ============================================================== REAL oracle key


def synthetic_pdf(tmp: Path, n_pages: int) -> Path:
    """x21's deterministic synthetic PDF geometry, so a frame built here can really be rendered."""
    doc = pymupdf.open()
    for p in range(n_pages):
        page = doc.new_page(width=612, height=792)
        for i in range(LINES_PER_REGION):
            page.insert_text((LEFT_X, 120.0 + i * 20.0), f"SYNTHETIC HEADING P{p} LINE {i}", fontsize=11)
    path = tmp / f"x27_synthetic_{n_pages}.pdf"
    doc.save(path)
    doc.close()
    return path


def start_annotation(record: dict, occurrence_record: dict) -> dict:
    """The (start_physical_line, start_x_px) that names this occurrence, from COMMITTED facts.

    The inverse of A38.7's join, built from the key's own `region_line_bijection`,
    `identity_candidates`, `bbox_pdf_points` and `dpi` -- and from the A34 transform's own
    inverse rather than a second linear guess. Nothing here reads a PDF or an arm's text.
    """
    key = occurrence_record["occurrence_key"]
    line_key, ngid = key[2], key[3]
    bijection = [list(m) for m in record["region_line_bijection"]]
    index = bijection.index(list(line_key))
    candidates = record["identity_candidates"][f"{line_key[0]}:{line_key[1]}"]
    x0 = next(float(c[1]) for c in candidates if int(c[0]) == ngid)
    return {
        "start_physical_line": index + 1,
        "start_x_px": OG.pdf_x_to_pixel(x0, record["bbox_pdf_points"][0], record["dpi"]),
    }


def synthesize_adjudication(key: dict, *, truth: str = "H", role: str = "account", text_from=None) -> dict:
    """An `oracle_adjudicated/1` artifact derived from the KEY's own committed facts.

    A MECHANISM FIXTURE. The heading text comes from an arm's own emitted output (or from
    `text_from`), so this can prove the join binds and the denominators are right; it can never
    measure accuracy, and no number derived from it is an accuracy claim.
    """
    out = {"schema": BO.ADJUDICATED_SCHEMA, BO.ROUTE_AI: {}, BO.ROUTE_HUMAN: {}}
    for bid, record in key["stimuli"].items():
        headings = []
        if record["control_kind"] is None:
            for row in record["architecture_occurrences"][truth]:
                if row["occurrence_key"] is None:
                    continue  # A30 refused: the oracle side has no identity to name it by
                headings.append(
                    {
                        "text": text_from(row) if text_from else row["anchor"]["text"],
                        "role": role,
                        # THE ADJUDICATOR'S OWN REPRESENTATION, not Python's. `adjudicator_prompt.md`
                        # section 3 asks for the printed parent text or the literal `NONE`; a JSON
                        # null is not an answer the prompt can produce, and a fixture that emitted
                        # one let M4 pass without ever exercising the real encoding.
                        "parent": row["immediate_parent"]
                        if row["immediate_parent"] is not None
                        else SM.ORACLE_PARENT_NONE,
                        **start_annotation(record, row),
                    }
                )
        else:
            # A control's committed expected truth. Its non-text fields are placeholders, which
            # is safe precisely BECAUSE no metric may read a control answer -- and the
            # invariance control below is what proves none does.
            for expected in record["control_expected_truth"] or []:
                headings.append(
                    {
                        "text": expected.get("text", ""),
                        "role": "account",
                        "parent": SM.ORACLE_PARENT_NONE,
                        "start_physical_line": 1,
                        "start_x_px": 0,
                    }
                )
        for route in record["adjudication_routes"]:
            # INDEPENDENT PER ROUTE. Sharing one list object across the two namespaces makes a
            # route-specific perturbation impossible -- `copy.deepcopy` memoizes, so the shared
            # reference survives into the copy and a "human-only" edit silently changes the AI
            # answer too. Two adjudication sources produce two answers (A36.6 keeps them
            # separately namespaced), so the fixture must too.
            out[route][bid] = {"id": bid, "headings": copy.deepcopy(headings)}
    return out


def join_fixture(tmp: Path, *, n_pages: int = 2, occurrences=None, page_kwargs=None) -> tuple:
    """A REAL oracle key over a REAL frame, plus the adjudication that names its occurrences."""
    kwargs = page_kwargs or {}
    pages = [page_input(p + 1, start_gid=p * 100, **kwargs.get(p + 1, {})) for p in range(n_pages)]
    occ = occurrences or {
        arm: [occurrence(p + 1, 2, p * 100 + 4, text="SALARIES AND EXPENSES") for p in range(n_pages)]
        for arm in ("H", "X")
    }
    f = frame(pages, occurrences=occ)
    built = BO.build([{"frame": f, "pdf_path": synthetic_pdf(tmp, n_pages), "stratum": "SYNTHETIC"}])
    return f, built, synthesize_adjudication(built.key)


def part_join(tmp: Path) -> dict:
    print("\n== M1-M5: the occurrence-level join, on a real oracle key ==")
    f, built, adjudicated = join_fixture(tmp, n_pages=2)
    scored = SM.score(inputs([f], key=built.key, adjudicated=adjudicated))
    frames_present = sorted(scored["headings_pooled"])
    pooled = scored["headings_pooled"][BO.C_FRAME]
    counts = pooled["counts"]
    check(
        "the join BINDS: every adjudicated heading matches an emitted occurrence in both arms",
        (2, 2, 2, 0),
        (
            counts["n_adjudicated"],
            counts["n_matched"]["H"],
            counts["n_matched"]["X"],
            counts["n_adjudicated_unresolvable"],
        ),
        "the two sides of the M1-M5 join do not meet, so every matched-heading denominator is zero",
    )
    check(
        "M1 recall and precision are reported with their own denominators",
        (1.0, 2, 1.0, 2),
        (
            pooled["M1"]["H"]["recall"]["value"],
            pooled["M1"]["H"]["recall"]["denominator"],
            pooled["M1"]["H"]["precision"]["value"],
            pooled["M1"]["H"]["precision"]["denominator"],
        ),
        "a rate is reported without the denominator it is a fraction of",
    )
    check(
        "only the frames the fixture actually populates are reported",
        [BO.C_FRAME],
        frames_present,
        "an unpopulated frame is reported with invented counts, or C and D were pooled",
    )

    # --- I10: recall's denominator is the ADJUDICATED enumeration, never the emitted one.
    fewer = copy.deepcopy(f)
    fewer["architecture_occurrences"]["H"] = fewer["architecture_occurrences"]["H"][:1]
    built2 = BO.build([{"frame": fewer, "pdf_path": synthetic_pdf(tmp, 2), "stratum": "SYNTHETIC"}])
    # the adjudication still enumerates BOTH printed headings -- it is built from X, which kept them
    adj2 = synthesize_adjudication(built2.key, truth="X")
    scored2 = SM.score(inputs([fewer], key=built2.key, adjudicated=adj2))
    p2 = scored2["headings_pooled"][BO.C_FRAME]
    check(
        "I10 -- an arm that emitted one of two printed headings scores recall 1/2, not 1/1",
        (1, 2, 0.5, 1, 1, 1.0),
        (
            p2["M1"]["H"]["recall"]["numerator"],
            p2["M1"]["H"]["recall"]["denominator"],
            p2["M1"]["H"]["recall"]["value"],
            p2["M1"]["H"]["precision"]["numerator"],
            p2["M1"]["H"]["precision"]["denominator"],
            p2["M1"]["H"]["precision"]["value"],
        ),
        "recall's denominator is the EMITTED enumeration, which makes an arm that dropped a "
        "heading look perfect -- the denominator shrinks with the failure it should expose",
    )
    check(
        "...and the WRONG denominator would have given a different number, so this is decisive",
        True,
        p2["M1"]["H"]["recall"]["value"] != p2["M1"]["H"]["precision"]["value"],
        "the two denominators coincide on this fixture, so I10 was never actually tested",
    )

    # --- NEGATIVE: wrong numerator. An emitted occurrence matching NOTHING must not be counted.
    extra = copy.deepcopy(f)
    extra["architecture_occurrences"]["H"] = list(extra["architecture_occurrences"]["H"]) + [
        occurrence(1, 4, 999, text="A HEADING NOBODY ADJUDICATED")
    ]
    built3 = BO.build([{"frame": extra, "pdf_path": synthetic_pdf(tmp, 2), "stratum": "SYNTHETIC"}])
    scored3 = SM.score(inputs([extra], key=built3.key, adjudicated=synthesize_adjudication(built3.key, truth="X")))
    p3 = scored3["headings_pooled"][BO.C_FRAME]
    check(
        "NEGATIVE -- an unmatchable EMITTED heading enlarges the precision denominator only",
        (2, 3, 2, 2),
        (
            p3["M1"]["H"]["recall"]["numerator"],
            p3["M1"]["H"]["precision"]["denominator"],
            p3["M1"]["H"]["precision"]["numerator"],
            p3["M1"]["H"]["recall"]["denominator"],
        ),
        "the numerator counts EMITTED rather than MATCHED headings, so emitting more raises the "
        "score -- a precision metric that rewards over-emission",
    )

    # --- NEGATIVE: a silent record drop. An UNMATCHED occurrence must stay in the denominator.
    unmatched = copy.deepcopy(f)
    unmatched["architecture_occurrences"]["H"] = list(unmatched["architecture_occurrences"]["H"]) + [
        occurrence(1, 5, 12, text="PRODUCTION EMITTED THIS", matchable=False)
    ]
    built4 = BO.build([{"frame": unmatched, "pdf_path": synthetic_pdf(tmp, 2), "stratum": "SYNTHETIC"}])
    scored4 = SM.score(inputs([unmatched], key=built4.key, adjudicated=synthesize_adjudication(built4.key, truth="X")))
    p4 = scored4["headings_pooled"][BO.C_FRAME]
    check(
        "NEGATIVE -- an A30-refused occurrence is KEPT in the precision denominator",
        3,
        p4["M1"]["H"]["precision"]["denominator"],
        "an UNMATCHED occurrence is dropped, shrinking a denominator invisibly -- the one failure "
        "mode A38.3 names explicitly",
    )
    return {
        "pooled_c_counts": counts,
        "i10": {"recall": p2["M1"]["H"]["recall"], "precision": p2["M1"]["H"]["precision"]},
        "n_stimuli": built.key["n_stimuli"],
    }


def part_m3(tmp: Path) -> dict:
    print("\n== section 5 rows: the M3 weld/space fixture and M3's insulation ==")

    # --- row: FAMILYHOUSING vs FAMILY HOUSING must reach M3 as X_CORRECTS.
    #
    # The two arms carry DIFFERENT text on the SAME occurrence key, which is exactly what A30.1
    # licenses: identity is the source position, never the text. x16 measured 30 such cases.
    occ = {
        "H": [occurrence(1, 2, 4, text="FAMILYHOUSING")],
        "X": [occurrence(1, 2, 4, text="FAMILY HOUSING")],
    }
    f, built, _adj = join_fixture(tmp, n_pages=1, occurrences=occ)
    adjudicated = synthesize_adjudication(built.key, truth="X")  # the oracle prints FAMILY HOUSING
    scored = SM.score(inputs([f], key=built.key, adjudicated=adjudicated))
    m3 = scored["headings_pooled"][BO.C_FRAME]["M3"]
    check(
        "the weld/space fixture reaches M3 as X_CORRECTS",
        (1, 0, 0),
        (
            m3["heading_outcomes"]["X_CORRECTS"],
            m3["heading_outcomes"]["X_REGRESSES"],
            m3["heading_outcomes"]["BOTH_CLEAN"],
        ),
        "`FAMILYHOUSING` against `FAMILY HOUSING` does not reach M3 as X_CORRECTS -- the primary "
        "comparative metric cannot see the failure class the seam choice governs",
        row="M3 weld/space fixture",
    )
    check(
        "the reported outcome vocabulary IS `m3_boundaries.HeadingOutcome`, complete",
        sorted(o.value for o in M3.HeadingOutcome),
        sorted(m3["heading_outcomes"]),
        "an outcome bucket is missing, so headings falling into it vanish from the tally the "
        "decision rule counts -- X_REGRESSES above all",
        row="M3 weld/space fixture",
    )
    check(
        "...and the weld is charged to H at the BOUNDARY level, not as a character error",
        (1, 0, 0, 0),
        (
            m3["boundary_outcomes"]["H"]["WELD"],
            m3["boundary_outcomes"]["H"]["SPLIT"],
            m3["boundary_outcomes"]["H"]["TEXT_ERROR"],
            m3["boundary_outcomes"]["X"]["WELD"],
        ),
        "a spacing defect is scored as a character defect (or vice versa), which is the "
        "conflation section 6.3 exists to prevent",
        row="M3 weld/space fixture",
    )
    check(
        "...and M2 sees the weld as inexact while X reads exactly",
        (0.0, 1.0),
        (
            scored["headings_pooled"][BO.C_FRAME]["M2"]["H"]["value"],
            scored["headings_pooled"][BO.C_FRAME]["M2"]["X"]["value"],
        ),
        "M2 cannot separate a welded heading from a correct one under the frozen normalisation",
    )

    # --- row: M3 insulation. A SEGMENTATION-only difference must fabricate no weld or split.
    same_text = {arm: [occurrence(1, 2, 4, text="SALARIES AND EXPENSES")] for arm in ("H", "X")}
    seg_f, seg_built, _ = join_fixture(tmp, n_pages=1, occurrences=same_text, page_kwargs={1: {"merge": {2}}})
    seg_scored = SM.score(inputs([seg_f], key=seg_built.key, adjudicated=synthesize_adjudication(seg_built.key)))
    seg_m3 = seg_scored["headings_pooled"][BO.C_FRAME]["M3"]
    seg_m0 = seg_scored["per_document"]["SYNTHETIC/1"]["M0"]
    check(
        "the insulation fixture really IS segmentation-discordant, so the control is not vacuous",
        (2, 0, True),
        (
            seg_m0["M0b_segmentation"],
            seg_m0["M0a_text"],
            seg_f["pages"][0]["regions"][0]["d_frame"],
        ),
        "the fixture carries no segmentation difference, so 'M3 ignored it' proves nothing",
        row="M3 insulation",
    )
    check(
        "M3 fabricates NO weld or split from a segmentation-only difference",
        (0, 0, 0, 0, 1),
        (
            seg_m3["boundary_outcomes"]["H"]["WELD"],
            seg_m3["boundary_outcomes"]["H"]["SPLIT"],
            seg_m3["boundary_outcomes"]["X"]["WELD"],
            seg_m3["boundary_outcomes"]["X"]["SPLIT"],
            seg_m3["heading_outcomes"]["BOTH_CLEAN"],
        ),
        "a split-only difference fabricates a weld/split against a clean oracle, so the primary "
        "comparative metric would report a boundary defect that was never printed",
        row="M3 insulation",
    )

    # --- NEGATIVE: architecture segmentation substituted for oracle/text truth. Flipping which
    # lines the arms GROUP together, with every text unchanged, must not move M3 at all.
    plain_f, plain_built, _ = join_fixture(tmp, n_pages=1, occurrences=same_text)
    plain_m3 = SM.score(inputs([plain_f], key=plain_built.key, adjudicated=synthesize_adjudication(plain_built.key)))[
        "headings_pooled"
    ][BO.C_FRAME]["M3"]
    check(
        "NEGATIVE -- M3 is INVARIANT to the segmentation labels, text held identical",
        plain_m3,
        seg_m3,
        "M3 reads a segmentation label as truth, which section 5 forbids: it consumes projected "
        "text plus the oracle and nothing else",
        row="M3 insulation",
    )
    check(
        "...and the fixtures really do differ in segmentation, so the invariance is not vacuous",
        (0, 2),
        (
            SM.m0_block(plain_f)["M0b_segmentation"],
            SM.m0_block(seg_f)["M0b_segmentation"],
        ),
        "the two fixtures have identical segmentation, so 'M3 did not move' was guaranteed",
        row="M3 insulation",
    )

    # --- a severe corruption must count AGAINST an arm, never become an exclusion (A9).
    garbage = {
        "H": [occurrence(1, 2, 4, text="SALARIES AND EXPENSES")],
        "X": [occurrence(1, 2, 4, text="###")],
    }
    g_f, g_built, _ = join_fixture(tmp, n_pages=1, occurrences=garbage)
    g_m3 = SM.score(inputs([g_f], key=g_built.key, adjudicated=synthesize_adjudication(g_built.key, truth="H")))[
        "headings_pooled"
    ][BO.C_FRAME]["M3"]
    check(
        "severe corruption in one arm is X_REGRESSES, never UNSCORABLE",
        (1, 0, 1, 1),
        (
            g_m3["heading_outcomes"]["X_REGRESSES"],
            g_m3["heading_outcomes"]["UNSCORABLE"],
            g_m3["clean_rate"]["H"]["numerator"],
            g_m3["clean_rate"]["X"]["denominator"],
        ),
        "an arm's worst failures leave the denominator, which removes exactly the distinguishing "
        "cases -- the defect A9 withdrew UNALIGNABLE for",
    )
    return {
        "weld": m3["heading_outcomes"],
        "insulated": seg_m3["boundary_outcomes"],
        "garbage": g_m3["heading_outcomes"],
    }


def part_m4(tmp: Path) -> dict:
    print("\n== section 5 rows: the two M4 negatives ==")

    # One agency and three accounts beneath it, all keyed and all correct.
    def census(parent_of):
        rows = [occurrence(1, 1, 2, kind="agency", text="DEPARTMENTAL MANAGEMENT", parent=None)]
        for i, ordinal in enumerate((2, 3, 4)):
            rows.append(
                occurrence(
                    1,
                    ordinal,
                    ordinal * 2,
                    kind="account",
                    text=f"ACCOUNT {i}",
                    parent=parent_of(i),
                )
            )
        return rows

    base_occ = {arm: census(lambda i: "DEPARTMENTAL MANAGEMENT") for arm in ("H", "X")}
    f, built, _ = join_fixture(tmp, n_pages=1, occurrences=base_occ)
    adjudicated = synthesize_adjudication(built.key, truth="H", role="account")
    base = SM.score(inputs([f], key=built.key, adjudicated=adjudicated))["headings_pooled"][BO.C_FRAME]
    check(
        "the M4 baseline is perfect, so any fall below is caused by the injection",
        (1.0, 1.0, 4, 4),
        (
            base["M4"]["H"]["value"],
            base["M1"]["H"]["recall"]["value"],
            base["M4"]["H"]["denominator"],
            base["M1"]["H"]["recall"]["denominator"],
        ),
        "the baseline is already imperfect, so a 'fall' cannot be attributed to the injection",
    )

    # --- row: DELETE AGENCY ANCHORS. M4 must fall FURTHER than M1.
    #
    # Deleting the agency occurrence is what production does to the breadcrumb: the children's
    # penultimate element is gone, so their emitted immediate parent is None.
    deleted = copy.deepcopy(f)
    deleted["architecture_occurrences"]["H"] = [
        {**r, "immediate_parent": None, "breadcrumb": [r["anchor"]["text"]]}
        for r in deleted["architecture_occurrences"]["H"]
        if r["anchor"]["kind"] != "agency"
    ]
    d_built = BO.build([{"frame": deleted, "pdf_path": synthetic_pdf(tmp, 1), "stratum": "SYNTHETIC"}])
    # the ORACLE still sees all four printed headings, so it is built from the untouched arm
    d_adj = synthesize_adjudication(d_built.key, truth="X", role="account")
    after = SM.score(inputs([deleted], key=d_built.key, adjudicated=d_adj))["headings_pooled"][BO.C_FRAME]
    m1_drop = base["M1"]["H"]["recall"]["value"] - after["M1"]["H"]["recall"]["value"]
    m4_drop = base["M4"]["H"]["value"] - after["M4"]["H"]["value"]
    check(
        "deleting the agency anchors makes M4 fall FURTHER than M1",
        (0.25, 1.0, True),
        (m1_drop, m4_drop, m4_drop > m1_drop),
        "M4 does not fall further than M1, so the hierarchy metric adds nothing over presence -- "
        "it would be reporting the labels again rather than the tree",
        row="negative: delete agency anchors",
    )

    # --- row: SHIFT HEADING BASELINES ONE LINE-HEIGHT. M4 must fall.
    #
    # At the scorer's layer a one-line-height shift shows up as each heading inheriting the
    # NEIGHBOURING heading's parent: identity is unchanged (the shift is geometric, and A30
    # identity is a source position), so M1 must hold still while M4 moves. The upstream
    # geometric shift itself is `build_frames`' concern and `x17` owns it.
    shifted = copy.deepcopy(f)
    shifted["architecture_occurrences"]["H"] = [
        {**r, "immediate_parent": "SOME OTHER AGENCY" if r["anchor"]["kind"] == "account" else r["immediate_parent"]}
        for r in shifted["architecture_occurrences"]["H"]
    ]
    s_built = BO.build([{"frame": shifted, "pdf_path": synthetic_pdf(tmp, 1), "stratum": "SYNTHETIC"}])
    s_adj = synthesize_adjudication(s_built.key, truth="X", role="account")
    s_after = SM.score(inputs([shifted], key=s_built.key, adjudicated=s_adj))["headings_pooled"][BO.C_FRAME]
    check(
        "a one-line parent shift makes M4 fall while M1 holds still",
        (0.25, 1.0, 4),
        (
            s_after["M4"]["H"]["value"],
            s_after["M1"]["H"]["recall"]["value"],
            s_after["M4"]["H"]["denominator"],
        ),
        "M4 does not fall, so a hierarchy that points at the wrong parent scores as correct",
        row="negative: shift heading baselines one line-height",
    )

    # --- NEGATIVE: full ancestry substituted for the immediate parent.
    #
    # The emitted breadcrumb CONTAINS the adjudicated parent for a grandchild whose immediate
    # parent is wrong. A scorer matching against ancestry would call that correct.
    ancestry = copy.deepcopy(f)
    ancestry["architecture_occurrences"]["H"] = [
        {
            **r,
            "immediate_parent": "AN INTERMEDIATE GROUPING"
            if r["anchor"]["kind"] == "account"
            else r["immediate_parent"],
            "breadcrumb": ["DEPARTMENTAL MANAGEMENT", "AN INTERMEDIATE GROUPING", r["anchor"]["text"]],
        }
        for r in ancestry["architecture_occurrences"]["H"]
    ]
    a_built = BO.build([{"frame": ancestry, "pdf_path": synthetic_pdf(tmp, 1), "stratum": "SYNTHETIC"}])
    a_adj = synthesize_adjudication(a_built.key, truth="X", role="account")
    a_after = SM.score(inputs([ancestry], key=a_built.key, adjudicated=a_adj))["headings_pooled"][BO.C_FRAME]
    check(
        "NEGATIVE -- an ancestor that is not the IMMEDIATE parent scores as wrong",
        0.25,
        a_after["M4"]["H"]["value"],
        "M4 scored full ancestry, so a heading filed one level off its true parent counts as "
        "correct as long as the right agency appears somewhere above it",
    )
    check(
        "...and the adjudicated parent really IS in the emitted breadcrumb, so the trap is live",
        True,
        "DEPARTMENTAL MANAGEMENT" in ancestry["architecture_occurrences"]["H"][1]["breadcrumb"],
        "the fixture does not contain the ancestry trap, so the control could not have caught it",
    )
    _part_m4_sentinels(tmp)
    pairing = _part_m4_pairing(tmp)
    return {
        "pairing": pairing,
        "baseline_m4": base["M4"]["H"],
        "after_delete": after["M4"]["H"],
        "m1_drop": m1_drop,
        "m4_drop": m4_drop,
        "shifted_m4": s_after["M4"]["H"],
        "ancestry_m4": a_after["M4"]["H"],
    }


def _m4_pairing_census(bad_account: str) -> list:
    """One agency and three accounts, with ONE named account given the wrong immediate parent."""
    rows = [occurrence(1, 1, 2, kind="agency", text="DEPARTMENTAL MANAGEMENT", parent=None)]
    for i, ordinal in enumerate((2, 3, 4)):
        text = f"ACCOUNT {i}"
        rows.append(
            occurrence(
                1,
                ordinal,
                ordinal * 2,
                kind="account",
                text=text,
                parent="SOME OTHER AGENCY" if text == bad_account else "DEPARTMENTAL MANAGEMENT",
            )
        )
    return rows


def _m4_pairing_oracle(built) -> dict:
    """The adjudication for the pairing fixture, carrying the TRUE printed parents.

    Neither arm is clean in this fixture -- each is wrong on a different account -- so the oracle
    cannot be synthesized from one arm's output the way the other M4 controls do it. The structure
    (identities, start annotations, routes) still comes from the REAL key; only the `parent` field
    is stated, which is the one field this control is about.
    """
    adjudicated = synthesize_adjudication(built.key, truth="H", role="account")
    for route in (BO.ROUTE_AI, BO.ROUTE_HUMAN):
        for answer in adjudicated[route].values():
            for heading in answer["headings"]:
                heading["parent"] = (
                    SM.ORACLE_PARENT_NONE if heading["text"] == "DEPARTMENTAL MANAGEMENT" else "DEPARTMENTAL MANAGEMENT"
                )
    return adjudicated


def _part_m4_pairing(tmp: Path) -> dict:
    """A5 row 4's PAIRED quantity, on the one fixture shape that separates it from the aggregates.

    THE FIXTURE IS THE ARGUMENT. H is wrong on `ACCOUNT 0` and X is wrong on `ACCOUNT 1`, so:

        m4_correct    H 3 / 4   X 3 / 4      -- EQUAL on both arms, and the RATES are equal too
        the pairing   ACCOUNT 1 is correct under H and WRONG under X -- Rule 1's condition 4 is
                      violated, and NOTHING in the aggregates can see it

    This is the payload A42.3 states as the one on which the two readings of A5 row 4 give
    different architectures. The ruling took the per-heading existential, so the scorer must emit
    the pair; this control is what stops that being quietly re-derived from `m4_correct` later.
    """
    print("\n== A5 row 4: the PAIRED M4 quantity, where the aggregates are blind ==")
    occ = {"H": _m4_pairing_census("ACCOUNT 0"), "X": _m4_pairing_census("ACCOUNT 1")}
    f, built, _ = join_fixture(tmp, n_pages=1, occurrences=occ)
    pooled = SM.score(inputs([f], key=built.key, adjudicated=_m4_pairing_oracle(built)))["headings_pooled"][BO.C_FRAME]
    counts, m4 = pooled["counts"], pooled["M4"]

    check(
        "the per-arm M4 aggregates are EQUAL -- so they cannot express the condition",
        (3, 3, 4, 4, True),
        (
            counts["m4_correct"]["H"],
            counts["m4_correct"]["X"],
            counts["m4_scored"]["H"],
            counts["m4_scored"]["X"],
            m4["H"]["value"] == m4["X"]["value"],
        ),
        "the fixture does not actually produce equal aggregates, so it does not separate the two "
        "readings and this whole control proves nothing",
    )
    check(
        "...while the PAIRED fact sees the violation, and names the heading it fired on",
        (1, 1, [6]),
        (
            counts["m4_h_correct_x_wrong"],
            counts["m4_x_correct_h_wrong"],
            [k[3] for k in counts["m4_h_correct_x_wrong_keys"]],
        ),
        "A5 row 4's per-heading existential was collapsed into a count comparison, which is the "
        "reading A42.3 rejected -- an X that breaks one hierarchy H had right would win Rule 1 as "
        "long as it repaired a different one",
    )
    check(
        "the paired fact is surfaced on the reported M4 block, where the decider reads it",
        (1, 1),
        (m4["h_correct_x_wrong"], m4["x_correct_h_wrong"]),
        "the quantity exists only in raw counts, so the decider would have to reach past the "
        "reported metric to find it",
    )

    # NEAR-MISS: equal aggregates again, but NO opposite pairing. If the paired fact were secretly
    # a function of the aggregates, this would report 1 as well.
    clean = {arm: _m4_pairing_census("ACCOUNT 0") for arm in ("H", "X")}
    cf, cbuilt, _ = join_fixture(tmp, n_pages=1, occurrences=clean)
    clean_pooled = SM.score(inputs([cf], key=cbuilt.key, adjudicated=_m4_pairing_oracle(cbuilt)))["headings_pooled"][
        BO.C_FRAME
    ]
    check(
        "NEAR-MISS -- both arms wrong on the SAME account: aggregates equal, pairing ZERO",
        (3, 3, 0, 0),
        (
            clean_pooled["counts"]["m4_correct"]["H"],
            clean_pooled["counts"]["m4_correct"]["X"],
            clean_pooled["counts"]["m4_h_correct_x_wrong"],
            clean_pooled["counts"]["m4_x_correct_h_wrong"],
        ),
        "the paired fact fires whenever an arm is wrong anywhere, so it is a restatement of the "
        "aggregates rather than the per-heading comparison Rule 1 needs",
    )
    return {
        "opposite_pairing": {k: counts[k] for k in ("m4_correct", "m4_scored", "m4_h_correct_x_wrong")},
        "near_miss": clean_pooled["counts"]["m4_h_correct_x_wrong"],
    }


def _part_m4_sentinels(tmp: Path) -> dict:
    """The adjudicator's ACTUAL parent representation: literal `NONE` and `OFF_REGION`.

    The reviewer's finding. Every M4 fixture above supplies a Python `None` for a root heading,
    which is not a value `adjudicator_prompt.md` can produce -- so M4 was green without ever
    seeing the encoding the real oracle will hand it. These controls go through the same
    `SM.score` path with the literal strings.
    """
    print("\n== M4: the frozen `NONE` / `OFF_REGION` parent sentinels (section 5.3) ==")
    # A root heading (emitted parent None) and a child (emitted parent = the root's text).
    occ = {
        arm: [
            occurrence(1, 2, 4, kind="agency", text="DEPARTMENTAL MANAGEMENT", parent=None),
            occurrence(1, 3, 6, kind="account", text="SALARIES AND EXPENSES", parent="DEPARTMENTAL MANAGEMENT"),
        ]
        for arm in ("H", "X")
    }
    f, built, _ = join_fixture(tmp, n_pages=1, occurrences=occ)
    record = next(r for r in built.key["stimuli"].values() if not r["is_r1_repeat"])
    rows = record["architecture_occurrences"]["H"]
    root, child = rows[0], rows[1]

    def answer(parent_of_root: str, parent_of_child: str) -> dict:
        headings = [
            {
                "text": root["anchor"]["text"],
                "role": "agency",
                "parent": parent_of_root,
                **start_annotation(record, root),
            },
            {
                "text": child["anchor"]["text"],
                "role": "account",
                "parent": parent_of_child,
                **start_annotation(record, child),
            },
        ]
        out = {"schema": BO.ADJUDICATED_SCHEMA, BO.ROUTE_AI: {}, BO.ROUTE_HUMAN: {}}
        for bid, rec in built.key["stimuli"].items():
            for route in rec["adjudication_routes"]:
                out[route][bid] = {"id": bid, "headings": headings}
        return out

    def m4_of(adjudicated):
        return SM.score(inputs([f], key=built.key, adjudicated=adjudicated))["headings_pooled"][BO.C_FRAME]["M4"]

    # --- POSITIVE: literal "NONE" scores correctly against an emitted `immediate_parent is None`.
    good = m4_of(answer(SM.ORACLE_PARENT_NONE, "DEPARTMENTAL MANAGEMENT"))
    check(
        'literal "NONE" against an emitted None scores CORRECT, and the child scores too',
        (2, 2, 1.0, 0, 0),
        (
            good["H"]["numerator"],
            good["H"]["denominator"],
            good["H"]["value"],
            good["excluded_off_region"],
            good["excluded_unreadable"],
        ),
        'the scorer compares "NONE" as ordinary parent TEXT, so a correct root heading scores '
        "WRONG -- M4 penalises an architecture for having no parent to name",
    )

    # --- NEGATIVE: "NONE" claimed where the arm DID emit a parent must be wrong.
    wrong = m4_of(answer(SM.ORACLE_PARENT_NONE, SM.ORACLE_PARENT_NONE))
    check(
        'NEGATIVE -- "NONE" against an emitted parent is WRONG, so the sentinel is not a wildcard',
        (1, 2, 0.5),
        (wrong["H"]["numerator"], wrong["H"]["denominator"], wrong["H"]["value"]),
        '"NONE" matches whatever the arm emitted, so a hierarchy claim can never be contradicted',
    )

    # --- OFF_REGION leaves the population entirely; it is never compared as text.
    off = m4_of(answer(SM.ORACLE_PARENT_NONE, SM.ORACLE_PARENT_OFF_REGION))
    check(
        '"OFF_REGION" LEAVES M4\'s population and is counted, never scored as text',
        (1, 1, 1.0, 1),
        (off["H"]["numerator"], off["H"]["denominator"], off["H"]["value"], off["excluded_off_region"]),
        '"OFF_REGION" is compared as literal parent text, which can never equal any emitted '
        "parent -- so every off-region answer counts against an architecture for a limit of the "
        "ORACLE's field of view",
    )
    check(
        "...and the frozen answer vocabulary is stated in the artifact",
        f"printed text | NONE | OFF_REGION | {BO.UNREADABLE}",
        off["parent_answers"],
        "the artifact does not record which parent answers were recognised, so a reader cannot "
        "tell a scored population from an excluded one",
    )

    # --- a JSON null is not one of the four answers and REFUSES.
    check(
        "NEGATIVE -- a null parent REFUSES rather than being read as 'no parent'",
        SM.PARENT_MISSING,
        refusal(lambda: SM.score(inputs([f], key=built.key, adjudicated=answer(None, "DEPARTMENTAL MANAGEMENT")))),
        "a null is silently read as NONE, which is the representation gap that let the old M4 "
        "fixtures pass without ever producing the adjudicator's own encoding",
    )
    check(
        "UNREADABLE stays excluded, as already frozen",
        (1, 1, 1),
        (
            m4_of(answer(SM.ORACLE_PARENT_NONE, BO.UNREADABLE))["H"]["denominator"],
            m4_of(answer(SM.ORACLE_PARENT_NONE, BO.UNREADABLE))["excluded_unreadable"],
            m4_of(answer(SM.ORACLE_PARENT_NONE, BO.UNREADABLE))["H"]["numerator"],
        ),
        "an UNREADABLE parent entered or left the denominator differently than before",
    )
    return {"none_scored": good["H"], "off_region": off, "vocabulary": off["parent_answers"]}


def part_m5(tmp: Path) -> dict:
    print("\n== M5: the frozen role map, and UNSCORABLE out of the denominator ==")
    occ = {
        arm: [
            occurrence(1, 2, 4, kind="account", text="ACCOUNT A"),
            occurrence(1, 3, 6, kind="subsection", text="SUBSECTION B"),
        ]
        for arm in ("H", "X")
    }
    f, built, _ = join_fixture(tmp, n_pages=1, occurrences=occ)
    adjudicated = synthesize_adjudication(built.key, truth="H", role="account")
    pooled = SM.score(inputs([f], key=built.key, adjudicated=adjudicated))["headings_pooled"][BO.C_FRAME]
    check(
        "an UNSCORABLE pair leaves the M5 DENOMINATOR and is reported as a raw exclusion",
        (1, 1, 1.0, 1),
        (
            pooled["M5"]["H"]["agreement"]["numerator"],
            pooled["M5"]["H"]["agreement"]["denominator"],
            pooled["M5"]["H"]["agreement"]["value"],
            pooled["M5"]["H"]["excluded_unscorable"],
        ),
        "an UNSCORABLE pair is counted as a disagreement, penalising an architecture for a role "
        "M5 was never licensed to score",
    )

    # --- NEGATIVE: change UNSCORABLE to scored. The exclusion must be driven by the frozen map.
    promoted = copy.deepcopy(f)
    promoted["architecture_occurrences"]["H"] = [
        {**r, "anchor": {**r["anchor"], "kind": "account"}} for r in promoted["architecture_occurrences"]["H"]
    ]
    p_built = BO.build([{"frame": promoted, "pdf_path": synthetic_pdf(tmp, 1), "stratum": "SYNTHETIC"}])
    p_adj = synthesize_adjudication(p_built.key, truth="H", role="account")
    p_pooled = SM.score(inputs([promoted], key=p_built.key, adjudicated=p_adj))["headings_pooled"][BO.C_FRAME]
    check(
        "NEGATIVE -- making the UNSCORABLE kind scorable MOVES the denominator",
        (2, 0),
        (p_pooled["M5"]["H"]["agreement"]["denominator"], p_pooled["M5"]["H"]["excluded_unscorable"]),
        "the denominator does not respond to the frozen A36.7 map, so the exclusion is decoration",
    )

    # --- a role outside the frozen map must REFUSE, never become a silent UNSCORABLE.
    bad_role = synthesize_adjudication(built.key, truth="H", role="a role nobody froze")
    check(
        "NEGATIVE -- an unmapped oracle role REFUSES (A36.7)",
        "UnknownRole",
        refusal(lambda: SM.score(inputs([f], key=built.key, adjudicated=bad_role))),
        "an unknown role maps to UNSCORABLE and quietly SHRINKS the M5 denominator, which reads "
        "as a cleaner result rather than as a defect",
    )
    check(
        "with no R1 pair in the key, the M5 gate is NOT EVALUABLE and is not a pass",
        (SM.R1_NOT_EVALUABLE, False, True),
        (
            pooled["M5"]["r1_role_gate"]["status"],
            pooled["M5"]["r1_role_gate"]["m5_void"],
            "computed" in pooled["M5"]["r1_role_gate"]["evidence"],
        ),
        "M5 is reported as though its section 6 gate had been checked when no R1 pair exists -- "
        "green because nothing measured it",
    )
    check(
        "NO caller channel exists that could hand the gate a verdict",
        (False, False),
        (
            "r1_role_agreement" in {fld.name for fld in dataclasses.fields(SM.ScoreInputs)},
            "r1_role_agreement" in inspect.signature(SM.score).parameters,
        ),
        "a free scalar can still reach a result-bearing reliability gate, so a PASS can be "
        "asserted with no evidence behind it and nothing downstream could tell",
    )
    return {"m5": pooled["M5"]["H"], "promoted_denominator": p_pooled["M5"]["H"]["agreement"]["denominator"]}


def part_r1(tmp: Path) -> dict:
    """Section 5.6's R1 reliability, computed from committed artifacts under the A41.2 R6 ruling.

    R6 is RULED, so this part pins the ruled computation rather than exhibiting a choice: the
    symmetric-union denominator under one-to-one identity matching, exact text equality, the fine
    role, the per-route micro-average, and the worst-route gate. It also enforces A36.6 -- the
    required routes come from FRAME MEMBERSHIP, never from the repeat's own declaration -- and
    proves no caller scalar can reach the gate.
    """
    print("\n== section 5.6 R1: the ruled computation (A41.2 R6) and A36.6 route inheritance ==")
    # 12 discordant pages so the D census gives 12 primaries and plan_r1_repeats draws exactly one.
    pages = [page_input(p + 1, start_gid=p * 100, text_differs={5}) for p in range(12)]
    # THREE headings per region, so the unequal-enumeration fixture below can drop one from the repeat's
    # answer and still leave two agreeing -- the exact shape on which the candidate denominators
    # disagree. One heading per region could not exhibit it at all.
    occ = {
        arm: [
            occurrence(p + 1, ordinal, p * 100 + ordinal * 2, text=f"ACCOUNT P{p + 1} N{ordinal}")
            for p in range(12)
            for ordinal in (1, 2, 3)
        ]
        for arm in ("H", "X")
    }
    f = frame(pages, occurrences=occ)
    built = BO.build([{"frame": f, "pdf_path": synthetic_pdf(tmp, 12), "stratum": "SYNTHETIC"}])
    repeat_bid, repeat = next((b, r) for b, r in built.key["stimuli"].items() if r["is_r1_repeat"])
    primary_bid = next(
        b
        for b, r in built.key["stimuli"].items()
        if not r["is_r1_repeat"] and r["base_identity"] == repeat["r1_base_identity"]
    )
    check(
        "the fixture really carries an R1 pair, so nothing below is vacuous",
        (True, True),
        (repeat["is_r1_repeat"], primary_bid != repeat_bid),
        "no repeat exists, so every R1 figure below was computed on an empty population",
    )

    # --- an IDENTICAL repeat answer: perfect agreement, and every denominator agrees, so there is
    # nothing to rule on and the gate is decided.
    identical = synthesize_adjudication(built.key)
    agree = SM.r1_reliability(built.key, identical)
    # TWO pairs, not one: every region here is discordant, so the repeated region is in C AND D,
    # and A36.6 gives the repeat both inherited routes -- one pair per route, never pooled.
    check(
        "an identical repeat gives PASS on both dimensions, with all four denominators agreeing",
        ("PASS", "PASS", 2, [BO.ROUTE_AI, BO.ROUTE_HUMAN]),
        (agree["text"]["status"], agree["role"]["status"], agree["n_pairs"], sorted(agree["per_route"])),
        "a perfectly self-consistent adjudicator does not reach PASS, so the reliability gate "
        "cannot be satisfied by any real adjudication",
    )
    # --- PER ROUTE, proven BEHAVIOURALLY. The first version of this control asserted the
    # `pooled_across_routes: False` label and the route key names, and the injection sweep caught
    # it: pooling the rows left both untouched, so the control could not fail. A route-asymmetric
    # fixture is the only thing that can tell the two implementations apart -- only the HUMAN
    # repeat disagrees, so per-route gives {ai: 1.0, human: 0.0} and pooling gives {ai: 0.5,
    # human: 0.5}.
    human_only = copy.deepcopy(identical)
    for heading in human_only[BO.ROUTE_HUMAN][repeat_bid]["headings"]:
        heading["text"] = "ONLY THE HUMAN REPEAT DISAGREES"
    asymmetric = SM.r1_reliability(built.key, human_only)
    ai_ratio = asymmetric["per_route"][BO.ROUTE_AI]["text"]["ratio"]
    human_ratio = asymmetric["per_route"][BO.ROUTE_HUMAN]["text"]["ratio"]
    check(
        "R1 is computed PER ROUTE: a human-only disagreement leaves the AI route untouched",
        ("PASS", "FAIL", 1.0, 0.0, False),
        (
            asymmetric["per_route"][BO.ROUTE_AI]["text"]["status"],
            asymmetric["per_route"][BO.ROUTE_HUMAN]["text"]["status"],
            ai_ratio,
            human_ratio,
            asymmetric["pooled_across_routes"],
        ),
        "AI and human pairs are pooled, so one route's disagreement is averaged into the other -- "
        "which measures inter-source disagreement rather than the repeat reliability section 5.6 "
        "asks for, and can hide a failing route behind a passing one",
    )
    check(
        "...and the overall gate takes the WORST route, so a passing route cannot mask a failure",
        ("FAIL", True),
        (asymmetric["text"]["status"], ai_ratio != human_ratio),
        "the overall verdict is an average or the best route, so a route that failed its "
        "reliability gate does not reach Rule 3",
    )

    # --- a DISAGREEING repeat: the same heading, different text and role. Both gates must move.
    disagreeing = copy.deepcopy(identical)
    for route in (BO.ROUTE_AI, BO.ROUTE_HUMAN):
        if repeat_bid in disagreeing.get(route, {}):
            for heading in disagreeing[route][repeat_bid]["headings"]:
                heading["text"] = "A COMPLETELY DIFFERENT HEADING"
                heading["role"] = "grouping"
    disagree = SM.r1_reliability(built.key, disagreeing)
    check(
        "NEGATIVE -- a repeat that answers differently drives BOTH gates to FAIL",
        ("FAIL", "FAIL"),
        (disagree["text"]["status"], disagree["role"]["status"]),
        "an adjudicator that contradicts itself on a re-presented stimulus still passes, which is "
        "exactly the phase-1 defect R1 exists to catch (six identical stimuli, 3 BOUNDARY / 3 NOT)",
    )
    # --- THE FINE ROLE, proven with a fixture that DISCRIMINATES. The first version reused the
    # `grouping` fixture above, whose role differs under the coarsening TOO (account -> LEAF vs
    # grouping -> CONTAINER), so a coarsening implementation failed it identically and the control
    # could not fail. `account` and `section` are different fine roles that BOTH coarsen to LEAF,
    # which is the only shape that separates the two readings.
    same_coarse = copy.deepcopy(identical)
    for route in (BO.ROUTE_AI, BO.ROUTE_HUMAN):
        for heading in same_coarse[route][repeat_bid]["headings"]:
            heading["role"] = "section"
    coarse_blind = SM.r1_reliability(built.key, same_coarse)
    check(
        "the role comparison uses the FINE section 5.3 role: account vs section is a DISAGREEMENT",
        ("FAIL", "PASS", MC.M5_LEAF, MC.M5_LEAF),
        (
            coarse_blind["role"]["status"],
            coarse_blind["text"]["status"],
            MC.m5_oracle_role("account"),
            MC.m5_oracle_role("section"),
        ),
        "R1 coarsens the role before comparing, so two DIFFERENT fine roles that collapse to the "
        "same M5 class read as agreement -- A36.7 says M5 ALONE coarsens, and an adjudicator "
        "flipping account/section would look perfectly reliable",
    )
    check(
        "...and the coarse-blind fixture leaves TEXT agreement untouched, so only the role moved",
        (1.0, "PASS"),
        (
            coarse_blind["per_route"][BO.ROUTE_AI]["text"]["ratio"],
            coarse_blind["per_route"][BO.ROUTE_AI]["text"]["status"],
        ),
        "the fixture perturbed the text as well, so a role-only claim cannot be attributed to the role comparison",
    )

    # ================= R6.1 the SYMMETRIC UNION denominator, under one-to-one identity matching
    # The fixture that used to exhibit the ambiguity is now the fixture that pins the RULED
    # answer: 3 primary headings, 2 repeat, both shared agreeing -> 2/3, which FAILS 0.90.
    fewer = copy.deepcopy(identical)
    for route in (BO.ROUTE_AI, BO.ROUTE_HUMAN):
        fewer[route][repeat_bid]["headings"] = fewer[route][repeat_bid]["headings"][:2]
    one_sided = SM.r1_reliability(built.key, fewer)
    pair = one_sided["pairs"][0]
    check(
        "R6.1 -- a heading present on ONE side stays in the denominator and earns no numerator",
        (3, 2, 2, 2, 3, 2 / 3, "FAIL"),
        (
            pair["n_primary_headings"],
            pair["n_repeat_headings"],
            pair["n_matched_pairs"],
            pair["n_text_agree"],
            pair["denominator"],
            one_sided["per_route"][pair["route"]]["text"]["ratio"],
            one_sided["text"]["status"],
        ),
        "the denominator is the INTERSECTION, so an adjudicator who silently drops a heading scores "
        "perfectly reliable -- the enumeration instability section 5.6 exists to detect",
    )

    # --- NEGATIVE 1: an UNRESOLVED repeat heading cannot disappear from the denominator. Induced
    # through the REAL resolver by removing one line's identity candidates from the repeat's key
    # record, so `resolve_adjudicated_occurrence` refuses with MISSING_IDENTITY_CANDIDATES.
    def strip_candidates(bids):
        mutated = copy.deepcopy(built.key)
        for target in bids:
            line = mutated["stimuli"][target]["region_line_bijection"][2]
            mutated["stimuli"][target]["identity_candidates"].pop(f"{line[0]}:{line[1]}", None)
        return mutated

    repeat_unresolved = SM.r1_reliability(strip_candidates([repeat_bid]), identical)
    u_pair = repeat_unresolved["pairs"][0]
    check(
        "R6.1 NEGATIVE -- one UNRESOLVED repeat heading stays in the denominator, agreement falls",
        (3, 3, 1, 2, 2, 4, 0.5),
        (
            u_pair["n_primary_headings"],
            u_pair["n_repeat_headings"],
            u_pair["n_repeat_unresolved"],
            u_pair["n_matched_pairs"],
            u_pair["n_text_agree"],
            u_pair["denominator"],
            repeat_unresolved["per_route"][u_pair["route"]]["text"]["ratio"],
        ),
        "an unresolved heading vanishes from the denominator, so a geometric refusal quietly "
        "IMPROVES the measured reliability of the adjudicator that produced it",
    )

    # --- NEGATIVE 2: BOTH sides unresolved must not become vacuous or perfect.
    both_unresolved = SM.r1_reliability(strip_candidates([primary_bid, repeat_bid]), identical)
    b_pair = both_unresolved["pairs"][0]
    check(
        "R6.1 NEGATIVE -- BOTH sides unresolved is denominator-bearing, never vacuous or perfect",
        (1, 1, 2, 2, 4, 0.5, "FAIL"),
        (
            b_pair["n_primary_unresolved"],
            b_pair["n_repeat_unresolved"],
            b_pair["n_matched_pairs"],
            b_pair["n_text_agree"],
            b_pair["denominator"],
            both_unresolved["per_route"][b_pair["route"]]["text"]["ratio"],
            both_unresolved["text"]["status"],
        ),
        "two unresolved headings cancel into a vacuous or perfect result, so an adjudication the "
        "join could not read at all would satisfy the reliability gate",
    )

    # --- NEGATIVE 3: a DUPLICATED resolved key must not be collapsed into a perfect match. Two
    # repeat headings are given the SAME (line, x), so both resolve to one identity.
    duplicated = copy.deepcopy(identical)
    for route in (BO.ROUTE_AI, BO.ROUTE_HUMAN):
        rows = duplicated[route][repeat_bid]["headings"]
        rows[1]["start_physical_line"] = rows[0]["start_physical_line"]
        rows[1]["start_x_px"] = rows[0]["start_x_px"]
        rows[1]["text"] = rows[0]["text"]
    dup = SM.r1_reliability(built.key, duplicated)
    d_pair = dup["pairs"][0]
    check(
        "R6.1 NEGATIVE -- a duplicated occurrence key is NOT pairable and cannot be overwritten",
        (2, 3, 3, 1, 5, "FAIL"),
        (
            d_pair["n_repeat_non_unique"],
            d_pair["n_repeat_headings"],
            d_pair["n_primary_headings"],
            d_pair["n_matched_pairs"],
            d_pair["denominator"],
            dup["text"]["status"],
        ),
        "the duplicate is collapsed through a dict -- last write wins -- so two answers for one "
        "identity become a single perfect match instead of the disagreement evidence they are",
    )

    # ================= R6.2 EXACT text equality: no normalizer may hide a spacing difference
    whitespace = copy.deepcopy(identical)
    for route in (BO.ROUTE_AI, BO.ROUTE_HUMAN):
        for heading in whitespace[route][repeat_bid]["headings"]:
            heading["text"] = heading["text"].replace(" ", "  ", 1)
    spaced = SM.r1_reliability(built.key, whitespace)
    sample = whitespace[BO.ROUTE_AI][repeat_bid]["headings"][0]["text"]
    primary_sample = identical[BO.ROUTE_AI][repeat_bid]["headings"][0]["text"]
    check(
        "R6.2 -- a whitespace-run difference that M2 would call EQUAL makes R1 text agreement fall",
        ("FAIL", 0.0, True, True),
        (
            spaced["text"]["status"],
            spaced["per_route"][BO.ROUTE_AI]["text"]["ratio"],
            # the discriminator: M2's normalisation really does equate these two strings
            SM.m2_normalize(sample) == SM.m2_normalize(primary_sample),
            sample != primary_sample,
        ),
        "R1 normalises the text before comparing, so an adjudicator whose spacing wanders reads as "
        "perfectly reliable -- and spacing instability is exactly what the repeat records",
    )
    check(
        "...and the ROLE gate is untouched by the spacing change, so the two dimensions are separate",
        "PASS",
        spaced["role"]["status"],
        "a text-only perturbation moved the role gate, so the two agreements are not independent",
    )

    # ================= R6.3 UNREADABLE never agrees, including against itself
    unreadable = copy.deepcopy(identical)
    for route in (BO.ROUTE_AI, BO.ROUTE_HUMAN):
        for bid in (primary_bid, repeat_bid):
            for heading in unreadable[route][bid]["headings"]:
                heading["role"] = BO.UNREADABLE
    unread = SM.r1_reliability(built.key, unreadable)
    check(
        "R6.3 NEGATIVE -- UNREADABLE vs UNREADABLE is NOT role agreement",
        ("FAIL", 0.0, "PASS"),
        (
            unread["role"]["status"],
            unread["per_route"][BO.ROUTE_AI]["role"]["ratio"],
            unread["text"]["status"],
        ),
        "repeated unreadability manufactures role reliability -- an absence of evidence counted as "
        "evidence of consistency, and the one input an adjudicator can always produce",
    )

    # ================= R6.4 micro-average over occurrences, not a mean of per-region rates
    check(
        "R6.4 -- the route ratio is a heading-occurrence micro-average of the summed counts",
        (True, 2, 3),
        (
            one_sided["per_route"][pair["route"]]["text"]["ratio"]
            == one_sided["per_route"][pair["route"]]["text"]["numerator"]
            / one_sided["per_route"][pair["route"]]["text"]["denominator"],
            one_sided["per_route"][pair["route"]]["text"]["numerator"],
            one_sided["per_route"][pair["route"]]["text"]["denominator"],
        ),
        "the ratio is not numerator/denominator over occurrences, so a one-heading region and a "
        "forty-heading region carry the same weight in the reliability figure",
    )
    check(
        "...and no abstention status survives the ruling",
        (False, False),
        (
            hasattr(SM, "R1_AMBIGUOUS"),
            hasattr(SM, "R1_DENOMINATOR_RULES"),
        ),
        "the candidate-denominator machinery or the AMBIGUOUS status is still reachable, so a "
        "consumer can read a status the protocol no longer defines",
    )

    # ================= A36.6 ENFORCEMENT: required routes come from FRAMES, not from the repeat
    # The route-asymmetric fixture is the one that matters here: AI passes and human FAILS, so a
    # repeat able to declare "AI only" could delete the failing route and leave a coherent artifact.
    shortened_key = copy.deepcopy(built.key)
    shortened_key["stimuli"][repeat_bid]["adjudication_routes"] = [BO.ROUTE_AI]
    shortened_answers = copy.deepcopy(human_only)
    del shortened_answers[BO.ROUTE_HUMAN][repeat_bid]  # keep key+answers internally coherent
    check(
        "A36.6 -- a repeat declaring only the PASSING route REFUSES; it cannot delete the failure",
        ("ScoreInputError", SM.R1_ROUTE_SET_MISMATCH),
        refusal_any(lambda: SM.r1_reliability(shortened_key, shortened_answers)),
        "the scorer iterates the routes the REPEAT claims, so a shortened repeat record plus a "
        "correspondingly shortened answer set silently drops a FAILING required route and the gate "
        "passes on the survivor -- and nothing in the artifact looks wrong",
    )
    check(
        "...and the un-shortened pair still reaches the FAIL, so the refusal is the only difference",
        "FAIL",
        SM.r1_reliability(built.key, human_only)["text"]["status"],
        "the asymmetric fixture does not actually fail on the human route, so the control above "
        "would refuse something that was never going to be a masked failure",
    )
    narrowed = copy.deepcopy(built.key)
    narrowed["stimuli"][repeat_bid]["frames"] = [BO.C_FRAME]
    check(
        "A36.6 -- a repeat whose FRAMES are silently narrowed REFUSES",
        ("ScoreInputError", SM.R1_FRAME_SET_MISMATCH),
        refusal_any(lambda: SM.r1_reliability(narrowed, identical)),
        "frame membership is taken from the repeat, so narrowing it changes the required route set "
        "-- the same masking, one level further back",
    )
    coherent_narrowing = copy.deepcopy(built.key)
    coherent_narrowing["stimuli"][repeat_bid]["frames"] = [BO.C_FRAME]
    coherent_narrowing["stimuli"][repeat_bid]["adjudication_routes"] = [BO.ROUTE_AI]
    check(
        "...even when frames AND routes are narrowed together, so the record is self-consistent",
        ("ScoreInputError", SM.R1_FRAME_SET_MISMATCH),
        refusal_any(lambda: SM.r1_reliability(coherent_narrowing, shortened_answers)),
        "a self-consistent narrowing passes because only frames-vs-routes agreement is checked, "
        "never agreement with the PRIMARY -- which is what A36.6 actually freezes",
    )
    check(
        "the frozen frame->route map is derived from build_oracle's own constants",
        ((BO.ROUTE_AI,), (BO.ROUTE_HUMAN,), (BO.ROUTE_AI, BO.ROUTE_HUMAN)),
        (
            SM._frame_routes([BO.C_FRAME]),
            SM._frame_routes([BO.D_FRAME]),
            SM._frame_routes([BO.C_FRAME, BO.D_FRAME]),
        ),
        "the C->AI / D->human / C&D->both mapping is restated here and can drift from A36.4's owner",
    )

    # --- an orphaned repeat REFUSES rather than shrinking the reliability population.
    orphan = copy.deepcopy(built.key)
    orphan["stimuli"][repeat_bid]["r1_base_identity"] = "a base identity nobody committed"
    check(
        "NEGATIVE -- a repeat whose primary is absent REFUSES",
        SM.R1_PRIMARY_MISSING,
        refusal(lambda: SM.r1_reliability(orphan, identical)),
        "an orphaned repeat is skipped, shrinking the very population whose size decides whether "
        "an unreliable adjudicator can be detected",
    )
    return {
        "n_pairs": agree["n_pairs"],
        "identical": {"text": agree["text"]["status"], "role": agree["role"]["status"]},
        "disagreeing": {"text": disagree["text"]["status"], "role": disagree["role"]["status"]},
        "one_sided_pair": pair,
        "unresolved_pair": u_pair,
        "duplicate_pair": d_pair,
        "whitespace": spaced["per_route"][BO.ROUTE_AI]["text"],
        "unreadable_role": unread["per_route"][BO.ROUTE_AI]["role"],
        "ruled_by": agree["ruled_by"],
    }


def part_r8(tmp: Path) -> dict:
    """A41.2 R8 -- the N-A / N-B / N-C factual verdicts, on the REAL committed control manifest.

    The chain is not rebuilt: `control_fixtures.json` -> `BO.control_specs` -> committed key ->
    committed adjudications -> scorer verdicts. G6 and `x26` own the binding that makes the key's
    carried truth trustworthy, and nothing here reimplements source replay.
    """
    print("\n== A41.2 R8: the N-A / N-B / N-C factual verdicts ==")
    manifest = json.loads(CF.MANIFEST_PATH.read_text())
    built = BO.build([], controls=BO.control_specs(manifest, EV, REPO))
    truthful = synthesize_adjudication(built.key)

    verdicts = SM.control_verdicts(built.key, truthful)
    by_kind = verdicts["by_kind"]
    check(
        "the committed 8 / 8 / 4 controls all PASS against their own committed truth, on BOTH routes",
        ({"N-A": "PASS", "N-B": "PASS", "N-C": "PASS"}, {"N-A": 16, "N-B": 16, "N-C": 8}, 20),
        (
            {k: by_kind[k]["status"] for k in SM.CONTROL_KINDS},
            {k: by_kind[k]["n_total"] for k in SM.CONTROL_KINDS},
            verdicts["n_controls"],
        ),
        "the verdicts cannot even reproduce the manifest's own expected answers, so every negative "
        "below would be measuring the fixture rather than the rule",
    )
    check(
        "...and every fixture is evaluated on EVERY required route (A36.6), 2 per control",
        {"N-A": {"ai": 8, "human": 8}, "N-B": {"ai": 8, "human": 8}, "N-C": {"ai": 4, "human": 4}},
        {k: {r: v["n_total"] for r, v in by_kind[k]["by_route"].items()} for k in SM.CONTROL_KINDS},
        "a control class is missing from an answer route, so it cannot bound that route -- and a "
        "route-specific failure would be invisible",
    )

    def mutate(fn) -> dict:
        answers = copy.deepcopy(truthful)
        fn(answers)
        return SM.control_verdicts(built.key, answers)

    def first_of(kind: str) -> str:
        return next(b for b, r in sorted(built.key["stimuli"].items()) if r["control_kind"] == kind)

    na_bid, nb_bid, nc_bid = first_of("N-A"), first_of("N-B"), first_of("N-C")

    # --- 1. N-A: the expected text differs only by a WHITESPACE RUN. No normalizer may hide it --
    # a WELD/SPLIT control differs from its source only in spacing, so normalising here would make
    # the control incapable of detecting the very mutation it exists to test.
    def widen_space(answers):
        for route in (BO.ROUTE_AI, BO.ROUTE_HUMAN):
            head = answers[route][na_bid]["headings"][0]
            head["text"] = head["text"].replace(" ", "  ", 1)

    spaced = mutate(widen_space)
    original = truthful[BO.ROUTE_AI][na_bid]["headings"][0]["text"]
    widened = original.replace(" ", "  ", 1)
    check(
        "R8 NEGATIVE -- an N-A answer differing only by a whitespace run FAILS as ABSENT",
        ("FAIL", SM.CONTROL_TARGET_ABSENT, True, True),
        (
            *first_failure(spaced["by_kind"]["N-A"]),
            SM.m2_normalize(widened) == SM.m2_normalize(original),  # M2 would call these EQUAL
            widened != original,
        ),
        "the comparison normalises whitespace, so a WELD or SPLIT control passes whether or not the "
        "adjudicator saw the alteration -- the control becomes decoration",
    )

    # --- 2. N-A: the expected target absent entirely.
    absent = mutate(
        lambda a: [a[r][na_bid].__setitem__("headings", [{"text": "SOMETHING ELSE ENTIRELY"}]) for r in ("ai", "human")]
    )
    check(
        "R8 NEGATIVE -- an absent N-A target FAILS",
        ("FAIL", SM.CONTROL_TARGET_ABSENT),
        first_failure(absent["by_kind"]["N-A"]),
        "a control whose mutated heading was never transcribed still passes, so M2/M3 keep their "
        "licence on an oracle that cannot see the failure class",
    )

    # --- 3. N-B: target absent while ANOTHER plausible heading remains, so the failure is not
    # merely "the answer was empty".
    def swap_nb(answers):
        for route in (BO.ROUTE_AI, BO.ROUTE_HUMAN):
            answers[route][nb_bid]["headings"] = [{"text": "A PLAUSIBLE BUT WRONG ACCOUNT HEADING"}]

    nb_absent = mutate(swap_nb)
    check(
        "R8 NEGATIVE -- an absent N-B target FAILS even though a plausible heading is present",
        ("FAIL", SM.CONTROL_TARGET_ABSENT, 1),
        (
            *first_failure(nb_absent["by_kind"]["N-B"]),
            len((nb_absent["by_kind"]["N-B"]["failures"] or [{"observed_texts": []}])[0]["observed_texts"]),
        ),
        "N-B passes on any non-empty answer, so the corroborated heading is not actually being "
        "checked -- and N-B is what establishes the adjudicator is reliable at all",
    )

    # --- 4. a DUPLICATED expected target is a failure, not a match.
    def duplicate_target(answers):
        for route in (BO.ROUTE_AI, BO.ROUTE_HUMAN):
            rows = answers[route][na_bid]["headings"]
            answers[route][na_bid]["headings"] = rows + [dict(rows[0])]

    duplicated = mutate(duplicate_target)
    check(
        "R8 NEGATIVE -- a DUPLICATED N-A target FAILS rather than counting as found",
        ("FAIL", SM.CONTROL_TARGET_DUPLICATED),
        first_failure(duplicated["by_kind"]["N-A"]),
        "'at least once' is accepted, so an adjudicator reporting the same heading twice satisfies "
        "a control whose truth names exactly one occurrence",
    )

    # --- 5. N-C: one fabricated heading in a constructionally heading-free region.
    def fabricate(answers):
        for route in (BO.ROUTE_AI, BO.ROUTE_HUMAN):
            answers[route][nc_bid]["headings"] = [{"text": "A HEADING THAT IS NOT PRINTED"}]

    fabricated = mutate(fabricate)
    check(
        "R8 NEGATIVE -- ONE fabricated heading FAILS N-C",
        ("FAIL", SM.CONTROL_HEADING_REPORTED),
        first_failure(fabricated["by_kind"]["N-C"]),
        "over-triggering passes, so every precision claim keeps its licence while the oracle "
        "invents headings -- the exact condition section 5.6 voids precision for",
    )

    # --- 6. ROUTE ASYMMETRY: the AI route answers correctly, the human route does not.
    def human_only(answers):
        answers[BO.ROUTE_HUMAN][na_bid]["headings"] = [{"text": "ONLY THE HUMAN ROUTE IS WRONG"}]

    asymmetric = mutate(human_only)
    # `.get` with an explicit absent marker rather than direct indexing: a fault that scores only
    # one route leaves the other absent, and a KeyError here would turn a caught fault into a crash.
    absent = {"n_passed": "ROUTE ABSENT", "n_total": "ROUTE ABSENT"}
    routes = {r: asymmetric["by_kind"]["N-A"]["by_route"].get(r, absent) for r in (BO.ROUTE_AI, BO.ROUTE_HUMAN)}
    check(
        "R8 -- one route cannot mask the other: AI passes, human fails, the KIND fails",
        ("FAIL", 8, 7, [BO.ROUTE_HUMAN]),
        (
            asymmetric["by_kind"]["N-A"]["status"],
            routes[BO.ROUTE_AI]["n_passed"],
            routes[BO.ROUTE_HUMAN]["n_passed"],
            sorted({f["route"] for f in asymmetric["by_kind"]["N-A"]["failures"]}),
        ),
        "a passing route averages away a failing one, so a control that failed on the route whose "
        "labels are actually consumed still reads PASS",
    )
    check(
        "...and a kind PASS requires EVERY fixture on EVERY route -- no tolerance, no percentage",
        (True, "no tolerance"),
        ("every fixture passes on every required route" in verdicts["aggregation"], "no tolerance"),
        "the aggregation admits a threshold or a percentage, which the frozen Rule 3 blockers do not",
    )

    # --- 7. SELF-CERTIFICATION is impossible: swapping two controls' expected truths in the
    # SCORER INPUT must not silently produce a pass. The G6 / x26 binding is preserved, not
    # reimplemented -- this only proves the scorer cannot be fed a self-consistent lie.
    swapped_key = copy.deepcopy(built.key)
    a_truth = swapped_key["stimuli"][na_bid]["control_expected_truth"]
    b_truth = swapped_key["stimuli"][nb_bid]["control_expected_truth"]
    swapped_key["stimuli"][na_bid]["control_expected_truth"] = b_truth
    swapped_key["stimuli"][nb_bid]["control_expected_truth"] = a_truth
    swapped = SM.control_verdicts(swapped_key, truthful)
    check(
        "R8 NEGATIVE -- swapping two controls' expected truths cannot self-certify",
        ("FAIL", "FAIL"),
        (swapped["by_kind"]["N-A"]["status"], swapped["by_kind"]["N-B"]["status"]),
        "truth attached to the wrong control still passes, which would mean the verdict is not "
        "reading the committed truth at all",
    )
    check(
        "...and nothing here is malformed, so the failure is about BINDING rather than shape",
        (True, True),
        (isinstance(a_truth, list) and bool(a_truth), isinstance(b_truth, list) and bool(b_truth)),
        "the swap produced a malformed record, so the control would fail for the wrong reason",
    )

    # ================= THE FROZEN 8 / 8 / 4 CENSUS, and both routes per control
    # Each fixture below stays internally well formed; only the POPULATION is wrong, which is what
    # makes these meaningful rather than malformedness tests.
    na_bids = [b for b, r in built.key["stimuli"].items() if r["control_kind"] == "N-A"]

    incomplete_key = copy.deepcopy(built.key)
    del incomplete_key["stimuli"][na_bids[0]]
    incomplete_answers = copy.deepcopy(truthful)
    for route in (BO.ROUTE_AI, BO.ROUTE_HUMAN):
        del incomplete_answers[route][na_bids[0]]
    check(
        "R8 -- deleting ONE N-A control and both its answers REFUSES, it does not certify 7/7",
        ("ScoreInputError", SM.CONTROL_POPULATION_INCOMPLETE),
        refusal_any(lambda: SM.control_verdicts(incomplete_key, incomplete_answers)),
        "a coherent key missing one control reports 7/7 PASS and satisfies a Rule 3 blocker on a "
        "SMALLER census than the protocol froze -- self-certification by omission, and the "
        "artifact looks complete from the inside",
    )
    check(
        "...and the same key WITH the control present passes, so the refusal is about completeness",
        "PASS",
        SM.control_verdicts(built.key, truthful)["by_kind"]["N-A"]["status"],
        "the complete population is refused too, so the control above proves nothing",
    )

    one_route_key = copy.deepcopy(built.key)
    one_route_key["stimuli"][na_bids[0]]["adjudication_routes"] = [BO.ROUTE_AI]
    one_route_answers = copy.deepcopy(truthful)
    del one_route_answers[BO.ROUTE_HUMAN][na_bids[0]]
    check(
        "R8 -- a control declaring only ONE route REFUSES; it is not scored on the survivor",
        ("ScoreInputError", SM.CONTROL_ROUTE_SET_MISMATCH),
        refusal_any(lambda: SM.control_verdicts(one_route_key, one_route_answers)),
        "a control is scored on the route it kept, so the route whose labels are actually consumed "
        "goes unchecked while the kind still reports PASS (A36.6 gives every control both routes)",
    )

    reidentified = copy.deepcopy(built.key)
    reidentified["stimuli"][na_bids[1]]["canonical_identity"] = reidentified["stimuli"][na_bids[0]][
        "canonical_identity"
    ]
    check(
        "R8 -- a DUPLICATED control identity REFUSES even though the counts still look right",
        ("ScoreInputError", SM.CONTROL_IDENTITY_DUPLICATED),
        refusal_any(lambda: SM.control_verdicts(reidentified, truthful)),
        "identity uniqueness is not checked, so one real fixture goes unexercised while another is "
        "scored twice and the 8/8/4 census still reads correct",
    )
    check(
        "the frozen census and required routes are STATED in the artifact, not implicit",
        ({"N-A": 8, "N-B": 8, "N-C": 4}, [BO.ROUTE_AI, BO.ROUTE_HUMAN], True),
        (verdicts["frozen_population"], verdicts["required_routes"], verdicts["population_present"]),
        "a reader cannot tell which census was enforced, or whether one was present at all",
    )
    check(
        "a key with NO controls reports NOT_EVALUABLE everywhere rather than PASS",
        ({"N-A": "NOT_EVALUABLE", "N-B": "NOT_EVALUABLE", "N-C": "NOT_EVALUABLE"}, False),
        (
            {k: v["status"] for k, v in SM.control_verdicts(EMPTY_KEY, EMPTY_ADJUDICATED)["by_kind"].items()},
            SM.control_verdicts(EMPTY_KEY, EMPTY_ADJUDICATED)["population_present"],
        ),
        "a control-free key reports PASS on a blocker it never evaluated -- and DEVELOPMENT material "
        "legitimately carries no controls, so this path must be honest rather than forbidden",
    )

    # --- malformed committed truth REFUSES rather than silently passing or failing.
    broken = copy.deepcopy(built.key)
    broken["stimuli"][na_bid]["control_expected_truth"] = []
    check(
        "NEGATIVE -- an N-A record with no committed expected heading REFUSES",
        SM.CONTROL_TRUTH_MALFORMED,
        refusal(lambda: SM.control_verdicts(broken, truthful)),
        "a control with no truth to check against is silently scored, so a manifest defect becomes a PASS",
    )
    check(
        "no architecture decision is taken here -- statuses only",
        (True, True),
        ("decide_architecture" in verdicts["decision_owner"], "FACTS" in verdicts["decision_owner"]),
        "the scorer applies a Rule 3 consequence to a control status, taking a decision section 7 owns",
    )
    return {
        "by_kind": {k: {m: by_kind[k][m] for m in ("status", "n_passed", "n_total")} for k in SM.CONTROL_KINDS},
        "n_controls": verdicts["n_controls"],
        "whitespace_reason": first_failure(spaced["by_kind"]["N-A"])[1],
        "route_asymmetry": routes,
    }


def _row_field(rows, index: int, field: str):
    """`rows[index][field]`, or a marker. A control that IndexErrors on an emptied detail list
    detects its fault by crashing, which cannot distinguish a broken rule from a broken probe."""
    if not isinstance(rows, list) or index >= len(rows):
        return "<NO ROW>"
    return rows[index].get(field, "<ABSENT>")


def _walk(node, path=()):
    """Every (path, node) in a finished payload, at any depth. Dicts and lists alike."""
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, path + (str(key),))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, path + (f"[{index}]",))


M6_PATTERN = re.compile(r"(?i)(^|[^a-z0-9])m6([^a-z0-9]|$)")


def m6_surfaces(payload) -> list:
    """Every place in a FINISHED payload that names M6, at any depth. Keys and string values.

    A source grep would pass while the schema still carried the key -- and the schema is what a
    consumer reads. This walks the built result instead.
    """
    hits = []
    for path, node in _walk(payload):
        if path and M6_PATTERN.search(path[-1]):
            hits.append({"path": "/".join(path), "kind": "KEY"})
        if isinstance(node, str) and M6_PATTERN.search(node):
            hits.append({"path": "/".join(path) or "<root>", "kind": "VALUE", "text": node[:80]})
    return hits


#: A per-document result surface is recognised by its CONTENT, not by a list of paths copied from
#: the production code: any dict carrying one of these marker keys is a result the I13 label must
#: travel with. Discovering surfaces this way is what makes the control able to notice a labelling
#: path the production code forgot -- including one nobody thought to enumerate here.
RESULT_SURFACE_MARKERS = (
    "M0a_text",
    # The M7 BLOCK's own marker. Without it only the per-arm sub-blocks are discovered, and a
    # missing label on the M7 block itself would be inherited-away by the arms' parent lookup.
    "threshold_single_char_tokens",
    "n_display_split",
    "coverage_floor",
    "M1",
    "n_anchor_discordant_regions",
    "difference",
)


def per_document_result_surfaces(payload: dict) -> list:
    """Every per-document result surface in a finished payload, discovered from its content.

    "Per-document" is established structurally: either the surface's path passes through a scored
    document identity, or the surface itself carries a `document` field naming one. Pooled rows have
    neither and are deliberately not required to carry a per-document label -- the >1/3 headline
    qualifications cover them.

    A surface counts as labelled when it carries `qualification` ITSELF or inherits one from an
    ANCESTOR: the label travels with the result, so a per-arm sub-block inside an already-labelled
    M7 or M9 block is covered. Removing a production labelling path still reddens, because then
    neither the block nor any ancestor carries it.
    """
    documents = set(payload.get("documents_scored") or [])
    found = []
    for path, node in _walk(payload):
        if not isinstance(node, dict):
            continue
        if not any(marker in node for marker in RESULT_SURFACE_MARKERS):
            continue
        if not (any(step in documents for step in path) or node.get("document") in documents):
            continue
        labelled = "qualification" in node
        for depth in range(len(path) - 1, -1, -1):
            if labelled:
                break
            ancestor = payload
            for step in path[:depth]:
                ancestor = ancestor[int(step[1:-1])] if step.startswith("[") else ancestor[step]
            # INHERIT ONLY FROM A RESULT SURFACE, never from any labelled ancestor. The purpose of
            # inheritance is to spare per-ARM sub-blocks inside an already-labelled metric block
            # (M7/H, M9/X) -- not to let the DOCUMENT-level label cover a metric block whose own
            # labelling path was removed. Accepting any labelled ancestor made exactly that hole:
            # deleting the per-frame heading label left the suite green, because `per_document/<doc>`
            # carries a qualification of its own.
            labelled = (
                isinstance(ancestor, dict)
                and "qualification" in ancestor
                and any(marker in ancestor for marker in RESULT_SURFACE_MARKERS)
            )
        found.append({"path": "/".join(path), "labelled": labelled})
    return found


def part_m6_and_i13(tmp: Path) -> dict:
    """M6 must be ABSENT from the schema, and I13 must label every applicable result surface."""
    print("\n== M6 absence, and I13 labelling of every per-document result surface ==")
    pages = [page_input(1), page_input(2, start_gid=100)]
    occ = {arm: [occurrence(p + 1, 2, p * 100 + 4) for p in range(2)] for arm in ("H", "X")}
    a = frame(pages, document="COND/1", occurrences=occ)
    b = frame([page_input(1)], document="CLEAN/1", sha=DOC_SHA_B)
    pdf = synthetic_pdf(tmp, 2)
    built = BO.build(
        [{"frame": a, "pdf_path": pdf, "stratum": "SYNTHETIC"}, {"frame": b, "pdf_path": pdf, "stratum": "SYNTHETIC"}]
    )
    adjudicated = synthesize_adjudication(built.key)
    scored = SM.score(
        inputs(
            [a, b],
            key=built.key,
            adjudicated=adjudicated,
            cross_engine=cross_engine_artifact(["COND/1", "CLEAN/1"], failed={"COND/1"}),
        )
    )

    # ---- M6 is absent from the finished payload, at any depth.
    check(
        "M6 appears NOWHERE in the finished payload -- no key, no string, at any depth",
        [],
        SM.__dict__ and m6_surfaces(scored),
        "a key or value naming M6 is in the result-bearing schema. Section 5 owns 'M0-M9 minus M6', "
        "so even a value that says DEFERRED puts a deferred metric in an artifact a consumer reads "
        "-- and invites it to be reserved, looked up, or filled in later",
    )
    planted = copy.deepcopy(scored)
    planted["m6"] = "DEFERRED by A20"
    planted["per_document"]["COND/1"]["M6_attribution"] = {"value": None}
    check(
        "...and the scanner FINDS a planted M6 key, so the emptiness above is not vacuous",
        (2, ["KEY", "KEY"]),
        (len(m6_surfaces(planted)), [h["kind"] for h in m6_surfaces(planted)]),
        "the scanner cannot see an M6 surface even when one is planted in a finished payload, so "
        "its clean result proves nothing",
    )
    check(
        "...and it finds one hidden in a nested VALUE too, not only in a key",
        True,
        any(h["kind"] == "VALUE" for h in m6_surfaces({"note": "M6 is deferred", "deep": [{"x": "see m6"}]})),
        "only keys are scanned, so prose reintroducing M6 into the schema would pass",
    )

    # ---- I13 labels every per-document result surface, discovered from the payload's content.
    surfaces = per_document_result_surfaces(scored)
    unlabelled = sorted(s["path"] for s in surfaces if not s["labelled"])
    check(
        "EVERY per-document result surface carries an explicit I13 qualification field",
        [],
        unlabelled,
        "a per-document result is reported with no qualification field, so a reader cannot tell "
        "whether it was computed on a PDFIUM-conditioned frame -- and I13 requires the label on "
        "EVERY RQ1/RQ2 result computed on a failing document, not on a parent block alone",
    )
    check(
        "...and the discovery really found the M0 / M7 / M9 / heading / event / paired surfaces",
        (True, True, True, True, True, True),
        (
            any(s["path"].endswith("/M0") for s in surfaces),
            any(s["path"].endswith("/M7") for s in surfaces),
            any(s["path"].endswith("/M9") for s in surfaces),
            any("headings_by_frame" in s["path"] for s in surfaces),
            any("section8/per_document" in s["path"] for s in surfaces),
            any("paired" in s["path"] and "per_document" in s["path"] for s in surfaces),
        ),
        "the content-based discovery missed a surface class, so 'everything is labelled' was "
        "asserted over an incomplete set",
    )
    conditioned = scored["per_document"]["COND/1"]
    clean = scored["per_document"]["CLEAN/1"]
    check(
        "a FAILING document is labelled on each surface; a PASSING one carries explicit None",
        (
            SM.PDFIUM_CONDITIONED_FRAME,
            SM.PDFIUM_CONDITIONED_FRAME,
            SM.PDFIUM_CONDITIONED_FRAME,
            None,
            None,
            None,
        ),
        (
            conditioned["M0"].get("qualification", "<ABSENT>"),
            conditioned["M7"].get("qualification", "<ABSENT>"),
            conditioned["M9"].get("qualification", "<ABSENT>"),
            clean["M0"].get("qualification", "<ABSENT>"),
            clean["M7"].get("qualification", "<ABSENT>"),
            clean["M9"].get("qualification", "<ABSENT>"),
        ),
        "a passing document has an ABSENT field rather than an explicit null, so 'not conditioned' "
        "is indistinguishable from 'nobody labelled this'",
    )
    events = {e["document"]: e.get("qualification", "<ABSENT>") for e in scored["section8"]["per_document"]}
    paired_rows = [
        row
        for quantity in scored["section8"]["paired"]["by_population"].values()
        for block in quantity.values()
        for row in block["per_document"]
    ]
    check(
        "the section 8 event vector and EVERY paired-difference detail row carry the label too",
        ({"COND/1": SM.PDFIUM_CONDITIONED_FRAME, "CLEAN/1": None}, True, 4),
        (
            events,
            all("qualification" in row for row in paired_rows),
            len(paired_rows),
        ),
        "a section 8 row is reported without its qualification, so the statistic's own per-document "
        "detail hides which documents were frame-conditioned",
    )
    check(
        "BOTH headline qualifications are emitted from the >1/3 rule, explicitly",
        ({"RQ1": SM.PDFIUM_CONDITIONED_FRAME, "RQ2": SM.PDFIUM_CONDITIONED_FRAME}, True),
        (
            scored["cross_engine_qualification"]["headline_qualifications"],
            scored["cross_engine_qualification"]["both_headlines_qualified"],
        ),
        "the headline qualifications are left for a reader to derive from a boolean, so a report can "
        "omit them without contradicting the artifact",
    )
    check(
        "...and 1 of 2 failing really is MORE than a third, so the fixture exercises the rule",
        True,
        1 * 3 > 2,
        "the fixture does not cross the one-third boundary, so the headline check passed by accident",
    )
    check(
        "cross-engine remains REPORTING-ONLY -- it reaches no decision input",
        (False, False, False),
        (
            scored["cross_engine_qualification"]["decision_blocking"],
            scored["decision_taken_here"],
            any(
                isinstance(node, dict) and "qualification" in node and node.get("m5_void") is True
                for _p, node in _walk(scored)
            ),
        ),
        "a qualification field reaches a gate or a decision input, which A27.6 forbids: x09 "
        "qualifies reporting and blocks nothing",
    )
    return {
        "m6_surfaces": m6_surfaces(scored),
        "n_labelled_surfaces": len(surfaces),
        "unlabelled": unlabelled,
        "headline_qualifications": scored["cross_engine_qualification"]["headline_qualifications"],
    }


def part_m7() -> dict:
    print("\n== section 5 row: inject an `R E P O R T` page, and M7's own failure mode ==")
    injected = frame(
        [page_input(1)],
        occurrences={
            "H": [occurrence(1, 2, 4, text="R E P O R T")],
            "X": [occurrence(1, 2, 4, text="REPORT")],
        },
    )
    block = SM.m7_block(injected)
    check(
        "the injected letter-spaced page is DETECTED for the arm that split it",
        (1, 1, 0),
        (block["H"]["n_display_split"], len(block["H"]["instances"]), block["X"]["n_display_split"]),
        "M7 does not detect an injected `R E P O R T`, so phase 2's flip condition cannot be "
        "evaluated on fresh data at all",
        row="negative: inject an R E P O R T page",
    )
    check(
        "...and the matching text is PRINTED, not merely counted",
        "R E P O R T",
        block["H"]["instances"][0]["text"],
        "only a count is reported, so a reader cannot tell a real signature from a coincidence",
        row="negative: inject an R E P O R T page",
    )

    # --- NEGATIVE: M7 must be able to FAIL independently. The threshold is the frozen >= 3.
    boundary = frame(
        [page_input(1)],
        occurrences={
            "H": [
                occurrence(1, 2, 4, text="A B OF THE THING"),  # exactly 2 single-char tokens
                occurrence(1, 3, 6, text="A B C OF THE THING"),  # exactly 3
            ],
            "X": [],
        },
    )
    b = SM.m7_block(boundary)
    signatures = [SM.m7_signature(t) for t in ("A B OF THE THING", "A B C OF THE THING")]
    check(
        "NEGATIVE -- 2 single-character tokens do NOT match and 3 DO: the threshold is live",
        (1, [False, True], [2, 3]),
        (
            b["H"]["n_display_split"],
            [s["matches"] for s in signatures],
            [s["n_single_char_tokens"] for s in signatures],
        ),
        "the frozen `>= 3 single-character tokens` condition is not what is implemented, so M7 "
        "either fires on ordinary prose or cannot fire at all",
        row="negative: inject an R E P O R T page",
    )
    check(
        "...and an ordinary heading matches nothing, so M7 is not simply always true",
        (0, 0),
        (
            SM.m7_signature("SALARIES AND EXPENSES")["n_single_char_tokens"],
            SM.m7_block(frame([page_input(1)], occurrences={"H": [occurrence(1, 2, 4)], "X": []}))["H"][
                "n_display_split"
            ],
        ),
        "M7 fires on an ordinary account heading, so its rate carries no information",
        row="negative: inject an R E P O R T page",
    )
    check(
        "M7's denominator is the arm's COMPLETE emitted census (100 % of the holdout)",
        (2, 1),
        (b["H"]["rate"]["denominator"], block["H"]["rate"]["denominator"]),
        "M7 is computed over an adjudicated subset, which section 6 does not license -- it is a "
        "self-signature over each architecture's own output",
    )
    check(
        "an arm that emitted nothing reports VACUOUS, not a zero rate",
        (SM.VACUOUS, None),
        (b["X"]["rate"]["status"], b["X"]["rate"]["value"]),
        "a zero-denominator M7 is printed as 0.0, which reads as 'no display splits observed'",
        row="vacuity",
    )
    return {"injected": block["H"], "boundary": {"n_display_split": b["H"]["n_display_split"]}}


def part_rule0() -> dict:
    print("\n== M9 / Rule 0 raw facts: no tolerance, and the floor cannot move ==")
    f = frame([page_input(1)], m9_h=m9_facts(margin=197), m9_x=m9_facts(margin=198))
    facts = SM.rule0_facts(f)
    check(
        "a ONE-line margin deficit fires, and names the loser -- no tolerance",
        ("H", True, 1),
        (facts["margin_line_loss"]["loser"], facts["margin_line_loss"]["fires"], facts["margin_line_loss"]["deficit"]),
        "a tolerance was introduced, so 'loses margin-numbered lines' became 'loses more than N' "
        "-- choosing the sensitivity of a decision rule the frozen text does not parameterise",
    )
    equal = SM.rule0_facts(frame([page_input(1)], m9_h=m9_facts(margin=198), m9_x=m9_facts(margin=198)))
    check(
        "...and an EQUAL count does not fire, so the clause is not simply always true",
        (None, False, 0),
        (
            equal["margin_line_loss"]["loser"],
            equal["margin_line_loss"]["fires"],
            equal["margin_line_loss"]["deficit"],
        ),
        "the margin clause fires on identical counts, which would reject an arm for nothing",
    )
    check(
        "no Rule 0 OUTCOME is emitted here -- only the facts the rule reads",
        (None, True),
        (facts["rule0_outcome"], "decide_architecture" in facts["rule0_owner"]),
        "the scorer decided Rule 0, taking a decision section 7 owns and A27.4 gave its own outcome enum",
    )

    band = SM.rule0_facts(frame([page_input(1)], m9_h=m9_facts(band=False), m9_x=m9_facts(band=True)))
    both = SM.rule0_facts(frame([page_input(1)], m9_h=m9_facts(band=False), m9_x=m9_facts(band=False)))
    check(
        "the band clause fires for exactly ONE losing arm, and NOT when both lose",
        ("H", True, None, False),
        (
            band["band_loss"]["loser"],
            band["band_loss"]["fires"],
            both["band_loss"]["loser"],
            both["band_loss"]["fires"],
        ),
        "a shared failure is read as an asymmetric loss, which would reject an arm on evidence "
        "that distinguishes nothing (section 7.2 rule 0's both-lose branch)",
    )

    low = SM.rule0_facts(frame([page_input(1)], m9_h=m9_facts(coverage=0.84), m9_x=m9_facts(coverage=0.85)))
    check(
        "the coverage clause bites exactly at the frozen 0.85 floor",
        ("H", True, 0.85),
        (low["coverage_loss"]["loser"], low["coverage_loss"]["fires"], low["coverage_floor"]),
        "the 0.85 floor moved, so an arm keeps or loses a document's whole heading tree by a "
        "threshold this study invented",
    )

    # --- NEGATIVE: the coverage threshold changed. A frame committing another floor REFUSES.
    moved = copy.deepcopy(f)
    moved["m9"]["H"]["coverage_floor"] = 0.80
    check(
        "NEGATIVE -- a committed coverage floor other than production's 0.85 REFUSES",
        SM.COVERAGE_FLOOR_DRIFT,
        refusal(lambda: SM.score(inputs([moved]))),
        "a moved threshold is scored silently, which is a DEVIATION presented as a result",
    )
    inconsistent = copy.deepcopy(f)
    inconsistent["m9"]["X"]["coverage"] = 0.5
    check(
        "NEGATIVE -- a committed verdict that contradicts its own floor REFUSES",
        SM.COVERAGE_FLOOR_DRIFT,
        refusal(lambda: SM.score(inputs([inconsistent]))),
        "the scorer trusts `coverage_meets_floor` over the coverage and the floor beside it",
    )
    return {"margin": facts["margin_line_loss"], "band": band["band_loss"], "coverage": low["coverage_loss"]}


def part_section8() -> dict:
    print("\n== section 8: the document unit, the exact bound, the bootstrap, the pairing ==")

    # --- row: INDEPENDENCE. The bound must be computed on DOCUMENTS, never on headings.
    doc_bound = SM.clopper_pearson_upper(0, 14)
    heading_bound = SM.clopper_pearson_upper(0, 600)
    check(
        "section 8.1's own fixture reproduces: 14 documents 0.1926 vs 600 headings 0.00498",
        (0.1926, 0.00498, 39),
        (round(doc_bound, 4), round(heading_bound, 5), round(doc_bound / heading_bound)),
        "the two bounds agree, so nothing here could detect headings being treated as iid "
        "trials -- the 39x overstatement section 8.1 measured",
        row="section 8 independence",
    )

    docs = [frame([page_input(1)], document=f"DOC/{i}", sha=DOC_SHA) for i in range(14)]
    block = SM.section8(docs, {}, {})
    check(
        "N is the number of DOCUMENTS scored, and the bound is the document-unit one",
        (14, 0, "document", round(doc_bound, 10)),
        (
            block["n_documents"],
            block["events"],
            block["independent_unit"],
            round(block["clopper_pearson_upper_bound"], 10),
        ),
        "N counts headings, regions or stimuli, so the bound asserts an independence the design explicitly denies",
        row="section 8 independence",
    )
    check(
        "NEGATIVE -- a heading-level table (one document, many rows) REFUSES",
        MC.DUPLICATE_DOCUMENT_IDENTITY,
        refusal(lambda: MC.section8_document_bootstrap([("DOC/0", True), ("DOC/0", False)])),
        "a heading-as-rows table is accepted and silently double-weights a document, which is "
        "exactly how a per-heading denominator gets in",
        row="section 8 independence",
    )

    # --- row: ZERO-EVENT. No bootstrap, and the closed form must be `1 - 0.05 ** (1/N)`.
    check(
        "at zero events NO bootstrap is reported, and the reason is explicit",
        (False, MC.ZERO_EVENTS_BOOTSTRAP_REFUSED, False),
        (block["bootstrap"]["reported"], block["bootstrap"]["reason"], block["bootstrap"]["gating"]),
        "a bootstrap is reported at zero events, where 8.1 measured the percentile interval is "
        "[0.0, 0.0] and carries no information about a new document",
        row="section 8 zero-event",
    )
    check(
        "...and the zero-event bound IS the frozen closed form, to the last bit",
        (1 - 0.05 ** (1 / 14), True),
        (block["clopper_pearson_upper_bound"], block["zero_event_closed_form_used"]),
        "the closed form is not `1 - 0.05 ** (1/N)`, so the one number section 8 froze verbatim "
        "was recomputed by something else",
        row="section 8 zero-event",
    )
    check(
        "...and the general bisection AGREES with the closed form at k = 0, so it is not a special case",
        [True, True, True],
        [abs(SM.clopper_pearson_upper(0, n) - MC.zero_event_upper_bound(n)) < 1e-12 for n in (1, 14, 600)],
        "the general Clopper-Pearson path disagrees with the frozen closed form, so one of the "
        "two is wrong and only the zero-event case would ever reveal it",
        row="section 8 zero-event",
    )
    # The wording gate has to test for the ASSERTIVE forms, and separately for the presence of
    # the disclaimer: a naive substring search for "the true rate is zero" hits the disclaimer
    # itself, which would fail the honest sentence and pass a silent one.
    claims = {
        phrase: phrase in block["statement"]
        for phrase in ("the architectures agree", "are identical", "produced identical", "the rate is zero.")
    }
    check(
        "...and the reported wording is an OBSERVATION plus a bound, with an explicit disclaimer",
        (True, True, {p: False for p in claims}),
        (
            "no heading-level discordance observed" in block["statement"],
            "not a claim that the true rate is zero" in block["statement"],
            claims,
        ),
        "the zero-event sentence asserts equivalence, or carries no disclaimer, so a loose bound "
        "reads as 'the architectures agree' -- the phrasing section 7.2 forbids",
        row="section 8 zero-event",
    )

    # --- the non-zero branch: a bootstrap IS reported, deterministically, and never gates.
    with_event = [
        frame(
            [
                page_input(
                    1,
                    h_anchors={0: {anchor(1, 3)}},
                    x_anchors={0: {anchor(1, 3, text="SALARIESAND EXPENSES")}},
                )
            ],
            document="DOC/0",
        )
    ] + [frame([page_input(1)], document=f"DOC/{i}") for i in range(1, 14)]
    nonzero = SM.section8(with_event, {}, {})
    again = SM.section8(with_event, {}, {})
    check(
        "one discordant document gives 1/14, a REPORTED non-gating bootstrap, and a wider bound",
        (1, 14, True, False, True),
        (
            nonzero["events"],
            nonzero["n_documents"],
            nonzero["bootstrap"]["reported"],
            nonzero["bootstrap"]["gating"],
            nonzero["clopper_pearson_upper_bound"] > block["clopper_pearson_upper_bound"],
        ),
        "an event does not move the bound or the bootstrap, so section 8 is not reading the "
        "per-document evidence at all",
    )
    check(
        "...and the bootstrap interval is deterministic across runs",
        nonzero["bootstrap"]["interval"],
        again["bootstrap"]["interval"],
        "the interval moves between runs, so no reported figure is reproducible",
    )

    # --- P-HEAD ONLY. A P-robust document may not enter the statistic.
    robust = frame(
        [
            page_input(
                1,
                h_anchors={0: {anchor(1, 3)}},
                x_anchors={0: {anchor(1, 3, text="OTHER")}},
            )
        ],
        document="ROBUST/1",
        population="P-robust",
    )
    mixed = SM.section8(docs + [robust], {}, {})
    check(
        "a P-robust document is EXCLUDED from the section 8 statistic and named",
        (14, 0, ["ROBUST/1"]),
        (mixed["n_documents"], mixed["events"], mixed["excluded_documents_not_p_head"]),
        "a P-robust document enters a heading-level statistic section 4.4.1 claims nothing "
        "about, inflating N and reusing a draw sequence that is not its own",
    )
    check(
        "...and that document really DID carry an event, so the exclusion is not vacuous",
        True,
        SM.document_discordance_event(robust)["event"],
        "the excluded document had no event anyway, so 'the numbers did not move' proves nothing",
    )

    # --- the event definition is heading-level, not line-level.
    text_only = frame([page_input(1, text_differs={0})], document="TEXTONLY/1")
    check(
        "the event is HEADING-level: a body-line text difference is not a section 8 event",
        (False, 0, 1),
        (
            SM.document_discordance_event(text_only)["event"],
            SM.document_discordance_event(text_only)["n_anchor_discordant_regions"],
            SM.m0_block(text_only)["M0a_text"],
        ),
        "a line-level difference on ordinary body text counts as heading-level discordance, so "
        "section 8 would answer a different question under its own name",
    )
    # ---- THE STRUCTURED POPULATION must contain the statistic's members and nothing else.
    # A P-robust row inside `per_document` is not a diagnostic, it is a category error: section
    # 4.4.1 claims NO heading metric on P-robust, and the list documents `n_documents`/`events`.
    print("\n-- section 8's structured per_document is the P-head statistic population")
    members = {e["document"] for e in mixed["per_document"]}
    check(
        "a P-robust document with a discordance is ABSENT from the P-head per_document vector",
        (False, 14, 14),
        ("ROBUST/1" in members, len(mixed["per_document"]), mixed["n_documents"]),
        "an excluded P-robust row sits inside the vector that documents N and the event count, so "
        "a reader (or a later consumer) counts it as a member of a statistic it is barred from",
    )
    check(
        "...and it remains explicitly REPORTED, under a name that cannot be read as membership",
        (["ROBUST/1"], ["ROBUST/1"], True),
        (
            mixed["excluded_documents_not_p_head"],
            [e["document"] for e in mixed["excluded_diagnostics_not_in_statistic"]],
            all(e["population"] != MC.P_HEAD for e in mixed["excluded_diagnostics_not_in_statistic"]),
        ),
        "the exclusion is silent, so nothing records that a document was held out of a heading statistic at all",
    )
    p_head_only = SM.section8([f for f in docs], {}, {})
    check(
        "...and adding it changes NO reported figure: N, events, bound and bootstrap all hold",
        (
            p_head_only["n_documents"],
            p_head_only["events"],
            p_head_only["clopper_pearson_upper_bound"],
            p_head_only["bootstrap"]["reported"],
        ),
        (
            mixed["n_documents"],
            mixed["events"],
            mixed["clopper_pearson_upper_bound"],
            mixed["bootstrap"]["reported"],
        ),
        "a P-robust document moved a reported section 8 figure, so the P-head restriction is "
        "decoration rather than a filter",
    )
    return {
        "zero_event": {"n": block["n_documents"], "bound": block["clopper_pearson_upper_bound"]},
        "nonzero": {"events": nonzero["events"], "bound": nonzero["clopper_pearson_upper_bound"]},
        "bootstrap_interval": nonzero["bootstrap"]["interval"],
        "excluded_p_robust": mixed["excluded_documents_not_p_head"],
        "structured_population": sorted(members),
    }


def part_pairing(tmp: Path) -> dict:
    """Section 5 row + A41.2 R9: the paired quantities, unweighted, populations never pooled."""
    print("\n== section 5 row: section 8 pairing (A41.2 R9 -- the two M9 basis quantities) ==")
    # THREE documents, chosen so every negative below has something to move:
    #   P-head A   margin 100 -> 110 (+10), coverage 0.90 -> 0.95 (+0.05), 1 heading
    #   P-head B   margin 100 -> 120 (+20), coverage 0.90 -> 0.85 (-0.05), 3 headings
    #   P-robust R margin 100 -> 200 (+100)  -- a deliberately large delta, so pooling it in would
    #              visibly move a P-head mean and cannot be mistaken for rounding.
    a_frame = frame(
        [page_input(1, start_gid=0)],
        document="DOC/A",
        occurrences={arm: [occurrence(1, 2, 4)] for arm in ("H", "X")},
        m9_h=m9_facts(margin=100, coverage=0.90),
        m9_x=m9_facts(margin=110, coverage=0.95),
    )
    b_frame = frame(
        [page_input(1, start_gid=0)],
        document="DOC/B",
        sha=DOC_SHA_B,
        occurrences={
            arm: [occurrence(1, o, o * 2, text=f"ACCOUNT {i}", sha=DOC_SHA_B) for i, o in enumerate((2, 3, 4))]
            for arm in ("H", "X")
        },
        m9_h=m9_facts(margin=100, coverage=0.90),
        m9_x=m9_facts(margin=120, coverage=0.85),
    )
    r_frame = frame(
        [page_input(1, start_gid=0)],
        document="ROBUST/R",
        sha=hashlib.sha256(b"x27-pairing-robust").hexdigest(),
        population="P-robust",
        m9_h=m9_facts(margin=100, coverage=0.90),
        m9_x=m9_facts(margin=200, coverage=0.90),
    )
    pdf = synthetic_pdf(tmp, 1)
    built = BO.build(
        [
            {"frame": a_frame, "pdf_path": pdf, "stratum": "SYNTHETIC"},
            {"frame": b_frame, "pdf_path": pdf, "stratum": "SYNTHETIC"},
        ]
    )
    adjudicated = synthesize_adjudication(built.key, truth="X")
    scored = SM.score(
        inputs(
            [a_frame, b_frame, r_frame],
            key=built.key,
            adjudicated=adjudicated,
            strata={"DOC/A": 1, "DOC/B": 2, "ROBUST/R": 4},
        )
    )
    paired = scored["section8"]["paired"]
    head = paired["by_population"][MC.P_HEAD]
    robust = paired["by_population"]["P-robust"]

    check(
        "R9 -- exactly the two non-constant numeric M9 basis quantities are paired",
        ["coverage", "n_margin_numbered_lines"],
        sorted(paired["quantities"]),
        "a quantity outside R9's ruling is paired. M1-M5 and M7 can be VACUOUS, so pairing them "
        "needs an unruled missingness policy; the booleans are Rule 0's; coverage_floor is a "
        "constant; and the glyph-size count is a diagnostic rather than A39.1's quantity",
        row="section 8 pairing",
    )
    check(
        "the per-document differences and the UNWEIGHTED mean are exact, over documents",
        (10, 20, 15.0, 2),
        (
            _row_field(head["n_margin_numbered_lines"]["per_document"], 0, "difference"),
            _row_field(head["n_margin_numbered_lines"]["per_document"], 1, "difference"),
            head["n_margin_numbered_lines"]["unweighted_mean_difference"],
            head["n_margin_numbered_lines"]["n_documents"],
        ),
        "the mean is not the unweighted mean of the per-document differences",
        row="section 8 pairing",
    )
    # HEADING-COUNT WEIGHTING would give a different number on this fixture: A has 1 heading and B
    # has 3, so a weighted mean is (10*1 + 20*3)/4 = 17.5 against the unweighted 15.0.
    weighted = (10 * 1 + 20 * 3) / 4
    check(
        "...and the heading-count-WEIGHTED mean differs, so the fixture can tell them apart",
        (17.5, True),
        (weighted, weighted != head["n_margin_numbered_lines"]["unweighted_mean_difference"]),
        "both means agree on this fixture, so 'unweighted' was never actually tested",
        row="section 8 pairing",
    )
    check(
        "P-head and P-robust are reported SEPARATELY, with no combined mean anywhere",
        ([MC.P_HEAD, "P-robust"], 15.0, 100.0, True),
        (
            sorted(paired["by_population"]),
            head["n_margin_numbered_lines"]["unweighted_mean_difference"],
            robust["n_margin_numbered_lines"]["unweighted_mean_difference"],
            paired["populations_never_pooled"],
        ),
        "the two populations are pooled into one mean, mixing a heading-bearing population with one "
        "the study claims no heading metric on -- and section 4.4.1 never pools them",
        row="section 8 pairing",
    )
    pooled_mean = (10 + 20 + 100) / 3
    check(
        "...and the POOLED mean is a different number that appears NOWHERE in the payload",
        (43.333333333333336, False),
        (
            pooled_mean,
            any(isinstance(node, float) and abs(node - pooled_mean) < 1e-9 for _p, node in _walk(scored)),
        ),
        "the pooled 3-document mean is reported somewhere in the artifact, so a reader can quote a "
        "figure the population rule forbids",
        row="section 8 pairing",
    )
    check(
        "per-document detail is MANDATORY: every document in each population has a row",
        (2, 1, 2, 1),
        (
            len(head["n_margin_numbered_lines"]["per_document"]),
            len(robust["n_margin_numbered_lines"]["per_document"]),
            len(head["coverage"]["per_document"]),
            len(robust["coverage"]["per_document"]),
        ),
        "only the mean is reported, so a large single-document delta cannot be distinguished from a "
        "population-wide shift",
        row="section 8 pairing",
    )
    check(
        "coverage pairs too, and its P-head mean is the unweighted 0.0 (+0.05 and -0.05)",
        (0.0, 2),
        (
            round(head["coverage"]["unweighted_mean_difference"], 12),
            head["coverage"]["n_documents"],
        ),
        "the second R9 quantity is not actually paired, or its mean is not unweighted",
        row="section 8 pairing",
    )
    check(
        "no M1-M5 or M7 quantity is present in the paired block",
        [],
        sorted(
            q
            for pop in paired["by_population"].values()
            for q in pop
            if q not in ("n_margin_numbered_lines", "coverage")
        ),
        "a potentially VACUOUS metric is paired, which requires a missingness rule R9 declined to "
        "invent -- and the old implementation dropped VACUOUS documents silently",
        row="section 8 pairing",
    )
    return {
        "quantities": paired["quantities"],
        "p_head": {q: head[q]["unweighted_mean_difference"] for q in head},
        "p_robust": {q: robust[q]["unweighted_mean_difference"] for q in robust},
        "weighted_would_be": weighted,
        "pooled_would_be": pooled_mean,
    }


def part_adequacy() -> dict:
    print("\n== section 4.5 adequacy facts (A28.1 / A28.2 / A30.4) ==")
    kinds = ("account", "agency", "grouping", "section", "title")
    occ = {
        arm: [occurrence(1, i, i * 2 + 2, kind=kind, text=f"H{i}") for i, kind in enumerate(kinds)]
        for arm in ("H", "X")
    }
    head = frame([page_input(1)], document="HEAD/1", occurrences=occ)
    facts = SM.adequacy_facts([head], {"HEAD/1": 1})
    check(
        "only account / agency / grouping occurrences count, and both arms count ONCE",
        (3, sorted(MC.ADEQUACY_KINDS)),
        (facts["n_occurrences"], facts["kinds_counted"]),
        "the adequacy denominator is widened to title/division/section, which would make the "
        "holdout look more adequate than the frozen quantity it is compared against",
    )
    robust = frame([page_input(1)], document="ROBUST/1", population="P-robust", occurrences=occ)
    with_robust = SM.adequacy_facts([head, robust], {"HEAD/1": 1, "ROBUST/1": 4})
    check(
        "a P-robust document adds NOTHING to the occurrence count (A28.1 via A30.4)",
        3,
        with_robust["n_occurrences"],
        "a P-robust document inflates the adequacy count, and a larger count reads as MORE "
        "adequate -- the caller-obligation hole A30.4 closed",
    )
    # --- THE EMPTY-MAPPING ESCAPE HATCH. An absent stratum is missing INPUT, not a thin holdout;
    # letting it through produced "0 strata filled" and therefore a real-looking INADEQUATE verdict
    # about the population, which is the worst possible way to fail closed.
    one_doc = frame([page_input(1)], document="SYNTHETIC/1")
    two_docs = [one_doc, frame([page_input(1)], document="SYNTHETIC/2", sha=DOC_SHA_B)]
    check(
        "NEGATIVE -- an EMPTY strata mapping REFUSES instead of reporting a false INADEQUATE",
        SM.STRATUM_MISSING,
        refusal(lambda: SM.score(inputs([one_doc], strata={}))),
        "an empty mapping bypasses the check, so section 4.5 counts zero strata filled and prints "
        "INADEQUATE -- turning input the caller never supplied into a finding about the holdout",
    )
    check(
        "NEGATIVE -- ONE missing document in a multi-document set REFUSES",
        SM.STRATUM_MISSING,
        refusal(lambda: SM.score(inputs(two_docs, strata={"SYNTHETIC/1": 1}))),
        "a partially supplied mapping is accepted, so the strata-filled count silently undercounts "
        "and the adequacy verdict is computed on a population that was never fully described",
    )
    check(
        "...and a COMPLETE mapping scores, so the refusals are not refusing everything",
        None,
        refusal(lambda: SM.score(inputs(two_docs, strata={"SYNTHETIC/1": 1, "SYNTHETIC/2": 2}))),
        "a complete mapping is refused too, so the two negatives prove nothing about completeness",
    )
    check(
        "the A28.2 state machine's verdict is reported as a fact, with its owner named",
        ("INADEQUATE", True),
        (facts["verdict"], "decide_architecture" in facts["owner"]),
        "the scorer applies Rule 3's consequence, taking a decision A27.6 assigns elsewhere",
    )
    # 8 strata x 100 distinct occurrences = the frozen 800. Each document needs its OWN sha, or
    # the keys collide across documents and the union counts 100 rather than 800 -- which is
    # itself the A28.1 union semantics working correctly.
    generous = SM.adequacy_facts(
        [
            frame(
                [page_input(1)],
                document=f"D/{i}",
                sha=hashlib.sha256(f"x27-adequacy-{i}".encode()).hexdigest(),
                occurrences={
                    arm: [
                        occurrence(
                            1,
                            j % 8,
                            j * 2 + 2,
                            kind="account",
                            text=f"A{j}",
                            sha=hashlib.sha256(f"x27-adequacy-{i}".encode()).hexdigest(),
                        )
                        for j in range(100)
                    ]
                    for arm in ("H", "X")
                },
            )
            for i in range(8)
        ],
        {f"D/{i}": i for i in range(8)},
    )
    check(
        "...and the machine really can return the other states, so INADEQUATE is not hardcoded",
        ("GENERALISABLE", 8),
        (generous["verdict"], generous["strata_filled"]),
        "every population is INADEQUATE, so the verdict carries no information",
    )
    return {"head_only": facts, "with_robust": with_robust["n_occurrences"], "generous": generous["verdict"]}


def part_qualification() -> dict:
    print("\n== I13: the PDFIUM-CONDITIONED FRAME label, and the one-third rule ==")
    docs = [f"DOC/{i}" for i in range(6)]
    one = SM.qualification(cross_engine_artifact(docs, failed={"DOC/0"}))
    two = SM.qualification(cross_engine_artifact(docs, failed={"DOC/0", "DOC/1"}))
    three = SM.qualification(cross_engine_artifact(docs, failed={"DOC/0", "DOC/1", "DOC/2"}))
    check(
        "a failing document is labelled, and the label never blocks",
        (SM.PDFIUM_CONDITIONED_FRAME, None, False),
        (one["per_document"]["DOC/0"], one["per_document"]["DOC/1"], one["decision_blocking"]),
        "a cross-engine failure blocks the decision, which A27.6 forbids -- x09 qualifies reporting and nothing else",
    )
    check(
        "EXACTLY one third does not qualify both headlines; MORE than one third does",
        (False, True, True),
        (two["both_headlines_qualified"], three["both_headlines_qualified"], one["n_failed"] == 1),
        "the one-third rule is implemented as >= rather than >, so a compliant run acquires a "
        "qualification it did not earn (or the reverse)",
    )
    check(
        "NEGATIVE -- a scored document missing from the cross-engine artifact REFUSES",
        SM.CROSS_ENGINE_DOCUMENT_MISSING,
        # An EMPTY population, so this isolates "missing" -- a wrong-document artifact would now
        # trip the extra-document check first and this control would pass for that reason instead.
        refusal(lambda: SM.score(inputs([frame([page_input(1)])], cross_engine=cross_engine_artifact([])))),
        "a document is scored with no cross-engine verdict, so it could never acquire the "
        "qualification the rule attaches to it -- the silent-escape case max(1, ...) exists for",
    )

    # ---- THE POPULATION IS A DENOMINATOR, so it must be EXACT, and the refusal must come
    # ---- BEFORE `qualification` runs. Each fixture below is individually well-formed; only the
    # ---- SET is wrong, which is what makes these meaningful rather than malformedness tests.
    print("\n-- the cross-engine document population is exact")
    scored_docs = [frame([page_input(1)], document="SYNTHETIC/1")]

    def with_rows(rows):
        return SM.score(inputs(scored_docs, cross_engine={"schema": "cross_engine_control/1", "per_document": rows}))

    ok_row = {"document": "SYNTHETIC/1", "passed": True, "qualification": None}
    fail_row = {"document": "SYNTHETIC/1", "passed": False, "qualification": "Q"}
    check(
        "the exactly-matching population SCORES, so the refusals below are not refusing everything",
        None,
        refusal(lambda: with_rows([ok_row])),
        "an exact cross-engine population is refused, making every negative below meaningless",
    )
    check(
        "NEGATIVE -- one EXTRA passing row REFUSES rather than diluting the one-third fraction",
        SM.CROSS_ENGINE_EXTRA_DOCUMENT,
        refusal(lambda: with_rows([ok_row, {"document": "NOT/SCORED", "passed": True, "qualification": None}])),
        "an unscored passing document enlarges the denominator of I13's `> 1/3` rule, so a run "
        "that earned the both-headlines qualification can have it diluted away",
    )
    check(
        "NEGATIVE -- one EXTRA failing row REFUSES rather than manufacturing the qualification",
        SM.CROSS_ENGINE_EXTRA_DOCUMENT,
        refusal(lambda: with_rows([ok_row, {"document": "NOT/SCORED", "passed": False, "qualification": "Q"}])),
        "an unscored FAILING document can push a clean run over `> 1/3` and qualify both "
        "headlines on evidence about a document the study did not score",
    )
    check(
        "NEGATIVE -- a DUPLICATED document with conflicting verdicts REFUSES, never order-dependent",
        SM.CROSS_ENGINE_DUPLICATE_DOCUMENT,
        refusal(lambda: with_rows([ok_row, fail_row])),
        "two rows for one document are both consumed, so the reported verdict depends on which "
        "row is read last -- a silent order dependence in a reported qualification",
    )
    check(
        "...and the reverse row order refuses IDENTICALLY, so the refusal is not itself ordered",
        SM.CROSS_ENGINE_DUPLICATE_DOCUMENT,
        refusal(lambda: with_rows([fail_row, ok_row])),
        "the duplicate refusal depends on row order, so one arrangement would still be accepted",
    )
    # The refusal must precede qualification: a `qualification()` computed on the extra row would
    # be a REPORTED number, and this proves none is ever produced from a wrong population.
    # `refusal_any` rather than `refusal`: without the structural check these inputs escape as a
    # bare KeyError from deep inside the scorer, and a control that only asserts "something raised"
    # cannot tell a deterministic refusal from an accidental crash.
    check(
        "NEGATIVE -- a row missing `passed` REFUSES structurally, before any verdict is read",
        ("ScoreInputError", SM.CROSS_ENGINE_ROW_MALFORMED),
        refusal_any(lambda: with_rows([{"document": "SYNTHETIC/1", "qualification": None}])),
        "a row with no verdict reaches `qualification`, where an absent key either raises far from "
        "the cause or -- with a `.get` default -- invents a verdict for a real document",
    )
    check(
        "NEGATIVE -- a row missing `document` REFUSES too, deterministically and not as a KeyError",
        ("ScoreInputError", SM.CROSS_ENGINE_ROW_MALFORMED),
        refusal_any(lambda: with_rows([ok_row, {"passed": False}])),
        "an anonymous row is counted into I13's denominator, so a verdict about nothing changes the "
        "both-headlines qualification",
    )
    check(
        "the refusal happens at INPUT VALIDATION, before any qualification is computed",
        (SM.CROSS_ENGINE_EXTRA_DOCUMENT, "validate_inputs"),
        (
            refusal(lambda: with_rows([ok_row, {"document": "NOT/SCORED", "passed": False, "qualification": "Q"}])),
            _refusal_frame(
                lambda: with_rows([ok_row, {"document": "NOT/SCORED", "passed": False, "qualification": "Q"}])
            ),
        ),
        "the population check runs after qualification, so a wrong denominator is computed and "
        "only then rejected -- and a partial payload may already have been produced",
    )
    return {
        "one": one,
        "two_of_six": two["both_headlines_qualified"],
        "three_of_six": three["both_headlines_qualified"],
    }


def _refusal_frame(fn) -> str | None:
    """The function name that RAISED, so a control can pin WHERE a refusal happens."""
    try:
        fn()
    except SM.ScoreInputError as exc:
        tb = exc.__traceback__
        name = None
        while tb is not None:
            name = tb.tb_frame.f_code.co_name
            tb = tb.tb_next
        return name
    return None


def part_refusals(tmp: Path) -> dict:
    print("\n== malformed and INCOMPLETE input refuses; nothing is skipped ==")
    good = frame([page_input(1)])
    cases = {}

    no_m9 = copy.deepcopy(good)
    del no_m9["m9"]
    cases[SM.MISSING_REQUIRED_FIELD] = refusal(lambda: SM.score(inputs([no_m9])))

    duplicate_doc = [copy.deepcopy(good), copy.deepcopy(good)]
    cases[SM.DUPLICATE_DOCUMENT_IDENTITY] = refusal(lambda: SM.score(inputs(duplicate_doc)))
    # THE LAYER MATTERS HERE, and only here. `methodology_contracts` defines the same reason
    # STRING and its frozen document-vector validator sits one layer below, so the reason alone
    # passes whether or not the scorer's own guard exists -- found by deleting that guard and
    # watching this suite stay green. Two independent layers refuse a duplicated document, which
    # is good defence; this check pins the outer one so its removal is visible.
    duplicate_layer = refusal_detail(lambda: SM.score(inputs(duplicate_doc)))

    bad_population = copy.deepcopy(good)
    bad_population["population"] = "P-something"
    cases[SM.UNKNOWN_POPULATION] = refusal(lambda: SM.score(inputs([bad_population])))

    half_status = copy.deepcopy(good)
    half_status["architecture_occurrences"]["H"] = [
        {**occurrence(1, 2, 4), "match_status": "MATCHABLE", "occurrence_key": None}
    ]
    cases[SM.OCCURRENCE_RECORD_INCOMPLETE] = refusal(lambda: SM.score(inputs([half_status])))

    duplicate_key = copy.deepcopy(good)
    duplicate_key["architecture_occurrences"]["H"] = [occurrence(1, 2, 4), occurrence(1, 2, 4)]
    cases[SM.DUPLICATE_OCCURRENCE_KEY] = refusal(lambda: SM.score(inputs([duplicate_key])))

    not_a_sequence = SM.ScoreInputs(
        frames=good, oracle_key=EMPTY_KEY, oracle_adjudicated=EMPTY_ADJUDICATED, cross_engine={}, s1={}
    )
    cases[SM.FRAMES_NOT_A_SEQUENCE] = refusal(lambda: SM.score(not_a_sequence))

    _f, built, adjudicated = join_fixture(tmp, n_pages=1)
    orphan_key = copy.deepcopy(built.key)
    for record in orphan_key["stimuli"].values():
        record["document"] = "A DOCUMENT WITH NO FRAME"
    cases[SM.STIMULUS_DOCUMENT_NOT_IN_FRAMES] = refusal(
        lambda: SM.score(inputs([good], key=orphan_key, adjudicated=adjudicated))
    )

    missing_answer = {k: (dict(v) if isinstance(v, dict) else v) for k, v in adjudicated.items()}
    missing_answer[BO.ROUTE_AI] = {}
    cases[BO.ADJUDICATION_ROUTE_MISSING] = refusal(
        lambda: SM.score(inputs([_f], key=built.key, adjudicated=missing_answer))
    )

    control_in_frame = copy.deepcopy(built.key)
    for record in control_in_frame["stimuli"].values():
        record["control_kind"] = "N-A"
    cases[SM.CONTROL_STIMULUS_IN_ESTIMAND] = refusal(
        lambda: SM.score(inputs([_f], key=control_in_frame, adjudicated=adjudicated))
    )

    check(
        "every malformed or incomplete input REFUSES with its own reason",
        {reason: reason for reason in cases},
        cases,
        "a malformed record is skipped, scored, or refused under the wrong reason -- and a "
        "skipped record moves a denominator with nothing to show for it",
    )
    check(
        "a duplicated document is refused by the SCORER, not only by the section 8 helper",
        ("ScoreInputError", SM.DUPLICATE_DOCUMENT_IDENTITY),
        duplicate_layer,
        "the scorer's own duplicate-document guard is gone and the refusal is coming from the "
        "frozen section 8 vector validator instead -- which shares the reason STRING, so the "
        "check above cannot see the difference and stays green with the guard deleted",
    )
    check(
        "...and the equivalent WELL-FORMED input still scores, so nothing above refuses blindly",
        None,
        refusal(lambda: SM.score(inputs([good]))),
        "valid input is refused too, so the refusals prove nothing about malformedness",
    )
    return {"refusals": cases, "duplicate_document_layer": duplicate_layer}


def part_attacks(tmp: Path) -> dict:
    print("\n== additional false-green attacks ==")
    f, built, adjudicated = join_fixture(tmp, n_pages=2)
    base = SM.score(inputs([f], key=built.key, adjudicated=adjudicated))
    base_json = json.dumps(base, sort_keys=True, default=str)
    out = {}

    # --- 1. change record IDENTITY, preserve the aggregate count.
    reidentified = copy.deepcopy(f)
    reidentified["architecture_occurrences"]["H"] = [
        {**r, "occurrence_key": [r["occurrence_key"][0], r["occurrence_key"][1], r["occurrence_key"][2], 999]}
        for r in reidentified["architecture_occurrences"]["H"]
    ]
    r_built = BO.build([{"frame": reidentified, "pdf_path": synthetic_pdf(tmp, 2), "stratum": "SYNTHETIC"}])
    r_scored = SM.score(
        inputs([reidentified], key=r_built.key, adjudicated=synthesize_adjudication(r_built.key, truth="X"))
    )
    out["reidentified_matched"] = r_scored["headings_pooled"][BO.C_FRAME]["counts"]["n_matched"]["H"]
    check(
        "ATTACK -- changing an occurrence's identity while keeping the COUNT identical is caught",
        (2, 0),
        (base["headings_pooled"][BO.C_FRAME]["counts"]["n_matched"]["H"], out["reidentified_matched"]),
        "the join counts records rather than identities, so a heading matched to the wrong "
        "occurrence scores as a match",
    )

    # --- 2. swap two DOCUMENT identities.
    a = frame(
        [page_input(1, h_anchors={0: {anchor(1, 3)}}, x_anchors={0: {anchor(1, 3, text="OTHER")}})], document="A/1"
    )
    b = frame([page_input(1)], document="B/1")
    straight = SM.section8([a, b], {}, {})
    swapped_a = frame(
        [page_input(1, h_anchors={0: {anchor(1, 3)}}, x_anchors={0: {anchor(1, 3, text="OTHER")}})], document="B/1"
    )
    swapped_b = frame([page_input(1)], document="A/1")
    swapped = SM.section8([swapped_a, swapped_b], {}, {})
    events_straight = {e["document"]: e["event"] for e in straight["per_document"]}
    events_swapped = {e["document"]: e["event"] for e in swapped["per_document"]}
    check(
        "ATTACK -- swapping two document identities MOVES the per-document evidence",
        ({"A/1": True, "B/1": False}, {"A/1": False, "B/1": True}),
        (events_straight, events_swapped),
        "the per-document record does not follow the document identity, so a finding could be "
        "reported against the wrong bill",
    )
    check(
        "...while the aggregate is unchanged, which is why the per-document detail is mandatory",
        (straight["events"], straight["n_documents"]),
        (swapped["events"], swapped["n_documents"]),
        "the aggregate moved too, so this attack could have been caught by a total alone",
    )

    # --- 3. corrupt the committed SUMMARY. The scorer must recompute from the records.
    lying_counts = copy.deepcopy(f)
    lying_counts["counts"] = {k: 0 for k in lying_counts["counts"]}
    lying_counts["d_frame_census"] = []
    l_built = BO.build([{"frame": lying_counts, "pdf_path": synthetic_pdf(tmp, 2), "stratum": "SYNTHETIC"}])
    l_scored = SM.score(inputs([lying_counts], key=l_built.key, adjudicated=synthesize_adjudication(l_built.key)))
    check(
        "ATTACK -- zeroing the frame's own `counts` summary changes NOTHING",
        base["per_document"]["SYNTHETIC/1"]["M0"]["risk_set"],
        l_scored["per_document"]["SYNTHETIC/1"]["M0"]["risk_set"],
        "the scorer reads the committed summary instead of the records, so a wrong summary "
        "silently becomes the reported result",
    )

    # --- 4. permute the input ORDER.
    two_docs = [f, frame([page_input(1)], document="SYNTHETIC/2")]
    forward = SM.score(inputs(two_docs, key=built.key, adjudicated=adjudicated))
    reverse = SM.score(inputs(list(reversed(two_docs)), key=built.key, adjudicated=adjudicated))
    check(
        "ATTACK -- reversing the document order gives a byte-identical payload",
        json.dumps(forward, sort_keys=True, default=str),
        json.dumps(reverse, sort_keys=True, default=str),
        "the caller's listing order changes a reported number, so two runs over the same "
        "population print different results",
    )
    reordered_pages = copy.deepcopy(f)
    reordered_pages["pages"] = list(reversed(reordered_pages["pages"]))
    p_built = BO.build([{"frame": reordered_pages, "pdf_path": synthetic_pdf(tmp, 2), "stratum": "SYNTHETIC"}])
    p_scored = SM.score(inputs([reordered_pages], key=p_built.key, adjudicated=synthesize_adjudication(p_built.key)))
    check(
        "...and reversing the PAGE order leaves every M0 quantity identical",
        {
            k: base["per_document"]["SYNTHETIC/1"]["M0"][k]
            for k in ("risk_set", "M0a_text", "M0b_segmentation", "both_absent")
        },
        {
            k: p_scored["per_document"]["SYNTHETIC/1"]["M0"][k]
            for k in ("risk_set", "M0a_text", "M0b_segmentation", "both_absent")
        },
        "page order changes M0, so the artifact's page ordering is load-bearing when it must not be",
    )

    # --- 5. the base payload is stable, so every 'changed' verdict above means something.
    check(
        "the unattacked payload is reproducible, so 'it changed' is evidence",
        base_json,
        json.dumps(SM.score(inputs([f], key=built.key, adjudicated=adjudicated)), sort_keys=True, default=str),
        "the scorer is not deterministic, so no attack above can be distinguished from noise",
    )
    return out


def part_controls_and_repeats(tmp: Path) -> dict:
    """Controls and R1 repeats must not move a single denominator."""
    print("\n== controls and R1 repeats are excluded, and the exclusion is INVARIANT ==")
    # 12 pages, EVERY region discordant. The C-frame is capped at 8 regions per document (A27.2),
    # so a concordant 12-page fixture yields 8 primaries and `plan_r1_repeats`' floor(8 * 0.10) is
    # ZERO -- the vacuous case. The D-frame is an uncapped census, so making every region
    # discordant gives 12 primaries and exactly one repeat.
    n_pages = 12
    pages = [page_input(p + 1, start_gid=p * 100, text_differs={5}) for p in range(n_pages)]
    occ = {arm: [occurrence(p + 1, 2, p * 100 + 4) for p in range(n_pages)] for arm in ("H", "X")}
    f = frame(pages, occurrences=occ)
    pdf = synthetic_pdf(tmp, n_pages)

    plain = BO.build([{"frame": f, "pdf_path": pdf, "stratum": "SYNTHETIC"}])
    manifest = json.loads(CF.MANIFEST_PATH.read_text())
    with_controls = BO.build(
        [{"frame": f, "pdf_path": pdf, "stratum": "SYNTHETIC"}], controls=BO.control_specs(manifest, EV, REPO)
    )

    n_repeats = sum(1 for r in plain.key["stimuli"].values() if r["is_r1_repeat"])
    n_controls = sum(1 for r in with_controls.key["stimuli"].values() if r["control_kind"] is not None)
    check(
        "the fixture really contains R1 repeats and real controls, so the invariance is not vacuous",
        (True, 20),
        (n_repeats >= 1, n_controls),
        "no repeat or control is present, so 'adding them changed nothing' was guaranteed",
    )

    plain_scored = SM.score(inputs([f], key=plain.key, adjudicated=synthesize_adjudication(plain.key)))
    loaded_scored = SM.score(inputs([f], key=with_controls.key, adjudicated=synthesize_adjudication(with_controls.key)))
    strip = lambda payload: {  # noqa: E731
        "pooled": payload["headings_pooled"],
        "per_document": payload["per_document"],
        "section8": payload["section8"],
        "adequacy": payload["adequacy_4_5"],
    }
    check(
        "adding 20 REAL controls moves no metric, no denominator and no section 8 figure",
        json.dumps(strip(plain_scored), sort_keys=True, default=str),
        json.dumps(strip(loaded_scored), sort_keys=True, default=str),
        "a control contributed to an estimand it exists only to bound, which would put "
        "deliberately altered text into a correctness denominator",
    )
    # WHICH CHECK GUARDS WHAT, measured by injection rather than assumed. Deleting the scorer's
    # `control_kind` skip does NOT move the invariance check above: a control carries `frames == ()`
    # (A40 F5), so the frame-membership filter refuses it a second time and no metric moves. The
    # count below is what makes the deletion visible, and `part_refusals`' CONTROL_STIMULUS_IN_ESTIMAND
    # covers the remaining case -- a control that somehow claims frame membership.
    check(
        "...and the exclusions are COUNTED rather than silent",
        (20, n_repeats),
        (
            loaded_scored["heading_population_notes"]["excluded_stimuli"]["control"],
            loaded_scored["heading_population_notes"]["excluded_stimuli"]["r1_repeat"],
        ),
        "the excluded stimuli are invisible in the artifact, so a reader cannot see what was "
        "left out of the denominators",
    )
    # The expected stimulus count is DERIVED from the committed frame, not asserted: the C-frame
    # cap and the D census are `build_frames`' business, and hardcoding a number here would make
    # this control fail whenever that (frozen, separately tested) arithmetic changed.
    c_regions = sum(1 for page in f["pages"] for r in page["regions"] if r["c_frame"])
    d_regions = sum(1 for page in f["pages"] for r in page["regions"] if r["d_frame"])
    counts = {name: plain_scored["headings_pooled"][name]["counts"] for name in (BO.C_FRAME, BO.D_FRAME)}
    check(
        "an R1 repeat does not double-count its primary's region, in EITHER frame",
        {BO.C_FRAME: (c_regions, c_regions), BO.D_FRAME: (d_regions, d_regions)},
        {name: (c["n_stimuli"], c["n_adjudicated"]) for name, c in counts.items()},
        "a repeat is scored as an independent stimulus, so one physical occurrence enters a "
        "denominator twice -- and the repeat exists to measure the ADJUDICATOR, not the arms",
    )
    check(
        "...and the two frames really are different sizes here, so C and D are not interchangeable",
        (8, 12, True),
        (c_regions, d_regions, c_regions != d_regions),
        "C and D have the same population in this fixture, so a scorer that pooled them or read "
        "the wrong one would look correct",
    )
    return {"n_repeats": n_repeats, "n_controls": n_controls, "c_regions": c_regions, "d_regions": d_regions}


def part_reproducibility(tmp: Path) -> dict:
    print("\n== reproducibility, and no live object is required ==")
    f, built, adjudicated = join_fixture(tmp, n_pages=2)
    first = SM.score(inputs([f], key=built.key, adjudicated=adjudicated))
    second = SM.score(inputs([f], key=built.key, adjudicated=adjudicated))
    check(
        "two runs over the same inputs produce byte-identical output",
        json.dumps(first, sort_keys=True, default=str),
        json.dumps(second, sort_keys=True, default=str),
        "the scorer is not deterministic, so no reported number is reproducible",
    )
    # A38's central claim, exercised: every input round-trips through JSON, so nothing survives
    # only in a live Python object still holding a PDF handle or a runner result.
    round_tripped = SM.ScoreInputs(
        frames=tuple(json.loads(json.dumps(x, default=str)) for x in [f]),
        oracle_key=json.loads(json.dumps(built.key, default=str)),
        oracle_adjudicated=json.loads(json.dumps(adjudicated, default=str)),
        cross_engine=json.loads(json.dumps(cross_engine_artifact([f["document"]]), default=str)),
        s1=json.loads(json.dumps(s1_artifact(), default=str)),
        document_strata={f["document"]: 1},
    )
    check(
        "scoring COMMITTED JSON alone reproduces the same payload -- no PDF, no runner",
        json.dumps(first, sort_keys=True, default=str),
        json.dumps(SM.score(round_tripped), sort_keys=True, default=str),
        "a fact the scorer needs survives only in a live Python object, so it would have to "
        "reopen a PDF or rerun an architecture to score",
    )
    return {"payload_sha256": hashlib.sha256(json.dumps(first, sort_keys=True, default=str).encode()).hexdigest()}


#: Run in a CHILD interpreter by `_renderer_free_probe`. It blocks the PDF renderer at the import
#: system rather than relying on an environment that happens to lack one: the x27 interpreter DOES
#: carry `pymupdf` (this module imports it), so without the blocker the property would be tested
#: against a renderer that is present, and would pass for the wrong reason.
RENDERER_FREE_CHILD = '''
import json
import sys

BLOCKED = {"pymupdf", "fitz"}


class _RendererBlocker:
    """Make the PDF renderer genuinely unimportable, so no installed copy can answer instead."""

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError("No module named %r" % name)
        return None


for _loaded in [m for m in sys.modules if m.split(".")[0] in BLOCKED]:
    del sys.modules[_loaded]
sys.meta_path.insert(0, _RendererBlocker())
sys.path.insert(0, sys.argv[1])

out = {}

# (a) Is the blocker actually blocking? Without this the whole probe passes vacuously -- an
#     interpreter with no renderer installed looks identical to a scorer that needs none.
try:
    import build_oracle  # noqa: F401

    out["blocker_live"] = False
except ModuleNotFoundError as exc:
    out["blocker_live"] = "pymupdf" in str(exc)

# (b) The property under test: the scorer imports anyway.
try:
    import score_metrics as SM

    out["scorer_imports"] = True
except BaseException as exc:
    out["scorer_imports"] = False
    out["scorer_import_error"] = "%s: %s" % (type(exc).__name__, exc)

if out["scorer_imports"]:
    # (c) It does not merely import: JSON-only scoring still WORKS. A27.5 assigns the general
    #     Clopper-Pearson bound to the scorer itself, so it depends on no oracle helper.
    out["section8_bound"] = round(SM.clopper_pearson_upper(0, 14), 4)
    # (d) ...and the frozen owners are still reached rather than locally restated. A
    #     `build_oracle`-owned derivation must still route into `build_oracle`, and so must still
    #     fail loudly when the renderer is genuinely absent. Silence here would mean the
    #     dependency was removed by copying a frozen rule.
    try:
        SM.frozen_control_routes()
        out["bo_owned_still_delegates"] = False
    except ModuleNotFoundError as exc:
        out["bo_owned_still_delegates"] = "pymupdf" in str(exc)

print(json.dumps(out))
'''


def _renderer_free_probe(tmp: Path) -> dict:
    """Import and exercise the scorer in a child interpreter that cannot import a PDF renderer."""
    script = tmp / "renderer_free_child.py"
    script.write_text(RENDERER_FREE_CHILD)
    proc = subprocess.run(
        [sys.executable, str(script), str(HERE.parent)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        # Returned rather than raised: a crash cannot distinguish "the rule broke" from "the
        # probe has a bug", so the failure has to land on a named check.
        return {"child_failed": (proc.stderr or "<no stderr>").strip()[-800:]}
    return json.loads(proc.stdout.strip().splitlines()[-1])


def part_boundary(tmp: Path) -> dict:
    print("\n== the execution boundary, and what this module may not touch ==")
    payload = {"schema": SM.SCHEMA}
    check(
        "writing the CANONICAL metrics.json REFUSES before a valid execution boundary",
        BO.CONFIRMATORY_WRITE_BEFORE_EXECUTION,
        refusal(lambda: SM.write_metrics(payload, EV / "results" / "metrics.json")),
        "a confirmatory scoring artifact can be created before execution is authorised, which "
        "is the one-way boundary A11 exists to enforce",
    )
    scratch = SM.write_metrics(payload, tmp / "metrics.json")
    check(
        "...and an ordinary path still writes, so the guard is not refusing everything",
        True,
        scratch.exists(),
        "the writer refuses every path, so the control above proves nothing about the boundary",
    )

    # The import graph, from the AST rather than from a substring search. A prose mention of
    # "PDFIUM-CONDITIONED FRAME" is not a call, and a scan that cannot tell the difference either
    # fails on the honest docstring or passes on a real import hidden in a long line.
    source = (HERE.parent / "score_metrics.py").read_text()
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    permitted = {
        "__future__",
        "collections",
        "math",
        "sys",
        "json",
        "dataclasses",
        "pathlib",
        "build_frames",
        "build_oracle",
        "m3_boundaries",
        "methodology_contracts",
        "neutral_identity",
        "xml_sources",
    }
    check(
        "the scorer imports NOTHING outside the frozen consumer allowlist",
        set(),
        imported - permitted,
        "the scorer imports an architecture, an engine, a runner or the contamination probe, "
        "which would make it a producer rather than a consumer of committed facts",
    )
    forbidden_calls = {
        "run_hybrid.run": "run_hybrid" in imported,
        "run_extended.run": "run_extended" in imported,
        "x01_contamination": any(name.startswith("x01") for name in imported),
        "an engine": bool(imported & {"pypdfium2", "pymupdf", "fitz"}),
        "extract_anchors": "pdf_anchors" in imported or "extract_anchors(" in source,
        "filesystem_discovery": any(token in source for token in ("rglob", "glob(", "os.walk", "iterdir")),
    }
    check(
        "...and it neither runs an arm, re-extracts anchors, nor enumerates the repository",
        {k: False for k in forbidden_calls},
        forbidden_calls,
        "the scorer can run an architecture, re-run anchor recognition, or discover files on "
        "disk -- and the contamination evidence is exactly what repo discovery would rewrite",
    )
    # --- the renderer dependency, asked of the INTERPRETER rather than of the source.
    #
    # A38 exists so the scorer consumes committed JSON and nothing else. That was true of the DATA
    # path and false of the IMPORT line: `score_metrics` imported `build_oracle` at module scope,
    # and `build_oracle` imports `pymupdf` at module scope because rendering adjudication stimuli
    # is part of what IT owns -- so merely importing the scorer required a PDF renderer, which is
    # the dependency A38 was written to remove. The import is now deferred to the call sites that
    # need the frozen A38.7 helpers.
    #
    # A source grep is not evidence for this. It reads the import line an author wrote, not the
    # graph the interpreter walks, and it would go on passing if any OTHER frozen dependency
    # acquired a renderer tomorrow. So the control makes the renderer genuinely unimportable in a
    # child interpreter and asks that interpreter what happens.
    renderer_free = _renderer_free_probe(tmp)
    check(
        "the scorer IMPORTS with the PDF renderer made unimportable -- and the blocker is live",
        {"blocker_live": True, "scorer_imports": True},
        {k: renderer_free.get(k) for k in ("blocker_live", "scorer_imports")},
        "importing `score_metrics` re-acquires a PDF renderer, so A38's pure-consumer property "
        "holds for the data path but not for the import graph -- or `blocker_live` is False, in "
        "which case the renderer was importable after all and this control proves nothing",
    )
    check(
        "...and JSON-only scoring still COMPUTES there: A27.5's own bound, section 8.1's 0.1926",
        0.1926,
        renderer_free.get("section8_bound"),
        "the scorer imports without a renderer but cannot actually score without one, so the "
        "property is cosmetic -- an import that reaches no working function is not a consumer",
    )
    check(
        "...and the frozen `build_oracle` owners are still DELEGATED to, never locally restated",
        True,
        renderer_free.get("bo_owned_still_delegates"),
        "a `build_oracle`-owned derivation now answers from a local copy: the dependency was "
        "removed by restating a frozen rule, and two copies of a rule are two rules",
    )
    # The precondition that makes the three checks above discriminating. If `build_oracle` ever
    # stops importing a renderer eagerly, they all pass no matter what the scorer does -- so the
    # control must be re-pointed at that moment, not quietly trusted.
    check(
        "the control is DECISIVE: `build_oracle` still imports the renderer at module scope",
        True,
        "import pymupdf" in (HERE.parent / "build_oracle.py").read_text(),
        "`build_oracle` no longer imports a renderer eagerly, so the renderer-free checks above "
        "would pass however `score_metrics` imported it -- they must be re-pointed, not trusted",
    )
    existing = {
        name: (EV / "results" / name).exists()
        for name in (
            "frames.json",
            "oracle_key.json",
            "oracle_blind.json",
            "oracle_adjudicated.json",
            "s1_control.json",
            "cross_engine_control.json",
            "metrics.json",
            "scores.json",
            "EXECUTION-START.json",
        )
    }
    check(
        "NO canonical confirmatory artifact exists after this probe",
        {name: False for name in existing},
        existing,
        "a canonical artifact was created, which would cross the execution boundary this session may not cross",
    )
    return {
        "scorer_imports": sorted(imported),
        "forbidden_calls": forbidden_calls,
        "renderer_dependency": (
            "NONE at import: `build_oracle` (which imports pymupdf at module scope) is imported "
            "lazily by `score_metrics._bo`, so the scorer imports and scores JSON-only quantities "
            "with the renderer unimportable. The frozen A38.7/A36.4 helpers are still called, so a "
            "derivation that genuinely needs them still requires the renderer"
        ),
        "renderer_free_child": renderer_free,
        "canonical_artifacts_present": existing,
    }


# ============================================================== DEVELOPMENT: the real chain

DEV_DOC = "118-hr-8752/1"
DEV_PATH = REPO / "tests/corpus/118-hr-8752/1_reported-in-house.pdf"
DEV_PAGE_LIMIT = 8  # machinery demonstration window, NOT a census


def part_development(tmp: Path) -> dict:
    """The scorer against the REAL producers, so no fixture encodes a belief about their shape.

    A synthetic frame is my belief about what `build_frames` emits. This part removes the belief:
    real `run_hybrid` / `run_extended` output, the real public `build_document_frame`, the real
    `build_oracle`, and an adjudication derived from the key's own committed facts.
    """
    print("\n== DEVELOPMENT: the whole chain on a real non-holdout document ==")
    import run_extended  # local: the PROBE may run an architecture; `score_metrics` may not
    import run_hybrid

    for member in BO.HOLDOUT_GUARD:
        if member in str(DEV_PATH):
            raise SystemExit(f"REFUSED: {DEV_PATH} touches holdout member {member}")

    h = run_hybrid.run(DEV_PATH, limit=DEV_PAGE_LIMIT)
    x, _s = run_extended.run(DEV_PATH, limit=DEV_PAGE_LIMIT)
    sha = hashlib.sha256(DEV_PATH.read_bytes()).hexdigest()
    dev_frame = BF.build_document_frame(sha, DEV_DOC, BF.P_HEAD, h, x)
    built = BO.build([{"frame": dev_frame, "pdf_path": DEV_PATH, "stratum": "DEVELOPMENT"}])
    adjudicated = synthesize_adjudication(built.key)

    scored = SM.score(
        inputs(
            [dev_frame],
            key=built.key,
            adjudicated=adjudicated,
            strata={DEV_DOC: 1},
            cross_engine=cross_engine_artifact([DEV_DOC]),
        )
    )
    check(
        "the REAL producer's frame passes every input validation unchanged",
        (DEV_DOC, BF.P_HEAD),
        (scored["documents_scored"][0], scored["per_document"][DEV_DOC]["population"]),
        "the scorer's contract disagrees with what `build_frames` actually emits, so every "
        "synthetic fixture above encodes a belief rather than the producer's shape",
    )
    m0 = scored["per_document"][DEV_DOC]["M0"]
    check(
        "M0 is computed over a real, non-empty risk set with BOTH_ABSENT held out",
        (True, True, True),
        (
            m0["risk_set"] > 0,
            m0["both_absent"] > 0,
            m0["risk_set"] + m0["both_absent"] == m0["neutral_lines_in_scope"],
        ),
        "the real document yields no risk set or no chrome, so the M0 controls above ran on "
        "material unlike anything the study will score",
    )
    # PER FRAME, and PRIMARIES ONLY. A region may be in both C and D (A36.1), where it is scored
    # once in each estimand, and an R1 repeat is outside every metric population -- so a single
    # pooled total would compare a scored figure against a census of different membership.
    resolved = {}
    for name, member in ((BO.C_FRAME, "in_c_frame"), (BO.D_FRAME, "in_d_frame")):
        resolved[name] = sum(
            1
            for record in built.key["stimuli"].values()
            if record[member] and not record["is_r1_repeat"] and record["control_kind"] is None
            for row in (record["architecture_occurrences"] or {}).get("H", [])
            if row["occurrence_key"] is not None
        )
    matched = {
        name: metrics["counts"]["n_matched"]["H"]
        for name, metrics in scored["per_document"][DEV_DOC]["headings_by_frame"].items()
    }
    check(
        "the A38.7 join binds real occurrences: every keyed occurrence in a stimulus matches",
        (True, {name: resolved[name] for name in matched}),
        (sum(resolved.values()) > 0, matched),
        "the geometric round trip through `pdf_x_to_pixel` / `pixel_to_pdf_x` does not resolve "
        "back to the same glyph on real material, so the join is unproven where it matters",
    )
    check(
        "M9's real facts carry production's own coverage floor",
        (0.85, True),
        (scored["per_document"][DEV_DOC]["M9"]["coverage_floor"], scored["section8"]["n_documents"] == 1),
        "the real M9 basis does not carry the frozen floor, so Rule 0's coverage clause could "
        "not be evaluated from committed facts",
    )
    return {
        "document": DEV_DOC,
        "page_limit": DEV_PAGE_LIMIT,
        "note": "DEV_PAGE_LIMIT is a machinery demonstration window, not a census",
        "m0": {k: m0[k] for k in ("risk_set", "both_absent", "M0a_text", "M0b_segmentation", "M0_any")},
        "m0_rates": {k: m0[k]["value"] for k in ("M0a_text_rate", "M0b_segmentation_rate", "M0_any_rate")},
        "n_stimuli": built.key["n_stimuli"],
        "keyed_occurrences_in_stimuli": resolved,
        "matched_occurrences": matched,
        "m7": {arm: scored["per_document"][DEV_DOC]["M7"][arm]["n_display_split"] for arm in ("H", "X")},
        "rule0": scored["per_document"][DEV_DOC]["M9"]["margin_line_loss"],
        "section8": {
            "events": scored["section8"]["events"],
            "bound": scored["section8"]["clopper_pearson_upper_bound"],
        },
        "adequacy": scored["adequacy_4_5"]["n_occurrences"],
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        evidence = {
            "m0": part_m0(),
            "i9": part_i9(),
            "s1": part_s1(),
            "join": part_join(tmp),
            "m3": part_m3(tmp),
            "m4": part_m4(tmp),
            "m5": part_m5(tmp),
            "r1": part_r1(tmp),
            "r8_controls": part_r8(tmp),
            "m6_and_i13": part_m6_and_i13(tmp),
            "m7": part_m7(),
            "rule0": part_rule0(),
            "section8": part_section8(),
            "pairing": part_pairing(tmp),
            "adequacy": part_adequacy(),
            "qualification": part_qualification(),
            "refusals": part_refusals(tmp),
            "attacks": part_attacks(tmp),
            "controls_and_repeats": part_controls_and_repeats(tmp),
            "reproducibility": part_reproducibility(tmp),
            "development": part_development(tmp),
            "boundary": part_boundary(tmp),
        }

    uncovered = [row for row, names in COVERED.items() if not names]
    check(
        "every section 5 control row has at least one executable check",
        [],
        uncovered,
        "a frozen control row is unimplemented, so the scorer carries a quantity nothing can falsify",
    )

    doc = {
        "population": "SYNTHETIC + DEVELOPMENT -- no holdout opened, nothing adjudicated by a human or an AI",
        "contract": "HARNESS-PLAN section 5 (the scorer) over PRE-REGISTRATION section 6 and section 8",
        "question": "does `score_metrics` compute the frozen quantities from committed artifacts, "
        "and can each of them be made to go RED?",
        "artifacts_created": "NONE of frames.json, oracle_key.json, oracle_blind.json, "
        "oracle_adjudicated.json, s1_control.json, cross_engine_control.json, metrics.json, "
        "scores.json, EXECUTION-START.json",
        "synthetic_adjudication_caveat": "the fixtures' oracle text comes from an arm's own emitted "
        "output, so every agreement figure here is evidence about the JOIN and never about accuracy",
        "section5_rows": {row: names for row, names in COVERED.items()},
        "evidence": evidence,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
