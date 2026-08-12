"""score_metrics -- section 6 (M0-M9 MINUS M6) and the section 8 statistical contract.

RESULT-BEARING, and a PURE CONSUMER of committed artifacts. It introduces NO new
methodological rule: every rule below is already frozen, and where a frozen source designates
an executable owner this module CALLS it rather than transliterating it.

    section 6   M0a/M0b/M0-any/M0c + raw components, M1-M5, M7, M9
    section 8   the statistical contract (A27.5), whose primary bound is THIS module's own
                obligation and is deliberately absent from `methodology_contracts`
    A19/A22/A23 denominators, the M0 comparative risk set, the D-frame
    A3/A4       M3, via `m3_boundaries.heading_outcome` -- the authoritative decision logic
    A36.4/A36.7 the purpose->route table, and the M5 role coarsening
    A38.1       the score-input ownership table: every fact comes from a committed artifact
    A38.7       the occurrence-level join, via `build_oracle.resolve_adjudicated_occurrence`
    A38.10      the A37 helper boundary -- `section8_document_bootstrap` only, no custom id
    A39.1       Rule 0's margin-line FACT, via `methodology_contracts.margin_line_loss`
    A40.6       the corrected metric->control mapping (M1 -> N-B + N-C; M2 -> N-A; M3 -> N-A)

M6 IS STRUCK. Section 5 of HARNESS-PLAN specifies "section 6 (M0-M9 minus M6)" and A20
deferred M6 to a separate study. There is no M6 output here, no M6 acceptance condition, and
nothing that could be read as one. Its absence is deliberate and is asserted by a control.

WHAT THIS MODULE MAY NOT DECIDE, carried verbatim from HARNESS-PLAN section 5: to pool M0c
with the line rates; to weight the components into a composite; to drop `both_absent` from the
report; to let M3 read a segmentation label. Nor may it apply Rule 0, Rule 1 or Rule 3 --
`decide_architecture` owns every decision, and this module owns every measurement.

WHY IT NEVER OPENS A PDF, AND WHY IT DOES NOT IMPORT THE RENDERER. A38 exists so this stage
is reachable from committed JSON alone. `build_oracle` is imported LAZILY, inside the three
functions that need its frozen join and route helpers, because it imports `pymupdf` at module
scope -- and a scorer that cannot be imported without a PDF renderer would quietly re-acquire
the dependency A38 removed. The same lazy pattern is already used by `s1_control` and by
`build_oracle.execution_boundary_state`.

FAIL CLOSED. Every malformed, missing, inconsistent or ambiguous input raises
`ScoreInputError`. None of them is representable as a value a caller might not read, because a
scorer that returns a plausible number on broken input is the exact failure the study's
controls exist to catch: a passing score is indistinguishable from a correct one.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

import anchor_provenance as AP  # noqa: F401  -- refusal vocabulary shared with the A38.7 join
import m3_boundaries as M3B
import methodology_contracts as MC
import neutral_identity as NI

HERE = Path(__file__).resolve()
EV = HERE.parents[1]

#: I11 -- a metric whose CONTENT-BEARING denominator is zero. Never printed as agreement, and
#: never as a rate. It is a string precisely so it cannot be arithmetic on by accident.
VACUOUS = "VACUOUS"

#: A38.7's per-field sentinel, mirrored here so the scorer never compares against a bare
#: literal that could drift from the encoding `build_oracle` validates.
UNREADABLE = "UNREADABLE"

# ------------------------------------------------------------------- refusal classes
#
# Each names a condition under which a score would be a fiction. None is a return value.

FRAME_MISSING_FIELD = "FRAME_MISSING_FIELD"
FRAME_STATE_INCONSISTENT = "FRAME_STATE_INCONSISTENT"
FRAME_RISK_SET_INCONSISTENT = "FRAME_RISK_SET_INCONSISTENT"
FRAME_ANCHOR_EVIDENCE_INCONSISTENT = "FRAME_ANCHOR_EVIDENCE_INCONSISTENT"
DISCORDANT_LINE_OUTSIDE_D_FRAME = "DISCORDANT_LINE_OUTSIDE_D_FRAME"
DUPLICATE_DOCUMENT_FRAME = "DUPLICATE_DOCUMENT_FRAME"
STIMULUS_MISSING_OCCURRENCES = "STIMULUS_MISSING_OCCURRENCES"
AMBIGUOUS_EMITTED_OCCURRENCE_KEY = "AMBIGUOUS_EMITTED_OCCURRENCE_KEY"
CONTROL_IN_ESTIMAND = "CONTROL_IN_ESTIMAND"
UNKNOWN_ARM = "UNKNOWN_ARM"
INVALID_EVENT_COUNT = "INVALID_EVENT_COUNT"
EMPTY_DOCUMENT_SET = "EMPTY_DOCUMENT_SET"
DUPLICATE_PAIRED_DOCUMENT = "DUPLICATE_PAIRED_DOCUMENT"
NON_NUMERIC_PAIRED_VALUE = "NON_NUMERIC_PAIRED_VALUE"
S1_NOT_LIVE = "S1_NOT_LIVE"
MISSING_S1_RESULT = "MISSING_S1_RESULT"
MISSING_CROSS_ENGINE_RESULT = "MISSING_CROSS_ENGINE_RESULT"

ARMS = ("H", "X")


class ScoreInputError(Exception):
    """Scoring is NOT EXECUTABLE on this input. Deterministic, and never a value.

    THE FAILURE THIS PREVENTS. Every condition raised below is one where a scorer could
    instead emit a number: a frame whose committed discordance flag disagrees with the
    predicate that produced it, an occurrence key that appears twice in one region, a control
    that reached an estimand denominator. Each of those yields a *smaller* or *cleaner* result,
    and a cleaner result reads as a better one. Refusing is the only response that cannot be
    mistaken for a finding.
    """

    def __init__(self, reason: str, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason} {detail!r}")


def _build_oracle():
    """The frozen oracle-side helpers, imported lazily. See the module docstring."""
    import build_oracle as BO

    return BO


# --------------------------------------------------------------------- shared primitives


def rate(numerator: int, denominator: int):
    """I11 -- a rate, or `VACUOUS` when the content-bearing denominator is zero.

    Not `0.0`, and not `None`. A zero-denominator metric printed as `0.0` is indistinguishable
    from perfect agreement, which is precisely the reading section 6 forbids.
    """
    if denominator == 0:
        return VACUOUS
    return numerator / denominator


def _hashable(value):
    """Lists -> tuples, recursively, so a committed JSON key can index a dict.

    Both sides of the M1-M5 join are committed JSON, so both arrive as lists. Comparing a
    tuple against a list would make every matched-heading denominator silently zero -- the
    defect A38 recorded and fixed once already, kept unspellable here by normalising both
    sides through this one function.
    """
    if isinstance(value, (list, tuple)):
        return tuple(_hashable(v) for v in value)
    return value


def m2_normalize(text: str) -> str:
    """Section 6 / 6.2's FROZEN M2 normalisation: NFKC, collapse whitespace RUNS, strip ends.

    Case is preserved. This is deliberately NOT `m3_boundaries.normalize`, which leaves
    interior spacing untouched because M3 measures exactly what this collapses. Two
    normalisations, two metrics, and 6.2 is explicit that M2 "cannot distinguish one space
    from three" while M3 can.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


#: Section 6's M7 signature. Frozen: "emitted headings matching the letter-spaced signature
#: (>= 3 single-character tokens)".
M7_MIN_SINGLE_CHAR_TOKENS = 3


def m7_is_display_split(text: str) -> bool:
    """The M7 self-signature. NOT a correctness measure and it has no oracle.

    Section 6 licenses M7 as "display-split INCIDENCE ... per architecture", with oracle
    "none (a self-signature)". It answers "how often does this architecture emit a heading
    that looks letter-spaced", never "is this heading right".
    """
    tokens = unicodedata.normalize("NFKC", text).split()
    return sum(1 for token in tokens if len(token) == 1) >= M7_MIN_SINGLE_CHAR_TOKENS


# ------------------------------------------------------------- validation, kept SEPARATE
#
# Validation is not folded into the computations below. A metric function that also checks its
# own inputs can only be tested by a control that reproduces the same traversal, and the two
# then share whatever the traversal gets wrong.


def validate_frame(frame: dict) -> dict:
    """Refuse a committed frame that cannot support a faithful score. Returns a fact summary.

    A38.1 designates the COMMITTED fields as the scorer's inputs, so the scorer reads them.
    This function independently RECOMPUTES each one through `neutral_identity`'s authoritative
    predicates and refuses on disagreement. That is a real check rather than a restatement:
    the committed booleans were serialized by `build_frames` from a live runner pass, and
    nothing else in the chain would notice a frame that was truncated, hand-edited, or written
    by a drifted producer.
    """
    for field_name in ("document", "document_sha256", "pages", "counts", "m9", "architecture_occurrences"):
        if field_name not in frame:
            raise ScoreInputError(FRAME_MISSING_FIELD, {"field": field_name, "document": frame.get("document")})

    n_lines = n_risk = n_regions = 0
    for page in frame["pages"]:
        regions = {r["region_ordinal"]: r for r in page["regions"]}
        n_regions += len(regions)
        for line in page["neutral_lines"]:
            n_lines += 1
            state = line["line_state"]

            # the authoritative predicates, recomputed from the underlying quantities
            text_d = NI.text_discordance(state)
            seg_d = NI.segmentation_discordance(state)
            in_risk = NI.in_risk_set(state)

            if text_d != state["text_discordance"] or seg_d != state["segmentation_discordance"]:
                raise ScoreInputError(
                    FRAME_STATE_INCONSISTENT,
                    {
                        "document": frame["document"],
                        "line": line["key"],
                        "committed": [state["text_discordance"], state["segmentation_discordance"]],
                        "recomputed": [text_d, seg_d],
                    },
                )
            if in_risk != line["in_m0_risk_set"]:
                raise ScoreInputError(
                    FRAME_RISK_SET_INCONSISTENT,
                    {"document": frame["document"], "line": line["key"], "state": state["state"]},
                )
            n_risk += bool(in_risk)

            # I9 -- a discordant line's region MUST be in the D-frame. The same predicates
            # decide both, so a divergence means the two eligibility sets have drifted apart
            # and the D-frame census no longer describes the discordances being reported.
            if text_d or seg_d:
                region = regions.get(line["region_ordinal"])
                if region is None or not region["d_frame"]:
                    raise ScoreInputError(
                        DISCORDANT_LINE_OUTSIDE_D_FRAME,
                        {"document": frame["document"], "line": line["key"], "region": line["region_ordinal"]},
                    )

        for region in page["regions"]:
            differs = region["anchor_evidence"]["differ"]
            declared = "ANCHOR_DISCORDANCE" in region["d_reasons"]
            if differs != declared:
                raise ScoreInputError(
                    FRAME_ANCHOR_EVIDENCE_INCONSISTENT,
                    {
                        "document": frame["document"],
                        "page": page["page_number"],
                        "region": region["region_ordinal"],
                        "differ": differs,
                        "d_reasons": region["d_reasons"],
                    },
                )
    return {"neutral_lines": n_lines, "risk_set_lines": n_risk, "regions": n_regions}


def validate_frames(frames: list[dict]) -> dict:
    """Every frame, plus the document-uniqueness the section 8 unit depends on."""
    seen: set[str] = set()
    facts = {}
    for frame in frames:
        document = frame["document"]
        if document in seen:
            raise ScoreInputError(DUPLICATE_DOCUMENT_FRAME, {"document": document})
        seen.add(document)
        facts[document] = validate_frame(frame)
    return facts


# ---------------------------------------------------------------------------- the M0 block


def m0_document(frame: dict) -> dict:
    """Section 5's M0 block, exactly, for ONE document.

        risk set              neutral lines with state != BOTH_ABSENT
        M0a                   |TEXT_DISCORDANCE|         / |risk set|
        M0b_segmentation_rate |SEGMENTATION_DISCORDANCE| / |risk set|
        M0-any                UNION, never a sum         / |risk set|
        M0b_defined           lines where SEGMENTATION_DEFINED
        M0b_rate_on_defined   |SEGMENTATION_DISCORDANCE| / |M0b_defined|
        M0c                   |regions with ANCHOR_DISCORDANCE| / |regions|
        both_absent           raw count, reported, NEVER in a denominator

    THE UNION IS LOAD-BEARING. A line can be both text- and segmentation-discordant, so
    summing the two components double-counts it and can exceed the risk set outright -- a rate
    above 1.0, or a plausible one that is simply wrong.

    M0c IS NOT POOLED WITH THE LINE RATES. It is returned under its own key with its own
    denominator (regions, not lines) because they measure different units; averaging or adding
    them produces a number with no denominator at all.

    `both_absent` NEVER ENTERS A DENOMINATOR. That is structural here rather than remembered:
    every denominator below is computed from `risk`, a list that excludes BOTH_ABSENT by
    construction, so there is no expression in which the count could appear.
    """
    lines = [line for page in frame["pages"] for line in page["neutral_lines"]]
    regions = [region for page in frame["pages"] for region in page["regions"]]

    risk = [ln for ln in lines if ln["in_m0_risk_set"]]
    text = [ln for ln in risk if ln["line_state"]["text_discordance"]]
    seg = [ln for ln in risk if ln["line_state"]["segmentation_discordance"]]
    any_d = [ln for ln in risk if ln["line_state"]["text_discordance"] or ln["line_state"]["segmentation_discordance"]]
    defined = [ln for ln in risk if ln["line_state"]["diagnostics"]["SEGMENTATION_DEFINED"]]
    anchor_regions = [r for r in regions if r["anchor_evidence"]["differ"]]

    return {
        "document": frame["document"],
        "population": frame.get("population"),
        "neutral_lines_in_scope": len(lines),
        "risk_set": len(risk),
        "M0a_text_discordant_lines": len(text),
        "M0b_segmentation_discordant_lines": len(seg),
        "M0_any_discordant_lines": len(any_d),
        "M0b_defined": len(defined),
        # I3 -- reported, and structurally outside every denominator above.
        "both_absent": len(lines) - len(risk),
        "M0a_text_rate": rate(len(text), len(risk)),
        # NEVER emitted as a bare "M0b": section 5's reporting rule requires both this rate
        # (over the full risk set) and `M0b_rate_on_defined`, because only the latter may be
        # described as "the fraction of comparable groupings that disagree".
        "M0b_segmentation_rate": rate(len(seg), len(risk)),
        "M0b_rate_on_defined": rate(len(seg), len(defined)),
        "M0_any_rate": rate(len(any_d), len(risk)),
        "M0_any_rule": "UNION of the two components, never their sum",
        "m0c": {
            "unit": "region",
            "anchor_discordant_regions": len(anchor_regions),
            "regions": len(regions),
            "M0c_rate": rate(len(anchor_regions), len(regions)),
            "pooled_with_line_rates": False,
            "why_not_pooled": "M0c's denominator is REGIONS and M0a/M0b's is LINES; combining "
            "them yields a rate with no denominator",
        },
        "denominator_rule": "the comparative risk set -- neutral lines emitted by at least one "
        "arm. BOTH_ABSENT lines are reported and never counted in it",
    }


def m0_block(frames: list[dict], s1: dict | None) -> dict:
    """M0 per document and pooled, with S1's liveness verdict attached.

    POOLED MEANS COUNT-POOLED: the sum of numerators over the sum of denominators, so the
    pooled figure keeps a real content-bearing denominator as section 6 requires. It is not a
    mean of per-document rates, which would silently weight a 40-line document like a
    4,000-line one.

    M0 IS NOT REPORTABLE WHEN S1 DOES NOT FIRE. Section 5's control table states the
    consequence directly -- "M0 does not rise -> the comparator is not live and M0 is not
    reportable" -- so the flag travels WITH the numbers rather than being left for a reader to
    apply. The numbers are still emitted: suppressing them would destroy the evidence that the
    comparator is dead.
    """
    per_document = [m0_document(frame) for frame in frames]

    risk = sum(d["risk_set"] for d in per_document)
    pooled = {
        "risk_set": risk,
        "M0a_text_discordant_lines": sum(d["M0a_text_discordant_lines"] for d in per_document),
        "M0b_segmentation_discordant_lines": sum(d["M0b_segmentation_discordant_lines"] for d in per_document),
        "M0_any_discordant_lines": sum(d["M0_any_discordant_lines"] for d in per_document),
        "M0b_defined": sum(d["M0b_defined"] for d in per_document),
        "both_absent": sum(d["both_absent"] for d in per_document),
    }
    pooled["M0a_text_rate"] = rate(pooled["M0a_text_discordant_lines"], risk)
    pooled["M0b_segmentation_rate"] = rate(pooled["M0b_segmentation_discordant_lines"], risk)
    pooled["M0b_rate_on_defined"] = rate(pooled["M0b_segmentation_discordant_lines"], pooled["M0b_defined"])
    pooled["M0_any_rate"] = rate(pooled["M0_any_discordant_lines"], risk)
    pooled["pooling_rule"] = "sum of numerators / sum of denominators, never a mean of rates"

    anchor_regions = sum(d["m0c"]["anchor_discordant_regions"] for d in per_document)
    regions = sum(d["m0c"]["regions"] for d in per_document)
    pooled["m0c"] = {
        "unit": "region",
        "anchor_discordant_regions": anchor_regions,
        "regions": regions,
        "M0c_rate": rate(anchor_regions, regions),
        "pooled_with_line_rates": False,
    }

    live = bool(s1 and s1.get("fires"))
    return {
        "per_document": per_document,
        "pooled": pooled,
        "s1_liveness": s1_block(s1),
        "reportable": live,
        "not_reportable_reason": None if live else S1_NOT_LIVE,
    }


def s1_block(s1: dict | None) -> dict:
    """A38.9 -- primary and sabotaged M0 reported SEPARATELY, alongside `fires`.

    Collapsing them to one number would hide what the control established: a comparator is
    only shown to be live by the DIFFERENCE between an ordinary run and a sabotaged one.
    """
    if not s1:
        return {"present": False, "fires": False, "reason": MISSING_S1_RESULT}
    return {
        "present": True,
        "advance_scale": s1.get("advance_scale"),
        "sabotaged_arm": s1.get("sabotaged_arm"),
        "fires": bool(s1.get("fires")),
        "per_document": s1.get("per_document"),
        "n_documents": s1.get("n_documents"),
        "n_firing": s1.get("n_firing"),
        "gate_applied_here": False,
        "gate_owner": "decide_architecture (A27.6 Rule 3)",
    }


# ------------------------------------------------------- the occurrence-level join (A38.7)


def emitted_occurrences(key_record: dict, arm: str) -> dict:
    """One region's emitted occurrences for one arm: `{occurrence_key: row}` plus the residue.

    EVERY production occurrence is counted, including one whose A30 resolution refused. An
    UNMATCHED occurrence has no key and can never match an adjudication, but it stays in the
    PRECISION denominator: production emitted a heading there, and dropping it would shrink
    the denominator invisibly and make precision look better for the arm that failed hardest.
    """
    if arm not in ARMS:
        raise ScoreInputError(UNKNOWN_ARM, {"arm": arm})
    occurrences = key_record.get("architecture_occurrences")
    if not occurrences or arm not in occurrences:
        raise ScoreInputError(
            STIMULUS_MISSING_OCCURRENCES,
            {"document": key_record.get("document"), "arm": arm, "control_kind": key_record.get("control_kind")},
        )

    rows = occurrences[arm]
    by_key: dict = {}
    unmatched = []
    for row in rows:
        if row["match_status"] != "MATCHABLE" or row["occurrence_key"] is None:
            unmatched.append(row)
            continue
        key = _hashable(row["occurrence_key"])
        if key in by_key:
            # Two emitted occurrences claiming one source position. The join would be
            # ambiguous and whichever row won would depend on iteration order.
            raise ScoreInputError(
                AMBIGUOUS_EMITTED_OCCURRENCE_KEY,
                {"arm": arm, "key": list(key), "document": key_record.get("document")},
            )
        by_key[key] = row
    return {"by_key": by_key, "unmatched": unmatched, "total": len(rows)}


def adjudicated_occurrences(key_record: dict, answer: dict) -> list[dict]:
    """One adjudication's headings, each resolved to an A30 occurrence key or an explicit refusal.

    A38.7's helper is CALLED, never reimplemented: the pixel->PDF transform, the nearest-glyph
    resolver and its no-tolerance tie rule all live in `build_oracle`, and a second spelling
    here would be a second rule.

    A refusal -- an out-of-range physical line, an UNREADABLE coordinate, no candidate, an
    exact geometric tie -- yields an unresolved heading. It stays in the ADJUDICATED
    enumeration (I10) and can never match, so it counts against recall rather than vanishing
    from the denominator.
    """
    BO = _build_oracle()
    out = []
    for heading in answer.get("headings", []):
        text = heading.get("text")
        record = {
            "text": text,
            "role": heading.get("role"),
            "parent": heading.get("parent"),
            "readable_text": text is not None and text != UNREADABLE,
            "occurrence_key": None,
            "unresolved_reason": None,
        }
        try:
            resolved = BO.resolve_adjudicated_occurrence(key_record, heading)
        except BO.OracleBuildError as exc:
            record["unresolved_reason"] = exc.reason
            out.append(record)
            continue
        except (TypeError, ValueError) as exc:
            # An UNREADABLE or otherwise non-numeric coordinate. Reported, never guessed at.
            record["unresolved_reason"] = f"UNRESOLVABLE_COORDINATE: {type(exc).__name__}"
            out.append(record)
            continue
        if resolved["matched"]:
            record["occurrence_key"] = _hashable(resolved["occurrence_key"])
        else:
            record["unresolved_reason"] = resolved.get("reason")
        out.append(record)
    return out


# ------------------------------------------------------------------------ M1-M5 and M7
#
# A36.3 -- "never pooled" means SEPARATE ESTIMANDS. C and D are therefore scored and reported
# apart, each reading the route its purpose mandates (A36.4): C metrics take the AI answer even
# where a human answer exists, because D membership is conditional on architecture
# disagreement and mixing the two would let the architectures choose their own oracle on
# exactly the regions where they disagree.

ESTIMAND_C = "C"
ESTIMAND_D = "D"


def _estimand_records(key: dict, estimand: str) -> list[tuple[str, dict]]:
    """The PRIMARY stimuli of one estimand, selected on FRAME MEMBERSHIP and repeat status only.

    CONTROL STATUS IS DELIBERATELY NOT FILTERED HERE, and that is the point. A control has
    `frames == ()`, so it never acquires membership and never appears -- but if one ever did,
    filtering it out silently would hide a malformed oracle key behind a slightly smaller
    denominator. `score_estimand` therefore REFUSES on a control instead, which turns the
    exclusion into a gate that can fail rather than a filter that cannot.

    An earlier spelling filtered on `control_kind` here as well. That made the refusal in
    `score_estimand` unreachable: it read as protection while being incapable of firing, which
    is the same defect the study's own controls exist to catch. `x27`'s N2 attack found it.
    """
    flag = "in_c_frame" if estimand == ESTIMAND_C else "in_d_frame"
    return [
        (bid, record)
        for bid, record in sorted(key["stimuli"].items())
        if record.get(flag) and not record.get("is_r1_repeat")
    ]


def score_estimand(key: dict, adjudicated: dict, estimand: str) -> dict:
    """M1-M5 for one estimand, per document and pooled.

    M1  recall/precision of emitted occurrences against the ADJUDICATED enumeration (I10),
        matched on the A27.1/A30.1 source-position key. No text similarity anywhere.
    M2  emitted == adjudicated under the frozen `m2_normalize`.
    M3  `m3_boundaries.heading_outcome(oracle, hybrid, extended)` -- called, never reproduced.
        It consumes PROJECTED TEXT AND THE ORACLE ONLY and never reads a segmentation label.
    M4  the emitted IMMEDIATE parent -- production `breadcrumb_for`'s penultimate element, as
        committed by `build_frames` -- against the adjudicated parent. Never full ancestry.
    M5  `methodology_contracts.m5_agreement`; `None` is out of the denominator and is counted.
    """
    BO = _build_oracle()
    purpose = BO.PURPOSE_C_METRICS if estimand == ESTIMAND_C else BO.PURPOSE_D_DECISION
    route = BO.PURPOSE_ROUTE[purpose]

    per_document: dict[str, dict] = {}
    for bid, record in _estimand_records(key, estimand):
        if record.get("control_kind") is not None:
            raise ScoreInputError(CONTROL_IN_ESTIMAND, {"blind_id": bid, "estimand": estimand})

        answers = {ns: adjudicated.get(ns, {}).get(bid) for ns in BO.ADJUDICATION_NAMESPACES}
        answer = BO.select_answer(record, purpose, answers)

        document = record["document"]
        bucket = per_document.setdefault(document, _empty_estimand_bucket(document))
        bucket["stimuli"] += 1

        adjudications = adjudicated_occurrences(record, answer)
        emitted = {arm: emitted_occurrences(record, arm) for arm in ARMS}

        bucket["adjudicated_headings"] += len(adjudications)
        bucket["adjudicated_unresolved"] += sum(1 for a in adjudications if a["occurrence_key"] is None)
        for arm in ARMS:
            bucket["arms"][arm]["emitted_occurrences"] += emitted[arm]["total"]
            bucket["arms"][arm]["emitted_unmatchable"] += len(emitted[arm]["unmatched"])

        _score_stimulus(bucket, adjudications, emitted)

    documents = [_finalize_estimand_bucket(b) for _doc, b in sorted(per_document.items())]
    return {
        "estimand": estimand,
        "purpose": purpose,
        "route": route,
        "route_rule": "A36.4 -- the route the PURPOSE mandates, never the one that happens to exist",
        "n_stimuli": sum(d["stimuli"] for d in documents),
        "per_document": documents,
        "pooled": _pool_estimand(documents),
    }


def _empty_estimand_bucket(document: str) -> dict:
    return {
        "document": document,
        "stimuli": 0,
        "adjudicated_headings": 0,
        "adjudicated_unresolved": 0,
        "arms": {
            arm: {
                "emitted_occurrences": 0,
                "emitted_unmatchable": 0,
                "m1_recall_matched": 0,
                "m1_precision_matched": 0,
                "m2_denominator": 0,
                "m2_exact": 0,
                "m4_denominator": 0,
                "m4_agree": 0,
                "m4_unreadable_excluded": 0,
                "m5_denominator": 0,
                "m5_agree": 0,
                "m5_out_of_scope_excluded": 0,
                "m5_unreadable_excluded": 0,
            }
            for arm in ARMS
        },
        "m3": {
            "denominator": 0,
            "no_reference_excluded": 0,
            "neither_arm_emitted": 0,
            **{outcome.value: 0 for outcome in M3B.HeadingOutcome},
        },
    }


def _score_stimulus(bucket: dict, adjudications: list[dict], emitted: dict) -> None:
    """One stimulus's contribution to M1-M5. Pure accumulation; no rate is formed here."""
    matched_emitted = {arm: set() for arm in ARMS}

    for adjudication in adjudications:
        key = adjudication["occurrence_key"]
        rows = {arm: (emitted[arm]["by_key"].get(key) if key is not None else None) for arm in ARMS}

        for arm in ARMS:
            arm_bucket = bucket["arms"][arm]
            row = rows[arm]
            if row is None:
                continue
            arm_bucket["m1_recall_matched"] += 1
            matched_emitted[arm].add(key)

            # M2 -- exactness under the frozen normalisation, on matched headings only.
            if adjudication["readable_text"]:
                arm_bucket["m2_denominator"] += 1
                arm_bucket["m2_exact"] += m2_normalize(row["anchor"]["text"]) == m2_normalize(adjudication["text"])

            # M4 -- the IMMEDIATE parent only. `breadcrumb` is deliberately never read.
            _score_m4(arm_bucket, row, adjudication)

            # M5 -- the frozen A36.7 coarsening. `UnknownRole` propagates.
            _score_m5(arm_bucket, row, adjudication)

        _score_m3(bucket["m3"], rows, adjudication)

    for arm in ARMS:
        bucket["arms"][arm]["m1_precision_matched"] += len(matched_emitted[arm])


def _score_m4(arm_bucket: dict, row: dict, adjudication: dict) -> None:
    """M4 -- emitted immediate parent vs adjudicated parent.

    `None` on the emitted side is production's one-element breadcrumb, i.e. no parent, and it
    AGREES with an adjudicated null. Treating "no parent" as an automatic disagreement would
    penalise every top-level heading in the document.
    """
    parent = adjudication["parent"]
    if parent == UNREADABLE:
        arm_bucket["m4_unreadable_excluded"] += 1
        return
    arm_bucket["m4_denominator"] += 1
    emitted_parent = row["immediate_parent"]
    if emitted_parent is None or parent is None:
        arm_bucket["m4_agree"] += emitted_parent is None and parent is None
        return
    arm_bucket["m4_agree"] += m2_normalize(emitted_parent) == m2_normalize(parent)


def _score_m5(arm_bucket: dict, row: dict, adjudication: dict) -> None:
    """M5 -- role agreement on the frozen A36.7 leaf/container coarsening.

    An UNREADABLE role is excluded and counted. An unknown role RAISES: A36.7 is explicit that
    mapping it to UNSCORABLE would quietly shrink the denominator, and a smaller denominator
    reads as a cleaner result rather than as the defect it is.
    """
    role = adjudication["role"]
    if role == UNREADABLE or role is None:
        arm_bucket["m5_unreadable_excluded"] += 1
        return
    agreement = MC.m5_agreement(role, row["anchor"]["kind"])
    if agreement is None:
        arm_bucket["m5_out_of_scope_excluded"] += 1
        return
    arm_bucket["m5_denominator"] += 1
    arm_bucket["m5_agree"] += bool(agreement)


def _score_m3(m3_bucket: dict, rows: dict, adjudication: dict) -> None:
    """M3 -- the heading-level outcome, from `m3_boundaries.heading_outcome`.

    THE AUTHORITATIVE DECISION LOGIC IS CALLED. A3 fixes the decision unit as the heading
    occurrence and A4 fixes the alignment; transliterating either here would give the study
    two spellings of its primary comparative metric.

    An arm that emitted nothing for a printed heading contributes `""`, which
    `score_heading` scores as a maximal TEXT_ERROR rather than an exclusion (A9). That keeps
    the heading in the denominator, which is the whole point: excluding it would remove
    exactly the cases where an architecture failed worst.

    M3 NEVER READS A SEGMENTATION LABEL. Its only inputs are the oracle's text and each arm's
    projected text, and no `line_state` value is in scope in this function.
    """
    if adjudication["occurrence_key"] is None:
        return
    if not adjudication["readable_text"]:
        m3_bucket["no_reference_excluded"] += 1
        return

    hybrid = rows["H"]["anchor"]["text"] if rows["H"] is not None else ""
    extended = rows["X"]["anchor"]["text"] if rows["X"] is not None else ""
    outcome, _h_score, _x_score = M3B.heading_outcome(adjudication["text"], hybrid, extended)

    m3_bucket["denominator"] += 1
    m3_bucket[outcome.value] += 1
    if rows["H"] is None and rows["X"] is None:
        m3_bucket["neither_arm_emitted"] += 1


def _arm_rates(counts: dict, adjudicated_headings: int) -> dict:
    """Counts -> rates for one arm. THE REPORTED DENOMINATOR IS THE ONE THE RATE USED.

    Each denominator is bound to a local and then consumed twice -- once by `rate` and once by
    the reported field. Spelling them separately let the label drift from the computation, and
    a reported denominator that is not the one divided by is unfalsifiable: it publishes I10
    while the arithmetic does something else. `x27`'s F4 fault injection found exactly that.
    """
    recall_denominator = adjudicated_headings
    precision_denominator = counts["emitted_occurrences"]
    return {
        **counts,
        "M1_recall": rate(counts["m1_recall_matched"], recall_denominator),
        "M1_recall_denominator": recall_denominator,
        "M1_recall_denominator_rule": "I10 -- the ADJUDICATED enumeration, never the emitted one",
        "M1_precision": rate(counts["m1_precision_matched"], precision_denominator),
        "M1_precision_denominator": precision_denominator,
        "M1_precision_denominator_rule": "every emitted occurrence, INCLUDING one the A30 bridge refused",
        "M2_exactness": rate(counts["m2_exact"], counts["m2_denominator"]),
        "M4_parent_agreement": rate(counts["m4_agree"], counts["m4_denominator"]),
        "M5_role_agreement": rate(counts["m5_agree"], counts["m5_denominator"]),
    }


def _finalize_estimand_bucket(bucket: dict) -> dict:
    """Turn accumulated counts into rates. Every denominator is content-bearing, or VACUOUS."""
    out = dict(bucket)
    out["arms"] = {arm: _arm_rates(bucket["arms"][arm], bucket["adjudicated_headings"]) for arm in ARMS}
    m3 = dict(bucket["m3"])
    m3["X_CORRECTS_minus_X_REGRESSES"] = (
        m3[M3B.HeadingOutcome.X_CORRECTS.value] - m3[M3B.HeadingOutcome.X_REGRESSES.value]
    )
    m3["rule1_applied_here"] = False
    m3["rule1_owner"] = "decide_architecture (A5 as amended by A20)"
    out["m3"] = m3
    return out


def _pool_estimand(documents: list[dict]) -> dict:
    """Count-pooled M1-M5 across documents, keeping every content-bearing denominator."""
    adjudicated = sum(d["adjudicated_headings"] for d in documents)
    arms = {}
    for arm in ARMS:
        counts = {
            field_name: sum(d["arms"][arm][field_name] for d in documents)
            for field_name in (
                "emitted_occurrences",
                "emitted_unmatchable",
                "m1_recall_matched",
                "m1_precision_matched",
                "m2_denominator",
                "m2_exact",
                "m4_denominator",
                "m4_agree",
                "m4_unreadable_excluded",
                "m5_denominator",
                "m5_agree",
                "m5_out_of_scope_excluded",
                "m5_unreadable_excluded",
            )
        }
        # The SAME rate builder as the per-document path, so pooled and per-document figures
        # cannot be computed by two expressions that drift apart.
        arms[arm] = _arm_rates(counts, adjudicated)
    m3 = {
        field_name: sum(d["m3"][field_name] for d in documents)
        for field_name in ("denominator", "no_reference_excluded", "neither_arm_emitted")
    }
    for outcome in M3B.HeadingOutcome:
        m3[outcome.value] = sum(d["m3"][outcome.value] for d in documents)
    m3["rule1_applied_here"] = False
    return {
        "adjudicated_headings": adjudicated,
        "adjudicated_unresolved": sum(d["adjudicated_unresolved"] for d in documents),
        "arms": arms,
        "m3": m3,
    }


def m7_block(frames: list[dict]) -> dict:
    """M7 -- display-split INCIDENCE per architecture, over 100 % of the holdout.

    No oracle, and no correctness claim. Section 6 gives M7 oracle "none (a self-signature)",
    so this counts how often each architecture emits a letter-spaced-looking heading and says
    nothing about whether that heading is right.

    THE MATCHING INSTANCES ARE PRINTED, NOT ONLY COUNTED. A bare count cannot distinguish a
    detector that fired on the right headings from one that fired on the wrong ones, and the
    injected `R E P O R T` control needs the instance list to prove it was actually seen.
    """
    per_document = []
    for frame in frames:
        row = {"document": frame["document"], "arms": {}}
        for arm in ARMS:
            occurrences = frame["architecture_occurrences"][arm]
            hits = [occ for occ in occurrences if m7_is_display_split(occ["anchor"]["text"])]
            row["arms"][arm] = {
                "emitted_occurrences": len(occurrences),
                "display_split_headings": len(hits),
                "incidence": rate(len(hits), len(occurrences)),
                "instances": [
                    {
                        "page_number": occ["anchor"]["page_number"],
                        "line_number": occ["anchor"]["line_number"],
                        "text": occ["anchor"]["text"],
                    }
                    for occ in hits
                ],
            }
        per_document.append(row)

    pooled = {}
    for arm in ARMS:
        emitted = sum(d["arms"][arm]["emitted_occurrences"] for d in per_document)
        hits = sum(d["arms"][arm]["display_split_headings"] for d in per_document)
        pooled[arm] = {
            "emitted_occurrences": emitted,
            "display_split_headings": hits,
            "incidence": rate(hits, emitted),
        }
    return {
        "signature": f">= {M7_MIN_SINGLE_CHAR_TOKENS} single-character tokens",
        "oracle": "none -- a self-signature",
        "is_a_correctness_measure": False,
        "population": "100 % of the holdout",
        "per_document": per_document,
        "pooled": pooled,
    }


# ------------------------------------------------------------------------------ M9 (A38.8)


def m9_block(frames: list[dict]) -> dict:
    """M9's raw facts per document per architecture, plus A39.1's margin-line FACT.

    THE FACT IS `methodology_contracts.margin_line_loss`, CALLED. A39.1 ruled the quantity is
    the count of `Page.lines` where `line_number is not None` -- NOT `_coverage`'s numerator,
    and NOT a geometric approximation -- and that ANY strictly positive deficit fires, with no
    tolerance, no minimum and no percentage.

    RULE 0 IS NOT APPLIED HERE. I12 gives M9 the power to reject an arm outright, and A27.4
    gives that decision its own outcomes; both belong to `decide_architecture`. This records
    which arm loses margin-numbered lines on which document, and stops.
    """
    per_document = []
    for frame in frames:
        m9 = frame["m9"]
        loss = MC.margin_line_loss(m9["H"]["n_margin_numbered_lines"], m9["X"]["n_margin_numbered_lines"])
        per_document.append(
            {
                "document": frame["document"],
                "arms": {
                    arm: {
                        "derive_size_bands_returns_a_band": m9[arm]["derive_size_bands_returns_a_band"],
                        "coverage": m9[arm]["coverage"],
                        "coverage_floor": m9[arm]["coverage_floor"],
                        "coverage_meets_floor": m9[arm]["coverage_meets_floor"],
                        "n_lines_total": m9[arm]["n_lines_total"],
                        "n_margin_numbered_lines": m9[arm]["n_margin_numbered_lines"],
                        "n_margin_numbered_with_glyph_size": m9[arm]["n_margin_numbered_with_glyph_size"],
                    }
                    for arm in ARMS
                },
                "margin_line_loss": loss,
            }
        )
    return {
        "quantity": "count of Page.lines where line_number is not None (A39.1)",
        "tolerance": "NONE -- any strictly positive deficit fires",
        "diagnostics_excluded_from_the_clause": [
            "n_margin_numbered_with_glyph_size",
            "margin_numbered_line_keys",
        ],
        "rule0_applied_here": False,
        "rule0_owner": "decide_architecture (section 7.2 rule 0, outcomes by A27.4)",
        "per_document": per_document,
        "n_documents_with_margin_line_loss": sum(1 for d in per_document if d["margin_line_loss"]["fires"]),
    }


# --------------------------------------------------------------- section 8 (A27.5, A38.10)


def binomial_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p). Exact rational terms, no library dependence."""
    return sum(math.comb(n, i) * (p**i) * ((1 - p) ** (n - i)) for i in range(k + 1))


def clopper_pearson_upper(events: int, n: int, alpha: float = 0.05) -> float:
    """The exact one-sided 95 % Clopper-Pearson UPPER bound on pi. THE UNIT IS THE DOCUMENT.

    A27.5 makes this `score_metrics`' own obligation and deliberately keeps it OUT of
    `methodology_contracts`, which carries only the zero-event closed form. Implementing it
    here is therefore the frozen arrangement, not a relocation of a contract.

    AT ZERO EVENTS THE FROZEN CLOSED FORM IS RETURNED, from its single owner
    (`methodology_contracts.zero_event_upper_bound`). Section 8.3 froze `1 - 0.05**(1/N)`
    verbatim, so re-deriving it numerically here would give the study two spellings of one
    frozen number. A control asserts the general solver agrees with it, which is what proves
    they are the same statistic rather than two.

    Otherwise the bound is the p solving `P(X <= events | n, p) = alpha`, found by bisection
    on a monotone function. Bisection rather than a special-function library: the study has no
    scipy dependency, and an interval endpoint that moves with a backend version is exactly
    the drift A37.6 refused for the bootstrap percentiles.
    """
    if n < 1:
        raise ScoreInputError(EMPTY_DOCUMENT_SET, {"n": n})
    if not 0 <= events <= n:
        raise ScoreInputError(INVALID_EVENT_COUNT, {"events": events, "n": n})
    if events == 0:
        return MC.zero_event_upper_bound(n)
    if events == n:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if binomial_cdf(events, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


#: Section 8.2's frozen wording constraint. Zero events licenses an OBSERVATION, never a claim
#: about the true rate: "the true rate is zero" is exactly the inference the bound exists to
#: refuse, and 8.1 measured that the zero-event bootstrap carries no information at all.
ZERO_EVENT_STATEMENT = "no heading-level discordance was observed on {n} documents"


def document_events(frames: list[dict]) -> list[tuple[str, bool]]:
    """The section 8 event, per DOCUMENT: "has >= 1 heading-level H/X discordance".

    Derived from the frame's own committed region evidence -- `anchor_evidence.differ`, which
    is section 5.8's frozen predicate "every region where their emitted anchor sets differ".
    That is the heading-level comparison; M0a and M0b are LINE-level and are deliberately not
    used, because a line-text difference inside a paragraph is not a heading discordance.

    ONE RECORD PER DOCUMENT. The document is the independent unit (8.3), and
    `canonical_document_vector` refuses a duplicate identity -- which is what makes a
    heading-level table structurally unpassable to the statistics below.
    """
    return [
        (
            frame["document"],
            any(region["anchor_evidence"]["differ"] for page in frame["pages"] for region in page["regions"]),
        )
        for frame in frames
    ]


def section8(records: list[tuple[str, bool]]) -> dict:
    """The section 8 statistical contract. Unit = DOCUMENT, everywhere and without exception.

        estimand    pi = P(a document from the target population shows the event)
        bound       exact one-sided 95 % Clopper-Pearson upper bound on pi
        zero events closed form 1 - 0.05**(1/N); NO bootstrap (degenerate, measured in 8.1)
        non-zero    bootstrap permitted, reported alongside
        forbidden   any per-heading probability, any heading-as-iid-trial denominator

    THE FORBIDDEN FORM IS UNREACHABLE FROM HERE. This function takes document records only,
    and `canonical_document_vector` refuses duplicates, an empty set and a non-boolean event.
    A heading-as-trials vector -- many rows carrying one document identity -- therefore raises
    rather than producing the 39x-tighter bound 8.1 measured.

    THE BOOTSTRAP IS A37's HELPER, CALLED WITH NO CUSTOM STATISTIC ID (A38.10). It refuses at
    zero events by itself; this function additionally omits the interval from the report, so
    nothing downstream can read a degenerate [0.0, 0.0] as an estimate.
    """
    vector = MC.canonical_document_vector(records)
    n = len(vector)
    events = sum(1 for _identity, event in vector if event)

    bound = clopper_pearson_upper(events, n)
    bootstrap = MC.section8_document_bootstrap(records)

    out = {
        "estimand": "pi = P(a document from the target population exhibits >= 1 heading-level H/X discordance)",
        "unit": "document",
        "independent_unit_rule": "8.3 -- the document, never the heading",
        "n_documents": n,
        "events": events,
        "observed_rate": events / n,
        "clopper_pearson_upper_95": bound,
        "procedure": "exact one-sided 95 % Clopper-Pearson upper bound on the DOCUMENT unit",
        "per_document": [{"document": identity, "event": event} for identity, event in vector],
        "per_heading_probability_reported": False,
    }
    if events == 0:
        out["zero_event"] = True
        out["zero_event_form"] = "1 - 0.05**(1/N)"
        out["bootstrap_reported"] = False
        out["bootstrap_refusal_reason"] = bootstrap["reason"]
        out["statement"] = ZERO_EVENT_STATEMENT.format(n=n)
        # Asserted rather than assumed: the general solver and the frozen closed form must be
        # the same number, or the study would be quoting two different statistics.
        if not math.isclose(bound, MC.zero_event_upper_bound(n), rel_tol=0.0, abs_tol=1e-15):
            raise ScoreInputError(
                INVALID_EVENT_COUNT,
                {"bound": bound, "closed_form": MC.zero_event_upper_bound(n), "n": n},
            )
    else:
        out["zero_event"] = False
        out["bootstrap_reported"] = True
        out["bootstrap"] = bootstrap
    return out


def paired_differences(pairs: list[tuple[str, float, float]], quantity: str) -> dict:
    """Section 8.3 -- per-document paired differences, UNWEIGHTED mean, per-document detail.

    `pairs` is `[(document_identity, h_value, x_value), ...]` and the difference is `X - H`.

    THE MEAN IS UNWEIGHTED OVER DOCUMENTS AND THERE IS NO WEIGHT PARAMETER. Weighting by
    heading count is the specific defect section 8 forbids: it re-imports the heading-as-unit
    assumption 8.1 measured to be worth a factor of 39, through the back door of an average.
    There is no argument through which a caller could supply one.

    PER-DOCUMENT DETAIL IS MANDATORY AND IS RETURNED WITH THE MEAN, never collapsed into it.
    """
    if not pairs:
        raise ScoreInputError(EMPTY_DOCUMENT_SET, {"quantity": quantity})
    seen: set[str] = set()
    detail = []
    for identity, h_value, x_value in pairs:
        if identity in seen:
            raise ScoreInputError(DUPLICATE_PAIRED_DOCUMENT, {"document": identity, "quantity": quantity})
        seen.add(identity)
        if isinstance(h_value, bool) or isinstance(x_value, bool) or not _numeric(h_value) or not _numeric(x_value):
            raise ScoreInputError(
                NON_NUMERIC_PAIRED_VALUE,
                {"document": identity, "quantity": quantity, "H": repr(h_value), "X": repr(x_value)},
            )
        detail.append({"document": identity, "H": h_value, "X": x_value, "difference_X_minus_H": x_value - h_value})
    return {
        "quantity": quantity,
        "unit": "document",
        "n_documents": len(detail),
        "weighting": "UNWEIGHTED mean over documents -- never weighted by heading count",
        "mean_difference_X_minus_H": sum(d["difference_X_minus_H"] for d in detail) / len(detail),
        "per_document": detail,
    }


def _numeric(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


# ------------------------------------------------------- section 4.5 adequacy and the labels


def adequacy_block(frames: list[dict], strata_filled: int) -> dict:
    """Section 4.5 via the frozen chain: `filter_keys` -> `adequacy_occurrences` -> `adequacy`.

    A30.4 made `filter_keys` apply BOTH the P-head population restriction and the
    account/agency/grouping kind restriction itself, so nothing here re-implements either.
    Only MATCHABLE occurrences carry a key; an UNMATCHED one has no source position to count.
    """
    keyed = {arm: [] for arm in ARMS}
    for frame in frames:
        population = frame["population"]
        for arm in ARMS:
            for occurrence in frame["architecture_occurrences"][arm]:
                if occurrence["occurrence_key"] is None:
                    continue
                keyed[arm].append((_hashable(occurrence["occurrence_key"]), occurrence["anchor"]["kind"], population))

    h_keys = MC.filter_keys(keyed["H"])
    x_keys = MC.filter_keys(keyed["X"])
    occurrences = MC.adequacy_occurrences(h_keys, x_keys)
    return {
        "strata_filled": strata_filled,
        "occurrences": occurrences,
        "occurrence_rule": "|H_keys union X_keys| over A27.1 source-position keys, P-head and "
        "account/agency/grouping only (A28.1 as made executable by A30.4)",
        "verdict": MC.adequacy(strata_filled, occurrences),
        "gate_applied_here": False,
        "gate_owner": "decide_architecture (A27.6 Rule 3)",
    }


#: I13 -- the frozen consequence of a cross-engine failure. It is a REPORTING QUALIFICATION and
#: never blocks a decision (A27.6).
PDFIUM_CONDITIONED_FRAME = "PDFIUM-CONDITIONED FRAME"
CROSS_ENGINE_HEADLINE_FRACTION = 1 / 3


def cross_engine_block(cross_engine: dict | None) -> dict:
    """I13 -- label every RQ1/RQ2 result on a failing document; never block anything.

    A document below 0.95, or with any sampled page below 0.75, labels EVERY RQ1 and RQ2
    result computed on it. Failure on MORE THAN a third of sampled documents applies the
    qualification to BOTH headlines. The gate itself has exactly one owner -- `X09.gate`, via
    `cross_engine_control` -- and this function reads that verdict rather than recomputing a
    threshold.
    """
    if not cross_engine:
        return {
            "present": False,
            "reason": MISSING_CROSS_ENGINE_RESULT,
            "decision_blocking": False,
            "document_labels": {},
            "headline_qualification": None,
        }
    rows = cross_engine.get("per_document", [])
    labels = {row["document"]: (None if row["passed"] else PDFIUM_CONDITIONED_FRAME) for row in rows}
    failed = sum(1 for row in rows if not row["passed"])
    headline = PDFIUM_CONDITIONED_FRAME if rows and (failed / len(rows)) > CROSS_ENGINE_HEADLINE_FRACTION else None
    return {
        "present": True,
        "n_documents": len(rows),
        "n_failed": failed,
        "document_labels": labels,
        "headline_qualification": headline,
        "headline_rule": "> 1/3 of sampled documents failing qualifies BOTH headlines",
        "decision_blocking": False,
        "gate_owner": "x09_skeleton_cross_engine.gate, via cross_engine_control",
    }


def control_block(key: dict, adjudicated: dict, control_fixtures: dict | None) -> dict:
    """The N-A / N-B / N-C controls, reported as FACTS. No gate is applied here.

    A40.6's corrected mapping is recorded alongside, because the mapping is the thing a reader
    needs in order to know which metric each control is evidence about:

        M1 -> N-B + N-C     M2 -> N-A     M3 -> N-A

    A control never enters a C or D denominator. That is enforced in `_estimand_records` and
    in `score_estimand`, and asserted again here by reporting the control stimuli separately.
    """
    BO = _build_oracle()
    rows = []
    for bid, record in sorted(key["stimuli"].items()):
        if record.get("control_kind") is None:
            continue
        answers = {ns: adjudicated.get(ns, {}).get(bid) for ns in BO.ADJUDICATION_NAMESPACES}
        rows.append(
            {
                "blind_id": bid,
                "control_kind": record["control_kind"],
                "control_variant": record["control_variant"],
                "in_c_frame": record.get("in_c_frame", False),
                "in_d_frame": record.get("in_d_frame", False),
                "answered_routes": sorted(ns for ns, answer in answers.items() if answer is not None),
                "expected_truth": record.get("control_expected_truth"),
                "answers": {ns: answer for ns, answer in answers.items() if answer is not None},
            }
        )
    return {
        "metric_control_mapping": {"M1": ["N-B", "N-C"], "M2": ["N-A"], "M3": ["N-A"]},
        "mapping_source": "A40.6",
        "n_control_stimuli": len(rows),
        "counts": (control_fixtures or {}).get("counts"),
        "in_any_estimand_denominator": False,
        "gate_applied_here": False,
        "gate_owner": "decide_architecture (A27.6 Rule 3)",
        "per_control": rows,
    }


# --------------------------------------------------------------------------- the entrypoint


def score(
    *,
    frames: list[dict],
    adjudicated: dict,
    key: dict,
    s1: dict | None = None,
    cross_engine: dict | None = None,
    control_fixtures: dict | None = None,
    strata_filled: int = 0,
) -> dict:
    """THE result-bearing entrypoint: committed artifacts in, `metrics.json` payload out.

    Every input is a committed artifact. No PDF is opened, no architecture is re-run, no
    neutral clustering or anchor recognition happens here, and no decision is taken: Rule 0,
    Rule 1 and Rule 3 all belong to `decide_architecture`, and every block above says so in
    its own output rather than leaving it to be remembered.

    M6 IS ABSENT. Not disabled, not zero, not empty -- absent, per A20 and section 5's
    "M0-M9 minus M6".
    """
    BO = _build_oracle()
    validate_frames(frames)
    BO.validate_adjudicated(adjudicated, key)

    estimands = {
        ESTIMAND_C: score_estimand(key, adjudicated, ESTIMAND_C),
        ESTIMAND_D: score_estimand(key, adjudicated, ESTIMAND_D),
    }
    m9 = m9_block(frames)
    events = document_events(frames)

    return {
        "schema": "metrics/1",
        "implements": "section 6 (M0-M9 MINUS M6) and the section 8 contract (A27.5)",
        "m6": None,
        "m6_status": "STRUCK by A20 -- deferred to a separate validation study; no M6 output "
        "and no M6 acceptance condition exists",
        "n_documents": len(frames),
        "documents": [frame["document"] for frame in frames],
        "m0": m0_block(frames, s1),
        "estimands": estimands,
        "estimands_pooled_together": False,
        "why_estimands_are_separate": "A36.3 -- 'never pooled' means SEPARATE ESTIMANDS; C reads "
        "the AI route and D the human route (A36.4)",
        "m7": m7_block(frames),
        "m9": m9,
        "section8": section8(events),
        "section8_paired": [
            paired_differences(
                [
                    (
                        row["document"],
                        row["arms"]["H"]["n_margin_numbered_lines"],
                        row["arms"]["X"]["n_margin_numbered_lines"],
                    )
                    for row in m9["per_document"]
                ],
                "margin-numbered lines recovered",
            ),
            paired_differences(
                [
                    (row["document"], row["arms"]["H"]["coverage"], row["arms"]["X"]["coverage"])
                    for row in m9["per_document"]
                ],
                "_coverage",
            ),
        ],
        "adequacy": adequacy_block(frames, strata_filled),
        "cross_engine": cross_engine_block(cross_engine),
        "controls": control_block(key, adjudicated, control_fixtures),
        "decision_taken_here": False,
        "decision_owner": "decide_architecture",
    }


def write_metrics(payload: dict, out_path: Path | None = None) -> Path:
    """Write the canonical `results/metrics.json`. REFUSES before a VALID execution boundary.

    Guarded exactly as the oracle key, S1 and cross-engine writers are, through the same
    single authority: `metrics.json` is in `build_oracle.CANONICAL_ARTIFACTS`, so this path
    cannot be written while the one-way boundary is ABSENT, UNCOMMITTED or MUTATED. A stray
    marker on disk unlocks nothing.
    """
    BO = _build_oracle()
    out_path = Path(out_path) if out_path else (EV / "results" / "metrics.json")
    BO.assert_write_permitted(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1, default=str))
    return out_path
