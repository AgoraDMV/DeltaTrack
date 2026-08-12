"""x28 -- HARNESS-PLAN section 6's control table, executed against `decide_architecture`.

NOT CONFIRMATORY. SYNTHETIC only. No holdout document is opened, nothing is adjudicated, no
confirmatory artifact is created, and no real architecture decision is taken. Every outcome this
probe prints is a property of a fixture built here. Evidence: `results/x28_decide_architecture.json`.

RUN WITH AN INTERPRETER CARRYING `pymupdf` AND `pypdfium2`, as `score_metrics` transitively needs.

WHAT THIS PROBE EXISTS TO PROVE, and what would make each half FALSE:

    the decider reads fields the REAL scorer really emits   part_contract -- not a hand-written dict
    every frozen rule can go RED                            the boundary sweeps and part_injection
    exactly five outcomes exist, and all five are reachable  part_enums
    incomplete evidence REFUSES rather than deciding         part_refusals
    a reporting qualification never moves an outcome         part_qualification_never_decides

THE FIXTURE DISCIPLINE, stated because it decides what these numbers are worth. Every payload
starts as REAL `score_metrics.score(...)` output over synthetic frames, so the decider is read
against the producer's own field names and shapes. Where a Rule 3 gate has to be forced to PASS to
reach a later rule, the gate STATUS is overwritten on that real payload and nothing else -- those
statuses are FIXTURES, never evidence, and `part_contract` is what stops the overwrite drifting
onto a field the scorer does not have.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import re
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
import decide_architecture as DA  # noqa: E402
import score_metrics as SM  # noqa: E402
from neutral_identity import Cell, EmittedLine, NeutralLine  # noqa: E402

OUT = EV / "results" / "x28_decide_architecture.json"
SOURCE = HERE.parent / "decide_architecture.py"
ROWS: list[dict] = []
FAILED: list[str] = []

#: HARNESS-PLAN section 6's control table, so the evidence file states which row each check
#: discharges and a final check fails if any row is unimplemented.
SECTION6_ROWS = (
    "synthetic X win (6 corrects, 0 regressions, no M4 regression)",
    "synthetic 5 corrects and 1 regression",
    "synthetic 5 corrects and 1 M4 regression",
    "synthetic census of 61 regions",
    "synthetic asymmetric M9 loss for H only",
    "synthetic asymmetric M9 loss on BOTH arms, different documents",
    "any Rule 3 gate set to FAIL",
    "x09 set to FAIL",
    "synthetic empty census",
    "wording gate",
    "M9 one-arm loss",
)
COVERED: dict[str, list[str]] = {row: [] for row in SECTION6_ROWS}

REGION = BF.REGION_SIZE
DOC_SHA = hashlib.sha256(b"x28-synthetic").hexdigest()
DOC_SHA_B = hashlib.sha256(b"x28-synthetic-b").hexdigest()
LEFT_X, RIGHT_X = 100.0, 300.0


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
    """The refusal class a callable raises, or None if it returned.

    Any OTHER exception is reported as its own type name rather than swallowed: a control that
    accepts a bare crash as evidence cannot tell "the rule refused" from "the probe has a bug",
    which A41.3's round 3 recorded as a distinct class of control defect.
    """
    try:
        fn()
    except DA.DecisionInputError as exc:
        return exc.reason
    except Exception as exc:  # noqa: BLE001 -- naming whatever came out IS the control
        return f"UNEXPECTED:{type(exc).__name__}"
    return None


# ------------------------------------------------------------------ synthetic scorer fixtures


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
        candidates=tuple((g, LEFT_X + 40.0 * (i % 2)) for i, g in enumerate(ordered)),
    )


def page_input(page_number: int, n_lines: int, text_differs=()) -> BF.PageInput:
    """One page whose X arm emits a different character on the named ordinals.

    A text discordance puts that line's REGION into the D-frame, which is how the census below is
    built by `build_frames` itself rather than written down here.
    """
    neutral, h, x, gid = [], [], [], 0
    for i in range(n_lines):
        gids = list(range(gid, gid + 2))
        neutral.append(nline(page_number, i, gids))
        gid += 2
    for i, line in enumerate(neutral):
        gids = sorted(line.gids)
        h.append(EmittedLine(cells=[Cell(ngid=g, char="A") for g in gids]))
        char = "Z" if i in text_differs else "A"
        x.append(EmittedLine(cells=[Cell(ngid=g, char=char) for g in gids]))
    return BF.PageInput(
        page_number=page_number,
        neutral=neutral,
        h_emitted=h,
        x_emitted=x,
        h_anchors_by_region={},
        x_anchors_by_region={},
    )


def m9_facts(*, band: bool = True, coverage: float = 1.0, margin: int = 120) -> dict:
    return {
        "derive_size_bands_returns_a_band": band,
        "coverage": coverage,
        "coverage_floor": 0.85,
        "coverage_meets_floor": coverage >= 0.85,
        "n_lines_total": 140,
        "n_margin_numbered_lines": margin,
        "n_margin_numbered_with_glyph_size": margin,
        "margin_numbered_line_keys": [[1, i] for i in range(margin)],
        "rule0_comparison": "RAW FACTS ONLY",
    }


def frame(*, document: str = "SYNTHETIC/1", sha: str = DOC_SHA, d_regions: int = 0, m9_h=None, m9_x=None) -> dict:
    """One committed document frame carrying EXACTLY `d_regions` D-frame regions.

    The census is produced by `build_frames` from real discordant lines and then read back, so a
    fixture cannot claim a census its own regions do not support.
    """
    n_regions = max(d_regions, 1)
    differs = {r * REGION for r in range(d_regions)}
    pages = [page_input(1, n_regions * REGION, text_differs=differs)]
    built = BF._build_document_frame_from_inputs(sha, document, BF.P_HEAD, pages)
    built["architecture_occurrences"] = {"H": [], "X": []}
    built["m9"] = {"H": m9_h or m9_facts(), "X": m9_x or m9_facts()}
    return built


EMPTY_KEY = {"schema": "oracle_key/3", "stimuli": {}}
EMPTY_ADJUDICATED = {"schema": BO.ADJUDICATED_SCHEMA, BO.ROUTE_AI: {}, BO.ROUTE_HUMAN: {}}


def scored(frames, *, s1_fires: bool = True, cross_failed=()) -> dict:
    """A payload from the REAL scorer. Every field the decider reads comes from here."""
    docs = [f["document"] for f in frames]
    return SM.score(
        SM.ScoreInputs(
            frames=tuple(frames),
            oracle_key=EMPTY_KEY,
            oracle_adjudicated=EMPTY_ADJUDICATED,
            cross_engine={
                "schema": "cross_engine_control/1",
                "per_document": [{"document": d, "passed": d not in cross_failed} for d in docs],
                "n_documents": len(docs),
            },
            s1={"schema": "s1_control/1", "advance_scale": 1.25, "fires": s1_fires, "n_firing": 1 if s1_fires else 0},
            document_strata={d: 1 for d in docs},
        )
    )


def d_pooled(
    *,
    corrects: int,
    regresses: int,
    n_stimuli: int,
    m4_regressions: int = 0,
    m4_correct: tuple = (4, 4),
    m4_scored: int = 4,
) -> dict:
    """A pooled D-frame heading block, SHAPED BY THE SCORER'S OWN producer.

    `_blank_heading_counts` and `_heading_metrics_from_counts` are `score_metrics`' own functions,
    so the block a fixture hands the decider has the structure the real run will hand it. Only the
    quantities Rule 1 reads are set: the two `m3_outcomes` tallies, the adjudicated-region count,
    and A5 row 4's PAIRED M4 fact.

    `m4_correct` is settable INDEPENDENTLY of `m4_regressions` on purpose -- the aggregates and the
    pairing are different quantities (A42.3), and a fixture that could not make them disagree could
    not test that the decider reads the right one.
    """
    counts = SM._blank_heading_counts()
    counts["n_stimuli"] = n_stimuli
    counts["m3_outcomes"]["X_CORRECTS"] = corrects
    counts["m3_outcomes"]["X_REGRESSES"] = regresses
    counts["m4_h_correct_x_wrong"] = m4_regressions
    counts["m4_h_correct_x_wrong_keys"] = [[DOC_SHA, 1, [1, 3], 6]] * m4_regressions
    counts["m4_correct"]["H"], counts["m4_correct"]["X"] = m4_correct
    counts["m4_scored"] = {arm: m4_scored for arm in ("H", "X")}
    return SM._heading_metrics_from_counts(counts, SM.r1_reliability(EMPTY_KEY, EMPTY_ADJUDICATED))


def pass_gates(payload: dict) -> dict:
    """Force every scorer-derived Rule 3 gate to PASS on a real payload.

    THESE STATUSES ARE FIXTURES AND NOT EVIDENCE. Building genuine PASSing R1, control and adequacy
    artifacts is `x27`'s job and it does it against the real oracle path; what x28 must prove is
    what the DECIDER does with a status, so the status is set and the field names it is set on are
    pinned by `part_contract` against real scorer output.
    """
    out = copy.deepcopy(payload)
    out["r1_reliability"]["text"]["status"] = DA.GATE_PASS
    out["r1_reliability"]["role"]["status"] = DA.GATE_PASS
    for kind in ("N-A", "N-B", "N-C"):
        out["control_verdicts"]["by_kind"][kind]["status"] = DA.GATE_PASS
    out["adequacy_4_5"]["verdict"] = "GENERALISABLE"
    return out


def decision(
    *,
    d_regions: int = 10,
    corrects: int = 0,
    regresses: int = 0,
    adjudicated: int | None = None,
    m4_regressions: int = 0,
    m4_correct: tuple = (4, 4),
    m9_h=None,
    m9_x=None,
    extra_frames=(),
    gates_pass: bool = True,
    s1_fires: bool = True,
    cross_failed=(),
    mutate=None,
    x2a: str = DA.GATE_PASS,
    x2b: str = DA.GATE_PASS,
) -> dict:
    """One end-to-end decision over a real scorer payload. The single fixture builder."""
    frames = [frame(d_regions=d_regions, m9_h=m9_h, m9_x=m9_x), *extra_frames]
    payload = scored(frames, s1_fires=s1_fires, cross_failed=cross_failed)
    if gates_pass:
        payload = pass_gates(payload)
    census = sum(f["counts"]["d_frame_census"] for f in frames)
    payload["headings_pooled"]["D"] = d_pooled(
        corrects=corrects,
        regresses=regresses,
        n_stimuli=census if adjudicated is None else adjudicated,
        m4_regressions=m4_regressions,
        m4_correct=m4_correct,
    )
    if mutate:
        mutate(payload)
    return DA.decide(DA.DecisionInputs(metrics=payload, frames=tuple(frames), x2a=x2a, x2b=x2b))


def outcome(**kwargs) -> str:
    return decision(**kwargs)["outcome"]


# ================================================================ the scorer/decider contract


#: Every field path `decide_architecture` reads out of the metrics payload. Written as data so the
#: check below can walk them against REAL scorer output.
CONTRACT_PATHS = (
    ("schema",),
    ("documents_scored",),
    ("decision_taken_here",),
    ("per_document",),
    ("headings_pooled",),
    ("s1", "fires"),
    ("r1_reliability", "text", "status"),
    ("r1_reliability", "role", "status"),
    ("control_verdicts", "by_kind", "N-A", "status"),
    ("control_verdicts", "by_kind", "N-B", "status"),
    ("control_verdicts", "by_kind", "N-C", "status"),
    ("adequacy_4_5", "verdict"),
    ("cross_engine_qualification", "headline_qualifications"),
    ("cross_engine_qualification", "n_failed"),
)

#: A5 row 4's paired quantity, walked against a REAL pooled block below. It lives under a frame
#: key, so it cannot be reached by the flat walk above.
POOLED_M4_PATHS = (("M4", "h_correct_x_wrong"), ("M4", "h_correct_x_wrong_occurrences"))

#: Per-document and frame paths, walked separately because they live one level down.
DOCUMENT_PATHS = (
    ("M9", "band_loss", "fires"),
    ("M9", "band_loss", "loser"),
    ("M9", "coverage_loss", "fires"),
    ("M9", "coverage_loss", "loser"),
    ("M9", "margin_line_loss", "fires"),
    ("M9", "margin_line_loss", "loser"),
    ("M9", "H", "coverage"),
    ("M9", "X", "n_margin_numbered_lines"),
)
FRAME_PATHS = (("document",), ("counts", "d_frame_census"), ("d_frame_census",), ("d_frame_truncated",))


def _real_pooled_block() -> dict:
    """A pooled heading block from `score_metrics`' OWN producer, with nothing this probe added.

    `d_pooled` sets values on top of this; here it is called bare, so a missing key is the
    SCORER's omission and cannot be one x28 papered over. The division of labour is deliberate:
    x27 proves the paired quantity is COMPUTED correctly over a real oracle key and a real
    adjudication; x28 proves the field exists where the decider reaches for it.
    """
    return SM._heading_metrics_from_counts(SM._blank_heading_counts(), SM.r1_reliability(EMPTY_KEY, EMPTY_ADJUDICATED))


def _resolve(node, path):
    for step in path:
        if not isinstance(node, dict) or step not in node:
            return None, False
        node = node[step]
    return node, True


def part_contract() -> dict:
    print("\n== the contract: every field the decider reads exists in REAL scorer output ==")
    f = frame(d_regions=3)
    payload = scored([f])
    missing = [".".join(p) for p in CONTRACT_PATHS if not _resolve(payload, p)[1]]
    check(
        "every metrics path the decider reads is present in a REAL score_metrics payload",
        [],
        missing,
        "the decider reads a field name the scorer does not emit -- the mismatch a hand-written "
        "fixture cannot see, because it encodes the decider's belief about the producer",
    )
    doc_block = next(iter(payload["per_document"].values()))
    missing_doc = [".".join(p) for p in DOCUMENT_PATHS if not _resolve(doc_block, p)[1]]
    check(
        "every per-document M9 path the decider reads is present in real scorer output",
        [],
        missing_doc,
        "Rule 0 reads an M9 clause field the scorer does not emit",
    )
    # A5 row 4's paired fact, on a pooled block the REAL scorer produced from a REAL oracle key --
    # not on `d_pooled`'s fixture. This is the check that would catch the scorer dropping the
    # quantity the ruling requires it to emit.
    real_pooled = _real_pooled_block()
    missing_pair = [".".join(p) for p in POOLED_M4_PATHS if not _resolve(real_pooled, p)[1]]
    check(
        "the PAIRED M4 fact the decider reads is emitted by the real scorer (A42.3)",
        [],
        missing_pair,
        "the scorer stopped emitting A5 row 4's paired quantity, so Rule 1's fourth condition has "
        "no producer again and the decider can only refuse",
    )
    missing_frame = [".".join(p) for p in FRAME_PATHS if not _resolve(f, p)[1]]
    check(
        "every frame path the budget reads is present in real build_frames output",
        [],
        missing_frame,
        "the A27.3 census is read from a key `build_frames` does not commit",
    )
    # NON-VACUITY: the walker must be able to report an absent path, or the three checks above are
    # green because nothing can ever be missing.
    planted, _ok = _resolve(payload, ("r1_reliability", "text", "NO_SUCH_FIELD"))
    check(
        "the contract walker DETECTS an absent path (non-vacuity)",
        (None, False),
        (planted, _resolve(payload, ("r1_reliability", "text", "NO_SUCH_FIELD"))[1]),
        "the walker returns 'present' for everything, so the three contract checks are vacuous",
    )
    check(
        "the scorer still declares it took no decision",
        False,
        payload["decision_taken_here"],
        "the scorer began deciding Rule 0, so two components own the architecture outcome",
    )
    return {"n_metrics_paths": len(CONTRACT_PATHS), "n_document_paths": len(DOCUMENT_PATHS)}


# ================================================================================== RULE 0 (M9)


def part_rule0() -> dict:
    print("\n== Rule 0: three predicates, each positive, near-miss, and superseding ==")
    evidence = {}

    # ---- predicate 1: `derive_size_bands` returns a band
    check(
        "BAND -- H loses the band, X keeps it -> EXTENDED_BY_RULE_0_M9",
        DA.EXTENDED_BY_RULE_0_M9,
        outcome(m9_h=m9_facts(band=False)),
        "an arm that lost the whole heading tree is not rejected outright, so section 7.2 rule 0's "
        "largest available heading failure decides nothing",
        row="synthetic asymmetric M9 loss for H only",
    )
    check(
        "BAND near-miss -- BOTH arms lose the band -> Rule 0 does NOT fire",
        (False, DA.HYBRID_BY_PRIOR),
        (
            decision(m9_h=m9_facts(band=False), m9_x=m9_facts(band=False))["rule0"]["fires"],
            outcome(m9_h=m9_facts(band=False), m9_x=m9_facts(band=False)),
        ),
        "a shared failure is read as an asymmetric loss, rejecting an arm on evidence that "
        "distinguishes nothing (section 7.2 rule 0's both-lose branch)",
    )
    check(
        "BAND near-miss -- NEITHER arm loses the band -> Rule 0 does not fire",
        False,
        decision()["rule0"]["fires"],
        "Rule 0 fires on a clean document, rejecting an arm for nothing",
    )

    # ---- predicate 2: the 0.85 coverage floor
    check(
        "COVERAGE -- H at 0.84, X at 0.85 -> HYBRID rejected, EXTENDED_BY_RULE_0_M9",
        DA.EXTENDED_BY_RULE_0_M9,
        outcome(m9_h=m9_facts(coverage=0.84), m9_x=m9_facts(coverage=0.85)),
        "the frozen 0.85 floor stopped biting, so an arm keeps a document's heading tree by a "
        "threshold this study invented",
    )
    check(
        "COVERAGE near-miss -- BOTH exactly at 0.85 -> the clause does not fire",
        False,
        decision(m9_h=m9_facts(coverage=0.85), m9_x=m9_facts(coverage=0.85))["rule0"]["fires"],
        "the floor is read as a strict inequality, so a document meeting it exactly is a loss",
    )
    check(
        "COVERAGE mirror -- X at 0.84, H at 0.85 -> HYBRID_BY_RULE_0_M9",
        DA.HYBRID_BY_RULE_0_M9,
        outcome(m9_h=m9_facts(coverage=0.85), m9_x=m9_facts(coverage=0.84)),
        "Rule 0 is one-directional, so it can only ever reject hybrid",
    )

    # ---- predicate 3: A39.1's margin-numbered line count, with NO tolerance
    check(
        "MARGIN -- a ONE-line deficit for H fires (A39.1: no tolerance) -> EXTENDED_BY_RULE_0_M9",
        DA.EXTENDED_BY_RULE_0_M9,
        outcome(m9_h=m9_facts(margin=197), m9_x=m9_facts(margin=198)),
        "a tolerance was introduced, so 'loses margin-numbered lines' became 'loses more than N' "
        "-- choosing the sensitivity of a decision rule the frozen text does not parameterise",
    )
    check(
        "MARGIN near-miss -- EQUAL counts do not fire",
        False,
        decision(m9_h=m9_facts(margin=198), m9_x=m9_facts(margin=198))["rule0"]["fires"],
        "the margin clause fires on identical counts, rejecting an arm for nothing",
    )

    # ---- SAME DOCUMENT, DIFFERENT CLAUSES. The case a per-clause implementation gets wrong.
    #
    # H loses the BAND on this document and X loses MARGIN LINES on the SAME document. Section 7.2
    # rule 0 fires only when exactly one architecture loses a document the other keeps, so both
    # losing it -- by whatever clause -- is neutral for RQ1 and stays a FAILURE in RQ2. An
    # implementation that asked each clause "did an arm lose me?" independently would see a band
    # loss naming H and a margin loss naming X and fire twice, rejecting BOTH arms on a single
    # document that distinguishes nothing. A27.4's two-sided branch requires DIFFERENT documents.
    same_document = decision(
        m9_h=m9_facts(band=False, margin=200),
        m9_x=m9_facts(band=True, margin=190),
        corrects=0,
    )
    check(
        "SAME document, DIFFERENT clauses (H band, X margin) -> Rule 0 does NOT fire",
        (False, [], [], ["SYNTHETIC/1"], DA.HYBRID_BY_PRIOR),
        (
            same_document["rule0"]["fires"],
            same_document["rule0"]["H_asymmetric_loss_documents"],
            same_document["rule0"]["X_asymmetric_loss_documents"],
            same_document["rule0"]["both_lose_documents"],
            same_document["outcome"],
        ),
        "the clauses were read independently instead of per document, so one document both arms "
        "lost was counted as an asymmetric loss for each -- rejecting BOTH architectures on "
        "evidence section 7.2 rule 0 calls neutral, and inventing A27.4's two-sided branch on a "
        "single document when A27.4 requires different ones",
    )
    check(
        "...and BOTH clauses really did fire on that document, so the trap is live",
        ("H", "X"),
        (
            same_document["rule0"]["per_document"]["SYNTHETIC/1"]["clauses"]["band_loss"],
            same_document["rule0"]["per_document"]["SYNTHETIC/1"]["clauses"]["margin_line_loss"],
        ),
        "the fixture does not actually produce two opposite clause losses on one document, so the "
        "control could not have caught the per-clause reading",
    )

    # ---- A27.4: each arm asymmetric on a DIFFERENT document -> BOTH rejected
    other = frame(document="SYNTHETIC/2", sha=DOC_SHA_B, d_regions=0, m9_x=m9_facts(band=False))
    two_sided = decision(m9_h=m9_facts(band=False), extra_frames=(other,))
    check(
        "A27.4 -- an asymmetric loss on EACH arm, different documents -> INSUFFICIENT, no ranking",
        (DA.INSUFFICIENT_COMPARATIVE_EVIDENCE, ["SYNTHETIC/1"], ["SYNTHETIC/2"]),
        (
            two_sided["outcome"],
            two_sided["rule0"]["H_asymmetric_loss_documents"],
            two_sided["rule0"]["X_asymmetric_loss_documents"],
        ),
        "a severity or count comparison was invented between two rejected arms, which A27.4 explicitly forbids",
        row="synthetic asymmetric M9 loss on BOTH arms, different documents",
    )
    evidence["two_sided"] = {
        k: two_sided["rule0"][k] for k in ("H_asymmetric_loss_documents", "X_asymmetric_loss_documents")
    }

    # ---- PRECEDENCE: Rule 0 supersedes everything below it
    check(
        "PRECEDENCE -- Rule 0 fires while Rule 1 would have chosen X: Rule 0 decides",
        (DA.HYBRID_BY_RULE_0_M9, DA.DECIDED_BY_RULE_0, False),
        (
            decision(m9_x=m9_facts(band=False), corrects=6, regresses=0)["outcome"],
            decision(m9_x=m9_facts(band=False), corrects=6, regresses=0)["decided_by"],
            decision(m9_x=m9_facts(band=False), corrects=6, regresses=0)["rule1_reached"],
        ),
        "Rule 1 was consulted after an arm had already been rejected outright -- section 7.2 rule 0 "
        "rejects 'regardless of every other metric'",
        row="M9 one-arm loss",
    )
    blocked = decision(m9_h=m9_facts(band=False), gates_pass=False)
    check(
        "PRECEDENCE -- Rule 0 fires while Rule 3 gates fail: Rule 0 decides, gates still reported",
        (DA.EXTENDED_BY_RULE_0_M9, DA.DECIDED_BY_RULE_0, False),
        (blocked["outcome"], blocked["decided_by"], blocked["rule3"]["all_pass"]),
        "either M9 stopped superseding 'everything below' (section 7.2 rule 0), or the failing "
        "gates vanished from the artifact when another rule decided",
    )
    check(
        "PRECEDENCE -- the FULL gate vector is emitted whatever decided",
        list(DA.RULE3_GATES),
        list(blocked["rule3"]["gates"]),
        "a gate that failed is invisible in the artifact because Rule 0 took the outcome first",
    )
    return evidence


# ============================================================================ RULE 3's gates


def part_rule3() -> dict:
    print("\n== Rule 3: nine named gates, and NOT_EVALUABLE is not a pass ==")
    evidence = {}
    for gate in ("N-A", "N-B", "N-C"):
        failed = decision(mutate=lambda p, g=gate: p["control_verdicts"]["by_kind"][g].update({"status": "FAIL"}))
        check(
            f"a FAILING {gate} control -> INSUFFICIENT_COMPARATIVE_EVIDENCE",
            (DA.INSUFFICIENT_COMPARATIVE_EVIDENCE, DA.DECIDED_BY_RULE_3, [gate]),
            (failed["outcome"], failed["decided_by"], failed["rule3"]["failing"]),
            f"a failed {gate} Rule 3 blocker does not block, so the study decides on evidence its "
            "own controls say is unreliable",
            row="any Rule 3 gate set to FAIL",
        )
        unevaluable = decision(
            mutate=lambda p, g=gate: p["control_verdicts"]["by_kind"][g].update({"status": "NOT_EVALUABLE"})
        )
        check(
            f"an UNEVALUABLE {gate} control is not a pass either (A41.2.1)",
            DA.INSUFFICIENT_COMPARATIVE_EVIDENCE,
            unevaluable["outcome"],
            "a blocker that was never measured certifies itself, which is exactly the "
            "self-consistent-but-incomplete artifact A41.2.1 closed",
        )

    for dimension in ("text", "role"):
        failed = decision(mutate=lambda p, d=dimension: p["r1_reliability"][d].update({"status": "FAIL"}))
        check(
            f"a FAILING R1 {dimension} reliability gate -> INSUFFICIENT",
            (DA.INSUFFICIENT_COMPARATIVE_EVIDENCE, ["R1"]),
            (failed["outcome"], failed["rule3"]["failing"]),
            f"section 5.6's {dimension} threshold stopped blocking Rule 3",
            row="any Rule 3 gate set to FAIL",
        )

    dead = decision(s1_fires=False)
    check(
        "S1 not firing -> INSUFFICIENT (the comparator is not live)",
        (DA.INSUFFICIENT_COMPARATIVE_EVIDENCE, ["S1"]),
        (dead["outcome"], dead["rule3"]["failing"]),
        "a dead comparator does not block the decision, so an architecture is chosen on a "
        "comparison that was never shown to move",
        row="any Rule 3 gate set to FAIL",
    )

    check(
        "section 4.5 INADEQUATE blocks; LIMITED does NOT (A28.2)",
        (DA.INSUFFICIENT_COMPARATIVE_EVIDENCE, DA.HYBRID_BY_PRIOR),
        (
            outcome(mutate=lambda p: p["adequacy_4_5"].update({"verdict": "INADEQUATE"})),
            outcome(mutate=lambda p: p["adequacy_4_5"].update({"verdict": "LIMITED"})),
        ),
        "either INADEQUATE stopped failing Rule 3, or LIMITED started to -- A28.2 says LIMITED "
        "does not fail Rule 3, and treating it as a blocker would void a valid study",
    )

    for name in ("x2a", "x2b"):
        failed = decision(**{name: DA.GATE_FAIL})
        check(
            f"a FAILING confirmatory {name.upper()} -> INSUFFICIENT",
            DA.INSUFFICIENT_COMPARATIVE_EVIDENCE,
            failed["outcome"],
            "X's own contract assertions failed and the study decided anyway",
            row="any Rule 3 gate set to FAIL",
        )

    # M9 evaluability, structurally
    stripped = decision(mutate=lambda p: next(iter(p["per_document"].values()))["M9"].pop("band_loss"))
    check(
        "an M9 clause missing from a document -> M9 NOT EVALUABLE -> INSUFFICIENT",
        (DA.INSUFFICIENT_COMPARATIVE_EVIDENCE, "NOT_EVALUABLE"),
        (stripped["outcome"], stripped["rule3"]["gates"]["M9_evaluability"]["status"]),
        "an unevaluable M9 gate lets Rule 0 report 'nothing fired', which is indistinguishable "
        "from 'both arms were structurally viable everywhere'",
    )
    evidence["gate_names"] = list(DA.RULE3_GATES)
    check(
        "the gate vector is exactly A27.6's nine, in its order",
        9,
        len(DA.RULE3_GATES),
        "a decision-blocking condition was added to or dropped from A27.6's vector",
    )
    return evidence


def part_qualification_never_decides() -> dict:
    print("\n== x09 is a reporting qualification and NEVER a decision blocker (A27.6) ==")
    clean = decision()
    failed = decision(cross_failed=("SYNTHETIC/1",))
    check(
        "x09 FAILING on every sampled document changes NO outcome -- it only adds a label",
        (clean["outcome"], clean["decided_by"], True),
        (failed["outcome"], failed["decided_by"], failed["qualification"]["n_failed"] == 1),
        "a cross-engine failure moved the architecture decision, making a REPORTING qualification "
        "decision-blocking against A27.6",
        row="x09 set to FAIL",
    )
    check(
        "x09 is absent from the Rule 3 gate vector",
        [],
        [g for g in DA.RULE3_GATES if "x09" in g or "cross" in g.lower()],
        "cross-engine became a Rule 3 gate",
    )
    check(
        "the decision records the qualification as non-blocking",
        False,
        failed["qualification"]["decision_blocking"],
        "the artifact claims the qualification blocks",
    )
    return {"n_failed": failed["qualification"]["n_failed"]}


# =============================================================== the A10 / A27.3 budget


def part_budget() -> dict:
    print("\n== the budget: 60 vs 61 REGIONS, and a census that was only sampled ==")
    sixty = decision(d_regions=60, corrects=6, regresses=0)
    sixty_one = decision(d_regions=61, corrects=6, regresses=0)
    check(
        "D = 60 regions -> Rule 1 IS evaluated (and X's win stands)",
        (DA.EXTENDED_BY_RULE_1, 60, True),
        (sixty["outcome"], sixty["budget"]["d_frame_census"], sixty["budget"]["within_budget"]),
        "the frozen 60-region budget moved, so a raw count is applied to a census it was never "
        "valid on -- or Rule 1 stopped running on a census it may run on",
    )
    check(
        "D = 61 regions -> INSUFFICIENT, and Rule 1 is NOT reached",
        (DA.INSUFFICIENT_COMPARATIVE_EVIDENCE, DA.DECIDED_BY_BUDGET, False, 61),
        (
            sixty_one["outcome"],
            sixty_one["decided_by"],
            sixty_one["rule1_reached"],
            sixty_one["budget"]["d_frame_census"],
        ),
        "a census over the human budget still chose X on raw counts -- A10's whole subject",
        row="synthetic census of 61 regions",
    )
    check(
        "the 61-region census came from build_frames, not from the fixture",
        61,
        frame(d_regions=61)["counts"]["d_frame_census"],
        "the census is a number the probe wrote down, so the budget check is tested against the "
        "fixture's belief rather than the producer's count",
    )
    partial = decision(d_regions=40, adjudicated=39, corrects=6, regresses=0)
    check(
        "a census of 40 with only 39 adjudicated -> INSUFFICIENT (A27.3: never a sample)",
        (DA.INSUFFICIENT_COMPARATIVE_EVIDENCE, DA.DECIDED_BY_BUDGET, False),
        (partial["outcome"], partial["decided_by"], partial["budget"]["census_fully_adjudicated"]),
        "Rule 1 ran on a SAMPLE of the census, which A27.3 forbids in the same words as the 60/120 "
        "clause it supersedes",
    )
    empty = decision(d_regions=0, corrects=0, regresses=0)
    check(
        "an EMPTY census -> HYBRID_BY_PRIOR, and the text makes no empirical claim for hybrid",
        (DA.HYBRID_BY_PRIOR, DA.DECIDED_BY_PRIOR, True),
        (empty["outcome"], empty["decided_by"], "BY PRIOR" in empty["conclusion"]),
        "an empty census produced something other than the prior, or the conclusion claimed hybrid "
        "won empirically on no evidence at all",
        row="synthetic empty census",
    )
    return {"census_60": sixty["budget"], "census_61": sixty_one["budget"]}


# ==================================================================================== RULE 1


def part_rule1() -> dict:
    print("\n== Rule 1: 4 vs 5 corrections, 0 vs 1 regression, and the M4 veto ==")
    four = decision(corrects=4, regresses=0)
    five = decision(corrects=5, regresses=0)
    check(
        "X_CORRECTS = 4 -> HYBRID_BY_PRIOR (condition 1 fails, so Rule 2's prior stands)",
        (DA.HYBRID_BY_PRIOR, DA.DECIDED_BY_PRIOR, False),
        (four["outcome"], four["decided_by"], four["rule1"]["conditions"]["x_corrects_at_least_5"]),
        "the >= 5 threshold moved down, so four corrections overturn the architectural prior",
    )
    check(
        "X_CORRECTS = 5 -> EXTENDED_BY_RULE_1 (the threshold is >= 5, not > 5)",
        (DA.EXTENDED_BY_RULE_1, DA.DECIDED_BY_RULE_1),
        (five["outcome"], five["decided_by"]),
        "the threshold moved up, so exactly five corrections -- the number section 7.3 names as "
        "falsifying the hybrid hypothesis -- no longer does",
    )
    check(
        "6 corrections, 0 regressions, no M4 regression -> EXTENDED_BY_RULE_1",
        DA.EXTENDED_BY_RULE_1,
        outcome(corrects=6, regresses=0, m4_regressions=0),
        "a clean synthetic X win does not produce an X win, so no evidence could ever flip the ADR",
        row="synthetic X win (6 corrects, 0 regressions, no M4 regression)",
    )

    zero = decision(corrects=6, regresses=0)
    one = decision(corrects=6, regresses=1)
    check(
        "X_REGRESSES = 0 wins; X_REGRESSES = 1 does NOT (A5 tightened '<= 1' to zero)",
        (DA.EXTENDED_BY_RULE_1, DA.INSUFFICIENT_COMPARATIVE_EVIDENCE),
        (zero["outcome"], one["outcome"]),
        "the regression tolerance came back, and at an expected denominator near zero '<= 1' is "
        "not a tolerance -- it is 20 % of the win threshold",
    )

    five_one = decision(corrects=5, regresses=1)
    check(
        "5 corrections AND 1 regression -> INSUFFICIENT, never EXTENDED_BY_RULE_1, never HYBRID",
        (DA.INSUFFICIENT_COMPARATIVE_EVIDENCE, DA.DECIDED_BY_RULE_1, ["x_regresses_exactly_0"]),
        (five_one["outcome"], five_one["decided_by"], five_one["rule1"]["vetoes_failing"]),
        "A5's asymmetry was lost: condition 1 holding with a veto failing is 'insufficient "
        "evidence / review, NEVER an X win' -- and equally never a hybrid victory",
        row="synthetic 5 corrects and 1 regression",
    )

    # THE A42.3 PAYLOAD, asserted directly: the aggregates are EQUAL and the pairing is 1. This is
    # the fixture on which the two readings of A5 row 4 gave different architectures, and the
    # ruling took the per-heading existential.
    m4 = decision(corrects=5, regresses=0, m4_regressions=1, m4_correct=(3, 3))
    check(
        "5 corrections, 0 regressions, ONE M4 parent regression -> INSUFFICIENT (A5 row 4 / A20)",
        (DA.INSUFFICIENT_COMPARATIVE_EVIDENCE, DA.DECIDED_BY_RULE_1, ["no_m4_parent_regression"], 1),
        (m4["outcome"], m4["decided_by"], m4["rule1"]["vetoes_failing"], m4["rule1"]["m4_h_correct_x_wrong"]),
        "the M4 parent veto stopped blocking, so X wins while breaking a hierarchy H had right",
        row="synthetic 5 corrects and 1 M4 regression",
    )
    a42_block = d_pooled(corrects=5, regresses=0, n_stimuli=10, m4_regressions=1, m4_correct=(3, 3))
    check(
        "...and it fires while the per-arm M4 AGGREGATES are equal -- the A42.3 payload",
        (3, 3, True, True),
        (
            a42_block["counts"]["m4_correct"]["H"],
            a42_block["counts"]["m4_correct"]["X"],
            a42_block["M4"]["H"]["value"] == a42_block["M4"]["X"]["value"],
            bool(m4["rule1"]["m4_vetoing_occurrences"]),
        ),
        "the fixture's aggregates are NOT equal, so it does not separate the two readings of A5 "
        "row 4 and the veto could have fired for the wrong reason",
        row="synthetic 5 corrects and 1 M4 regression",
    )
    check(
        "the M4 veto only bites when condition 1 holds -- 4 corrections still yields the PRIOR",
        DA.HYBRID_BY_PRIOR,
        outcome(corrects=4, regresses=0, m4_regressions=1, m4_correct=(3, 3)),
        "a failing veto beneath the win threshold was reported as insufficient evidence, when the "
        "census simply yielded no X win and Rule 2's prior applies",
    )
    check(
        "condition 4 is READ from the scorer's paired fact, not supplied and not inferred",
        (True, False),
        (
            "h_correct_x_wrong" in m4["rule1"]["m4_condition_source"],
            hasattr(DA.DecisionInputs(metrics={}), "m4_no_regression"),
        ),
        "the supplied-fact channel came back, so a caller can assert Rule 1's fourth condition "
        "with nothing behind it (R5's closed channel, reopened)",
    )
    check(
        "M6 is STRUCK by A20 and is not a Rule 1 condition",
        ["no_m4_parent_regression", "x_corrects_at_least_5", "x_regresses_exactly_0"],
        sorted(five["rule1"]["conditions"]),
        "A5's M6 amount-attribution veto came back, reviving a metric A20 deferred from the study",
    )
    return {"conditions": five["rule1"]["conditions"], "five_and_one": five_one["rule1"]}


# ============================================================== the enum, closed and reachable


OUTCOME_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]+$")


def module_outcome_literals() -> set:
    """Every outcome-SHAPED string literal in `decide_architecture.py`, read from the AST.

    An AST walk, not a grep: a grep reads the lines an author wrote, and would miss a literal
    assembled anywhere the source does not spell it on one line. Docstrings cannot match, because
    the token pattern admits no lowercase and no spaces.
    """
    tree = ast.parse(SOURCE.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if OUTCOME_TOKEN.match(value) and re.search(r"EXTENDED|HYBRID|INSUFFICIENT", value):
                found.add(value)
    return found


def part_enums() -> dict:
    print("\n== the outcome enum: exactly five, all reachable, no sixth ==")
    check(
        "the frozen enum is exactly the five outcomes A10 and A27.4 name",
        [
            "EXTENDED_BY_RULE_0_M9",
            "EXTENDED_BY_RULE_1",
            "HYBRID_BY_PRIOR",
            "HYBRID_BY_RULE_0_M9",
            "INSUFFICIENT_COMPARATIVE_EVIDENCE",
        ],
        sorted(DA.ARCHITECTURE_OUTCOMES),
        "an outcome was added, removed or renamed, so a consumer reads a decision the protocol does not define",
    )
    check(
        "no SIXTH outcome-shaped literal exists anywhere in the module (AST, not grep)",
        set(),
        module_outcome_literals() - set(DA.ARCHITECTURE_OUTCOMES),
        "a branch invents an outcome alias, which would leave the module as a string no gate, "
        "report or reader knows how to treat",
    )

    # A behavioural sweep: every combination of the fixture dimensions, and what it reaches.
    reached, seen = {}, set()
    for m9 in ("clean", "h_loses", "x_loses", "two_sided"):
        for gates in (True, False):
            for regions in (0, 10, 61):
                for corrects, regresses, m4_regressions in (
                    (0, 0, 0),
                    (5, 0, 0),
                    (5, 1, 0),
                    (5, 0, 1),
                    (6, 0, 0),
                ):
                    kwargs = {
                        "d_regions": regions,
                        "corrects": corrects,
                        "regresses": regresses,
                        "m4_regressions": m4_regressions,
                        "gates_pass": gates,
                    }
                    if m9 == "h_loses":
                        kwargs["m9_h"] = m9_facts(band=False)
                    elif m9 == "x_loses":
                        kwargs["m9_x"] = m9_facts(band=False)
                    elif m9 == "two_sided":
                        kwargs["m9_h"] = m9_facts(band=False)
                        kwargs["extra_frames"] = (
                            frame(document="SYNTHETIC/2", sha=DOC_SHA_B, m9_x=m9_facts(band=False)),
                        )
                    got = outcome(**kwargs)
                    seen.add(got)
                    reached.setdefault(got, 0)
                    reached[got] += 1
    check(
        "a 240-payload sweep emits ONLY the five frozen outcomes",
        set(),
        seen - set(DA.ARCHITECTURE_OUTCOMES),
        "some payload reaches an outcome outside the closed enum",
    )
    check(
        "and ALL FIVE are reachable by an intentional fixture",
        sorted(DA.ARCHITECTURE_OUTCOMES),
        sorted(seen),
        "an outcome the protocol defines can never be produced, so a real result could have no expressible answer",
    )
    # The closed-enum assertion must itself be able to fire. Driven by making a rule RETURN an
    # unknown outcome, which is the only way a sixth could ever reach the guard in production.
    check(
        "the closed-enum assertion REFUSES a fabricated outcome (non-vacuity)",
        DA.OUTCOME_NOT_IN_FROZEN_ENUM,
        _enum_refusal(),
        "the guard cannot fire, so 'no sixth outcome can be emitted' is certified by a check that "
        "was never able to fail",
    )
    check(
        "a pre-committed sentence exists for EXACTLY the five outcomes -- the second layer's basis",
        sorted(DA.ARCHITECTURE_OUTCOMES),
        sorted(DA.SENTENCES),
        "an outcome has no pre-committed sentence (so the wording would be chosen once the result "
        "is known), or a sentence exists for an outcome the enum does not define",
    )
    return {"reached": reached}


def _enum_refusal() -> str | None:
    """Drive `decide`'s own closed-enum guard by making a rule return an unknown outcome."""
    original = DA.HYBRID_BY_PRIOR
    try:
        DA.HYBRID_BY_PRIOR = "HYBRID_BY_SOMETHING_ELSE"
        return refusal(lambda: decision(corrects=0))
    finally:
        DA.HYBRID_BY_PRIOR = original


# ================================================================================ the wording gate


def part_wording() -> dict:
    print("\n== the wording gate: an X failure may never be rendered as an H victory ==")
    for name, kwargs in (
        ("prior", {"corrects": 0}),
        ("insufficient by veto", {"corrects": 5, "regresses": 1}),
        ("insufficient by budget", {"d_regions": 61, "corrects": 6}),
        ("insufficient by gate", {"gates_pass": False}),
    ):
        text = decision(**kwargs)["conclusion"]
        check(
            f"the {name} conclusion carries NO comparative-accuracy claim for hybrid",
            [],
            sorted(p for p in DA.SUPERIORITY_PATTERNS if re.search(p, text, re.IGNORECASE)),
            "'X failed to prove a win' was written as 'H empirically beat X', which A10 forbids in those words",
            row="wording gate",
        )
    check(
        "every prior/insufficient conclusion says hybrid stands BY PRIOR",
        [True, True, True, True],
        [
            "prior" in decision(corrects=0)["conclusion"].lower(),
            "prior" in decision(corrects=5, regresses=1)["conclusion"].lower(),
            "prior" in decision(d_regions=61, corrects=6)["conclusion"].lower(),
            "prior" in decision(gates_pass=False)["conclusion"].lower(),
        ],
        "a non-win is reported without saying hybrid survives by prior rather than by victory",
    )
    # NON-VACUITY: the gate must fire on a planted claim, or the four checks above prove nothing.
    check(
        "the gate FIRES on a planted superiority claim (non-vacuity)",
        DA.CONCLUSION_CLAIMS_SUPERIORITY,
        refusal(lambda: DA._assert_no_superiority_claim("Hybrid is more accurate than extended.")),
        "the wording gate cannot fire, so every conclusion above passed a check that was never able "
        "to fail -- the vacuous-pass shape this study keeps finding",
        row="wording gate",
    )
    check(
        "and on each forbidden pattern individually, not just the one example",
        [],
        [
            p
            for p, sample in (
                (r"\boutperform", "extended outperforms hybrid"),
                (r"\bbetter than\b", "hybrid is better than extended"),
                (r"\bsuperior\b", "hybrid proved superior"),
                (r"\bbeats?\b", "hybrid beats extended"),
            )
            if refusal(lambda s=sample: DA._assert_no_superiority_claim(s)) != DA.CONCLUSION_CLAIMS_SUPERIORITY
        ],
        "a forbidden pattern is in the list but matches nothing, so it is decoration",
    )
    return {"prior_conclusion": decision(corrects=0)["conclusion"]}


# ==================================================================================== refusals


def part_refusals() -> dict:
    print("\n== fail closed: incomplete evidence REFUSES rather than defaulting to a pass ==")
    base_frames = [frame(d_regions=5)]
    base = pass_gates(scored(base_frames))
    base["headings_pooled"]["D"] = d_pooled(corrects=6, regresses=0, n_stimuli=5)

    def call(**kwargs):
        args = {"metrics": base, "frames": tuple(base_frames), "x2a": DA.GATE_PASS, "x2b": DA.GATE_PASS}
        args.update(kwargs)
        return lambda: DA.decide(DA.DecisionInputs(**args))

    without_pair = copy.deepcopy(base)
    without_pair["headings_pooled"]["D"]["M4"].pop("h_correct_x_wrong")

    cases = (
        ("a MISSING X2-a status refuses", DA.GATE_STATUS_MISSING, call(x2a=None)),
        ("a MISSING X2-b status refuses", DA.GATE_STATUS_MISSING, call(x2b=None)),
        ("an UNKNOWN gate status refuses", DA.GATE_STATUS_UNKNOWN, call(x2a="PROBABLY_FINE")),
        (
            "a D block carrying NO paired M4 fact refuses -- the aggregates are not a fallback",
            DA.M4_VETO_FACT_MISSING,
            call(metrics=without_pair),
        ),
        (
            "an unknown metrics SCHEMA refuses",
            DA.METRICS_SCHEMA_UNKNOWN,
            call(metrics={**base, "schema": "metrics/2"}),
        ),
        (
            "a metrics payload MISSING a required block refuses",
            DA.MISSING_REQUIRED_FACT,
            call(metrics={k: v for k, v in base.items() if k != "control_verdicts"}),
        ),
        (
            "a scorer claiming it took the decision refuses",
            DA.SCORER_TOOK_A_DECISION,
            call(metrics={**base, "decision_taken_here": True}),
        ),
        ("frames that do not match the scored documents refuse", DA.FRAME_DOCUMENT_SET_MISMATCH, call(frames=())),
        (
            "a frame with no committed D census refuses",
            DA.D_CENSUS_MISSING,
            call(frames=(_without(base_frames[0], ("counts", "d_frame_census")),)),
        ),
        (
            "a census COUNT that disagrees with its own census LIST refuses",
            DA.D_CENSUS_DRIFT,
            call(frames=(_set(base_frames[0], ("counts", "d_frame_census"), 4),)),
        ),
        (
            "a TRUNCATED census refuses -- A27.3 requires the complete enumeration",
            DA.D_CENSUS_TRUNCATED,
            call(frames=(_set(base_frames[0], ("d_frame_truncated",), True),)),
        ),
    )
    for name, expected, fn in cases:
        check(
            name,
            expected,
            refusal(fn),
            "missing or malformed evidence was silently treated as zero or as a pass, which at the "
            "architecture decision is the one substitution nothing downstream can undo",
        )

    check(
        "M4's refusal NAMES the rejected fallback rather than silently taking it",
        True,
        _m4_refusal_names_the_rejected_reading(without_pair, base_frames),
        "the refusal is anonymous, so a reader cannot tell the decider declined to substitute the "
        "aggregates rather than simply failing to find a key",
    )
    # An EMPTY census is not a missing fact: it is a frozen, legitimate state, and the most likely
    # real outcome of the study. The D block is absent because there was nothing to adjudicate --
    # NOT because a census went unadjudicated, which is the partial case the budget refuses above.
    empty_frames = [frame(d_regions=0)]
    empty = pass_gates(scored(empty_frames))
    check(
        "an ABSENT D block over a ZERO census is not a refusal -- the prior stands",
        (DA.HYBRID_BY_PRIOR, 0, True),
        (
            (
                decided := DA.decide(
                    DA.DecisionInputs(metrics=empty, frames=tuple(empty_frames), x2a="PASS", x2b="PASS")
                )
            )["outcome"],
            decided["budget"]["d_frame_census"],
            decided["budget"]["census_fully_adjudicated"],
        ),
        "an empty census was turned into a refusal, so the most likely real outcome of the whole "
        "study could not be expressed at all",
    )
    return {"n_refusal_classes": len(cases)}


def _without(frame_dict: dict, path) -> dict:
    out = copy.deepcopy(frame_dict)
    node = out
    for step in path[:-1]:
        node = node[step]
    node.pop(path[-1])
    return out


def _set(frame_dict: dict, path, value) -> dict:
    out = copy.deepcopy(frame_dict)
    node = out
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return out


def _m4_refusal_names_the_rejected_reading(metrics: dict, frames) -> bool:
    """The refusal must say WHY it refused, not merely that a key was absent (A42.3)."""
    try:
        DA.decide(DA.DecisionInputs(metrics=metrics, frames=tuple(frames), x2a="PASS", x2b="PASS"))
    except DA.DecisionInputError as exc:
        return "m4_correct" in json.dumps(exc.detail)
    return False


# ============================================================================ fault injection


FAULTS = (
    (
        "X_CORRECTS_MIN = 5",
        "X_CORRECTS_MIN = 4",
        "rule1_threshold_lowered",
        lambda m: _faulted_outcome(m, corrects=4) == m.EXTENDED_BY_RULE_1,
    ),
    (
        '"x_regresses_exactly_0": regresses == X_REGRESSES_MAX,',
        '"x_regresses_exactly_0": regresses <= 1,',
        "regression_tolerance_restored",
        lambda m: _faulted_outcome(m, corrects=6, regresses=1) == m.EXTENDED_BY_RULE_1,
    ),
    (
        "D_FRAME_REGION_BUDGET = 60",
        "D_FRAME_REGION_BUDGET = 120",
        "budget_relaxed_to_120",
        lambda m: _faulted_outcome(m, d_regions=61, corrects=6) == m.EXTENDED_BY_RULE_1,
    ),
    (
        '"no_m4_parent_regression": m4_regressions == 0,',
        '"no_m4_parent_regression": True,',
        "m4_veto_disabled",
        lambda m: _faulted_outcome(m, corrects=5, m4_regressions=1) == m.EXTENDED_BY_RULE_1,
    ),
    # THE REJECTED READING, injected. A42.3 ruled the per-heading existential over the count
    # comparison; this fault IS reading (b), and on the equal-aggregate payload it flips the
    # architecture. Nothing else in the suite would notice, because every other fixture has the
    # aggregates and the pairing agreeing.
    (
        '        m4_regressions = pooled_d["M4"]["h_correct_x_wrong"]',
        '        _c = pooled_d["counts"]["m4_correct"]\n        m4_regressions = max(0, _c["H"] - _c["X"])',
        "m4_veto_inferred_from_aggregates_the_A42_3_rejected_reading",
        lambda m: _faulted_outcome(m, corrects=5, m4_regressions=1, m4_correct=(3, 3)) == m.EXTENDED_BY_RULE_1,
    ),
    (
        "if h_documents and x_documents:",
        "if False:",
        "rule0_two_sided_ranking_invented",
        lambda m: _faulted_two_sided(m) != m.INSUFFICIENT_COMPARATIVE_EVIDENCE,
    ),
    (
        'failing = [name for name, block in ordered.items() if block["status"] != GATE_PASS]',
        'failing = [name for name, block in ordered.items() if block["status"] == GATE_FAIL]',
        "not_evaluable_accepted_as_pass",
        lambda m: _faulted_not_evaluable(m) != m.INSUFFICIENT_COMPARATIVE_EVIDENCE,
    ),
    (
        'elif rule1_block["condition_1_holds"]:',
        "elif False:",
        "five_and_one_collapsed_into_the_prior",
        lambda m: _faulted_outcome(m, corrects=5, regresses=1) == m.HYBRID_BY_PRIOR,
    ),
    (
        'elif rule0_block["fires"]:',
        "elif False:",
        "rule0_no_longer_supersedes",
        lambda m: _faulted_outcome(m, m9_h=None, m9_x_band_false=True, corrects=6) != m.HYBRID_BY_RULE_0_M9,
    ),
    (
        "hits = sorted({p for p in SUPERIORITY_PATTERNS if re.search(p, text, re.IGNORECASE)})",
        "hits = []",
        "wording_gate_disabled",
        lambda m: _wording_gate_dead(m),
    ),
    (
        "if outcome not in ARCHITECTURE_OUTCOMES:",
        "if False:",
        "closed_enum_guard_removed",
        lambda m: _enum_guard_dead(m),
    ),
)


def _load_faulted(old: str, new: str):
    """Import a copy of the module with ONE textual fault applied, under its own module name.

    The copy lives in a TEMP directory, never inside the study tree: a fault-injection probe that
    writes into `results/` leaves debris outside every ignore rule, and `git status` reads clean
    while the file is committed by the next `git add`.

    The anchor must be UNIQUE. A fault that silently patched zero or two sites would report
    "detected" or "not detected" about a mutation that is not the one named here.
    """
    source = SOURCE.read_text()
    if source.count(old) != 1:
        raise AssertionError(f"fault anchor is not unique ({source.count(old)} hits): {old!r}")
    with tempfile.TemporaryDirectory() as raw:
        faulted = Path(raw) / "decide_architecture_faulted.py"
        faulted.write_text(source.replace(old, new))
        spec = importlib.util.spec_from_file_location("decide_architecture_faulted", faulted)
        module = importlib.util.module_from_spec(spec)
        # `@dataclass` resolves its own module through `sys.modules`, so a spec-loaded module must
        # be registered BEFORE execution or `DecisionInputs` cannot be built at all.
        sys.modules["decide_architecture_faulted"] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop("decide_architecture_faulted", None)
        return module


def _faulted_inputs(
    module,
    *,
    d_regions=10,
    corrects=0,
    regresses=0,
    m4_regressions=0,
    m4_correct=(4, 4),
    m9_h=None,
    m9_x=None,
    extra=(),
):
    frames = [frame(d_regions=d_regions, m9_h=m9_h, m9_x=m9_x), *extra]
    payload = pass_gates(scored(frames))
    census = sum(f["counts"]["d_frame_census"] for f in frames)
    payload["headings_pooled"]["D"] = d_pooled(
        corrects=corrects,
        regresses=regresses,
        n_stimuli=census,
        m4_regressions=m4_regressions,
        m4_correct=m4_correct,
    )
    return module.DecisionInputs(
        metrics=payload,
        frames=tuple(frames),
        x2a=module.GATE_PASS,
        x2b=module.GATE_PASS,
    )


def _faulted_outcome(module, *, m9_x_band_false: bool = False, **kwargs) -> str:
    if m9_x_band_false:
        kwargs["m9_x"] = m9_facts(band=False)
    return module.decide(_faulted_inputs(module, **kwargs))["outcome"]


def _faulted_two_sided(module) -> str:
    other = frame(document="SYNTHETIC/2", sha=DOC_SHA_B, m9_x=m9_facts(band=False))
    return module.decide(_faulted_inputs(module, m9_h=m9_facts(band=False), extra=(other,)))["outcome"]


def _faulted_not_evaluable(module) -> str:
    frames = [frame(d_regions=5)]
    payload = pass_gates(scored(frames))
    payload["control_verdicts"]["by_kind"]["N-A"]["status"] = "NOT_EVALUABLE"
    payload["headings_pooled"]["D"] = d_pooled(corrects=6, regresses=0, n_stimuli=5)
    return module.decide(
        module.DecisionInputs(metrics=payload, frames=tuple(frames), x2a=module.GATE_PASS, x2b=module.GATE_PASS)
    )["outcome"]


def _wording_gate_dead(module) -> bool:
    try:
        module._assert_no_superiority_claim("Hybrid is more accurate than extended.")
    except module.DecisionInputError:
        return False
    return True


def _enum_guard_dead(module) -> bool:
    """With `decide`'s closed-enum assertion deleted, the SECOND layer must still refuse BY NAME.

    The fault is detected by WHICH layer answered, not by whether something blew up: normally the
    reason is `OUTCOME_NOT_IN_FROZEN_ENUM`, and with the first guard gone it becomes
    `SENTENCE_MISSING_FOR_OUTCOME`. Two layers refusing is good defence; a control that could only
    see the fault as a traceback is the defect.
    """
    original = module.HYBRID_BY_PRIOR
    try:
        module.HYBRID_BY_PRIOR = "HYBRID_BY_SOMETHING_ELSE"
        try:
            _faulted_outcome(module, corrects=0)
        except module.DecisionInputError as exc:
            return exc.reason == module.SENTENCE_MISSING_FOR_OUTCOME
        return False  # it escaped BOTH layers, which is worse than the fault this names
    finally:
        module.HYBRID_BY_PRIOR = original


def part_injection() -> dict:
    print("\n== fault injection: every result-bearing branch can be made to go RED ==")
    caught = []
    for old, new, name, predicate in FAULTS:
        module = _load_faulted(old, new)
        crashed, detected = False, False
        try:
            detected = bool(predicate(module))
        except Exception as exc:  # noqa: BLE001
            crashed, detected = True, False
            print(f"        {name} raised {type(exc).__name__}: {exc}")
        check(
            f"FAULT {name} changes a result-bearing answer (and is caught by a NAMED check)",
            (True, False),
            (detected, crashed),
            "the fault is invisible, so the control asserting the correct behaviour is not "
            "discriminating -- or it was detected only by a crash, which cannot distinguish "
            "'the rule broke' from 'the probe has a bug'",
        )
        caught.append({"fault": name, "anchor": old, "replacement": new, "detected": detected, "crashed": crashed})
    return {"faults": caught, "n_faults": len(FAULTS)}


# ==================================================================================== boundary


FORBIDDEN_ARTIFACTS = (
    "results/frames.json",
    "results/oracle_key.json",
    "results/oracle_blind.json",
    "results/oracle_adjudicated.json",
    "results/s1_control.json",
    "results/cross_engine_control.json",
    "results/metrics.json",
    "results/scores.json",
    "EXECUTION-START.json",
    "results/_x28_faulted.py",
)


def part_boundary() -> dict:
    print("\n== the boundary: nothing confirmatory was created ==")
    present = [p for p in FORBIDDEN_ARTIFACTS if (EV / p).exists()]
    check(
        "NO confirmatory or execution artifact exists after this probe",
        [],
        present,
        "a probe wrote a confirmatory artifact, or left its own faulted module on disk inside the protected tree",
    )
    check(
        "the decider takes no path that could WRITE anything",
        [],
        [n for n in ("write_text", "mkdir", "open(") if n in SOURCE.read_text()],
        "the decider acquired a writer, so an architecture decision could be persisted before the "
        "frozen start procedure has been performed",
    )
    return {"checked": list(FORBIDDEN_ARTIFACTS)}


# ======================================================================================= main


def main() -> int:
    evidence = {
        "contract": part_contract(),
        "rule0": part_rule0(),
        "rule3": part_rule3(),
        "qualification": part_qualification_never_decides(),
        "budget": part_budget(),
        "rule1": part_rule1(),
        "enums": part_enums(),
        "wording": part_wording(),
        "refusals": part_refusals(),
        "injection": part_injection(),
        "boundary": part_boundary(),
    }
    uncovered = [row for row, names in COVERED.items() if not names]
    check(
        "every HARNESS-PLAN section 6 control row has at least one executable check",
        [],
        uncovered,
        "a frozen control row is unimplemented, so the decider carries a rule nothing can falsify",
    )

    doc = {
        "population": "SYNTHETIC only -- no holdout opened, nothing adjudicated, no real decision taken",
        "contract": "HARNESS-PLAN section 6 (the decider) over PRE-REGISTRATION section 7.2, A5, A10, "
        "A20, A27.3, A27.4, A27.6, A28.2, A39.1 and A41",
        "question": "does `decide_architecture` implement the frozen Rule 0 / Rule 1 / Rule 3 machinery, "
        "and can each result-bearing branch be made to go RED?",
        "artifacts_created": "NONE of frames.json, oracle_key.json, oracle_blind.json, "
        "oracle_adjudicated.json, s1_control.json, cross_engine_control.json, metrics.json, "
        "scores.json, EXECUTION-START.json",
        "fixture_caveat": "every payload is real `score_metrics.score(...)` output; Rule 3 gate STATUSES "
        "are overwritten to reach later rules and are fixtures, never evidence",
        "open_ruling": "Rule 1's M4 condition (A5 row 4 / A20) has NO producer -- the scorer emits "
        "per-arm M4 counts only. The verdict is SUPPLIED and its absence REFUSES; see A42",
        "section6_rows": {row: names for row, names in COVERED.items()},
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
