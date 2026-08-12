"""x27 -- `score_metrics.py`: section 6 (M0-M9 minus M6) and the section 8 contract.

NOT CONFIRMATORY. SYNTHETIC + DEVELOPMENT only. No holdout document is opened, nothing is
adjudicated, no confirmatory artifact is created, and no architecture decision is taken.
Evidence: `results/x27_score_metrics.json`.

THE QUESTION THIS PROBE ANSWERS, and its negative controls must be able to answer it FALSE:

    does `score_metrics` compute the frozen section 6 and section 8 quantities from committed
    artifacts, and does each of HARNESS-PLAN section 5's ELEVEN controls actually fire?

WHY THERE IS A SYNTHETIC ADJUDICATION, AND WHAT IT IS NOT. Scoring needs an adjudicated
artifact, and none exists: the execution boundary is ABSENT and creating a real one would
spend the holdout. So this probe DERIVES a synthetic adjudication from the COMMITTED key --
each heading's text, role and parent taken from an arm's own committed occurrence, and its
`start_physical_line` / `start_x_px` computed geometrically so the A38.7 resolver lands back
on the same `start_ngid`. That makes it a KNOWN-ANSWER fixture: on clean input every metric is
perfect, so any control that moves a metric has moved it for the reason under test.

    It is NOT an adjudication, NOT evidence about either architecture, and NOT written to
    `results/oracle_adjudicated.json`. It establishes that the SCORER is correct, never that
    an architecture is. Calling it an oracle would be the exact confusion section 5.1 refuses.

WHY THE CONTROLS RUN THROUGH THE LIVE SCORER. Every control below calls the real
`score_metrics` entrypoints on real key records. A control that reimplemented the traversal it
was checking could only ever agree with itself, which is the false-green class these controls
exist to catch.

RUN WITH AN INTERPRETER CARRYING BOTH `pymupdf` AND `pypdfium2`, as `x21`/`x22`/`x26` require.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
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
import build_oracle as BO  # noqa: E402
import control_fixtures as CF  # noqa: E402
import m3_boundaries as M3B  # noqa: E402
import methodology_contracts as MC  # noqa: E402
import oracle_geometry as OG  # noqa: E402
import run_extended  # noqa: E402
import run_hybrid  # noqa: E402
import s1_control as S1  # noqa: E402
import score_metrics as SM  # noqa: E402

from deltatrack.parsers import pdf_anchors as PA  # noqa: E402

OUT = EV / "results" / "x27_score_metrics.json"
ROWS: list[dict] = []
FAILED: list[str] = []
#: Ambiguities this probe carries as OPEN. Recorded rather than resolved: the frozen sources do
#: not determine them, and choosing here would be scoring behaviour decided after the fact.
STOPS: list[dict] = []

DOC_NAME = "118-hr-8752/1"
DOC_PATH = REPO / "tests/corpus/118-hr-8752/1_reported-in-house.pdf"
PAGE_LIMIT = 16  # machinery demonstration window, NOT a census

#: Emitted anchor kind -> a synthetic ORACLE role that coarsens the SAME way under A36.7.
#: Chosen so the known-answer fixture starts at perfect M5 agreement; the M5 controls then move
#: it deliberately. `major` has no oracle role, and `title` is the CONTAINER that stands in.
ORACLE_ROLE_FOR_KIND = {
    "account": "account",
    "section": "section",
    "agency": "agency",
    "grouping": "grouping",
    "title": "title",
    "major": "title",
    "subsection": "other",
    "preamble": "other",
}


def check(name: str, expected, observed, fails_when: str = "") -> bool:
    ok = expected == observed
    ROWS.append({"test": name, "expected": expected, "observed": observed, "pass": ok, "fails_when": fails_when})
    if not ok:
        FAILED.append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   expected={expected!r} observed={observed!r}"))
    return ok


def refusal(fn):
    """The refusal REASON a call raises, or None if it returned. Never swallows a pass."""
    try:
        fn()
    except (SM.ScoreInputError, BO.OracleBuildError, BF.FrameConstructionError) as exc:
        return exc.reason
    except MC.BootstrapInputError as exc:
        return exc.reason
    except MC.UnknownRole:
        return "UnknownRole"
    return None


# ------------------------------------------------------------------ DEVELOPMENT material


def development_material():
    """The real frame, the real oracle key (controls included), and the synthetic adjudication."""
    for member in BO.HOLDOUT_GUARD:
        if member in str(DOC_PATH):
            raise SystemExit(f"REFUSED: {DOC_PATH} touches holdout member {member}")
    h = run_hybrid.run(DOC_PATH, limit=PAGE_LIMIT)
    x, _s = run_extended.run(DOC_PATH, limit=PAGE_LIMIT)
    sha = hashlib.sha256(DOC_PATH.read_bytes()).hexdigest()
    frame = BF.build_document_frame(sha, DOC_NAME, BF.P_HEAD, h, x)

    manifest = json.loads(CF.MANIFEST_PATH.read_text())
    controls = BO.control_specs(manifest, EV, REPO)
    built = BO.build([{"frame": frame, "pdf_path": DOC_PATH, "stratum": "DEVELOPMENT"}], controls=controls)
    return sha, h, x, frame, built.key, manifest


def synthetic_headings(record: dict, arm: str = "H") -> list[dict]:
    """One region's adjudicated headings, derived so the A38.7 join resolves back exactly.

    The geometry is computed FORWARD through `oracle_geometry.pdf_x_to_pixel` and the scorer
    then inverts it through the frozen `pixel_to_pdf_x`. Anything that broke the transform, the
    bijection or the candidate set would show up as an unresolved heading rather than as a
    silently wrong match.
    """
    occurrences = record.get("architecture_occurrences")
    if not occurrences:
        return []
    bijection = [list(k) for k in record["region_line_bijection"]]
    headings = []
    for row in occurrences[arm]:
        if row["match_status"] != "MATCHABLE" or row["occurrence_key"] is None:
            continue
        _sha, _page, line_key, ngid = row["occurrence_key"]
        line_key = list(line_key)
        if line_key not in bijection:
            continue
        candidates = record["identity_candidates"].get(f"{line_key[0]}:{line_key[1]}") or []
        x0 = next((c[1] for c in candidates if c[0] == ngid), None)
        if x0 is None:
            continue
        headings.append(
            {
                "text": row["anchor"]["text"],
                "role": ORACLE_ROLE_FOR_KIND[row["anchor"]["kind"]],
                "parent": row["immediate_parent"],
                "start_physical_line": bijection.index(line_key) + 1,
                "start_x_px": OG.pdf_x_to_pixel(x0, record["bbox_pdf_points"][0], record["dpi"]),
            }
        )
    return headings


def synthetic_adjudication(key: dict) -> dict:
    """A complete, schema-valid adjudicated artifact for every stimulus and every required route.

    A control is answered with its OWN committed expected text and `UNREADABLE` coordinates:
    the probe does not know where a control's heading starts and refuses to invent it. Controls
    never enter an estimand denominator, so an unresolvable control coordinate cannot reach a
    metric -- which is itself asserted below.
    """
    adjudicated = {ns: {} for ns in BO.ADJUDICATION_NAMESPACES}
    for bid, record in key["stimuli"].items():
        if record.get("control_kind") is not None:
            headings = [
                {
                    "text": h.get("text"),
                    "role": "other",
                    "parent": None,
                    "start_physical_line": SM.UNREADABLE,
                    "start_x_px": SM.UNREADABLE,
                }
                for h in (record.get("control_expected_truth") or [])
            ]
        else:
            headings = synthetic_headings(record)
        for route in record["adjudication_routes"]:
            adjudicated[route][bid] = {"id": bid, "headings": copy.deepcopy(headings)}
    return adjudicated


# --------------------------------------------------------- a hand-built stimulus, for M3
#
# The real frame's headings are clean, which is the right baseline but cannot exhibit a weld.
# These build a REAL-SHAPED key record with chosen texts, so the M3 controls run through
# `score_estimand` -- the live path -- rather than through `heading_outcome` in isolation.

SYNTH_SHA = "s" * 64
SYNTH_BBOX = [72.0, 100.0, 300.0, 120.0]
SYNTH_DPI = MC.PRIMARY_DPI


def make_stimulus(
    oracle_text: str,
    h_text: str,
    x_text: str,
    *,
    role: str = "account",
    parent: str | None = "AGENCY",
    emitted_parent: str | None = "AGENCY",
    kind: str = "account",
    in_c: bool = False,
    in_d: bool = True,
    include_line_state: bool = True,
    document: str = "SYNTH/1",
    page: int = 1,
    region: int = 0,
    ngid: int = 10,
    extra_unmatchable_emitted: int = 0,
    extra_unresolvable_adjudications: int = 0,
):
    """One synthetic stimulus with a chosen oracle text and chosen H / X emissions.

    `include_line_state=False` proves M3's INSULATION structurally: the record carries no
    segmentation label at all, so a scorer that consulted one could not run.

    `extra_unmatchable_emitted` and `extra_unresolvable_adjudications` exist because the
    DEVELOPMENT window is degenerate for two denominators: every occurrence there is MATCHABLE
    and the adjudicated and emitted counts happen to be equal, so a scorer that dropped
    refusals from a denominator would score identically. The fault matrix found both. These
    make the two denominators DIFFER, so the checks below can distinguish them.
    """
    line_key = [page, region * BF.REGION_SIZE]
    candidates = {f"{line_key[0]}:{line_key[1]}": [[ngid, 100.0], [ngid + 1, 180.0]]}
    key_tuple = [SYNTH_SHA, page, line_key, ngid]

    def occurrence(text):
        return {
            "anchor": {
                "page_number": page,
                "line_number": 1,
                "kind": kind,
                "text": text,
                "division": None,
            },
            "page_number": page,
            "region_ordinal": region,
            "placed_neutral_line_key": line_key,
            "occurrence_key": key_tuple,
            "match_status": "MATCHABLE",
            "unmatched_reason": None,
            "immediate_parent": emitted_parent,
            "breadcrumb": ["TITLE I", "MAJOR", emitted_parent, text] if emitted_parent else [text],
        }

    def unmatchable_occurrence(text):
        """A production occurrence the A30 bridge REFUSED. It has no key and can never match."""
        row = occurrence(text)
        row.update({"occurrence_key": None, "match_status": "UNMATCHED", "unmatched_reason": "SYNTHETIC_REFUSAL"})
        return row

    bid = hashlib.sha256(
        f"{document}|{page}|{region}|{oracle_text}|{h_text}|{x_text}|"
        f"{extra_unmatchable_emitted}|{extra_unresolvable_adjudications}".encode()
    ).hexdigest()[:16]
    record = {
        "document": document,
        "document_sha256": SYNTH_SHA,
        "page_number": page,
        "region_ordinal": region,
        "frames": [f for f, on in (("C", in_c), ("D", in_d)) if on],
        "in_c_frame": in_c,
        "in_d_frame": in_d,
        "adjudication_routes": [r for r, on in ((BO.ROUTE_AI, in_c), (BO.ROUTE_HUMAN, in_d)) if on],
        "is_r1_repeat": False,
        "control_kind": None,
        "control_variant": None,
        "dpi": SYNTH_DPI,
        "bbox_pdf_points": SYNTH_BBOX,
        "region_line_bijection": [line_key],
        "identity_candidates": candidates,
        "architecture_occurrences": {
            arm: [occurrence(text)]
            + [unmatchable_occurrence(f"{text} REFUSED {i}") for i in range(extra_unmatchable_emitted)]
            for arm, text in (("H", h_text), ("X", x_text))
        },
    }
    if include_line_state:
        # Present but deliberately DISCORDANT: M3 must ignore it entirely.
        record["line_state_for_this_region"] = {"segmentation_discordance": True, "text_discordance": True}

    heading = {
        "text": oracle_text,
        "role": role,
        "parent": parent,
        "start_physical_line": 1,
        "start_x_px": OG.pdf_x_to_pixel(100.0, SYNTH_BBOX[0], SYNTH_DPI),
    }
    # An adjudicated heading the A38.7 resolver REFUSES: its reported physical line does not
    # exist in the region. It stays in the recall denominator and can never match (I10).
    unresolvable = [
        {**heading, "text": f"{oracle_text} UNRESOLVABLE {i}", "start_physical_line": 99 + i}
        for i in range(extra_unresolvable_adjudications)
    ]
    key = {"schema": "oracle_key/3", "n_stimuli": 1, "stimuli": {bid: record}}
    adjudicated = {ns: {} for ns in BO.ADJUDICATION_NAMESPACES}
    for route in record["adjudication_routes"]:
        adjudicated[route][bid] = {"id": bid, "headings": [dict(heading)] + [dict(u) for u in unresolvable]}
    return key, adjudicated


def m3_outcome_through_scorer(oracle_text: str, h_text: str, x_text: str, **kwargs) -> dict:
    """Run one synthetic stimulus through the LIVE `score_estimand` and return its M3 row."""
    key, adjudicated = make_stimulus(oracle_text, h_text, x_text, **kwargs)
    return SM.score_estimand(key, adjudicated, SM.ESTIMAND_D)["pooled"]["m3"]


def make_m0_frame(spec: list[tuple[bool, bool, bool]]) -> dict:
    """A synthetic frame with chosen per-line discordance. `spec` is (text_d, seg_d, both_absent).

    WHY THIS EXISTS. On the DEVELOPMENT window M0b is ZERO, so the two components do not
    overlap and `union` and `sum` are the SAME NUMBER -- a scorer that added them would score
    identically and the union check would pass on a coincidence. The fault matrix's F1 proved
    exactly that. This builds material where a line is BOTH text- and segmentation-discordant,
    so the two readings differ and the check can actually decide between them.

    Every committed field is built CONSISTENTLY with its flags, because `validate_frame`
    independently recomputes each one and would refuse otherwise.
    """
    lines, per_region = [], {}
    for ordinal, (text_d, seg_d, both_absent) in enumerate(spec):
        region_ordinal = ordinal // BF.REGION_SIZE
        state = "BOTH_ABSENT" if both_absent else ("TEXT_DIFFERS" if text_d else "SAME")
        lines.append(
            {
                "key": [1, ordinal],
                "baseline": 700.0 - ordinal,
                "bbox": [72.0, 700.0 - ordinal, 300.0, 710.0 - ordinal],
                "gids": [ordinal],
                "identity_candidates": [{"ngid": ordinal, "x0": 72.0}],
                "region_ordinal": region_ordinal,
                "in_m0_risk_set": not both_absent,
                "line_state": {
                    "state": state,
                    "h_text": "" if both_absent else "A",
                    "x_text": "" if both_absent else ("B" if text_d else "A"),
                    "h_signature": [] if both_absent else [1],
                    "x_signature": [] if both_absent else ([2] if seg_d else [1]),
                    "text_discordance": bool(text_d),
                    "segmentation_discordance": bool(seg_d),
                    "common_gids": [ordinal],
                    "diagnostics": {"SEGMENTATION_DEFINED": True},
                },
            }
        )
        bucket = per_region.setdefault(region_ordinal, {"keys": [], "text": False, "seg": False})
        bucket["keys"].append([1, ordinal])
        bucket["text"] = bucket["text"] or bool(text_d)
        bucket["seg"] = bucket["seg"] or bool(seg_d)

    regions = []
    for region_ordinal, bucket in sorted(per_region.items()):
        reasons = [
            r for r, on in (("TEXT_DISCORDANCE", bucket["text"]), ("SEGMENTATION_DISCORDANCE", bucket["seg"])) if on
        ]
        regions.append(
            {
                "page_number": 1,
                "region_ordinal": region_ordinal,
                "neutral_line_keys": bucket["keys"],
                "short_trailing": len(bucket["keys"]) < BF.REGION_SIZE,
                "line_count": len(bucket["keys"]),
                "d_frame": bool(reasons),
                "d_reasons": reasons,
                "discordant_lines": {"TEXT_DISCORDANCE": [], "SEGMENTATION_DISCORDANCE": []},
                "anchor_evidence": {"differ": False, "H": [], "X": []},
                "c_frame": False,
            }
        )
    empty_m9 = {
        "derive_size_bands_returns_a_band": True,
        "coverage": 1.0,
        "coverage_floor": 0.85,
        "coverage_meets_floor": True,
        "n_lines_total": len(lines),
        "n_margin_numbered_lines": len(lines),
        "n_margin_numbered_with_glyph_size": len(lines),
    }
    return {
        "document": "SYNTH-M0/1",
        "document_sha256": SYNTH_SHA,
        "population": BF.P_HEAD,
        "region_size": BF.REGION_SIZE,
        "pages": [{"page_number": 1, "neutral_lines": lines, "regions": regions}],
        "counts": {"neutral_lines": len(lines)},
        "m9": {"H": dict(empty_m9), "X": dict(empty_m9)},
        "architecture_occurrences": {"H": [], "X": []},
    }


# ------------------------------------------------------------------------- the M0 block


def part_m0(frame: dict, s1: dict) -> dict:
    print("\n== section 6: the M0 block ==")
    block = SM.m0_block([frame], s1)
    doc = block["per_document"][0]

    check(
        "the risk set EXCLUDES BOTH_ABSENT and the two partition the neutral lines",
        (True, doc["neutral_lines_in_scope"]),
        (doc["both_absent"] > 0, doc["risk_set"] + doc["both_absent"]),
        "BOTH_ABSENT lines are absent from this material (so the control is vacuous), or the "
        "risk set and the both-absent count do not partition the committed lines",
    )
    # THE UNION, ON MATERIAL WHERE UNION AND SUM DIFFER. This window's M0b is zero, so the two
    # readings coincide there and a scorer that added the components would score identically.
    # The synthetic frame below carries lines that are BOTH text- and segmentation-discordant,
    # which is the only shape that can tell the two apart.
    overlap_frame = make_m0_frame(
        [(True, False, False)] * 3 + [(False, True, False)] * 2 + [(True, True, False)] * 4 + [(False, False, True)] * 2
    )
    overlap = SM.m0_document(overlap_frame)
    check(
        "M0-any is the UNION of the two components, never their sum",
        (7, 6, 9, 9),
        (
            overlap["M0a_text_discordant_lines"],
            overlap["M0b_segmentation_discordant_lines"],
            overlap["M0_any_discordant_lines"],
            overlap["risk_set"],
        ),
        "M0-any was formed by addition, which double-counts a line that is both text- and "
        "segmentation-discordant and can push the reported rate above 1.0",
    )
    check(
        "...and on this fixture the SUM is a different number, so the check can decide",
        (13, False),
        (
            overlap["M0a_text_discordant_lines"] + overlap["M0b_segmentation_discordant_lines"],
            overlap["M0a_text_discordant_lines"] + overlap["M0b_segmentation_discordant_lines"]
            == overlap["M0_any_discordant_lines"],
        ),
        "the union and the sum agree on this fixture too, so the check above passed on a "
        "coincidence rather than on the rule",
    )
    check(
        "M0-any on the REAL frame equals the union recomputed independently here",
        len(
            [
                ln
                for page in frame["pages"]
                for ln in page["neutral_lines"]
                if ln["in_m0_risk_set"]
                and (ln["line_state"]["text_discordance"] or ln["line_state"]["segmentation_discordance"])
            ]
        ),
        doc["M0_any_discordant_lines"],
        "the scorer's M0-any disagrees with the union of the committed per-line flags",
    )
    check(
        "BOTH separately named M0b quantities are emitted, and no bare 'M0b' exists",
        (True, True, False),
        ("M0b_segmentation_rate" in doc, "M0b_rate_on_defined" in doc, "M0b" in doc),
        "a single 'M0b' is emitted, so a reader cannot tell the full-risk-set rate from the "
        "one section 5 permits calling 'the fraction of comparable groupings that disagree'",
    )
    check(
        "M0c is reported on its OWN denominator and is NOT pooled with the line rates",
        (False, "region"),
        (doc["m0c"]["pooled_with_line_rates"], doc["m0c"]["unit"]),
        "M0c is combined with M0a/M0b, producing a rate whose denominator is part lines and part regions",
    )
    check(
        "the pooled figures are count-pooled and carry their content-bearing denominator",
        (doc["risk_set"], doc["M0a_text_discordant_lines"]),
        (block["pooled"]["risk_set"], block["pooled"]["M0a_text_discordant_lines"]),
        "pooling averaged per-document rates, which weights a 40-line document like a "
        "4,000-line one and leaves the pooled figure with no real denominator",
    )
    return {
        "document": doc["document"],
        "risk_set": doc["risk_set"],
        "both_absent": doc["both_absent"],
        "M0a_text_discordant_lines": doc["M0a_text_discordant_lines"],
        "M0b_segmentation_discordant_lines": doc["M0b_segmentation_discordant_lines"],
        "M0_any_discordant_lines": doc["M0_any_discordant_lines"],
        "M0a_text_rate": doc["M0a_text_rate"],
        "M0b_rate_on_defined": doc["M0b_rate_on_defined"],
        "m0c": doc["m0c"],
        "reportable": block["reportable"],
    }


# --------------------------------------------------------- the occurrence-level join, M1-M5


def part_join(key: dict, adjudicated: dict) -> dict:
    print("\n== A38.7: the occurrence-level join, and M1-M5 on a known answer ==")
    c = SM.score_estimand(key, adjudicated, SM.ESTIMAND_C)
    d = SM.score_estimand(key, adjudicated, SM.ESTIMAND_D)

    check(
        "each estimand reads the route its PURPOSE mandates (A36.4)",
        (BO.ROUTE_AI, BO.ROUTE_HUMAN),
        (c["route"], d["route"]),
        "C metrics read the human answer, or D decisions read the AI answer -- either makes "
        "the oracle source depend on architecture disagreement",
    )
    check(
        "both estimands are non-empty, so nothing below is vacuous",
        (True, True),
        (c["n_stimuli"] > 0, d["n_stimuli"] > 0),
        "an estimand drew no stimuli here, so its metrics passed on an empty population",
    )
    check(
        "the estimands are reported SEPARATELY and never pooled together (A36.3)",
        True,
        c["estimand"] != d["estimand"] and c["pooled"] is not d["pooled"],
        "C and D were merged into one denominator, which is exactly what 'never pooled' forbids",
    )

    pooled = d["pooled"]
    check(
        "every synthetic adjudication RESOLVED through the frozen A38.7 geometry",
        0,
        pooled["adjudicated_unresolved"],
        "the forward pdf_x -> pixel map and the frozen inverse disagree, so the known-answer "
        "fixture cannot establish anything about the join",
    )
    check(
        "M1 recall is PERFECT on the known answer, for the arm it was derived from",
        1.0,
        pooled["arms"]["H"]["M1_recall"],
        "the join failed to match an occurrence to the adjudication derived FROM it, so the "
        "matching key is not doing what A27.1/A30.1 specify",
    )
    check(
        "M1 recall's denominator is the ADJUDICATED enumeration (I10)",
        pooled["adjudicated_headings"],
        pooled["arms"]["H"]["M1_recall_denominator"],
        "recall is scored against the EMITTED set, which cannot fall below 1.0 by construction "
        "and would report a perfect recall for an architecture that emitted nothing",
    )
    check(
        "M2, M4 and M5 are perfect on the known answer",
        (1.0, 1.0, 1.0),
        (
            pooled["arms"]["H"]["M2_exactness"],
            pooled["arms"]["H"]["M4_parent_agreement"],
            pooled["arms"]["H"]["M5_role_agreement"],
        ),
        "a metric disagrees with the committed values it was derived from, so it is measuring "
        "something other than what it claims",
    )
    # M3's KNOWN ANSWER, and the exact limit of what this fixture licenses. The oracle text is
    # H's own text, so H is clean on every heading BY CONSTRUCTION -- and X is clean only where
    # the two arms happen to agree. The invariant that follows is therefore about H, not about
    # both arms: nothing here may be read as evidence that X is worse, because the fixture is
    # definitionally biased toward the arm it was derived from. Any X_CORRECTS or BOTH_DIRTY
    # would mean M3 invented a defect against an extractor's own text.
    m3 = pooled["m3"]
    check(
        "M3 finds H clean on EVERY heading, the oracle being H's own text",
        (m3["denominator"], 0, 0),
        (
            m3[M3B.HeadingOutcome.BOTH_CLEAN.value] + m3[M3B.HeadingOutcome.X_REGRESSES.value],
            m3[M3B.HeadingOutcome.X_CORRECTS.value],
            m3[M3B.HeadingOutcome.BOTH_DIRTY.value],
        ),
        "M3 invents a defect against an oracle that IS the extractor's own text, or it scores "
        "a correction where the reference was taken from the arm being corrected",
    )
    # A MATERIAL FACT, NOT A FINDING ABOUT THE ARCHITECTURES. x16 measured that the two arms'
    # TEXT disagreed on 30 of 1,249 shared DEVELOPMENT occurrences. Where that happens in this
    # window, an oracle derived from H necessarily scores X as the regressing arm. Recorded so
    # the count below cannot later be quoted as a comparative result.
    disagreements = [
        {
            "page_number": h["anchor"]["page_number"],
            "line_number": h["anchor"]["line_number"],
            "H": h["anchor"]["text"],
            "X": x_row["anchor"]["text"],
        }
        for bid, record in SM._estimand_records(key, SM.ESTIMAND_D)
        if record.get("architecture_occurrences")
        for h in record["architecture_occurrences"]["H"]
        for x_row in record["architecture_occurrences"]["X"]
        if h["occurrence_key"] is not None
        and h["occurrence_key"] == x_row["occurrence_key"]
        and SM.m2_normalize(h["anchor"]["text"]) != SM.m2_normalize(x_row["anchor"]["text"])
    ]
    check(
        "every X_REGRESSES is explained by a REAL H-vs-X text disagreement in this material",
        m3[M3B.HeadingOutcome.X_REGRESSES.value],
        len(disagreements),
        "M3 reports a regression that no committed text disagreement accounts for, i.e. the "
        "outcome came from somewhere other than the two arms' emitted text",
    )
    # THE TWO DENOMINATORS, ON MATERIAL WHERE THEY DIFFER. In this window every occurrence is
    # MATCHABLE and the adjudicated and emitted counts are both 23, so I10 and its violation
    # produce the same number and a dropped refusal subtracts zero. The fault matrix's F4 and
    # F16 proved both blind spots. These two fixtures separate them.
    recall_key, recall_adj = make_stimulus("A HEADING", "A HEADING", "A HEADING", extra_unresolvable_adjudications=1)
    recall = SM.score_estimand(recall_key, recall_adj, SM.ESTIMAND_D)["pooled"]
    check(
        "I10 -- recall divides by the ADJUDICATED count even when the emitted count differs",
        (2, 1, 0.5),
        (
            recall["adjudicated_headings"],
            recall["arms"]["H"]["emitted_occurrences"],
            recall["arms"]["H"]["M1_recall"],
        ),
        "recall is scored against the EMITTED set: with 2 printed headings and 1 emitted this "
        "would report 1.0, a perfect recall for an architecture that missed half of them",
    )
    precision_key, precision_adj = make_stimulus("A HEADING", "A HEADING", "A HEADING", extra_unmatchable_emitted=1)
    precision = SM.score_estimand(precision_key, precision_adj, SM.ESTIMAND_D)["pooled"]
    check(
        "an UNMATCHABLE emitted occurrence stays in the PRECISION denominator",
        (2, 1, 0.5),
        (
            precision["arms"]["H"]["emitted_occurrences"],
            precision["arms"]["H"]["emitted_unmatchable"],
            precision["arms"]["H"]["M1_precision"],
        ),
        "an occurrence the A30 bridge refused was dropped, shrinking the denominator invisibly "
        "and reporting 1.0 for an arm that emitted a heading it could not place",
    )
    check(
        "the REPORTED denominator is the one the rate actually divided by",
        (recall["adjudicated_headings"], precision["arms"]["H"]["emitted_occurrences"]),
        (
            recall["arms"]["H"]["M1_recall_denominator"],
            precision["arms"]["H"]["M1_precision_denominator"],
        ),
        "the published denominator is a separate expression from the one used in the division, "
        "so the label can state I10 while the arithmetic does something else",
    )
    return {
        "C": {"n_stimuli": c["n_stimuli"], "pooled": c["pooled"]},
        "D": {"n_stimuli": d["n_stimuli"], "pooled": d["pooled"]},
        "h_vs_x_text_disagreements": disagreements,
        "what_this_fixture_licenses": "the oracle is H's own text, so H is clean by "
        "construction and X_REGRESSES counts arm disagreement, NOT architecture quality. "
        "Nothing here is evidence about H versus X.",
    }


# ------------------------------------------------------------------------- M7, M9, M6, 4.5


def part_m7_m9_m6(frame: dict) -> dict:
    print("\n== section 6: M7 incidence, M9 raw facts, and M6's ABSENCE ==")
    m7 = SM.m7_block([frame])
    m9 = SM.m9_block([frame])

    check(
        "M7 declares itself a self-signature and NOT a correctness measure",
        (False, "none -- a self-signature"),
        (m7["is_a_correctness_measure"], m7["oracle"]),
        "M7 is presented as heading correctness, which it cannot be: it has no oracle",
    )
    check(
        "M7 prints the matching INSTANCES, not only a count",
        True,
        all("instances" in row["arms"][arm] for row in m7["per_document"] for arm in ("H", "X")),
        "only counts are reported, so a detector firing on the wrong headings is "
        "indistinguishable from one firing on the right ones",
    )
    check(
        "M9 records the A39.1 margin-line FACT and does NOT apply Rule 0",
        (False, "NONE -- any strictly positive deficit fires"),
        (m9["rule0_applied_here"], m9["tolerance"]),
        "the scorer applies Rule 0, which belongs to decide_architecture, or it invented a "
        "tolerance A39.1 explicitly refuses",
    )
    check(
        "the margin-line quantity is the A39.1 count, matching `margin_line_loss` exactly",
        MC.margin_line_loss(frame["m9"]["H"]["n_margin_numbered_lines"], frame["m9"]["X"]["n_margin_numbered_lines"]),
        m9["per_document"][0]["margin_line_loss"],
        "the scorer computed a different margin-line comparison from the frozen one -- a "
        "coverage numerator or a geometric approximation instead of the ruled count",
    )
    return {"m7_pooled": m7["pooled"], "m9": m9}


def m6_surfaces(node, path: str = "") -> list[str]:
    """Every path in a finished payload whose KEY names M6. Recursive, structure-agnostic.

    Deliberately not a check against `dir(score_metrics)`. A module-symbol scan cannot see an
    `m6: None` key sitting in the result-bearing payload -- which is what the previous spelling
    emitted, and which a consumer can read, iterate, or render as "M6: not measured". That is a
    statement about M6, and A20 struck M6.

    Walking the FINISHED payload also means a future surface reintroducing M6 anywhere -- nested
    inside an estimand, a per-document row, a control record -- is caught wherever it appears,
    rather than only at the top level a hand-written key list would cover.
    """
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if re.fullmatch(r"(?i)m_?6.*", str(key)):
                found.append(here)
            found.extend(m6_surfaces(value, here))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(m6_surfaces(value, f"{path}[{index}]"))
    return found


# ------------------------------------------------------------------- I13, cross-engine
#
# The scorer names the surfaces it labels in `CROSS_ENGINE_LABELLED_PATHS`. The scan below
# DISCOVERS per-document result rows in the finished payload instead, so a surface added to the
# payload and forgotten in that list is found here rather than published unqualified.

#: Per-document surfaces that are NOT RQ1/RQ2 results, kept in the PROBE so the scorer cannot
#: quietly grow an exclusion for something it simply forgot to label.
#:
#:   `m0.s1_liveness`  -- S1 is a Rule 3 gate INPUT (A27.6), not a result computed on a document.
#:   `cross_engine`    -- the qualification's own source measurement; labelling it with itself
#:                        would be circular.
NON_RESULT_DOCUMENT_SURFACES = ("m0.s1_liveness.per_document", "cross_engine.per_document")


def document_result_rows(node, path: str = "") -> list[tuple[str, dict]]:
    """Every `(path, row)` in a finished payload that is a per-document RESULT row."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if key == "per_document" and isinstance(value, list):
                if not any(here.startswith(skip) for skip in NON_RESULT_DOCUMENT_SURFACES):
                    found.extend((here, row) for row in value if isinstance(row, dict) and "document" in row)
                continue
            found.extend(document_result_rows(value, here))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(document_result_rows(value, f"{path}[{index}]"))
    return found


def unlabelled_result_rows(payload: dict) -> list[str]:
    """Result rows carrying no I13 label at all. The omission this control exists to catch."""
    return sorted(
        f"{path}::{row['document']}"
        for path, row in document_result_rows(payload)
        if "cross_engine_qualification" not in row
    )


def synthetic_cross_engine(rows: list[tuple[str, bool]]) -> dict:
    """A `cross_engine_control/1`-shaped artifact. `rows` is [(document, passed), ...]."""
    return {
        "schema": "cross_engine_control/1",
        "per_document": [
            {
                "document": document,
                "passed": passed,
                "qualification": None if passed else SM.PDFIUM_CONDITIONED_FRAME,
                "decision_blocking": False,
            }
            for document, passed in rows
        ],
        "n_documents": len(rows),
        "decision_blocking": False,
    }


def part_cross_engine_i13(scored_failing: dict, scored_passing: dict) -> dict:
    print("\n== I13: the cross-engine qualification is APPLIED, not merely reported ==")

    rows = document_result_rows(scored_failing)
    surfaces = sorted({path for path, _row in rows})
    check(
        "the payload really carries per-document RESULT rows, so the scan is not vacuous",
        True,
        len(rows) >= 5 and len(surfaces) >= 5,
        "no per-document result surface was discovered, so 'every row is labelled' passed on an empty set",
    )
    check(
        "EVERY per-document result row on a FAILING document carries PDFIUM-CONDITIONED FRAME",
        ([], []),
        (
            unlabelled_result_rows(scored_failing),
            sorted(
                f"{path}::{row['document']}"
                for path, row in rows
                if row["cross_engine_qualification"] != SM.PDFIUM_CONDITIONED_FRAME
            ),
        ),
        "a result computed on a PDFium-conditioned frame is published without the "
        "qualification I13 attaches to it -- a detached label map is not I13",
    )
    check(
        "a PASSING document labels every row None, which is a different statement from absent",
        ([], True),
        (
            unlabelled_result_rows(scored_passing),
            all(
                row["cross_engine_qualification"] is None and row["pdfium_conditioned_frame"] is False
                for _path, row in document_result_rows(scored_passing)
            ),
        ),
        "a passing document leaves rows unlabelled, so 'checked and passed' is "
        "indistinguishable from 'nobody qualified this surface'",
    )

    # THE OMISSION CONTROL. Drop one declared surface from the scorer's own path list and
    # require the independent scan to find the resulting unlabelled rows. This is what makes
    # the check above sensitive to a FUTURE surface nobody remembered to label.
    original = SM.CROSS_ENGINE_LABELLED_PATHS
    dropped = tuple(p for p in original if p != ("m9", "per_document"))
    try:
        SM.CROSS_ENGINE_LABELLED_PATHS = dropped
        omitted = SM.apply_cross_engine_labels(copy.deepcopy(strip_labels(scored_failing)))
    finally:
        SM.CROSS_ENGINE_LABELLED_PATHS = original
    check(
        "NEGATIVE -- omitting ONE result surface from the label list is DETECTED",
        ["m9.per_document::" + DOC_NAME],
        unlabelled_result_rows(omitted),
        "dropping a surface from the scorer's label list goes unnoticed, so the labelling "
        "check only ever covered the surfaces that happened to be listed",
    )
    check(
        "...and restoring the list re-labels it, so the control is not stuck red",
        [],
        unlabelled_result_rows(SM.apply_cross_engine_labels(copy.deepcopy(strip_labels(scored_failing)))),
        "the label list did not restore, so every later check runs against a mutated scorer",
    )

    # HEADLINES. More than 1/3 of sampled documents failing qualifies BOTH RQ1 and RQ2.
    one_of_four = SM.cross_engine_block(synthetic_cross_engine([("a", False), ("b", True), ("c", True), ("d", True)]))
    two_of_four = SM.cross_engine_block(synthetic_cross_engine([("a", False), ("b", False), ("c", True), ("d", True)]))
    check(
        "exactly 1/4 failing does NOT qualify the headlines; 2/4 DOES, and it qualifies BOTH",
        (None, SM.PDFIUM_CONDITIONED_FRAME),
        (one_of_four["headline_qualification"], two_of_four["headline_qualification"]),
        "the headline rule is not '> 1/3 of sampled documents', so a frame-wide conditioning "
        "either goes unreported or is reported when it should not be",
    )
    both = SM.apply_cross_engine_labels({"cross_engine": two_of_four})
    check(
        "...and BOTH headlines carry it, never only one",
        {"RQ1": SM.PDFIUM_CONDITIONED_FRAME, "RQ2": SM.PDFIUM_CONDITIONED_FRAME},
        both["headline_qualifications"],
        "only one headline is qualified, so the other publishes a frame-wide PDFium "
        "conditioning as though it were unconditioned",
    )

    # NON-BLOCKING. A27.6 keeps cross-engine out of the Rule 3 gate vector entirely.
    check(
        "the qualification is NEVER decision-blocking",
        (False, False, False),
        (
            scored_failing["cross_engine"]["decision_blocking"],
            scored_failing["cross_engine_qualification_is_decision_blocking"],
            "x09" in " ".join(MC.GATE_VECTOR).lower() or "cross" in " ".join(MC.GATE_VECTOR).lower(),
        ),
        "a cross-engine failure blocks the architecture decision, which A27.6 forbids -- it "
        "qualifies a sentence, never a choice",
    )
    check(
        "...and qualifying changes NOTHING a decision reads",
        (
            scored_passing["decision_taken_here"],
            scored_passing["decision_owner"],
            scored_passing["section8"]["clopper_pearson_upper_95"],
            scored_passing["m9"]["per_document"][0]["margin_line_loss"],
        ),
        (
            scored_failing["decision_taken_here"],
            scored_failing["decision_owner"],
            scored_failing["section8"]["clopper_pearson_upper_95"],
            scored_failing["m9"]["per_document"][0]["margin_line_loss"],
        ),
        "the cross-engine verdict moved a measured quantity or a decision field, so it is "
        "acting as a gate rather than as a reporting qualification",
    )
    return {
        "labelled_surfaces": surfaces,
        "n_result_rows": len(rows),
        "headline_1_of_4": one_of_four["headline_qualification"],
        "headline_2_of_4": two_of_four["headline_qualification"],
        "decision_blocking": False,
    }


def strip_labels(payload: dict) -> dict:
    """A copy with every I13 label removed, so relabelling can be exercised from a clean state."""
    clean = copy.deepcopy(payload)
    for _path, row in document_result_rows(clean):
        row.pop("cross_engine_qualification", None)
        row.pop("pdfium_conditioned_frame", None)
    return clean


# ---------------------------------------------------------------------------- section 8


def part_section8(frame: dict) -> dict:
    print("\n== section 8: the statistical contract ==")
    events = SM.document_events([frame])
    check(
        "the section 8 event is derived PER DOCUMENT, one record each",
        (1, str),
        (len(events), type(events[0][0])),
        "the event vector is not one row per document, so the independent unit is not the document 8.3 requires",
    )

    # 14 documents, ZERO events -- the design's own expected outcome, and 8.1's fixture.
    zero = SM.section8([(f"doc-{i}", False) for i in range(14)])
    check(
        "zero events: the frozen closed form, and NO bootstrap interval",
        (0.1926, False, "1 - 0.05**(1/N)", False),
        (
            round(zero["clopper_pearson_upper_95"], 4),
            zero["bootstrap_reported"],
            zero["zero_event_form"],
            "bootstrap" in zero,
        ),
        "a bootstrap is reported at zero events -- 8.1 measured it degenerate at [0.0, 0.0] -- "
        "or the closed form is not 1 - 0.05**(1/N)",
    )
    check(
        "the zero-event WORDING is an observation, never a claim about the true rate",
        (True, False),
        (
            "no heading-level discordance was observed" in zero["statement"],
            "true rate is zero" in zero["statement"],
        ),
        "the report claims the true rate is zero, which is precisely the inference the bound exists to refuse",
    )

    nonzero = SM.section8([(f"doc-{i}", i < 3) for i in range(14)])
    check(
        "non-zero events: the bootstrap IS reported, alongside the exact bound",
        (True, True, "document"),
        (
            nonzero["bootstrap_reported"],
            nonzero["bootstrap"]["reported"],
            nonzero["bootstrap"]["unit"],
        ),
        "the permitted non-zero bootstrap is suppressed, or it resamples something other than documents",
    )
    check(
        "the exact bound is above the observed rate and below 1",
        True,
        nonzero["observed_rate"] < nonzero["clopper_pearson_upper_95"] < 1.0,
        "the Clopper-Pearson upper bound is not an upper bound on the observed rate",
    )
    check(
        "the bisection solver AGREES with the frozen zero-event closed form",
        True,
        all(abs(SM.binomial_cdf(0, n, MC.zero_event_upper_bound(n)) - 0.05) < 1e-12 for n in (2, 14, 30, 600)),
        "the closed form and the general procedure are different statistics, so the study "
        "would quote one at zero events and another everywhere else",
    )
    return {"zero_event_14": zero, "nonzero_3_of_14": {k: v for k, v in nonzero.items() if k != "per_document"}}


# ==========================================================================================
# HARNESS-PLAN section 5's control table. ELEVEN rows -- counted from the table itself, which
# has eleven data rows. A40.6 changes the metric->fixture MAPPING and adds no twelfth control.
# ==========================================================================================


def control_1_s1_liveness(frame: dict, s1: dict) -> dict:
    print("\n-- section 5 control 1/11: S1 liveness (advances x 1.25) --")
    check(
        "C1 S1 FIRES on DEVELOPMENT: sabotage RAISES M0",
        (True, True),
        (s1["fires"], s1["sabotaged"]["text_discordant_lines"] > s1["primary"]["text_discordant_lines"]),
        "advances x 1.25 does not raise the discordance count, which means M0 cannot detect a "
        "change it certainly should -- the comparator is not live and M0 is not reportable",
    )
    dead = copy.deepcopy(s1)
    dead["sabotaged"] = dict(dead["primary"])
    dead["fires"] = False
    live_block = SM.m0_block([frame], s1)
    dead_block = SM.m0_block([frame], dead)
    check(
        "C1 a DEAD comparator makes M0 NOT REPORTABLE, and a live one does not",
        (True, None, False, SM.S1_NOT_LIVE),
        (
            live_block["reportable"],
            live_block["not_reportable_reason"],
            dead_block["reportable"],
            dead_block["not_reportable_reason"],
        ),
        "M0 is reported as a finding while the comparator that proves it can move is dead",
    )
    return {"fires": s1["fires"], "advance_scale": s1["advance_scale"], "dead_comparator_blocks_m0": True}


def control_2_m3_weld() -> dict:
    print("\n-- section 5 control 2/11: the M3 weld/space fixture --")
    welded = m3_outcome_through_scorer("FAMILY HOUSING", "FAMILYHOUSING", "FAMILY HOUSING")
    check(
        "C2 `FAMILYHOUSING` vs `FAMILY HOUSING` reaches M3 as X_CORRECTS",
        (1, 0, 1),
        (
            welded[M3B.HeadingOutcome.X_CORRECTS.value],
            welded[M3B.HeadingOutcome.BOTH_CLEAN.value],
            welded["denominator"],
        ),
        "the weld does not reach M3 as a correction, so the primary comparative metric cannot "
        "see the failure class the seam choice actually governs",
    )
    mirrored = m3_outcome_through_scorer("FAMILY HOUSING", "FAMILY HOUSING", "FAMILYHOUSING")
    check(
        "C2 ...and the MIRROR is X_REGRESSES, so the metric has a direction",
        1,
        mirrored[M3B.HeadingOutcome.X_REGRESSES.value],
        "the same defect scores as a correction whichever arm carries it, i.e. M3 is "
        "symmetric and cannot support a directional claim",
    )
    half = m3_outcome_through_scorer("A B C", "ABC", "AB C")
    check(
        "C2 a HALF repair is BOTH_DIRTY, never a correction (A3)",
        (1, 0),
        (half[M3B.HeadingOutcome.BOTH_DIRTY.value], half[M3B.HeadingOutcome.X_CORRECTS.value]),
        "fixing one of two welds counts as a correction, inflating X_CORRECTS with labels that are still wrong",
    )
    return {"weld": welded, "mirror": mirrored, "half_repair": half}


def control_3_m3_insulation() -> dict:
    print("\n-- section 5 control 3/11: M3 insulation from segmentation --")
    # Identical heading text on both arms, in a region whose committed record carries a
    # DISCORDANT segmentation label. M3 must see BOTH_CLEAN.
    insulated = m3_outcome_through_scorer("SALARIES AND EXPENSES", "SALARIES AND EXPENSES", "SALARIES AND EXPENSES")
    check(
        "C3 a split-only (segmentation) difference fabricates NO weld or split",
        (1, 0, 0),
        (
            insulated[M3B.HeadingOutcome.BOTH_CLEAN.value],
            insulated[M3B.HeadingOutcome.X_CORRECTS.value],
            insulated[M3B.HeadingOutcome.X_REGRESSES.value],
        ),
        "a segmentation label leaked into M3 and manufactured a boundary defect against a "
        "clean oracle -- M3 consumes projected text and the oracle ONLY",
    )
    stripped = m3_outcome_through_scorer(
        "SALARIES AND EXPENSES", "SALARIES AND EXPENSES", "SALARIES AND EXPENSES", include_line_state=False
    )
    check(
        "C3 M3 scores identically with NO segmentation label present at all",
        insulated,
        stripped,
        "removing the segmentation label changed M3's answer, which proves it was reading one",
    )
    real_split = m3_outcome_through_scorer("SALARIES AND EXPENSES", "SALARIES AND EXPENSES", "SALA RIES AND EXPENSES")
    check(
        "C3 ...while a REAL inserted boundary is still caught, so insulation is not blindness",
        1,
        real_split[M3B.HeadingOutcome.X_REGRESSES.value],
        "M3 ignores a genuine printed-boundary violation, so the insulation above was bought "
        "by making the metric insensitive",
    )
    return {"insulated": insulated, "without_line_state": stripped, "real_boundary_split": real_split}


def control_4_delete_agency_anchors(key: dict, adjudicated: dict, frame: dict) -> dict:
    print("\n-- section 5 control 4/11: NEGATIVE -- delete agency anchors --")
    before = SM.score_estimand(key, adjudicated, SM.ESTIMAND_D)["pooled"]["arms"]["H"]

    # THE MUTATION USES PRODUCTION'S OWN HIERARCHY. Agency anchors are removed from the anchor
    # census and `breadcrumb_for` is re-run over what is left, so the surviving accounts get
    # the parent production would actually give them. Hand-writing a parent here would test a
    # hierarchy production never produces.
    all_anchors = [
        PA.Anchor(
            page_number=r["anchor"]["page_number"],
            line_number=r["anchor"]["line_number"],
            kind=r["anchor"]["kind"],
            text=r["anchor"]["text"],
            division=r["anchor"]["division"],
        )
        for r in frame["architecture_occurrences"]["H"]
    ]
    survivors = [a for a in all_anchors if a.kind != "agency"]
    reparented = {}
    for anchor in survivors:
        crumb = PA.breadcrumb_for(anchor, survivors)
        reparented[(anchor.page_number, anchor.line_number, anchor.kind, anchor.text)] = (
            crumb[-2] if len(crumb) >= 2 else None
        )

    mutated = copy.deepcopy(key)
    deleted = 0
    for record in mutated["stimuli"].values():
        if not record.get("architecture_occurrences"):
            continue
        kept = []
        for row in record["architecture_occurrences"]["H"]:
            anchor = row["anchor"]
            if anchor["kind"] == "agency":
                deleted += 1
                continue
            identity = (anchor["page_number"], anchor["line_number"], anchor["kind"], anchor["text"])
            row["immediate_parent"] = reparented.get(identity)
            kept.append(row)
        record["architecture_occurrences"]["H"] = kept

    after = SM.score_estimand(mutated, adjudicated, SM.ESTIMAND_D)["pooled"]["arms"]["H"]
    m1_fall = before["m1_recall_matched"] - after["m1_recall_matched"]
    m4_fall = before["m4_agree"] - after["m4_agree"]
    check(
        "C4 the mutation really deleted agency anchors, so the control is not vacuous",
        True,
        deleted > 0,
        "no agency anchor was present to delete, so the comparison below tested nothing",
    )
    check(
        "C4 M4 falls FURTHER than M1 when agency anchors are deleted",
        True,
        m4_fall > m1_fall,
        "M4 does not fall further than M1, which would mean the parent metric is insensitive "
        "to the hierarchy being destroyed -- it would be tracking presence, not structure",
    )
    return {
        "agency_anchors_deleted": deleted,
        "m1_recall_matched": [before["m1_recall_matched"], after["m1_recall_matched"], m1_fall],
        "m4_agree": [before["m4_agree"], after["m4_agree"], m4_fall],
    }


def control_5_shift_baselines(key: dict, adjudicated: dict) -> dict:
    print("\n-- section 5 control 5/11: NEGATIVE -- shift heading baselines one line-height --")
    before = SM.score_estimand(key, adjudicated, SM.ESTIMAND_D)["pooled"]["arms"]["H"]

    # One line-height down: each occurrence is re-placed onto the NEXT committed neutral line
    # of its region, exactly as a baseline shift would make production read it. The
    # adjudications still point at the true printed positions.
    mutated = copy.deepcopy(key)
    shifted = 0
    for record in mutated["stimuli"].values():
        if not record.get("architecture_occurrences"):
            continue
        bijection = [list(k) for k in record["region_line_bijection"]]
        for row in record["architecture_occurrences"]["H"]:
            if row["occurrence_key"] is None:
                continue
            line_key = list(row["occurrence_key"][2])
            if line_key not in bijection:
                continue
            index = bijection.index(line_key)
            if index + 1 >= len(bijection):
                continue
            row["occurrence_key"] = [
                row["occurrence_key"][0],
                row["occurrence_key"][1],
                bijection[index + 1],
                row["occurrence_key"][3],
            ]
            row["placed_neutral_line_key"] = bijection[index + 1]
            shifted += 1

    after = SM.score_estimand(mutated, adjudicated, SM.ESTIMAND_D)["pooled"]["arms"]["H"]
    check(
        "C5 the shift really moved occurrences, so the control is not vacuous",
        True,
        shifted > 0,
        "no occurrence could be shifted, so the comparison below tested nothing",
    )
    check(
        "C5 M4 FALLS when heading baselines shift one line-height",
        True,
        after["m4_agree"] < before["m4_agree"],
        "M4 does not fall when every heading is attributed to the wrong printed line, which "
        "would mean the parent metric is not anchored to source position at all",
    )
    check(
        "C5 ...and M1 falls with it, because the source-position key no longer matches",
        True,
        after["m1_recall_matched"] < before["m1_recall_matched"],
        "the matching key survived a one-line shift, so it is not the source position A27.1 "
        "fixes -- it must be matching on text",
    )
    return {
        "occurrences_shifted": shifted,
        "m1_recall_matched": [before["m1_recall_matched"], after["m1_recall_matched"]],
        "m4_agree": [before["m4_agree"], after["m4_agree"]],
    }


def control_6_inject_report(frame: dict) -> dict:
    print("\n-- section 5 control 6/11: NEGATIVE -- inject an `R E P O R T` page --")
    clean = SM.m7_block([frame])
    check(
        "C6 the clean material carries NO display-split heading, so injection is detectable",
        (0, 0),
        (clean["pooled"]["H"]["display_split_headings"], clean["pooled"]["X"]["display_split_headings"]),
        "the material already contains letter-spaced headings, so a rise after injection would "
        "not prove the injected one was seen",
    )
    injected = copy.deepcopy(frame)
    template = copy.deepcopy(injected["architecture_occurrences"]["H"][0])
    template["anchor"]["text"] = "R E P O R T"
    injected["architecture_occurrences"]["H"].append(template)

    after = SM.m7_block([injected])
    hits = [i["text"] for i in after["per_document"][0]["arms"]["H"]["instances"]]
    check(
        "C6 M7 DETECTS the injected `R E P O R T`, by instance and not only by count",
        (1, ["R E P O R T"]),
        (after["pooled"]["H"]["display_split_headings"], hits),
        "M7 does not detect a letter-spaced heading, so phase 2's flip condition 1 cannot be "
        "evaluated on fresh data at all",
    )
    check(
        "C6 ...and the OTHER arm is unaffected, so M7 is per-architecture",
        0,
        after["pooled"]["X"]["display_split_headings"],
        "injecting into one arm moved the other's incidence, so M7 is not measured per "
        "architecture as section 6 requires",
    )
    check(
        "C6 the signature threshold is the frozen >= 3 single-character tokens",
        (True, False, 3),
        (
            SM.m7_is_display_split("R E P O R T"),
            SM.m7_is_display_split("A B"),
            SM.M7_MIN_SINGLE_CHAR_TOKENS,
        ),
        "the threshold drifted from section 6's frozen `>= 3 single-character tokens`",
    )
    return {"clean": clean["pooled"], "after_injection": after["pooled"], "instances": hits}


def control_7_m0_denominator(frame: dict, s1: dict) -> dict:
    print("\n-- section 5 control 7/11: the M0 denominator --")
    doc = SM.m0_document(frame)
    inflated = doc["risk_set"] + doc["both_absent"]
    check(
        "C7 a BOTH_ABSENT line appears in NO M0 denominator",
        (True, True),
        (
            doc["both_absent"] > 0,
            doc["M0a_text_rate"] == doc["M0a_text_discordant_lines"] / doc["risk_set"],
        ),
        "an M0 rate is computed over a denominator that includes jointly-absent lines, making "
        "the reported rate a function of how much page furniture GPO put on the page",
    )
    check(
        "C7 ...and the wrong denominator would give a DIFFERENT number, so this is not vacuous",
        True,
        doc["M0a_text_discordant_lines"] / inflated != doc["M0a_text_rate"],
        "the two denominators happen to agree on this material, so the control above passed for the wrong reason",
    )

    # THE LIVE FAULT: a frame claiming a BOTH_ABSENT line is in the risk set must be REFUSED.
    tampered = copy.deepcopy(frame)
    victim = next(ln for page in tampered["pages"] for ln in page["neutral_lines"] if not ln["in_m0_risk_set"])
    victim["in_m0_risk_set"] = True
    check(
        "C7 a frame smuggling a BOTH_ABSENT line into the risk set is REFUSED, not scored",
        SM.FRAME_RISK_SET_INCONSISTENT,
        refusal(lambda: SM.m0_block([tampered], s1) if not SM.validate_frame(tampered) else None),
        "the scorer accepts a frame whose committed risk-set flag contradicts the state that "
        "produced it, so a hand-edited or drifted frame would be silently scored",
    )
    return {"risk_set": doc["risk_set"], "both_absent": doc["both_absent"], "inflated_denominator": inflated}


def control_8_vacuity(key: dict, adjudicated: dict) -> dict:
    print("\n-- section 5 control 8/11: vacuity --")
    check(
        "C8 a zero denominator yields VACUOUS, and a real zero yields 0.0",
        (SM.VACUOUS, 0.0, 0.5),
        (SM.rate(0, 0), SM.rate(0, 5), SM.rate(1, 2)),
        "a zero-denominator metric is printed as a rate -- 0.0 is indistinguishable from "
        "perfect agreement, and 1.0 from perfect success on nothing",
    )
    empty_key, empty_adj = make_stimulus("A HEADING", "A HEADING", "A HEADING")
    for record in empty_key["stimuli"]:
        empty_adj[BO.ROUTE_HUMAN][record]["headings"] = []
    pooled = SM.score_estimand(empty_key, empty_adj, SM.ESTIMAND_D)["pooled"]
    check(
        "C8 an estimand with ZERO adjudicated headings reports M1 recall VACUOUS",
        (SM.VACUOUS, 0),
        (pooled["arms"]["H"]["M1_recall"], pooled["adjudicated_headings"]),
        "recall over an empty adjudicated enumeration is printed as a number, which reads as "
        "agreement about a population that was never observed",
    )
    check(
        "C8 ...while PRECISION still has its content-bearing denominator and is not VACUOUS",
        0.0,
        pooled["arms"]["H"]["M1_precision"],
        "a genuinely zero precision was reported VACUOUS, which would hide a real failure behind a refusal to report",
    )
    check(
        "C8 VACUOUS is a string, so it cannot be averaged or summed by accident",
        str,
        type(SM.VACUOUS),
        "the vacuity sentinel is numeric, so it can silently enter an arithmetic mean",
    )
    return {"pooled": pooled["arms"]["H"]}


def control_9_section8_independence() -> dict:
    print("\n-- section 5 control 9/11: section 8 independence --")
    documents = SM.clopper_pearson_upper(0, 14)
    headings = SM.clopper_pearson_upper(0, 600)
    check(
        "C9 the DOCUMENT bound and the HEADING bound are 8.1's own 0.1926 vs 0.00498",
        (0.1926, 0.00498, 39),
        (round(documents, 4), round(headings, 5), round(documents / headings)),
        "the two units give the same bound, i.e. headings were treated as iid trials and the "
        "39x difference 8.1 measured has been erased",
    )
    reported = SM.section8([(f"doc-{i}", False) for i in range(14)])
    check(
        "C9 the scorer reports the DOCUMENT bound, on the document unit",
        ("document", round(documents, 10)),
        (reported["unit"], round(reported["clopper_pearson_upper_95"], 10)),
        "the reported bound is the heading-unit one, which overstates precision 39-fold",
    )
    heading_rows = [(f"doc-{i % 14}", False) for i in range(600)]
    check(
        "C9 a HEADING-as-trials vector is REFUSED, not silently scored",
        MC.DUPLICATE_DOCUMENT_IDENTITY,
        refusal(lambda: SM.section8(heading_rows)),
        "600 heading rows over 14 documents are accepted as 600 independent trials, which is "
        "exactly the estimand error section 8 exists to prevent",
    )
    check(
        "C9 no per-heading probability is reported anywhere",
        False,
        reported["per_heading_probability_reported"],
        "a per-heading probability is published, which section 8 forbids outright",
    )
    return {"document_bound_14": documents, "heading_bound_600": headings, "ratio": documents / headings}


def control_10_section8_zero_event() -> dict:
    print("\n-- section 5 control 10/11: section 8 zero-event --")
    zero = SM.section8([(f"doc-{i}", False) for i in range(14)])
    check(
        "C10 NO bootstrap is reported at zero events",
        (False, False, MC.ZERO_EVENTS_BOOTSTRAP_REFUSED),
        (zero["bootstrap_reported"], "bootstrap" in zero, zero["bootstrap_refusal_reason"]),
        "a bootstrap interval is reported at zero events -- 8.1 measured every resample of "
        "all-zero clusters is zero, so the interval is [0.0, 0.0] and carries no information",
    )
    check(
        "C10 the closed form is EXACTLY `1 - 0.05**(1/N)`, for every N",
        [1 - 0.05 ** (1 / n) for n in (1, 2, 14, 30, 600)],
        [SM.clopper_pearson_upper(0, n) for n in (1, 2, 14, 30, 600)],
        "the zero-event bound is not the frozen closed form section 8.3 fixed verbatim",
    )
    check(
        "C10 the closed form comes from its SINGLE owner, `methodology_contracts`",
        [MC.zero_event_upper_bound(n) for n in (2, 14, 600)],
        [SM.clopper_pearson_upper(0, n) for n in (2, 14, 600)],
        "the scorer spells the closed form itself, so the study carries two copies of one "
        "frozen number and they can drift",
    )
    check(
        "C10 the A37 helper is called with NO custom statistic id (A38.10)",
        (False, 1),
        (
            "statistic_id" in MC.section8_document_bootstrap.__code__.co_varnames,
            MC.section8_document_bootstrap.__code__.co_argcount,
        ),
        "the bootstrap accepts a caller-supplied statistic id, which would let a scorer draw a "
        "different resample sequence for the same frozen statistic",
    )
    return {"zero_event": {k: v for k, v in zero.items() if k != "per_document"}}


def control_11_section8_pairing() -> dict:
    print("\n-- section 5 control 11/11: section 8 pairing --")
    # A fixture where the two means DISAGREE: the document with the large heading count carries
    # the opposite-signed difference, so weighting flips the sign of the reported effect.
    pairs = [("doc-A", 10.0, 12.0), ("doc-B", 10.0, 12.0), ("doc-C", 100.0, 60.0)]
    heading_counts = {"doc-A": 5, "doc-B": 5, "doc-C": 500}
    paired = SM.paired_differences(pairs, "fixture")

    unweighted = (2.0 + 2.0 - 40.0) / 3
    weighted = (2.0 * 5 + 2.0 * 5 - 40.0 * 500) / sum(heading_counts.values())
    check(
        "C11 the paired mean is UNWEIGHTED over documents",
        round(unweighted, 10),
        round(paired["mean_difference_X_minus_H"], 10),
        "the paired mean is weighted by heading count, which re-imports the heading-as-unit "
        "assumption 8.1 measured to be worth a factor of 39",
    )
    check(
        "C11 ...and the weighted mean is a DIFFERENT number, so the control is not vacuous",
        True,
        abs(weighted - unweighted) > 1.0,
        "the two means agree on this fixture, so the control above passed for the wrong reason",
    )
    check(
        "C11 per-document detail is MANDATORY and travels with the mean",
        (3, True),
        (
            len(paired["per_document"]),
            all("difference_X_minus_H" in row for row in paired["per_document"]),
        ),
        "the paired comparison is collapsed to one number, which section 8.3 forbids",
    )
    check(
        "C11 there is NO weight parameter to supply",
        [],
        [
            n
            for n in SM.paired_differences.__code__.co_varnames[: SM.paired_differences.__code__.co_argcount]
            if "weight" in n
        ],
        "a caller can pass weights, so the frozen unweighted rule is an obligation rather than a gate",
    )
    check(
        "C11 a duplicated document REFUSES rather than being weighted twice",
        SM.DUPLICATE_PAIRED_DOCUMENT,
        refusal(lambda: SM.paired_differences([("d", 1.0, 2.0), ("d", 1.0, 2.0)], "dup")),
        "one document appearing twice is silently double-weighted, which is a heading-level "
        "table entering a document-level statistic",
    )
    return {"unweighted": unweighted, "weighted_would_be": weighted, "paired": paired}


# ---------------------------------------------- separately specified negative attacks


def part_negative(key: dict, adjudicated: dict, frame: dict, manifest: dict) -> dict:
    print("\n== separately specified NEGATIVE attacks (not among the 11) ==")
    out = {}

    # N1 -- a control must never reach an estimand denominator.
    control_ids = {bid for bid, r in key["stimuli"].items() if r["control_kind"] is not None}
    reached = {
        bid
        for estimand in (SM.ESTIMAND_C, SM.ESTIMAND_D)
        for bid, _r in SM._estimand_records(key, estimand)
        if bid in control_ids
    }
    check(
        "N1 NO control stimulus reaches a C or D denominator",
        (True, set()),
        (len(control_ids) == 20, reached),
        "a negative control entered an estimand, so the study's own falsification material "
        "would be counted as positive evidence about an architecture",
    )
    out["n_control_stimuli"] = len(control_ids)

    # N2 -- a control forced into the estimand must be REFUSED, not scored.
    forced = copy.deepcopy(key)
    victim = sorted(control_ids)[0]
    forced["stimuli"][victim]["in_d_frame"] = True
    check(
        "N2 a control FORCED into an estimand is refused by the scorer",
        SM.CONTROL_IN_ESTIMAND,
        refusal(lambda: SM.score_estimand(forced, adjudicated, SM.ESTIMAND_D)),
        "membership alone lets a control into a denominator, so the exclusion rests on the "
        "oracle key being well-formed rather than on a gate the scorer enforces",
    )

    # N3 -- a tampered discordance flag must be refused.
    tampered = copy.deepcopy(frame)
    line = next(
        ln for page in tampered["pages"] for ln in page["neutral_lines"] if not ln["line_state"]["text_discordance"]
    )
    line["line_state"]["text_discordance"] = True
    check(
        "N3 a committed discordance flag contradicting its own inputs is REFUSED",
        SM.FRAME_STATE_INCONSISTENT,
        refusal(lambda: SM.validate_frame(tampered)),
        "the scorer trusts a serialized boolean it can independently recompute, so a "
        "hand-edited or drifted frame is scored as though it were sound",
    )

    # N4 -- a discordant line outside the D-frame breaks I9 and must be refused.
    broken = copy.deepcopy(frame)
    for page in broken["pages"]:
        for region in page["regions"]:
            region["d_frame"] = False
            region["d_reasons"] = [r for r in region["d_reasons"] if r != "ANCHOR_DISCORDANCE"]
            region["anchor_evidence"]["differ"] = False
    check(
        "N4 I9 -- a discordant line whose region is not in the D-frame is REFUSED",
        SM.DISCORDANT_LINE_OUTSIDE_D_FRAME,
        refusal(lambda: SM.validate_frame(broken)),
        "the discordances being reported and the D-frame census describing them have drifted "
        "into two different eligibility sets, and nothing notices",
    )

    # N5 -- an ambiguous emitted occurrence key must refuse rather than pick one.
    duped = copy.deepcopy(key)
    target = next(
        r
        for r in duped["stimuli"].values()
        if r.get("architecture_occurrences") and len(r["architecture_occurrences"]["H"]) >= 1
    )
    target["architecture_occurrences"]["H"].append(copy.deepcopy(target["architecture_occurrences"]["H"][0]))
    check(
        "N5 two emitted occurrences claiming ONE source position are REFUSED",
        SM.AMBIGUOUS_EMITTED_OCCURRENCE_KEY,
        refusal(lambda: SM.score_estimand(duped, adjudicated, SM.ESTIMAND_D)),
        "the join silently keeps whichever duplicate iteration order reached last, so the "
        "matched set depends on dict ordering",
    )

    # N6 -- an unknown M5 role RAISES; it is never quietly UNSCORABLE (A36.7).
    bad_role_key, bad_role_adj = make_stimulus("A HEADING", "A HEADING", "A HEADING", role="not-a-real-role")
    check(
        "N6 an unknown adjudicated role RAISES rather than shrinking the M5 denominator",
        "UnknownRole",
        refusal(lambda: SM.score_estimand(bad_role_key, bad_role_adj, SM.ESTIMAND_D)),
        "an unmapped role becomes UNSCORABLE, quietly SHRINKING the M5 denominator -- and a "
        "smaller denominator reads as a cleaner result rather than as a defect",
    )

    # N7 -- M4 reads the IMMEDIATE parent only, never the ancestry.
    m4_key, m4_adj = make_stimulus("AN ACCOUNT", "AN ACCOUNT", "AN ACCOUNT", parent="AGENCY", emitted_parent="AGENCY")
    agree = SM.score_estimand(m4_key, m4_adj, SM.ESTIMAND_D)["pooled"]["arms"]["H"]
    m4_key2, m4_adj2 = make_stimulus(
        "AN ACCOUNT", "AN ACCOUNT", "AN ACCOUNT", parent="TITLE I", emitted_parent="AGENCY"
    )
    disagree = SM.score_estimand(m4_key2, m4_adj2, SM.ESTIMAND_D)["pooled"]["arms"]["H"]
    check(
        "N7 M4 agrees on the immediate parent and DISAGREES with a grandparent",
        (1.0, 0.0),
        (agree["M4_parent_agreement"], disagree["M4_parent_agreement"]),
        "M4 accepts any ancestor as the parent, which is the 'hierarchy is right' claim being "
        "satisfied by a heading that is merely somewhere underneath",
    )

    # N8 -- a missing mandated route REFUSES; it never falls back to the other namespace.
    missing_key, missing_adj = make_stimulus("A HEADING", "A HEADING", "A HEADING", in_c=True, in_d=False)
    missing_adj[BO.ROUTE_AI] = {}
    check(
        "N8 a missing MANDATED route refuses -- there is no fallback to the other namespace",
        BO.ANSWER_MISSING_FOR_REQUIRED_ROUTE,
        refusal(lambda: SM.score_estimand(missing_key, missing_adj, SM.ESTIMAND_C)),
        "C metrics fall back to the human answer, making C a mixed oracle whose source is "
        "chosen by architecture disagreement",
    )

    # N9 -- an adjudicated heading that cannot be resolved stays in the recall denominator.
    unres_key, unres_adj = make_stimulus("A HEADING", "A HEADING", "A HEADING")
    for bid in unres_adj[BO.ROUTE_HUMAN]:
        unres_adj[BO.ROUTE_HUMAN][bid]["headings"][0]["start_physical_line"] = 99
    unresolved = SM.score_estimand(unres_key, unres_adj, SM.ESTIMAND_D)["pooled"]
    check(
        "N9 an UNRESOLVABLE adjudicated heading counts against recall, never vanishing",
        (1, 1, 0.0),
        (
            unresolved["adjudicated_headings"],
            unresolved["adjudicated_unresolved"],
            unresolved["arms"]["H"]["M1_recall"],
        ),
        "a heading the A38.7 resolver refused is dropped from the denominator, so recall is "
        "computed only over the headings that happened to resolve",
    )

    # N10 -- the manifest's frozen control population is what reached the oracle.
    check(
        "N10 the frozen 8 / 8 / 4 control population is intact",
        {"N-A": 8, "N-B": 8, "N-C": 4},
        manifest["counts"],
        "the control population is not the frozen 8/8/4 set, so the Rule 3 blockers are not the ones the study froze",
    )

    # ---- N11-N13: THE SECTION 8 EVENT PREDICATE, attacked at its source.
    #
    # A41's approved event is "the document has >= 1 region whose emitted H/X anchor sets
    # differ". Everything section 8 reports rests on it, so these attacks go at the committed
    # anchor evidence itself and run through the REAL `validate_frame` and `score` paths -- not
    # a copied predicate, which could only ever agree with itself.

    def region_with_anchors(candidate):
        for page in candidate["pages"]:
            for region in page["regions"]:
                if region["anchor_evidence"]["H"] or region["anchor_evidence"]["X"]:
                    return page, region
        return None, None

    _page, sample = region_with_anchors(frame)
    check(
        "N11 the material carries a region with committed anchors, so N12/N13 are not vacuous",
        True,
        sample is not None,
        "no region carries an anchor value here, so the two attacks below would mutate nothing",
    )

    # N12 -- flip BOTH the flag and the reason, leave H and X untouched. The old check compared
    # `differ` against `d_reasons` only; a single edit setting both is invisible to it.
    flipped = copy.deepcopy(frame)
    _p, victim = region_with_anchors(flipped)
    victim["anchor_evidence"]["differ"] = not victim["anchor_evidence"]["differ"]
    if "ANCHOR_DISCORDANCE" in victim["d_reasons"]:
        victim["d_reasons"] = [r for r in victim["d_reasons"] if r != "ANCHOR_DISCORDANCE"]
    else:
        victim["d_reasons"] = [*victim["d_reasons"], "ANCHOR_DISCORDANCE"]
    victim["d_frame"] = bool(victim["d_reasons"])
    check(
        "N12 flipping `differ` AND `d_reasons` together, with H/X unchanged, is REFUSED",
        SM.FRAME_ANCHOR_EVIDENCE_INCONSISTENT,
        refusal(lambda: SM.validate_frame(flipped)),
        "the two committed fields are only checked against each other, so one edit setting "
        "both passes -- and the section 8 event, and the bound derived from it, move with it",
    )

    # N13 -- mutate the ANCHORS and leave `differ` stale. The flag now summarises anchors that
    # are no longer there.
    stale = copy.deepcopy(frame)
    _p2, victim2 = region_with_anchors(stale)
    was = victim2["anchor_evidence"]["differ"]
    if was:
        victim2["anchor_evidence"]["X"] = list(victim2["anchor_evidence"]["H"])
    else:
        victim2["anchor_evidence"]["X"] = [*victim2["anchor_evidence"]["X"], [99, 99, "account", "PLANTED", None]]
    check(
        "N13 mutating H/X while `differ` stays stale is REFUSED",
        SM.FRAME_ANCHOR_EVIDENCE_INCONSISTENT,
        refusal(lambda: SM.validate_frame(stale)),
        "the committed flag is trusted over the anchor values it claims to summarise, so a "
        "drifted or hand-edited frame is scored as though the flag were still true",
    )
    check(
        "N13 ...and the same stale frame is refused through the REAL `score` entrypoint",
        SM.FRAME_ANCHOR_EVIDENCE_INCONSISTENT,
        refusal(lambda: SM.score(frames=[stale], adjudicated=adjudicated, key=key)),
        "validation is reachable only by calling it directly, so the result-bearing path can "
        "score a frame the validator would have refused",
    )

    # N14 -- D membership must be exactly "some predicate fired". The victim is a region with
    # NO reasons, promoted to d_frame: a region that already carried a discordant line would
    # trip I9 first, and the control would pass on a refusal it did not cause.
    orphan = copy.deepcopy(frame)
    victim3 = next(
        (r for page in orphan["pages"] for r in page["regions"] if not r["d_frame"] and not r["d_reasons"]),
        None,
    )
    check(
        "N14 a region with NO d_reasons exists, so the invariant can be isolated",
        True,
        victim3 is not None,
        "every region here already carries a reason, so promoting one would collide with I9 "
        "and the control below would pass on the wrong refusal",
    )
    victim3["d_frame"] = True
    check(
        "N14 `d_frame` disagreeing with `bool(d_reasons)` is REFUSED",
        SM.FRAME_D_MEMBERSHIP_INCONSISTENT,
        refusal(lambda: SM.validate_frame(orphan)),
        "a region is a D-frame member with no predicate that put it there, or carries a "
        "predicate while absent from the census -- either way the D census stops describing "
        "the discordances being reported",
    )
    check(
        "N14 ...and the UNMUTATED frame still validates, so these gates refuse only faults",
        None,
        refusal(lambda: SM.validate_frame(frame)),
        "validation refuses clean input, making every control above meaningless",
    )
    out["section8_event_predicate"] = {
        "event": "document has >= 1 region whose emitted H/X anchor sets differ (A41, approved)",
        "recomputed_from": "the serialized anchor_evidence H and X values",
        "attacks": ["N12 flag+reason flipped together", "N13 anchors mutated, flag stale", "N14 d_frame orphaned"],
    }
    return out


# ------------------------------------------------------- the execution boundary, restated


def part_boundary() -> dict:
    print("\n== the one-way execution boundary ==")
    state = BO.execution_boundary_state()
    check(
        "the execution boundary is still ABSENT",
        "ABSENT",
        state,
        "the boundary moved during a scorer implementation slice, which would make every "
        "subsequent scoring-rule change a DEVIATION rather than an amendment",
    )
    forbidden = [
        "frames.json",
        "oracle_key.json",
        "oracle_blind.json",
        "oracle_adjudicated.json",
        "metrics.json",
        "scores.json",
        "EXECUTION-START.json",
    ]
    present = [name for name in forbidden if (EV / "results" / name).exists()]
    check(
        "NO canonical/execution artifact exists",
        [],
        present,
        "a canonical artifact was created before execution was authorised",
    )
    check(
        "`write_metrics` REFUSES to write results/metrics.json before a VALID boundary",
        BO.CONFIRMATORY_WRITE_BEFORE_EXECUTION,
        refusal(lambda: SM.write_metrics({"schema": "metrics/1"})),
        "the scorer can write its canonical artifact while the boundary is ABSENT, so the "
        "one-way gate does not cover the component that produces the study's numbers",
    )
    return {"execution_boundary_state": state, "forbidden_artifacts_present": present}


# -------------------------------------------------------------------------------- main


def main() -> int:
    sha, _h, _x, frame, key, manifest = development_material()
    adjudicated = synthetic_adjudication(key)

    # Schema validity of the synthetic artifact is asserted through the FROZEN validator, so a
    # fixture that could not be a real adjudication cannot silently carry the whole probe.
    BO.validate_adjudicated(adjudicated, key)

    s1 = S1.s1_result(DOC_PATH, limit=PAGE_LIMIT)

    m0 = part_m0(frame, s1)
    join = part_join(key, adjudicated)
    m7_m9 = part_m7_m9_m6(frame)
    s8 = part_section8(frame)

    controls = {
        "1_s1_liveness": control_1_s1_liveness(frame, s1),
        "2_m3_weld_space": control_2_m3_weld(),
        "3_m3_insulation": control_3_m3_insulation(),
        "4_delete_agency_anchors": control_4_delete_agency_anchors(key, adjudicated, frame),
        "5_shift_baselines": control_5_shift_baselines(key, adjudicated),
        "6_inject_report_page": control_6_inject_report(frame),
        "7_m0_denominator": control_7_m0_denominator(frame, s1),
        "8_vacuity": control_8_vacuity(key, adjudicated),
        "9_section8_independence": control_9_section8_independence(),
        "10_section8_zero_event": control_10_section8_zero_event(),
        "11_section8_pairing": control_11_section8_pairing(),
    }
    negative = part_negative(key, adjudicated, frame, manifest)
    boundary = part_boundary()

    # The whole entrypoint, end to end, on the committed material. Scored TWICE against a REAL
    # cross-engine artifact -- once with the document FAILING and once PASSING -- because I13's
    # whole content is what changes between those two runs, and `None` could never show it.
    s1_artifact = {
        "fires": s1["fires"],
        "advance_scale": s1["advance_scale"],
        "sabotaged_arm": "X",
        "per_document": [{"document": DOC_NAME, **s1}],
        "n_documents": 1,
        "n_firing": int(s1["fires"]),
    }

    def score_with(cross_engine):
        return SM.score(
            frames=[frame],
            adjudicated=adjudicated,
            key=key,
            s1=s1_artifact,
            cross_engine=cross_engine,
            control_fixtures=manifest,
            strata_filled=6,
        )

    payload = score_with(synthetic_cross_engine([(DOC_NAME, False)]))
    payload_passing = score_with(synthetic_cross_engine([(DOC_NAME, True)]))
    cross_engine_i13 = part_cross_engine_i13(payload, payload_passing)

    check(
        "the entrypoint runs end to end and takes NO decision",
        (False, "decide_architecture"),
        (payload["decision_taken_here"], payload["decision_owner"]),
        "the scorer takes an architecture decision",
    )
    # M6 ABSENCE, asserted END TO END against the real payload rather than the module's symbol
    # table. A symbol scan cannot see an `m6: None` key sitting in `metrics.json`.
    check(
        "M6 IS ABSENT from the result-bearing payload -- no key, at any depth",
        [],
        m6_surfaces(payload),
        "the payload carries an M6 surface, which A20 struck and section 5 excludes "
        "('M0-M9 minus M6'). A key holding null still says something about M6",
    )
    check(
        "...and the scan CAN see one, so the absence above is not vacuous",
        ["m6", "m9.per_document[0].M6_planted"],
        sorted(m6_surfaces({**payload, "m6": None, "m9": {"per_document": [{"M6_planted": 1}]}})),
        "the M6 scan cannot detect a planted M6 key, so it would report absence on a payload that carried one",
    )
    check(
        "section 8's paired block is present, unweighted, with per-document detail",
        (True, True),
        (
            all(p["weighting"].startswith("UNWEIGHTED") for p in payload["section8_paired"]),
            all(p["per_document"] for p in payload["section8_paired"]),
        ),
        "the paired comparison is weighted or collapsed, which section 8.3 forbids",
    )

    STOPS.append(
        {
            "id": "R1_AGREEMENT_DENOMINATOR",
            "status": "OPEN -- reported, NOT resolved here",
            "question": "5.6 requires R1 heading-text agreement >= 0.90 and role agreement >= 0.80, "
            "but no frozen source states the DENOMINATOR: occurrence keys resolved in BOTH the "
            "primary and the repeat, or their UNION. The two differ exactly when a repeat "
            "disagrees about a heading's PRESENCE, which is a reliability failure the "
            "intersection reading cannot see.",
            "why_not_settled_here": "choosing would fix the sensitivity of a Rule 3 gate after the "
            "protocol froze. A38.8 recorded three readings of Rule 0's margin-line clause and "
            "chose none; the same discipline applies. The scorer computes no R1 agreement, so "
            "no unfrozen choice has been made on a result-bearing path.",
            "owner": "a pre-execution amendment, then decide_architecture (A27.6 Rule 3)",
        }
    )

    doc = {
        "population": "SYNTHETIC + DEVELOPMENT -- no holdout opened, nothing adjudicated, "
        "no confirmatory artifact created",
        "contract": "section 6 (M0-M9 minus M6) and the section 8 contract (A27.5), as "
        "implemented by probes/score_metrics.py",
        "question": "does score_metrics compute the frozen quantities from committed artifacts, "
        "and does each of HARNESS-PLAN section 5's ELEVEN controls actually fire?",
        "document": DOC_NAME,
        "document_sha256": sha,
        "page_limit": PAGE_LIMIT,
        "note": "PAGE_LIMIT is a machinery demonstration window, not a census",
        "synthetic_adjudication": "DERIVED from the committed oracle key so the A38.7 join "
        "resolves back exactly. A KNOWN-ANSWER FIXTURE about the SCORER. It is not an "
        "adjudication, is not evidence about either architecture, and is never written to "
        "results/oracle_adjudicated.json",
        "artifacts_created": "NONE of frames.json, oracle_key.json, oracle_blind.json, "
        "oracle_adjudicated.json, metrics.json, scores.json, EXECUTION-START.json",
        "section5_control_rows": 11,
        "section5_control_row_note": "HARNESS-PLAN section 5's control table has ELEVEN data "
        "rows. A40.6 changes the metric->fixture MAPPING (M1 -> N-B + N-C; M2 -> N-A; M3 -> N-A) "
        "and adds no twelfth control.",
        "m0": m0,
        "join_m1_m5": join,
        "m7_m9_m6": m7_m9,
        "section8": s8,
        "section5_controls": controls,
        "negative_attacks": negative,
        "cross_engine_i13": cross_engine_i13,
        "execution_boundary": boundary,
        "metrics_payload_shape": sorted(payload),
        "forward_ambiguities": STOPS,
        "tests": ROWS,
        "failures": FAILED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\n{len(ROWS) - len(FAILED)}/{len(ROWS)} checks pass; {len(STOPS)} forward ambiguities OPEN")
    print(f"wrote {OUT}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
