"""decide_architecture -- section 7.2's rules 0, 1, 2 and 3, made executable.

THE ONLY COMPONENT THAT TAKES THE ARCHITECTURE DECISION. `score_metrics` deliberately records
M9's raw facts and emits `rule0_outcome: None` (A38.8 / A41); the Rule 0 choice, the Rule 1
evaluation, the A10/A27.3 budget and the A27.6 gate vector are all owned here.

WHAT THIS MODULE IS NOT ALLOWED TO DO, stated first because every one of them was available:

    it does not recompute a metric          every quantity is read from the scorer's payload
    it does not open a PDF or run an arm    no renderer, no `run_hybrid`, no `run_extended`
    it does not reconstruct oracle truth    no adjudication, no oracle, no answer is read
    it does not alter a population          the frames' committed censuses are read, never rebuilt
    it does not repair a surprising input   a missing or unknown fact REFUSES (see the refusals)

THE FIVE FROZEN OUTCOMES (A10 + A27.4), and nothing else may ever be emitted:

    EXTENDED_BY_RULE_0_M9            H has an asymmetric M9 loss, X has none
    HYBRID_BY_RULE_0_M9              X has an asymmetric M9 loss, H has none
    EXTENDED_BY_RULE_1               X met every Rule 1 condition on a FULL census
    HYBRID_BY_PRIOR                  the pre-stated architectural prior stands
    INSUFFICIENT_COMPARATIVE_EVIDENCE  Rule 1 could not be evaluated, or a Rule 3 gate did not pass

ORDER OF APPLICATION, and where each step's authority is:

    0. input validation                  refuse rather than decide on incomplete facts
    1. M9 evaluability                   section 7.2 rule 3's own item; Rule 0 cannot run without it
    2. RULE 0 (M9)                       section 7.2 rule 0 -- "M9 supersedes everything below",
                                         HARNESS-PLAN section 6 -- "Rule 0 (M9) runs FIRST"
    3. RULE 3 gate vector                A27.6 -- any failure -> INSUFFICIENT
    4. the A10 / A27.3 budget            > 60 D-frame regions -> Rule 1 cannot choose X
    5. RULE 1                            A5 as amended by A20
    6. RULE 2 -- the prior               HYBRID_BY_PRIOR

THE PROHIBITION THAT OUTLIVES THE OUTCOME. "X failed to prove a win because we did not
adjudicate enough items" must never be written as "H empirically beat X" (A10). Hybrid survives
BY PRIOR, and the rendered conclusion is gated against any comparative-accuracy claim for H.

RULE 1'S FOURTH CONDITION IS THE LITERAL PER-HEADING EXISTENTIAL (A42.3, ruled). "No heading whose
immediate parent is correct under H and wrong under X" is read from `score_metrics`' PAIRED fact,
`M4.h_correct_x_wrong`. The per-arm `m4_correct` counts are NOT sufficient and are never
substituted for it: two headings, one wrong under each arm, leave the aggregates equal while the
condition is violated. A D-frame block that carries no paired fact REFUSES.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))

SCHEMA = "architecture_decision/1"

#: The metrics payload this decider is written against. A different schema REFUSES rather than
#: being read optimistically: the field names below are the contract, not a convention.
METRICS_SCHEMA = "metrics/1"

ARMS = ("H", "X")

#: A5 as amended by A20. Both are RAW COUNTS over heading occurrences, valid on a census and not
#: on a sample (A10) -- which is why the budget below gates whether they may be applied at all.
X_CORRECTS_MIN = 5
X_REGRESSES_MAX = 0

#: A10 as unit-fixed by A27.3. The adjudication item is a REGION. `<= 60` -> the complete census
#: is adjudicated and Rule 1 may be evaluated; `> 60` -> Rule 1 cannot choose X.
D_FRAME_REGION_BUDGET = 60

#: A28.2's section 4.5 verdict that FAILS Rule 3. `LIMITED` explicitly does not fail it, and
#: `GENERALISABLE` does not; only `INADEQUATE` is a blocker.
ADEQUACY_BLOCKING = "INADEQUATE"

#: The Rule 3 gate vocabulary. Only `PASS` satisfies a blocker: A41.2.1 states of an empty control
#: population that every kind reports `NOT_EVALUABLE`, "which NO RULE 3 BLOCKER ACCEPTS". An
#: unevaluable gate is missing evidence, and treating missing evidence as a pass is the
#: self-certification defect A41.2.1 exists to close.
GATE_PASS = "PASS"
GATE_FAIL = "FAIL"
GATE_NOT_EVALUABLE = "NOT_EVALUABLE"
GATE_STATUSES = (GATE_PASS, GATE_FAIL, GATE_NOT_EVALUABLE)

#: A27.6's gate vector, in the order the amendment names them. Every one carries an explicit,
#: inspectable status in the output whether or not it decided anything.
RULE3_GATES = (
    "R1",
    "N-A",
    "N-B",
    "N-C",
    "S1",
    "X2-a",
    "X2-b",
    "M9_evaluability",
    "adequacy_4_5",
)

#: The two gates `score_metrics` does not own. A27.6 requires the confirmatory X2-a / X2-b run on
#: EVERY holdout document before scoring, and that execution-time artifact does not exist and has
#: no frozen shape, so its verdict is RECEIVED ("`decide_architecture` receives a named status for
#: every decision-blocking condition still operative"). Absent -> refuse.
SUPPLIED_GATES = ("X2-a", "X2-b")


# --------------------------------------------------------------------------------- the outcomes


EXTENDED_BY_RULE_0_M9 = "EXTENDED_BY_RULE_0_M9"
HYBRID_BY_RULE_0_M9 = "HYBRID_BY_RULE_0_M9"
EXTENDED_BY_RULE_1 = "EXTENDED_BY_RULE_1"
HYBRID_BY_PRIOR = "HYBRID_BY_PRIOR"
INSUFFICIENT_COMPARATIVE_EVIDENCE = "INSUFFICIENT_COMPARATIVE_EVIDENCE"

#: THE CLOSED SET. `decide` asserts its own result is a member before returning, so a sixth
#: outcome cannot escape even if some branch below were edited to invent one.
ARCHITECTURE_OUTCOMES = (
    EXTENDED_BY_RULE_0_M9,
    HYBRID_BY_RULE_0_M9,
    EXTENDED_BY_RULE_1,
    HYBRID_BY_PRIOR,
    INSUFFICIENT_COMPARATIVE_EVIDENCE,
)

#: Which rule took the decision. Reported beside the outcome because two different rules can reach
#: `INSUFFICIENT_COMPARATIVE_EVIDENCE` and collapsing them would hide WHY the study did not decide.
DECIDED_BY_RULE_0 = "RULE_0_M9"
DECIDED_BY_RULE_3 = "RULE_3_GATE"
DECIDED_BY_BUDGET = "BUDGET_A10_A27_3"
DECIDED_BY_RULE_1 = "RULE_1"
DECIDED_BY_PRIOR = "RULE_2_PRIOR"

#: The PRE-COMMITTED sentences (HARNESS-PLAN section 6: "the decider must emit the outcome enum and
#: a pre-committed sentence"). They are written here, before any confirmatory output exists, so the
#: wording cannot be chosen once the result is known.
SENTENCES = {
    EXTENDED_BY_RULE_0_M9: (
        "Rule 0 (M9) rejected hybrid outright: on {n} frozen document(s) hybrid lost structural "
        "viability that corrected extended glyph retained. Corrected extended glyph is selected by "
        "Rule 0, before any other metric was consulted."
    ),
    HYBRID_BY_RULE_0_M9: (
        "Rule 0 (M9) rejected corrected extended glyph outright: on {n} frozen document(s) "
        "corrected extended glyph lost structural viability that hybrid retained. Hybrid is "
        "retained by Rule 0, before any other metric was consulted."
    ),
    EXTENDED_BY_RULE_1: (
        "On the full D-frame region census ({census} regions, all adjudicated), corrected extended "
        "glyph met every Rule 1 condition: {corrects} corrections, {regresses} regressions, and no "
        "M4 parent regression. Corrected extended glyph is selected by Rule 1."
    ),
    # THE DISCLAIMER IS PHRASED SO THE GATE CAN STAY LITERAL. The obvious wording -- "this is not a
    # finding that hybrid is more accurate" -- contains the forbidden phrase inside a negation, and
    # teaching the gate to recognise negation would make it exactly the kind of check that passes
    # for the wrong reason. A blunt gate plus a disclaimer that avoids the phrase is the stricter
    # pair, and it was the first thing x28 caught.
    HYBRID_BY_PRIOR: (
        "Corrected extended glyph did not meet Rule 1's win conditions on the D-frame census. The "
        "pre-stated architectural prior therefore stands and hybrid is retained BY PRIOR. No "
        "comparative-accuracy finding about hybrid is made or implied."
    ),
    INSUFFICIENT_COMPARATIVE_EVIDENCE: (
        "The comparative evidence does not support a Rule 1 decision ({why}). Hybrid remains in "
        "place by the pre-stated prior. No comparative-accuracy finding about hybrid is made or "
        "implied."
    ),
}

#: The wording gate (HARNESS-PLAN section 6's control table). A10 forbids writing an X failure as an
#: H victory, so the RENDERED conclusion is scanned for comparative-accuracy claims about hybrid.
#: These are patterns, not a blocklist of one phrasing: the control exists because the tempting
#: sentence is the one nobody planned to write.
SUPERIORITY_PATTERNS = (
    r"\bmore accurate\b",
    r"\bmost accurate\b",
    r"\boutperform",
    r"\bbetter than\b",
    r"\bsuperior\b",
    r"\bbeats?\b",
    r"\bwins? on accuracy\b",
    r"\bempirically (?:beat|won|better)",
    r"\bproved more\b",
    r"\bhybrid is (?:better|more)\b",
)


# --------------------------------------------------------------------------------- the refusals


class DecisionInputError(Exception):
    """A malformed or incomplete decision input. NEVER a decision.

    Every refusal below exists because the alternative -- carrying on with a default -- would
    silently turn "this fact was not established" into "this fact passed". The architecture
    decision is the one place in the study where that substitution is unrecoverable.
    """

    def __init__(self, reason: str, detail=None):
        super().__init__(reason if detail is None else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


METRICS_SCHEMA_UNKNOWN = "METRICS_SCHEMA_UNKNOWN"
MISSING_REQUIRED_FACT = "MISSING_REQUIRED_FACT"
SCORER_TOOK_A_DECISION = "SCORER_TOOK_A_DECISION"
FRAME_DOCUMENT_SET_MISMATCH = "FRAME_DOCUMENT_SET_MISMATCH"
D_CENSUS_MISSING = "D_CENSUS_MISSING"
D_CENSUS_DRIFT = "D_CENSUS_DRIFT"
D_CENSUS_TRUNCATED = "D_CENSUS_TRUNCATED"
GATE_STATUS_MISSING = "GATE_STATUS_MISSING"
GATE_STATUS_UNKNOWN = "GATE_STATUS_UNKNOWN"
M4_VETO_FACT_MISSING = "M4_VETO_FACT_MISSING"
M9_CLAUSE_FACT_MISSING = "M9_CLAUSE_FACT_MISSING"
OUTCOME_NOT_IN_FROZEN_ENUM = "OUTCOME_NOT_IN_FROZEN_ENUM"
#: The SECOND layer under the closed enum, and it is deliberately a different reason. `decide`'s
#: own assertion is the first; if that one were ever deleted, an unknown outcome would still be
#: refused here -- by NAME, and by a name that says which layer caught it. A bare `KeyError` on
#: `SENTENCES` would catch the same fault while being unable to distinguish "the rule broke" from
#: "the probe has a bug", which A41.3 recorded as its own class of control defect.
SENTENCE_MISSING_FOR_OUTCOME = "SENTENCE_MISSING_FOR_OUTCOME"
CONCLUSION_CLAIMS_SUPERIORITY = "CONCLUSION_CLAIMS_SUPERIORITY"


# ----------------------------------------------------------------------------------- the inputs


@dataclass(frozen=True)
class DecisionInputs:
    """Everything the decision reads, and nothing else.

    `metrics` is `score_metrics.score(...)`'s payload verbatim. `frames` are the SAME committed
    document frames the scorer consumed -- they are read for exactly one quantity, `build_frames`'
    own committed `counts["d_frame_census"]`, which A27.3 requires be enumerated complete BEFORE
    any sampling and which the scorer does not re-emit. Reading a producer's committed count is
    not recomputing a metric; deriving the census here from regions would be, and is not done.

    `x2a` / `x2b` are the two A27.6 gates no committed artifact carries yet (the confirmatory X2
    run is an execution-time path that does not exist). They are the ONLY supplied facts: Rule 1's
    fourth condition was one too until A42.3 ruled it, and it is now read from the scorer's own
    paired M4 quantity like every other decision input.
    """

    metrics: dict
    frames: tuple = ()
    x2a: str | None = None
    x2b: str | None = None
    #: Free-text provenance for the two supplied gates, recorded in the artifact so a reader can
    #: see WHAT answered a gate rather than only that something did.
    supplied_evidence: dict = field(default_factory=dict)


def _require(mapping, keys, where: str) -> None:
    missing = [k for k in keys if k not in mapping]
    if missing:
        raise DecisionInputError(MISSING_REQUIRED_FACT, {"where": where, "missing": sorted(missing)})


def _gate_status(value, name: str) -> str:
    """Normalise one supplied gate status, refusing anything outside the frozen vocabulary."""
    if value is None:
        raise DecisionInputError(GATE_STATUS_MISSING, {"gate": name})
    if value not in GATE_STATUSES:
        raise DecisionInputError(GATE_STATUS_UNKNOWN, {"gate": name, "status": value})
    return value


def validate_inputs(inputs: DecisionInputs) -> dict:
    """Refuse before deciding. Every check here has a fixture that makes it fire.

    The scorer already refuses fifteen classes of malformed evidence; these are the ones that only
    become visible at the decision, where the metrics payload and the frames must agree about which
    documents exist and the census must be the complete one.
    """
    metrics = inputs.metrics
    if not isinstance(metrics, dict):
        raise DecisionInputError(MISSING_REQUIRED_FACT, {"where": "metrics", "missing": ["<payload>"]})
    if metrics.get("schema") != METRICS_SCHEMA:
        raise DecisionInputError(METRICS_SCHEMA_UNKNOWN, {"schema": metrics.get("schema")})
    _require(
        metrics,
        (
            "documents_scored",
            "per_document",
            "headings_pooled",
            "s1",
            "r1_reliability",
            "control_verdicts",
            "adequacy_4_5",
            "cross_engine_qualification",
            "decision_taken_here",
        ),
        "metrics",
    )
    # The scorer states it took no decision. If that ever flips, two components own Rule 0 and the
    # artifact cannot say which one the outcome came from.
    if metrics["decision_taken_here"]:
        raise DecisionInputError(SCORER_TOOK_A_DECISION, {"decision_owner": metrics.get("decision_owner")})

    scored = set(metrics["per_document"])
    frame_docs = [f.get("document") for f in inputs.frames]
    if sorted(d for d in frame_docs if d is not None) != sorted(frame_docs) or len(set(frame_docs)) != len(frame_docs):
        raise DecisionInputError(FRAME_DOCUMENT_SET_MISMATCH, {"reason": "a frame has no document, or a duplicate"})
    if set(frame_docs) != scored:
        raise DecisionInputError(
            FRAME_DOCUMENT_SET_MISMATCH,
            {"only_in_frames": sorted(set(frame_docs) - scored), "only_in_metrics": sorted(scored - set(frame_docs))},
        )
    return {"documents": sorted(scored)}


# -------------------------------------------------------------- the A10 / A27.3 evidence budget


def d_frame_budget(inputs: DecisionInputs) -> dict:
    """A10 as unit-fixed by A27.3: the COMPLETE D-frame region census, and whether it was adjudicated.

    Two separate frozen conditions live here, and conflating them would let a sampled census pass
    as a full one:

        the BUDGET     `<= 60` regions -> Rule 1 may be evaluated; `> 60` -> Rule 1 cannot choose X
        the CENSUS     "<= 60 regions -> human-adjudicate the COMPLETE census" (A27.3). Rule 1 must
                       never run on a 60- or 120-region SAMPLE, so an adjudicated count short of
                       the committed census means Rule 1's population is not the census

    The census comes from `build_frames`' own committed `counts["d_frame_census"]`, cross-checked
    against the committed census LIST it was derived from. Two records of one quantity that can
    disagree are worth checking; a summary trusted over its own detail is how a truncated census
    would look complete.
    """
    total = 0
    per_document = {}
    for frame in inputs.frames:
        document = frame.get("document")
        counts = frame.get("counts") or {}
        if "d_frame_census" not in counts:
            raise DecisionInputError(D_CENSUS_MISSING, {"document": document})
        declared = counts["d_frame_census"]
        listed = frame.get("d_frame_census")
        if listed is not None and len(listed) != declared:
            raise DecisionInputError(D_CENSUS_DRIFT, {"document": document, "counts": declared, "listed": len(listed)})
        if frame.get("d_frame_truncated"):
            raise DecisionInputError(D_CENSUS_TRUNCATED, {"document": document})
        per_document[document] = declared
        total += declared

    pooled_d = inputs.metrics["headings_pooled"].get("D")
    adjudicated = pooled_d["counts"]["n_stimuli"] if pooled_d else 0
    return {
        "d_frame_census": total,
        "per_document": per_document,
        "budget": D_FRAME_REGION_BUDGET,
        "within_budget": total <= D_FRAME_REGION_BUDGET,
        "n_adjudicated_d_regions": adjudicated,
        "census_fully_adjudicated": adjudicated == total,
        "unit": "REGION (A27.3); the census is enumerated complete BEFORE any sampling",
        "rule": "<= 60 -> Rule 1 may be evaluated; > 60 -> Rule 1 cannot choose X (A10)",
    }


# ------------------------------------------------------------------------------- RULE 0 (M9)


def _document_losses(m9: dict, document: str) -> dict:
    """Which arm, if either, has an M9 failure on ONE document.

    Section 7.2 rule 0's three clauses, read from the scorer's facts and never re-derived: the
    `derive_size_bands` band, the 0.85 coverage floor, and A39.1's margin-numbered line count.
    Each arrives already shaped as `{loser, fires}` -- `_clause_loss` for the two booleans and
    `methodology_contracts.margin_line_loss` for the count -- and each already collapses the
    BOTH-lose case to `fires: False`, because a shared failure distinguishes nothing.

    An arm loses this document if it loses ANY clause. A document both arms lose is neutral for
    RQ1 and stays a FAILURE in RQ2 and in M9 (section 7.2 rule 0); it is never an asymmetric loss
    for either arm, and it is never removed from anything.
    """
    clauses = ("band_loss", "coverage_loss", "margin_line_loss")
    _require(m9, clauses, f"M9 of {document}")
    losers = {}
    for clause in clauses:
        block = m9[clause]
        if not isinstance(block, dict) or "loser" not in block or "fires" not in block:
            raise DecisionInputError(M9_CLAUSE_FACT_MISSING, {"document": document, "clause": clause})
        losers[clause] = block["loser"] if block["fires"] else None
    return {
        "clauses": losers,
        "H_loses": "H" in losers.values(),
        "X_loses": "X" in losers.values(),
    }


def rule0(metrics: dict) -> dict:
    """Section 7.2 rule 0, with A27.4's own outcomes. Runs FIRST and supersedes everything below.

    "If EXACTLY ONE architecture loses `derive_size_bands`, falls below the 0.85 coverage floor, or
    loses margin-numbered lines on a document the other keeps, that architecture is rejected
    outright, regardless of every other metric."

    A27.4 adds the two-sided case: if EACH arm has an asymmetric loss, on different documents, then
    BOTH have been rejected and the outcome is `INSUFFICIENT_COMPARATIVE_EVIDENCE`. NO comparison
    by number or severity of losses is invented -- one loss each and one against forty read
    identically here, deliberately, because the frozen text licenses no ranking.

    Note that "on different documents" needs no separate test: a document BOTH arms lose is
    asymmetric for neither, so two asymmetric losses cannot sit on the same document.
    """
    h_documents, x_documents, both_documents = [], [], []
    per_document = {}
    for document, block in sorted(metrics["per_document"].items()):
        _require(block, ("M9",), f"per_document {document}")
        losses = _document_losses(block["M9"], document)
        per_document[document] = losses
        if losses["H_loses"] and losses["X_loses"]:
            both_documents.append(document)
        elif losses["H_loses"]:
            h_documents.append(document)
        elif losses["X_loses"]:
            x_documents.append(document)

    if h_documents and x_documents:
        outcome = INSUFFICIENT_COMPARATIVE_EVIDENCE
    elif h_documents:
        outcome = EXTENDED_BY_RULE_0_M9
    elif x_documents:
        outcome = HYBRID_BY_RULE_0_M9
    else:
        outcome = None

    return {
        "outcome": outcome,
        "fires": outcome is not None,
        "evaluated": True,
        "not_evaluated_because": None,
        "H_asymmetric_loss_documents": h_documents,
        "X_asymmetric_loss_documents": x_documents,
        "both_lose_documents": both_documents,
        "per_document": per_document,
        "clauses": "derive_size_bands band; coverage >= 0.85; margin-numbered line count (A39.1)",
        "no_severity_comparison": "A27.4 -- two-sided asymmetry rejects BOTH; losses are never ranked",
        "both_lose_treatment": "neutral for RQ1, retained as a FAILURE in RQ2 and M9 (section 7.2 rule 0)",
    }


def rule0_not_evaluated(why: str) -> dict:
    """Rule 0's block when its own precondition failed, in the SAME shape as a real evaluation.

    Rule 0 must not be run when the M9 gate cannot be evaluated: `_document_losses` would refuse on
    the very facts whose absence is what made the gate unevaluable, and a refusal is not the frozen
    answer -- section 7.2 rule 3's answer to "the M9 gate cannot be evaluated" is
    `INSUFFICIENT_COMPARATIVE_EVIDENCE`, which is a DECISION and not an error. Keeping the shape
    identical means a reader parses one block whichever branch produced it.
    """
    return {
        "outcome": None,
        "fires": False,
        "evaluated": False,
        "not_evaluated_because": why,
        "H_asymmetric_loss_documents": [],
        "X_asymmetric_loss_documents": [],
        "both_lose_documents": [],
        "per_document": {},
        "clauses": "derive_size_bands band; coverage >= 0.85; margin-numbered line count (A39.1)",
        "no_severity_comparison": "A27.4 -- two-sided asymmetry rejects BOTH; losses are never ranked",
        "both_lose_treatment": "neutral for RQ1, retained as a FAILURE in RQ2 and M9 (section 7.2 rule 0)",
    }


# ------------------------------------------------------------------------ RULE 3's gate vector


def rule3_gates(inputs: DecisionInputs, m9_evaluable: str) -> dict:
    """A27.6's nine named, inspectable statuses. Any non-PASS -> `INSUFFICIENT_COMPARATIVE_EVIDENCE`.

    Seven are DERIVED from facts the scorer computed and two are SUPPLIED, and the split is not a
    convenience: A41 closed R5 because "a caller scalar is not evidence for a result-bearing gate",
    so wherever a committed producer owns the fact it is read rather than accepted. X2-a and X2-b
    are supplied only because the confirmatory X2 run is an execution-time path that does not exist
    and has no frozen artifact shape -- exactly the case A27.6's "receives a named status" covers.

    `NOT_EVALUABLE` is not a pass. A41.2.1, on a key carrying no controls: every kind reports
    `NOT_EVALUABLE`, "which no Rule 3 blocker accepts".

    Cross-engine (x09) is ABSENT from this vector by A27.6: it is a reporting qualification and
    never a decision blocker.
    """
    metrics = inputs.metrics
    r1 = metrics["r1_reliability"]
    controls = metrics["control_verdicts"]["by_kind"]
    adequacy = metrics["adequacy_4_5"]["verdict"]

    # Section 5.6's two thresholds are separate dimensions of ONE reliability gate; the gate is the
    # worse of them, on R6.4's own precedence (any FAIL wins, else any NOT_EVALUABLE, else PASS).
    dimensions = [r1["text"]["status"], r1["role"]["status"]]
    r1_status = next((s for s in (GATE_FAIL, GATE_NOT_EVALUABLE) if s in dimensions), GATE_PASS)

    gates = {
        "R1": {
            "status": _gate_status(r1_status, "R1"),
            "source": "metrics.r1_reliability -- worst of text (>= 0.90) and role (>= 0.80), R6.4",
            "detail": {"text": r1["text"]["status"], "role": r1["role"]["status"]},
        },
        "S1": {
            "status": GATE_PASS if metrics["s1"]["fires"] else GATE_FAIL,
            "source": "metrics.s1.fires -- the extended-advances x 1.25 liveness control (A38.9)",
            "detail": {"advance_scale": metrics["s1"].get("advance_scale")},
        },
        "M9_evaluability": {
            "status": m9_evaluable,
            "source": "every scored document carries all three Rule 0 clause verdicts for both arms",
            "detail": {"documents_scored": metrics["documents_scored"]},
        },
        "adequacy_4_5": {
            "status": GATE_FAIL if adequacy == ADEQUACY_BLOCKING else GATE_PASS,
            "source": "metrics.adequacy_4_5.verdict -- A28.2; LIMITED does NOT fail Rule 3",
            "detail": {"verdict": adequacy},
        },
    }
    for kind in ("N-A", "N-B", "N-C"):
        block = controls.get(kind) or {}
        gates[kind] = {
            "status": _gate_status(block.get("status"), kind),
            "source": "metrics.control_verdicts.by_kind -- R8; a kind passes only if EVERY fixture "
            "passes on EVERY required route",
            "detail": {"n_passed": block.get("n_passed"), "n_total": block.get("n_total")},
        }
    for name, supplied in (("X2-a", inputs.x2a), ("X2-b", inputs.x2b)):
        gates[name] = {
            "status": _gate_status(supplied, name),
            "source": "SUPPLIED -- A27.6; the confirmatory X2 run has no committed artifact",
            "detail": {"evidence": inputs.supplied_evidence.get(name)},
        }

    ordered = {name: gates[name] for name in RULE3_GATES}
    failing = [name for name, block in ordered.items() if block["status"] != GATE_PASS]
    return {
        "gates": ordered,
        "failing": failing,
        "all_pass": not failing,
        "vocabulary": list(GATE_STATUSES),
        "not_evaluable_is_not_a_pass": "A41.2.1 -- NOT_EVALUABLE is a status no Rule 3 blocker accepts",
        "cross_engine_excluded": "A27.6 -- x09 is a reporting qualification, never decision-blocking",
    }


def m9_evaluability(metrics: dict) -> str:
    """Section 7.2 rule 3's "the M9 gate cannot be evaluated", as a status.

    STRUCTURAL, not a self-report: every scored document must carry all three Rule 0 clause
    verdicts for both arms, and there must be at least one document. A payload with no documents
    reports `NOT_EVALUABLE` rather than letting Rule 0 return "nothing fired" -- which would be
    indistinguishable from "both arms were structurally viable everywhere".
    """
    if not metrics["per_document"]:
        return GATE_NOT_EVALUABLE
    for block in metrics["per_document"].values():
        m9 = block.get("M9")
        if not isinstance(m9, dict):
            return GATE_NOT_EVALUABLE
        for clause in ("band_loss", "coverage_loss", "margin_line_loss"):
            entry = m9.get(clause)
            if not isinstance(entry, dict) or "fires" not in entry or "loser" not in entry:
                return GATE_NOT_EVALUABLE
        for arm in ARMS:
            facts = m9.get(arm)
            if not isinstance(facts, dict) or "coverage" not in facts or "n_margin_numbered_lines" not in facts:
                return GATE_NOT_EVALUABLE
    return GATE_PASS


# ------------------------------------------------------------------------------------- RULE 1


def rule1(inputs: DecisionInputs, budget: dict) -> dict:
    """A5's Rule 1 as amended by A20. Choose corrected extended glyph only if ALL hold, on a FULL census.

        1. `X_CORRECTS >= 5`     heading occurrences   (A5 row 1)
        2. `X_REGRESSES == 0`    heading occurrences   (A5 row 2; A5 tightened "<= 1" to zero)
        3. no heading whose immediate parent is correct under H and wrong under X   (A5 row 4 / M4)
           [A5 row 3 -- the M6 amount-attribution veto -- is STRUCK by A20]

    THE COUNTS ARE THE D-FRAME'S. A5 row 1 says "on the human-adjudicated D-frame census", and A3
    fixes the decision unit as the HEADING OCCURRENCE, so `m3_outcomes` is read and the WELD/SPLIT
    boundary tallies beside it are not -- they would inflate both counters (HARNESS-PLAN 7.2).

    CONDITION 1 IS NOT SYMMETRIC WITH THE OTHERS, and the asymmetry is A5's own:

        condition 1 fails                  -> Rule 2: the census yielded no X win, prior stands
        condition 1 holds, 2 or 3 fails    -> "insufficient evidence / review, NEVER an X win"

    So 5 corrections with 1 regression is not a hybrid victory and not an extended victory; it is
    `INSUFFICIENT_COMPARATIVE_EVIDENCE`, which is the only outcome that says what happened.
    """
    pooled_d = inputs.metrics["headings_pooled"].get("D")
    outcomes = pooled_d["M3"]["heading_outcomes"] if pooled_d else {}
    corrects = outcomes.get("X_CORRECTS", 0)
    regresses = outcomes.get("X_REGRESSES", 0)

    # CONDITION 4 IS READ, NEVER INFERRED (A42.3). An absent D block is an EMPTY census -- a frozen,
    # legitimate state in which condition 1 fails and the prior stands. A D block that exists but
    # carries no paired fact is a scorer that did not emit it, which REFUSES: falling back to the
    # aggregates would silently substitute the reading A42.3 rejected, and defaulting to "no
    # regression" is the one default that can only ever help X.
    if pooled_d is None:
        m4_regressions = 0
    elif "h_correct_x_wrong" not in pooled_d.get("M4", {}):
        raise DecisionInputError(
            M4_VETO_FACT_MISSING,
            {
                "condition": "A5 row 4 / A20 -- no heading whose immediate parent is correct under H and wrong under X",
                "why": "the D-frame block carries no paired M4 quantity; the per-arm m4_correct "
                "counts cannot express a per-heading existential and are NOT substituted (A42.3)",
            },
        )
    else:
        m4_regressions = pooled_d["M4"]["h_correct_x_wrong"]

    conditions = {
        "x_corrects_at_least_5": corrects >= X_CORRECTS_MIN,
        "x_regresses_exactly_0": regresses == X_REGRESSES_MAX,
        "no_m4_parent_regression": m4_regressions == 0,
    }
    return {
        "evaluable": budget["within_budget"] and budget["census_fully_adjudicated"],
        "x_corrects": corrects,
        "x_regresses": regresses,
        "m4_h_correct_x_wrong": m4_regressions,
        "m4_vetoing_occurrences": (pooled_d or {}).get("M4", {}).get("h_correct_x_wrong_occurrences", []),
        "thresholds": {"x_corrects_min": X_CORRECTS_MIN, "x_regresses_max": X_REGRESSES_MAX},
        "conditions": conditions,
        "all_conditions_hold": all(conditions.values()),
        "condition_1_holds": conditions["x_corrects_at_least_5"],
        "vetoes_failing": [k for k in ("x_regresses_exactly_0", "no_m4_parent_regression") if not conditions[k]],
        "decision_unit": "heading occurrence (A3); m3_outcomes, never WELD/SPLIT boundary tallies",
        "m6_veto": "STRUCK by A20 -- M6 is deferred and may not veto",
        "m4_condition_source": "metrics.headings_pooled.D.M4.h_correct_x_wrong -- the PAIRED "
        "per-heading existential (A42.3); the per-arm m4_correct rates are never substituted",
    }


# ------------------------------------------------------------------------------ the conclusion


def _assert_no_superiority_claim(text: str) -> None:
    """The wording gate. A10: an X failure may NEVER be rendered as an H victory.

    Applied to the text that is actually rendered, not to the template it came from: a caller
    appending one sentence to the conclusion is exactly how the forbidden claim would arrive.
    """
    hits = sorted({p for p in SUPERIORITY_PATTERNS if re.search(p, text, re.IGNORECASE)})
    if hits:
        raise DecisionInputError(CONCLUSION_CLAIMS_SUPERIORITY, {"patterns": hits})


def render_conclusion(outcome: str, rule0_block: dict, rule1_block: dict, budget: dict, why: str) -> str:
    """The pre-committed sentence for one outcome, filled with the facts it names, then GATED."""
    if outcome not in SENTENCES:
        raise DecisionInputError(SENTENCE_MISSING_FOR_OUTCOME, {"outcome": outcome})
    if outcome == EXTENDED_BY_RULE_0_M9:
        text = SENTENCES[outcome].format(n=len(rule0_block["H_asymmetric_loss_documents"]))
    elif outcome == HYBRID_BY_RULE_0_M9:
        text = SENTENCES[outcome].format(n=len(rule0_block["X_asymmetric_loss_documents"]))
    elif outcome == EXTENDED_BY_RULE_1:
        text = SENTENCES[outcome].format(
            census=budget["d_frame_census"],
            corrects=rule1_block["x_corrects"],
            regresses=rule1_block["x_regresses"],
        )
    elif outcome == INSUFFICIENT_COMPARATIVE_EVIDENCE:
        text = SENTENCES[outcome].format(why=why)
    else:
        text = SENTENCES[outcome]
    _assert_no_superiority_claim(text)
    return text


# --------------------------------------------------------------------------------- the decision


def decide(inputs: DecisionInputs) -> dict:
    """Section 7.2, applied in order. The ONLY function in the study that names an architecture.

    Rule 0 runs before the remaining Rule 3 gates because section 7.2 rule 0 says M9 "supersedes
    everything below" and rejects an arm "regardless of every other metric", and HARNESS-PLAN
    section 6 restates it as "Rule 0 (M9) runs FIRST". Its own precondition -- that M9 can be
    evaluated at all -- is section 7.2 rule 3's own listed item and is therefore checked before it.
    The FULL gate vector is emitted whatever decided, so a gate that failed is visible in the
    artifact even when Rule 0 took the outcome.
    """
    checked = validate_inputs(inputs)
    m9_evaluable = m9_evaluability(inputs.metrics)
    # Rule 0 is NOT run without its precondition: the facts it would read are the ones whose absence
    # made the gate unevaluable, and refusing there would turn section 7.2 rule 3's frozen ANSWER
    # into an exception. x28 found this by stripping one M9 clause.
    rule0_block = (
        rule0(inputs.metrics)
        if m9_evaluable == GATE_PASS
        else rule0_not_evaluated("the M9 gate cannot be evaluated (section 7.2 rule 3)")
    )
    gates = rule3_gates(inputs, m9_evaluable)
    budget = d_frame_budget(inputs)
    label = inputs.metrics["cross_engine_qualification"]

    rule1_block = None
    why = ""
    if m9_evaluable != GATE_PASS:
        outcome, decided_by = INSUFFICIENT_COMPARATIVE_EVIDENCE, DECIDED_BY_RULE_3
        why = "the M9 gate cannot be evaluated"
    elif rule0_block["fires"]:
        outcome, decided_by = rule0_block["outcome"], DECIDED_BY_RULE_0
        why = "both architectures were rejected by Rule 0 on different documents"
    elif not gates["all_pass"]:
        outcome, decided_by = INSUFFICIENT_COMPARATIVE_EVIDENCE, DECIDED_BY_RULE_3
        why = "Rule 3 gate(s) did not pass: " + ", ".join(gates["failing"])
    elif not budget["within_budget"]:
        outcome, decided_by = INSUFFICIENT_COMPARATIVE_EVIDENCE, DECIDED_BY_BUDGET
        why = (
            f"the D-frame census is {budget['d_frame_census']} regions, over the {D_FRAME_REGION_BUDGET}-region "
            "adjudication budget, so a raw count may not be applied to it"
        )
    elif not budget["census_fully_adjudicated"]:
        outcome, decided_by = INSUFFICIENT_COMPARATIVE_EVIDENCE, DECIDED_BY_BUDGET
        why = (
            f"{budget['n_adjudicated_d_regions']} of {budget['d_frame_census']} D-frame regions were "
            "adjudicated, so Rule 1's population is a sample and not the census"
        )
    else:
        rule1_block = rule1(inputs, budget)
        if rule1_block["all_conditions_hold"]:
            outcome, decided_by = EXTENDED_BY_RULE_1, DECIDED_BY_RULE_1
        elif rule1_block["condition_1_holds"]:
            # A5: condition 1 holds but a veto fails -> insufficient evidence / review, NEVER an X
            # win -- and never a hybrid win either, which is what the prior branch would have said.
            outcome, decided_by = INSUFFICIENT_COMPARATIVE_EVIDENCE, DECIDED_BY_RULE_1
            why = "Rule 1's threshold was met but a veto failed: " + ", ".join(rule1_block["vetoes_failing"])
        else:
            outcome, decided_by = HYBRID_BY_PRIOR, DECIDED_BY_PRIOR

    # THE CLOSED ENUM, asserted on the way out. A branch that invented a sixth outcome would reach
    # here, and this is the only place that can stop it leaving the module.
    if outcome not in ARCHITECTURE_OUTCOMES:
        raise DecisionInputError(OUTCOME_NOT_IN_FROZEN_ENUM, {"outcome": outcome})

    conclusion = render_conclusion(outcome, rule0_block, rule1_block or {}, budget, why)
    return {
        "schema": SCHEMA,
        "outcome": outcome,
        "decided_by": decided_by,
        "conclusion": conclusion,
        "documents": checked["documents"],
        "rule0": rule0_block,
        "rule3": gates,
        "budget": budget,
        "rule1": rule1_block,
        "rule1_reached": rule1_block is not None,
        # I13's label travels with the decision and CANNOT change it (A27.6). Emitted so a reader
        # sees the qualification beside the outcome rather than having to look it up.
        "qualification": {
            "headline_qualifications": label["headline_qualifications"],
            "n_failed": label["n_failed"],
            "decision_blocking": False,
        },
        "outcomes_frozen": list(ARCHITECTURE_OUTCOMES),
        "prohibitions": {
            "no_comparative_accuracy_claim_for_H": "A10 -- hybrid survives BY PRIOR, never by victory",
            "wording_gate": "the rendered conclusion is scanned for superiority claims before it is returned",
        },
    }
