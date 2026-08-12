"""build_frames -- the two frames, never pooled. A19 / A22 / A23 / §5.8, made executable.

RESULT-BEARING. This is the first component whose output every later stage reads, so it can
move a realized result if it is wrong. It introduces NO new methodological rule: every rule
below is already frozen, and the fidelity comes from the frozen contracts plus the positive
and negative controls in `x17_build_frames.py`.

    A19    neutral skeleton; 8-line page-bounded regions; enrichment withdrawn
    A22/23 text vs segmentation discordance; the M0 comparative risk set
    A27.2  no amount-bearing reservation -- plain uniform C-frame, <= 8 regions/document
    A27.3  the adjudication ITEM is a region; the budget belongs to `decide_architecture`
    A27.7  domain-separated deterministic selection
    A28.5  the bilateral anchor->neutral bridge

WHAT THIS COMPONENT MAY NOT DECIDE. Which lines are neutral (`eligible` + `cluster`, frozen);
region size or alignment; any use of text to form a region; any enrichment predicate; any
amount-bearing reservation; whether a jointly-absent line enters the D-frame (it does not);
the selection seed or ranking rule. The only permitted freedom is JSON layout.

THE D-FRAME IS A COMPLETE CENSUS. No sampling, no truncation, and the 60-region budget is NOT
applied here. If the census is 61 or 2,000 regions this emits all of them; A27.3 gives the
budget to `decide_architecture`, and applying it early would silently destroy the very count
that decides whether Rule 1 may run at all.

M0 RATES ARE NOT SCORED HERE. The per-line comparative quantities are preserved verbatim from
`neutral_identity`; turning them into rates is `score_metrics`' job.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import anchor_provenance as AP
import methodology_contracts as MC
from neutral_identity import (
    NeutralLine,
    build_owner,
    emitted_gids,
    line_state,
    segmentation_discordance,
    text_discordance,
)

from deltatrack.parsers import pdf_anchors as PA
from deltatrack.parsers.pdf_anchors import extract_anchors

REGION_SIZE = 8  # A19, frozen
C_FRAME_MAX_PER_DOCUMENT = 8  # A27.2, frozen
P_HEAD = MC.P_HEAD
P_ROBUST = "P-robust"
# The C-frame draw is P-head-only, so an UNRECOGNISED population string would silently yield
# zero C-frame regions instead of an error -- the same silent-reduction failure the structural
# preconditions exist to prevent. The set is closed and validated rather than trusted.
KNOWN_POPULATIONS = frozenset({P_HEAD, P_ROBUST})

# anchor placement refusals -- the x14 rule, which refuses rather than guessing
AMBIGUOUS_MARGIN_NUMBER_ON_PAGE = "AMBIGUOUS_MARGIN_NUMBER_ON_PAGE"
NO_PRINT_LINE_WITH_THAT_MARGIN_NUMBER = "NO_PRINT_LINE_WITH_THAT_MARGIN_NUMBER"
EMITTED_INDEX_OUT_OF_RANGE = "EMITTED_INDEX_OUT_OF_RANGE"
EMITTED_LINE_CARRIES_NO_NEUTRAL_INK = "EMITTED_LINE_CARRIES_NO_NEUTRAL_INK"
FIRST_GID_NOT_OWNED_BY_ANY_NEUTRAL_LINE = "FIRST_GID_NOT_OWNED_BY_ANY_NEUTRAL_LINE"

TEXT_DISCORDANCE = "TEXT_DISCORDANCE"
SEGMENTATION_DISCORDANCE = "SEGMENTATION_DISCORDANCE"
ANCHOR_DISCORDANCE = "ANCHOR_DISCORDANCE"

# structural preconditions -- each ABORTS, none is representable in a frame
UNKNOWN_POPULATION = "UNKNOWN_POPULATION"
DUPLICATE_PAGE_NUMBER = "DUPLICATE_PAGE_NUMBER"
PAGE_SET_MISMATCH = "PAGE_SET_MISMATCH"
NEUTRAL_SKELETON_MISMATCH = "NEUTRAL_SKELETON_MISMATCH"
PRINT_LINES_EMITTED_DRIFT = "PRINT_LINES_EMITTED_DRIFT"
ANCHOR_PLACEMENT_REFUSED = "ANCHOR_PLACEMENT_REFUSED"


class FrameConstructionError(Exception):
    """Frame construction is NOT EXECUTABLE on this input. Deterministic, never a value.

    Every condition below is one the frozen rules leave no way to represent inside a frame,
    so the only faithful response is to refuse to build one.

    THE ANCHOR-REFUSAL CASE IS THE ONE THAT LOOKS SURVIVABLE AND IS NOT. Dropping an anchor
    the bridge could not place and comparing the surviving sets silently converts "this
    document's anchor census is not knowable by the frozen rule" into "the arms emitted
    different anchors" -- an ANCHOR_DISCORDANCE that is an artifact of the harness, not an
    observation about the architectures. x14 already fixed the contract: any non-zero
    placement residue makes anchor discordance non-executable as frozen.
    """

    def __init__(self, reason: str, arm: str = "", page_number=None, detail=None):
        self.reason = reason
        self.arm = arm
        self.page_number = page_number
        self.detail = detail
        super().__init__(f"{reason} [arm={arm or '-'} page={page_number}] {detail!r}")


# --------------------------------------------------------------------------- regions


@dataclass(frozen=True)
class Region:
    page_number: int
    ordinal: int
    line_keys: tuple
    short_trailing: bool


def enumerate_regions(neutral: list[NeutralLine], region_size: int = REGION_SIZE) -> list[Region]:
    """A19 literally: non-overlapping windows of `region_size` consecutive neutral lines,
    aligned to the PAGE START, page-bounded, and the short trailing window KEPT.

    I1 -- enumerated from the NEUTRAL SKELETON only. Enumerating from emitted lines would
    make a line both arms dropped unsamplable, and a shared failure invisible; that is
    exactly the failure the C-frame exists to see.

    I5 -- regions never cross pages, because this is called per page and the ordinal restarts.

    The short trailing window is A19's frozen rule, not a convenience: dropping a 1-7 line
    page tail would make the last lines of every page unsamplable, which is a systematic
    coverage hole aligned with page structure rather than a rounding detail.
    """
    if not neutral:
        return []
    page = neutral[0].page
    regions = []
    for start in range(0, len(neutral), region_size):
        window = neutral[start : start + region_size]
        regions.append(
            Region(
                page_number=page,
                ordinal=start // region_size,
                line_keys=tuple(ln.key for ln in window),
                short_trailing=len(window) < region_size,
            )
        )
    return regions


# ------------------------------------------------------------------- anchor placement


def place_anchor(anchor, print_lines, emitted, owner, ordinal_by_key):
    """(region_ordinal, neutral_line_key) for one anchor, or (None, reason).

    THE A28.5 BRIDGE, unchanged: margin number -> unique print-line index -> same emitted
    index -> first neutral ngid -> owning NeutralLine -> region. No heading text is consulted
    at any step; matching an anchor to a line by its text would make anchor discordance
    circular, because text is one of the things being measured.

    `x17` asserts this reproduces `x14.place_anchor` for every anchor on every development
    page, so the rule lives in one place behaviourally even though it is spelled twice.
    """
    hits = [i for i, ln in enumerate(print_lines) if ln.line_number == anchor.line_number]
    if not hits:
        return None, NO_PRINT_LINE_WITH_THAT_MARGIN_NUMBER
    if len(hits) > 1:
        return None, AMBIGUOUS_MARGIN_NUMBER_ON_PAGE
    i = hits[0]
    if i >= len(emitted):
        return None, EMITTED_INDEX_OUT_OF_RANGE
    gids = sorted(emitted[i].gids)
    if not gids:
        return None, EMITTED_LINE_CARRIES_NO_NEUTRAL_INK
    key = owner.get(gids[0])
    if key is None:
        return None, FIRST_GID_NOT_OWNED_BY_ANY_NEUTRAL_LINE
    return (ordinal_by_key[key] // REGION_SIZE, key), None


def place_arm_anchors(anchors, print_lines, emitted, neutral, arm: str = ""):
    """region ordinal -> the set of emitted production Anchor VALUES resolved into it.

    The whole `Anchor` value is kept. No reduced signature is invented for frames: `Anchor`
    is a frozen dataclass, so set membership already compares page, line, kind, text and
    division, and choosing a subset would be this component inventing a matching rule the
    protocol never froze.

    ANY refusal ABORTS. The alternative -- dropping the anchor and comparing what is left --
    turns "the frozen bridge cannot name this document's anchor census" into an apparent
    ANCHOR_DISCORDANCE, which is a harness artifact wearing the costume of an observation.
    """
    owner = build_owner(neutral)
    ordinal_by_key = {ln.key: ln.ordinal for ln in neutral}
    by_region: dict[int, set] = {}
    for anchor in anchors:
        placed, reason = place_anchor(anchor, print_lines, emitted, owner, ordinal_by_key)
        if reason:
            raise FrameConstructionError(
                ANCHOR_PLACEMENT_REFUSED,
                arm=arm,
                page_number=anchor.page_number,
                detail={"anchor": anchor_repr(anchor), "refusal": reason},
            )
        by_region.setdefault(placed[0], set()).add(anchor)
    return by_region


# ------------------------------------------------------------------------ page frames


@dataclass
class PageInput:
    """One page's frozen inputs. `h_anchors_by_region` / `x_anchors_by_region` are already
    placed, so synthetic controls can supply them directly without constructing a PDF."""

    page_number: int
    neutral: list[NeutralLine]
    h_emitted: list
    x_emitted: list
    h_anchors_by_region: dict = field(default_factory=dict)
    x_anchors_by_region: dict = field(default_factory=dict)
    # There is deliberately NO refusal field. A placement refusal aborts construction, so a
    # PageInput that exists is one whose entire anchor census placed exactly; making refusals
    # representable here would invite later code to ignore them.


def build_page_frame(page: PageInput) -> dict:
    """Neutral lines with their comparative state, and the region grid with C/D evidence."""
    owner = build_owner(page.neutral)
    common = emitted_gids(page.h_emitted) & emitted_gids(page.x_emitted)

    states = {}
    for line in page.neutral:
        states[line.key] = line_state(page.h_emitted, page.x_emitted, line, owner, common)

    regions = enumerate_regions(page.neutral)
    region_rows = []
    for region in regions:
        h_anchors = page.h_anchors_by_region.get(region.ordinal, set())
        x_anchors = page.x_anchors_by_region.get(region.ordinal, set())

        # I4 -- the REGION is the membership unit; the LINE is the evidence. The two are
        # recorded separately so a concordant line inside a D region is never readable as
        # individually qualifying.
        text_lines = [k for k in region.line_keys if text_discordance(states[k])]
        seg_lines = [k for k in region.line_keys if segmentation_discordance(states[k])]
        anchors_differ = set(h_anchors) != set(x_anchors)

        reasons = []
        if text_lines:
            reasons.append(TEXT_DISCORDANCE)
        if seg_lines:
            reasons.append(SEGMENTATION_DISCORDANCE)
        if anchors_differ:
            reasons.append(ANCHOR_DISCORDANCE)

        region_rows.append(
            {
                "page_number": region.page_number,
                "region_ordinal": region.ordinal,
                "neutral_line_keys": [list(k) for k in region.line_keys],
                "short_trailing": region.short_trailing,
                "line_count": len(region.line_keys),
                "d_frame": bool(reasons),
                "d_reasons": reasons,
                # I4: the specific lines carrying each line-level predicate, never the whole region
                "discordant_lines": {
                    TEXT_DISCORDANCE: [list(k) for k in text_lines],
                    SEGMENTATION_DISCORDANCE: [list(k) for k in seg_lines],
                },
                "anchor_evidence": {
                    "differ": anchors_differ,
                    "H": sorted(anchor_repr(a) for a in h_anchors),
                    "X": sorted(anchor_repr(a) for a in x_anchors),
                },
                # C membership is filled by the document-level selector, which must see the
                # COMPLETE region enumeration before it may draw.
                "c_frame": False,
            }
        )

    line_rows = []
    for line in page.neutral:
        st = states[line.key]
        line_rows.append(
            {
                "key": list(line.key),
                "baseline": line.baseline,
                "bbox": [line.x0, line.y0, line.x1, line.y1],
                "gids": sorted(line.gids),
                # A38.2 -- A30.3's nearest-glyph candidates. ngid-ordered for SERIALIZATION
                # only; A30.1 forbids ordering occurrences by ngid.
                "identity_candidates": [{"ngid": gid, "x0": x0} for gid, x0 in line.candidates],
                "region_ordinal": line.ordinal // REGION_SIZE,
                # I3 -- BOTH_ABSENT stays in the grid and in the artifact. It is excluded
                # from the comparative risk set and can never alone qualify a D region.
                "in_m0_risk_set": st["state"] != "BOTH_ABSENT",
                "line_state": {
                    "state": st["state"],
                    "h_text": st["h_text"],
                    "x_text": st["x_text"],
                    "h_signature": _jsonable(st["h_signature"]),
                    "x_signature": _jsonable(st["x_signature"]),
                    "text_discordance": text_discordance(st),
                    "segmentation_discordance": segmentation_discordance(st),
                    "common_gids": st["common_gids"],
                    "diagnostics": st["diagnostics"],
                },
            }
        )

    return {
        "page_number": page.page_number,
        "neutral_lines": line_rows,
        "regions": region_rows,
        # no refusal key: an unplaceable anchor aborts before any frame is built
    }


def anchor_repr(anchor) -> tuple:
    """The emitted production Anchor value, verbatim, for the artifact.

    This is a SERIALIZATION of the whole value, not a matching projection: equality is always
    decided on the `Anchor` objects themselves in `build_page_frame`.
    """
    return (anchor.page_number, anchor.line_number, anchor.kind, anchor.text, anchor.division)


def _jsonable(obj):
    if isinstance(obj, (list, tuple)):
        return [_jsonable(o) for o in obj]
    return obj


# -------------------------------------------------------------------- document frames


def select_c_frame(
    document_sha256: str, population: str, page_frames: list[dict], max_per_document: int = C_FRAME_MAX_PER_DOCUMENT
) -> list:
    """A27.2/A27.7 -- the plain uniform C-frame draw, after the COMPLETE enumeration.

    P-head documents only. The draw ranks canonical region identities with the frozen
    domain-separated seed, so it is reproducible and independent of listing order.

    NO reroll and NO replacement after inspecting region contents: a selected region stays
    selected even if both architectures drop all of its content. Replacing it would delete
    precisely the shared-failure evidence RQ2 exists to collect, and would make the sample
    a function of the thing being measured.
    """
    # An unknown population string must not read as "not P-head" and quietly draw nothing.
    if population not in KNOWN_POPULATIONS:
        raise FrameConstructionError(UNKNOWN_POPULATION, detail={"population": population})
    if population != P_HEAD:
        return []
    identities = [
        MC.base_stimulus_identity(document_sha256, pf["page_number"], r["region_ordinal"])
        for pf in page_frames
        for r in pf["regions"]
    ]
    return MC.select("cframe-select", identities, max_per_document)


def _build_document_frame_from_inputs(
    document_sha256: str, document_id: str, population: str, pages: list[PageInput]
) -> dict:
    """PRIVATE, SYNTHETIC-ONLY pure constructor. Not a result-bearing entrypoint.

    It exists so controls can build inputs no PDF would ever produce -- a page neither arm
    emitted, a 61-region D census, an anchor set that differs with identical text. It applies
    NO structural gate, because its whole purpose is to be handed impossible input.

    REAL frame construction must go through `build_document_frame`, which owns the gates.
    Nothing here takes a region size: A19's 8 is not a parameter on any path that can return
    a study frame, so the "place anchors on a 7-line grid, then build an 8-line grid" defect
    is not merely rejected, it is unspellable.
    """
    page_frames = [build_page_frame(p) for p in pages]

    selected = select_c_frame(document_sha256, population, page_frames)
    chosen = {(ident[2], ident[3]) for ident in selected}  # (page_number, region_ordinal)
    for pf in page_frames:
        for r in pf["regions"]:
            if (pf["page_number"], r["region_ordinal"]) in chosen:
                r["c_frame"] = True

    d_census = [
        {"page_number": pf["page_number"], "region_ordinal": r["region_ordinal"], "d_reasons": r["d_reasons"]}
        for pf in page_frames
        for r in pf["regions"]
        if r["d_frame"]
    ]
    all_regions = [r for pf in page_frames for r in pf["regions"]]
    all_lines = [ln for pf in page_frames for ln in pf["neutral_lines"]]

    return {
        "document": document_id,
        "document_sha256": document_sha256,
        "population": population,
        "region_size": REGION_SIZE,
        "pages": page_frames,
        "counts": {
            "pages": len(page_frames),
            "neutral_lines": len(all_lines),
            "regions": len(all_regions),
            "short_trailing_regions": sum(1 for r in all_regions if r["short_trailing"]),
            "c_frame_selected": sum(1 for r in all_regions if r["c_frame"]),
            "d_frame_census": len(d_census),
            "d_text": sum(1 for r in all_regions if TEXT_DISCORDANCE in r["d_reasons"]),
            "d_segmentation": sum(1 for r in all_regions if SEGMENTATION_DISCORDANCE in r["d_reasons"]),
            "d_anchor": sum(1 for r in all_regions if ANCHOR_DISCORDANCE in r["d_reasons"]),
            "both_absent_lines": sum(1 for ln in all_lines if not ln["in_m0_risk_set"]),
            "m0_risk_set_lines": sum(1 for ln in all_lines if ln["in_m0_risk_set"]),
        },
        # the COMPLETE census, never sampled and never truncated to the A10 budget
        "d_frame_census": d_census,
        "d_frame_truncated": False,
        # not a count: an unplaceable anchor aborts, so a frame that exists had none
        "anchor_placement_refusals_are_fatal": True,
    }


# ------------------------------------------------------- extraction from a real document


def document_scope_anchors(arm_pages: list[dict]) -> list:
    """Every production anchor for ONE arm, extracted ONCE over the whole consumed page set.

    `extract_anchors` is DOCUMENT-SCOPED, and calling it per page silently changes what it
    finds: `derive_size_bands` and `_coverage` are computed over the supplied collection, the
    account/agency/major passes run over the FLATTENED pages, and `_assign_divisions` needs
    document-order context. Per-page calls therefore re-derive the size bands from one page's
    glyphs, cut every cross-page agency/major run at the page seam, and lose division labels.

    The pages are ordered by page number first, because document order is itself an input to
    the division and major passes.
    """
    return extract_anchors([d["page"] for d in sorted(arm_pages, key=lambda d: d["page_number"])])


def _page_inputs_from_arms(h_pages: list[dict], x_pages: list[dict]):
    """Build `PageInput`s from the two runners' returned per-page dicts, or ABORT.

    Each arm's production anchors are derived from ITS OWN returned production `Page` objects,
    exactly as `x14` does -- no runner needs an `anchors` key, and neither arm has a private
    path.

    EVERY STRUCTURAL PRECONDITION FAILS CLOSED HERE. None of them is returned as a value for a
    caller to notice: a caller obligation cannot fail, and each of these conditions would
    otherwise produce a frame that is quietly smaller or quietly wrong rather than absent.
    """
    # --- page numbers must be UNIQUE within each arm, checked BEFORE set equality, which
    # cannot see a duplicate: H=[1,1,2] and X=[1,2] have equal sets, and the later
    # page-number dictionary would silently collapse the duplicate. A physical PDF page has
    # one identity, so duplicate runner records make the document frame ill-defined.
    for arm, pages_data in (("H", h_pages), ("X", x_pages)):
        numbers = [d["page_number"] for d in pages_data]
        if len(numbers) != len(set(numbers)):
            dupes = sorted({n for n in numbers if numbers.count(n) > 1})
            raise FrameConstructionError(DUPLICATE_PAGE_NUMBER, arm=arm, detail={"duplicates": dupes})

    # --- page sets must match EXACTLY. Intersecting, or skipping the odd page out, would
    # silently shrink the frame and every denominator computed from it.
    h_nums = {d["page_number"] for d in h_pages}
    x_nums = {d["page_number"] for d in x_pages}
    if h_nums != x_nums:
        raise FrameConstructionError(
            PAGE_SET_MISMATCH, detail={"only_in_H": sorted(h_nums - x_nums), "only_in_X": sorted(x_nums - h_nums)}
        )

    # --- A28.5 anti-drift, on EVERY consumed page and for EACH arm, BEFORE any anchor index
    # is used. The bridge's index step reads emitted[i] for the i-th print line; if those two
    # lists have drifted, every anchor on the page places onto the wrong neutral line and the
    # frame is built from shifted indices with nothing to show for it.
    for arm, pages_data in (("H", h_pages), ("X", x_pages)):
        for d in pages_data:
            printed = [ln.text for ln in d["page"].print_lines]
            emitted_text = [e.text() for e in d["emitted"]]
            if printed != emitted_text:
                first = next(
                    (i for i, (a, b) in enumerate(zip(printed, emitted_text)) if a != b),
                    min(len(printed), len(emitted_text)),
                )
                raise FrameConstructionError(
                    PRINT_LINES_EMITTED_DRIFT,
                    arm=arm,
                    page_number=d["page_number"],
                    detail={"print_lines": len(printed), "emitted": len(emitted_text), "first_divergence": first},
                )

    # --- A19 requires ONE skeleton. If the arms disagreed, the two frames would not be the
    # same frame and reporting them side by side would be meaningless.
    x_by_page = {d["page_number"]: d for d in x_pages}
    for h in h_pages:
        x = x_by_page[h["page_number"]]
        # A38.2 -- candidates, INCLUDING x0, are compared here too, so a divergent candidate
        # geometry fails construction rather than being silently taken from H.
        #
        # STATED LIMIT: this is not two independent implementations. A19 requires ONE skeleton
        # and both runners deliberately call the same `run_hybrid.neutral_skeleton`; the gate
        # catches divergence in what each arm RETURNS AND CARRIES, which is the reachable
        # failure. `x13` separately asserts the two runners' skeletons are identical.
        h_sk = [(ln.key, sorted(ln.gids), ln.candidates) for ln in h["neutral"]]
        x_sk = [(ln.key, sorted(ln.gids), ln.candidates) for ln in x["neutral"]]
        if h_sk != x_sk:
            raise FrameConstructionError(
                NEUTRAL_SKELETON_MISMATCH,
                page_number=h["page_number"],
                detail={"H_lines": len(h_sk), "X_lines": len(x_sk)},
            )

    # --- DOCUMENT-SCOPED extraction, once per arm, then grouped by page for placement.
    h_anchors, x_anchors = document_scope_anchors(h_pages), document_scope_anchors(x_pages)
    h_by_page: dict[int, list] = {}
    x_by_page_anchors: dict[int, list] = {}
    for anchor in h_anchors:
        h_by_page.setdefault(anchor.page_number, []).append(anchor)
    for anchor in x_anchors:
        x_by_page_anchors.setdefault(anchor.page_number, []).append(anchor)

    inputs = []
    for h in sorted(h_pages, key=lambda d: d["page_number"]):
        pno = h["page_number"]
        x = x_by_page[pno]
        neutral = h["neutral"]
        inputs.append(
            PageInput(
                page_number=pno,
                neutral=neutral,
                h_emitted=h["emitted"],
                x_emitted=x["emitted"],
                h_anchors_by_region=place_arm_anchors(
                    h_by_page.get(pno, []), h["page"].print_lines, h["emitted"], neutral, "H"
                ),
                x_anchors_by_region=place_arm_anchors(
                    x_by_page_anchors.get(pno, []), x["page"].print_lines, x["emitted"], neutral, "X"
                ),
            )
        )
    return inputs


# ------------------------------------------------------------- THE PUBLIC ENTRYPOINT


def build_document_frame(
    document_sha256: str, document_id: str, population: str, h_pages: list[dict], x_pages: list[dict]
) -> dict:
    """THE result-bearing entrypoint. Runner outputs in, document frame out, gates unskippable.

    This is the only public route to a study frame, and it takes the two RUNNERS' outputs --
    not `PageInput`s -- so there is no argument through which a caller can hand in inputs that
    skipped validation. Every structural gate runs inside `_page_inputs_from_arms`, which this
    calls itself:

        duplicate page numbers per arm ... page-set equality ... A28.5 anti-drift on every
        consumed page and both arms ... one-skeleton equality ... document-scope anchor
        extraction ... exact placement, refusals fatal

    WHY THE SPLIT EXISTS. The pure constructor must stay callable so controls can build inputs
    no PDF would produce; but while it was ALSO the public route, a real caller could reach it
    directly and skip every gate -- and the standing principle is that a caller obligation is
    not a gate, because it cannot fail. It is now `_build_document_frame_from_inputs`, private
    and synthetic-only.

    NO REGION SIZE PARAMETER, anywhere on this path. It previously existed on both halves, so
    a caller could place anchors on a 7-line grid and then build an 8-line grid: the frame
    looked entirely valid, the region-size guard compared its own default against itself and
    passed, and the anchor evidence was assigned against a different partition than the one
    reported. That defect is not rejected here, it is unspellable.
    """
    frame = _build_document_frame_from_inputs(
        document_sha256, document_id, population, _page_inputs_from_arms(h_pages, x_pages)
    )
    # A38.3/A38.5 -- the frame owns the architecture occurrences, because this stage already
    # holds the complete H/X extraction and the A30 source-position bridge. A scorer must not
    # have to rebuild them from the serialized `anchor_evidence` tuples, which exist only as
    # D-frame membership evidence and are deliberately not overloaded into occurrence scoring.
    frame["architecture_occurrences"] = {
        "H": architecture_occurrences(document_sha256, h_pages),
        "X": architecture_occurrences(document_sha256, x_pages),
    }
    # A38.8 -- M9 RAW FACTS. Recorded, never decided: Rule 0 belongs to decide_architecture.
    frame["m9"] = {"H": m9_facts(h_pages), "X": m9_facts(x_pages)}
    return frame


# --------------------------------------------- A38.3 architecture occurrence records


ARCHITECTURE_EXTRACTION_DRIFT = "ARCHITECTURE_EXTRACTION_DRIFT"


def architecture_occurrences(document_sha256: str, arm_pages: list[dict]) -> list[dict]:
    """Every production heading occurrence for ONE arm, physically placed AND identity-keyed.

    THE TWO ARE SEPARATE CONCEPTS, and conflating them was a real defect:

        PHYSICAL REGION PLACEMENT  -- the A28.5 bridge. Where on the page this occurrence is.
        A30 OCCURRENCE IDENTITY    -- `key_for`. What its cross-arm identity is, if any.

    Placement runs FIRST and INDEPENDENTLY. Deriving `region_ordinal` from the A30 key, as this
    previously did, meant a genuine A30 refusal produced `region_ordinal = None` and the
    occurrence then vanished from every region-scoped record -- silently shrinking exactly the
    M1-M5 denominators A38 exists to keep honest. An identity refusal is a statement about
    identity; it says nothing about where the heading is printed.

    Built from the FROZEN machinery only -- `place_anchor` (A28.5), `instrumented_extract_anchors`,
    `strip_to_production`, `key_for`. No third anchor-recognition implementation, and no
    text/kind/order matching rule is invented anywhere here.

    Document order, never ngid order: A30.1 permits `ngid` for EQUALITY ONLY, and ngid order
    disagreed with printed order on 10 of 33,602 emitted lines.
    """
    ordered = [d["page"] for d in sorted(arm_pages, key=lambda d: d["page_number"])]
    occurrences, _refusals = AP.instrumented_extract_anchors(ordered)

    # The instrumented mirror must still BE production. Asserted element for element rather
    # than trusted: a drifted mirror would key occurrences that production never emitted.
    mirrored = AP.strip_to_production(occurrences)
    produced = PA.extract_anchors(ordered)
    if list(mirrored) != list(produced):
        raise FrameConstructionError(
            ARCHITECTURE_EXTRACTION_DRIFT,
            detail={"instrumented": len(mirrored), "production": len(produced)},
        )

    by_page = {d["page_number"]: d for d in arm_pages}
    all_anchors = list(produced)
    rows = []
    for occ in occurrences:
        page_data = by_page.get(occ.anchor.page_number)
        if page_data is None:
            raise FrameConstructionError(
                ANCHOR_PLACEMENT_REFUSED,
                page_number=occ.anchor.page_number,
                detail={"anchor": anchor_repr(occ.anchor), "refusal": "PAGE_NOT_CONSUMED"},
            )
        owner = build_owner(page_data["neutral"])
        ordinal_by_key = {ln.key: ln.ordinal for ln in page_data["neutral"]}

        # --- A28.5 PHYSICAL PLACEMENT, independent of identity. A refusal aborts, exactly as
        # it does in `place_arm_anchors`: an unplaceable anchor census cannot be compared.
        placed, place_reason = place_anchor(
            occ.anchor, page_data["page"].print_lines, page_data["emitted"], owner, ordinal_by_key
        )
        if place_reason:
            raise FrameConstructionError(
                ANCHOR_PLACEMENT_REFUSED,
                page_number=occ.anchor.page_number,
                detail={"anchor": anchor_repr(occ.anchor), "refusal": place_reason},
            )
        region_ordinal, placed_line_key = placed

        # --- A30 IDENTITY, separately. Failure leaves the placement above untouched.
        key, reason = AP.key_for(document_sha256, occ, page_data["page"], page_data["emitted"], owner)

        crumb = PA.breadcrumb_for(occ.anchor, all_anchors)  # A38.4, production's own hierarchy
        rows.append(
            {
                "anchor": {
                    "page_number": occ.anchor.page_number,
                    "line_number": occ.anchor.line_number,
                    "kind": occ.anchor.kind,
                    "text": occ.anchor.text,
                    "division": occ.anchor.division,
                },
                # A38 repair -- region ordinals RESTART every page, so physical region identity
                # is the PAIR. Filtering on the ordinal alone handed a stimulus every page's
                # same-numbered region.
                "page_number": occ.anchor.page_number,
                "region_ordinal": region_ordinal,
                "placed_neutral_line_key": list(placed_line_key),
                "occurrence_key": None if key is None else _jsonable(key),
                "match_status": "MATCHABLE" if key is not None else "UNMATCHED",
                "unmatched_reason": reason,
                "immediate_parent": crumb[-2] if len(crumb) >= 2 else None,
                "breadcrumb": list(crumb),
            }
        )
    return rows


# ------------------------------------------------------- A38.8 M9 raw structural facts


def m9_facts(arm_pages: list[dict]) -> dict:
    """The RAW M9 basis for one arm, from production's own functions. No Rule 0 here.

    A39.1 RULED the comparison: `margin_lines_recovered` is the count of `Page.lines` with
    `line_number is not None`, and ANY strictly positive per-document deficit fires. This
    function still records only FACTS -- the glyph-size count and the per-line keys remain
    diagnostics that A39.1 explicitly excluded from the clause, and applying the rule belongs
    to the later architecture decision, not to frame construction.
    """
    pages = [d["page"] for d in sorted(arm_pages, key=lambda d: d["page_number"])]
    numbered = [(pg.page_number, ln) for pg in pages for ln in pg.lines if ln.line_number is not None]
    return {
        "derive_size_bands_returns_a_band": PA.derive_size_bands(pages) is not None,
        "coverage": PA._coverage(pages),
        "coverage_floor": PA._COVERAGE_MIN,
        "coverage_meets_floor": PA._coverage(pages) >= PA._COVERAGE_MIN,
        "n_lines_total": sum(len(pg.lines) for pg in pages),
        # reading (a): margin-numbered lines
        "n_margin_numbered_lines": len(numbered),
        # reading (b): _coverage's NUMERATOR -- numbered lines that also carry a glyph size
        "n_margin_numbered_with_glyph_size": sum(1 for _p, ln in numbered if ln.glyph_size is not None),
        # reading (c): the identities themselves, so a SET difference remains computable
        "margin_numbered_line_keys": [[p, ln.line_number] for p, ln in numbered],
        "rule0_comparison": (
            "RAW FACTS ONLY -- Rule 0 margin-line interpretation frozen by A39.1 "
            "(count of Page.lines where line_number is not None; any positive deficit fires); "
            "application belongs to the later architecture decision"
        ),
    }
