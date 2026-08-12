"""control_fixtures -- A39.3 / A40: the N-A, N-B and N-C source fixtures, and their manifest.

    frozen rule   PRE-REGISTRATION 5.6 (N-A 8 / N-B 8 / N-C 4, all Rule-3 blockers), A39.3
                  (provenance + deterministic selection), A40 (the three LIVE N-A mutation
                  classes and their deterministic targets)
    executable    `build_manifest()` writes `results/control_fixtures.json`;
                  `validate_manifest()` is what G6 calls
    test          `x23_control_fixtures.py`

TRUTH COMES FROM THE COMMITTED RECIPE, NEVER FROM H OR X. No architecture output participates
in eligibility, ranking, target selection or expected truth anywhere in this module. N-A's
source truth is paired GPO XML corroboration, the same independent source N-B uses.

NO CONFIRMATORY MATERIAL. Every source is DEVELOPMENT or purpose-built synthetic, and the
manifest validator refuses any holdout id, path, parent or generated provenance.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

import m3_boundaries as M3  # noqa: E402
import methodology_contracts as MC  # noqa: E402
import xml_sources as XS  # noqa: E402

# ------------------------------------------------------------------ frozen constants

NA_TOTAL, NB_TOTAL, NC_TOTAL = 8, 8, 4

DELETE_ONE_WORD = "DELETE_ONE_WORD"
WELD_TWO_WORDS = "WELD_TWO_WORDS"
SPLIT_ONE_WORD = "SPLIT_ONE_WORD"
#: A40.1 -- the frozen index-mod-3 schedule. Realizes 3 delete / 3 weld / 2 split over 8.
NA_SCHEDULE = {0: DELETE_ONE_WORD, 1: WELD_TWO_WORDS, 2: SPLIT_ONE_WORD}
NA_VARIANTS = (DELETE_ONE_WORD, WELD_TWO_WORDS, SPLIT_ONE_WORD)
NA_EXPECTED_ALLOCATION = {DELETE_ONE_WORD: 3, WELD_TWO_WORDS: 3, SPLIT_ONE_WORD: 2}

#: A40.1 -- RETIRED by the A39.3 liveness falsification. Its presence is a G6 failure, not a
#: legacy value to tolerate: the census showed a size-only change moves no field the frozen
#: task records, so a fixture claiming it would be a control that cannot fire.
RETIRED_VARIANT = "PULL_HEADING_TO_BODY_SIZE"

NA_NAMESPACE = "na-source"
NB_NAMESPACE = "nb-source"

MIN_SPLIT_TOKEN = 6  # A40.3 eligibility, and A40.4's target rule
MIN_SPLIT_PIECE = 3  # A40.4 -- both halves must be substantial

MANIFEST_PATH = EV / "results" / "control_fixtures.json"
GENERATED_DIR = EV / "control_fixtures"

DEVELOPMENT_SOURCES = [
    (
        "114-hr-2029/4",
        REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf",
        REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.xml",
    ),
    (
        "118-hr-8752/1",
        REPO / "tests/corpus/118-hr-8752/1_reported-in-house.pdf",
        REPO / "tests/corpus/118-hr-8752/1_reported-in-house.xml",
    ),
]
SOURCE_PAGE_LIMIT = 40


class ControlFixtureError(Exception):
    """A fixture cannot be built or validated as frozen. Deterministic, never a value."""

    def __init__(self, reason: str, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason} {detail!r}")


INSUFFICIENT_ELIGIBLE_SOURCES = "INSUFFICIENT_ELIGIBLE_SOURCES"
DEAD_MUTATION = "DEAD_MUTATION"

#: A40.15 -- F3 and F4 ARE NOW IMPLEMENTED, so these are True and G6 no longer reports them.
#: They remain as named switches because a future slice that has to disable a replay must make
#: G6 go RED for that reason rather than quietly skipping the check.
SOURCE_SELECTION_REPLAY_IMPLEMENTED = True
MUTATION_TARGET_REPLAY_IMPLEMENTED = True
SOURCE_REPLAY_NOT_IMPLEMENTED = "SOURCE_REPLAY_NOT_IMPLEMENTED"
MUTATION_TARGET_REPLAY_NOT_IMPLEMENTED = "MUTATION_TARGET_REPLAY_NOT_IMPLEMENTED"
#: Nothing is outstanding now. `x23` asserts this set is EMPTY on the realized manifest, so the
#: constant keeps its meaning ("declared-outstanding work") instead of being deleted and silently
#: reappearing as an untested tuple later.
OUTSTANDING_REPLAY_DEFECTS = ()

# F3/F4 replay disagreements. Each names WHICH deterministic reconstruction the manifest failed,
# so a green G6 cannot be produced by a coherent-but-wrong manifest.
SOURCE_SELECTION_MISMATCH = "SOURCE_SELECTION_MISMATCH"
SOURCE_SELECTION_ORDER_MISMATCH = "SOURCE_SELECTION_ORDER_MISMATCH"
SOURCE_IDENTITY_MISMATCH = "SOURCE_IDENTITY_MISMATCH"
PHYSICAL_SOURCE_MISMATCH = "PHYSICAL_SOURCE_MISMATCH"
SOURCE_POPULATION_MISMATCH = "SOURCE_POPULATION_MISMATCH"
MUTATION_INPUT_MISMATCH = "MUTATION_INPUT_MISMATCH"
MUTATION_VARIANT_MISMATCH = "MUTATION_VARIANT_MISMATCH"
MUTATION_TARGET_MISMATCH = "MUTATION_TARGET_MISMATCH"
MUTATION_RECIPE_MISMATCH = "MUTATION_RECIPE_MISMATCH"
REGION_REALIZATION_MISMATCH = "REGION_REALIZATION_MISMATCH"


# --------------------------------------------------------------------- pure helpers


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


#: A PDF trailer `/ID` is two 32-hex-digit strings. pymupdf generates them RANDOMLY on every
#: save, so an unmodified fixture rebuilt from identical inputs produced different bytes every
#: run -- which made the manifest SHA stale immediately and flipped G6 red after any `x23`.
#
#: BOTH PDF string forms occur here and only handling `<hex>` is a silent no-op. One generated
#: fixture came out as `/ID[<hex>(binary literal)]` -- a hex string and a LITERAL string -- so a
#: hex-only pattern skipped it, left its random half in place, and that single file stayed
#: irreproducible while the other eleven looked fine.
_PDF_ID = re.compile(
    rb"/ID\s*\[\s*(?:<[0-9A-Fa-f]*>|\((?:\\.|[^)\\])*\))\s*"
    rb"(?:<[0-9A-Fa-f]*>|\((?:\\.|[^)\\])*\))\s*\]",
    re.S,
)


def deterministic_pdf_id(name: str) -> str:
    """A40.14 -- the trailer `/ID`, derived from the fixture's stable name. NO byte surgery.

    ROOT CAUSE, measured rather than guessed. Every fixture-byte difference collapsed to this one
    array: masking `/ID` alone made two differing outputs byte-identical across their whole
    537 KB. Two independent save-time behaviours produced it, and only both together explain what
    was observed:

      * pymupdf writes a RANDOM `/ID` on every save and its serialized length is NOT constant --
        measured spans of 69 AND 73 bytes on the same fixture. The old repair padded its
        replacement to whatever span it found, so file length followed the random id (537524 vs
        537528). That is the intermittent, arbitrary-fixture difference that kept reappearing.
      * setting the trailer id WITHOUT `no_new_id=True` is silently half-undone: the save
        replaces the SECOND element, giving `[<0000...><4F0890...>]` and 40 distinct SHAs in 40
        builds. That is why an earlier `xref_set_key`-only attempt looked right and was not.

    The fix is native and structural: set a deterministic id, then save with `no_new_id=True` so
    the save leaves it alone. Nothing rewrites a saved PDF afterwards, which is why
    `canonicalise_pdf_id` is deleted rather than kept alongside this.

    Derived from the output basename so each fixture keeps a DISTINCT id -- one shared constant
    would be equally deterministic but would give every control the same PDF identity -- and a
    basename is machine-independent, unlike an absolute path.
    """
    digest = hashlib.sha256(name.encode()).hexdigest()[:32].upper()
    return f"[<{digest}><{digest}>]"


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def alphabetic_tokens(s: str) -> list[str]:
    """A40.4 -- a maximal contiguous run of alphabetic characters."""
    return re.findall(r"[^\W\d_]+", s, flags=re.UNICODE)


def _token_spans(s: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"[^\W\d_]+", s, flags=re.UNICODE)]


# ------------------------------------------------------------ A40.4 mutation recipes


def delete_one_word(text: str) -> tuple[str, dict]:
    """Delete the LONGEST alphabetic token (tie -> earliest), leaving one normal boundary."""
    spans = _token_spans(text)
    if not spans:
        raise ControlFixtureError(DEAD_MUTATION, {"why": "no alphabetic token", "text": text})
    start, end, token = max(spans, key=lambda s: (len(s[2]), -s[0]))
    after = normalize_text(text[:start] + " " + text[end:])
    return after, {"variant": DELETE_ONE_WORD, "target_token": token, "target_span": [start, end]}


def weld_two_words(text: str) -> tuple[str, dict]:
    """Remove the whitespace run between the FIRST adjacent alphabetic token pair."""
    spans = _token_spans(text)
    for (s0, e0, t0), (s1, e1, t1) in zip(spans, spans[1:]):
        gap = text[e0:s1]
        if gap and gap.isspace():
            return text[:e0] + text[s1:], {
                "variant": WELD_TWO_WORDS,
                "target_pair": [t0, t1],
                "removed_gap_span": [e0, s1],
            }
    raise ControlFixtureError(DEAD_MUTATION, {"why": "no adjacent whitespace-separated pair", "text": text})


def split_one_word(text: str) -> tuple[str, dict]:
    """Insert ONE U+0020 after floor(len/2) of the longest token with len >= MIN_SPLIT_TOKEN."""
    spans = [s for s in _token_spans(text) if len(s[2]) >= MIN_SPLIT_TOKEN]
    if not spans:
        raise ControlFixtureError(DEAD_MUTATION, {"why": f"no token >= {MIN_SPLIT_TOKEN}", "text": text})
    start, end, token = max(spans, key=lambda s: (len(s[2]), -s[0]))
    cut = len(token) // 2
    if cut < MIN_SPLIT_PIECE or len(token) - cut < MIN_SPLIT_PIECE:
        raise ControlFixtureError(DEAD_MUTATION, {"why": "a piece would be too short", "token": token})
    after = text[: start + cut] + " " + text[start + cut :]
    return after, {
        "variant": SPLIT_ONE_WORD,
        "target_token": token,
        "split_after_chars": cut,
        "pieces": [token[:cut], token[cut:]],
    }


MUTATORS = {
    DELETE_ONE_WORD: delete_one_word,
    WELD_TWO_WORDS: weld_two_words,
    SPLIT_ONE_WORD: split_one_word,
}


# ------------------------------------------------------------------ A40.5 liveness


def mutation_evidence(before: str, after: str, variant: str) -> dict:
    """A40.5 -- prove the mutation class STRUCTURALLY, independent of any adjudicator.

    Uses `m3_boundaries.decompose`, the study's existing boundary definition, rather than a
    second one: the whole point of SPLIT/WELD is to exercise M3's own WELD/SPLIT distinction,
    so measuring them with a private notion of "boundary" would test something else.
    """
    b_chars, b_bounds = M3.decompose(before)
    a_chars, a_bounds = M3.decompose(after)
    same_len = len(b_bounds) == len(a_bounds)
    diffs = [i for i, (x, y) in enumerate(zip(b_bounds, a_bounds)) if x != y] if same_len else []
    evidence = {
        "variant": variant,
        "expected_before": before,
        "expected_after": after,
        "changed": normalize_text(before) != normalize_text(after),
        "non_space_before": b_chars,
        "non_space_after": a_chars,
        "non_space_unchanged": b_chars == a_chars,
        "boundary_len_before": len(b_bounds),
        "boundary_len_after": len(a_bounds),
        "boundary_diff_positions": diffs,
        "boundary_transitions": [[b_bounds[i], a_bounds[i]] for i in diffs],
    }
    if variant == DELETE_ONE_WORD:
        evidence["live"] = evidence["changed"] and not evidence["non_space_unchanged"]
        evidence["class_rule"] = "non-space sequence must CHANGE"
    elif variant == WELD_TWO_WORDS:
        evidence["live"] = (
            evidence["changed"]
            and evidence["non_space_unchanged"]
            and len(diffs) == 1
            and evidence["boundary_transitions"] == [[1, 0]]
        )
        evidence["class_rule"] = "non-space unchanged, exactly one boundary 1 -> 0"
    elif variant == SPLIT_ONE_WORD:
        evidence["live"] = (
            evidence["changed"]
            and evidence["non_space_unchanged"]
            and len(diffs) == 1
            and evidence["boundary_transitions"] == [[0, 1]]
        )
        evidence["class_rule"] = "non-space unchanged, exactly one boundary 0 -> 1"
    else:
        evidence["live"] = False
        evidence["class_rule"] = f"unknown or RETIRED variant: {variant}"
    return evidence


# ------------------------------------------------------- A40.3 eligibility + ranking


def _page_lines(lines: list[dict], page_number: int) -> list[dict]:
    """The page's printed lines in physical print order. `physical_lines` is already sorted."""
    return [ln for ln in lines if ln["page_number"] == page_number]


def oracle_region(lines: list[dict], hit: dict) -> dict:
    """F6 -- the EXACT adjudication region, under the already-frozen 8-line rule.

    `build_frames.REGION_SIZE` is reused rather than restated: A19's rule is non-overlapping
    windows of that many consecutive lines with `ordinal = start // size`, and the region bbox
    is A33's minimal union of its member line bboxes with ZERO padding. Applying the frozen rule
    to the independently observed lines keeps the crop size frozen while keeping H and X out of
    the geometry; nothing here invents a crop.

    Everything a future caller needs is returned, so `build_oracle.render_region` is handed the
    committed bbox verbatim and no later code re-derives a boundary or text-searches for a crop.
    """
    import build_frames as BF

    page_lines = _page_lines(lines, hit["page_number"])
    index_in_page = next(i for i, ln in enumerate(page_lines) if ln["line_index"] == hit["line_index"])
    ordinal = index_in_page // BF.REGION_SIZE
    window = page_lines[ordinal * BF.REGION_SIZE : (ordinal + 1) * BF.REGION_SIZE]
    height = hit["page_height"]
    # pymupdf line bboxes are top-left origin; the committed form is PDF points (y grows up)
    x0 = min(ln["bbox_topleft"][0] for ln in window)
    x1 = max(ln["bbox_topleft"][2] for ln in window)
    y0 = height - max(ln["bbox_topleft"][3] for ln in window)
    y1 = height - min(ln["bbox_topleft"][1] for ln in window)
    return {
        "region_ordinal": ordinal,
        "region_size_rule": f"build_frames.REGION_SIZE={BF.REGION_SIZE}, non-overlapping, ordinal=start//size",
        "region_bbox_pdf_points": [x0, y0, x1, y1],
        "region_n_lines": len(window),
        # index i (0-based) is the adjudicator's `start_physical_line` i+1
        "region_line_mapping": [[hit["page_number"], ordinal * BF.REGION_SIZE + i] for i in range(len(window))],
        "heading_index_in_region": index_in_page - ordinal * BF.REGION_SIZE,
        "heading_index_in_page": index_in_page,
    }


def _source_provenance(row: dict) -> dict:
    """F6 -- everything a later caller needs so nothing re-decides what to crop.

    The three objects stay separately named: `xml_source_text` (semantic source truth),
    `expected_rendered_heading` (source-determined expectation) and `expected_before` /
    `expected_text` (the physical observation) are never collapsed into one field.
    """
    return {
        "element": row["element"],
        "element_id": row["element_id"],
        "ancestor_path": row["ancestor_path"],
        "xml_document_ordinal": row["xml_document_ordinal"],
        "xml_source_text": row["xml_source_text"],
        "expected_rendered_heading": row["expected_rendered"],
        "page_number": row["page_number"],
        "page_height": row["page_height"],
        "physical_line_index": row["line_index"],
        "heading_index_in_page": row["heading_index_in_page"],
        "heading_bbox_pdf_points": row["line_bbox_pdf"],
        "region_ordinal": row["region_ordinal"],
        "region_size_rule": row["region_size_rule"],
        "region_bbox_pdf_points": row["region_bbox_pdf_points"],
        "region_n_lines": row["region_n_lines"],
        "region_line_mapping": row["region_line_mapping"],
        "heading_index_in_region": row["heading_index_in_region"],
    }


def development_account_sources(page_limit: int = SOURCE_PAGE_LIMIT) -> list[dict]:
    """A40 F1/F2 -- the COMPLETE independent source population, from the committed XML.

    NO ARCHITECTURE OUTPUT PARTICIPATES. There is no `run_hybrid`, no `run_extended` and no
    `pdf_anchors.extract_anchors` on this path: the account level is read from GPO's own legacy
    DTD structure, the printed occurrence is located by the approved XML->PDF bridge, and the
    physical observation comes from the independent renderer. `x24` proves it by making all three
    architecture entrypoints raise and requiring this population to come out byte-identical.

    THE THREE OBJECTS STAY SEPARATE on every row:
      * `xml_source_text`   semantic source truth -- what the XML says the heading IS
      * `expected_rendered` the source-determined expectation (content/punctuation/whitespace)
      * `expected_text`     the PHYSICALLY OBSERVED printed characters, which is what an
                            adjudicator transcribes and what every mutation is computed from

    `page_limit` is accepted for signature compatibility and deliberately UNUSED: the old H path
    needed it to bound extraction cost, while the bridge is whole-document and truncating it
    would silently shrink the population that eligibility is computed over.
    """
    return source_population(page_limit)["rows"]


def source_population(page_limit: int = SOURCE_PAGE_LIMIT) -> dict:
    """The population above, plus the refusal accounting G6 replays and the manifest reports."""
    rows, diagnostics = [], {}
    for document, pdf_path, xml_path in DEVELOPMENT_SOURCES:
        lines = XS.physical_lines(pdf_path)
        anchors = XS.independent_anchors(xml_path, pdf_path, lines=lines)
        records = XS.account_records(xml_path)
        bridged = XS.bridge(pdf_path, records, anchors=anchors["anchors"], lines=lines)
        pdf_sha, xml_sha = sha256_file(pdf_path), sha256_file(xml_path)
        for p in bridged["paired"]:
            # A40.12 -- NO position filter. The parent-based rule was falsified against the DTD
            # content model and GPO's own `ancestor::appropriations-small` template; see the note
            # in `xml_sources`. Every bridged record is an account source.
            height = p["page_height"]
            tl = p["bbox_topleft"]
            rows.append(
                {
                    "document": document,
                    "pdf_path": str(pdf_path),
                    "source_sha256": pdf_sha,
                    "xml_path": str(xml_path),
                    "xml_sha256": xml_sha,
                    "element": p["element"],
                    "element_id": p["element_id"],
                    "ancestor_path": p["ancestor_path"],
                    "xml_document_ordinal": p["xml_document_ordinal"],
                    "xml_offset": p["xml_offset"],
                    "xml_source_text": p["xml_source_text"],
                    "expected_rendered": p["rendering"]["expected_rendered"],
                    "page_number": p["page_number"],
                    "line_index": p["line_index"],
                    "line_bbox_pdf": [tl[0], height - tl[3], tl[2], height - tl[1]],
                    "line_bbox_topleft": list(tl),
                    "page_height": height,
                    # A40.13 -- the INDEPENDENTLY OBSERVED text origin and size of the heading's
                    # first inked span. The line bbox is not a substitute for either.
                    "span_origin": p["span_origin"],
                    "span_size": p["span_size"],
                    "span_font": p["span_font"],
                    "kind": "account",
                    "expected_text": p["printed_text"],
                    "xml_evidence": (
                        f"legacy-DTD {p['element']} id={p['element_id']} at {p['ancestor_path']}; "
                        "printed line agrees with the XML header under case folding alone"
                    ),
                    **oracle_region(lines, p),
                }
            )
        by_reason: dict = {}
        for r in bridged["refusals"]:
            by_reason[r["reason"]] = by_reason.get(r["reason"], 0) + 1
        diagnostics[document] = {
            "xml_account_records": len(records),
            "independent_anchors": anchors["n"],
            "anchor_inversions": anchors["monotonicity"]["n_inversions"],
            "bridge_paired": bridged["n_paired"],
            "bridge_refusals": by_reason,
            "admitted_sources": sum(1 for r in rows if r["document"] == document),
        }
    return {"rows": rows, "diagnostics": diagnostics}


def na_eligible(sources: list[dict]) -> list[dict]:
    """A40.3 -- the COMMON eligibility rule, applied before ranking and before assignment.

    One rule for all three variants, deliberately: a per-variant rule would let the schedule
    pick whichever source happened to suit the mutation it drew, which is selection after the
    fact wearing a deterministic costume.
    """
    out = []
    for row in sources:
        tokens = alphabetic_tokens(row["expected_text"])
        if len(tokens) < 3:
            continue  # enough words to delete one AND still weld a pair
        if not any(len(t) >= MIN_SPLIT_TOKEN for t in tokens):
            continue  # a splittable token
        out.append(row)
    return out


def source_identity(row: dict):
    """Canonical, pre-mutation, and unique per physical heading occurrence.

    XML-ANCHORED and content-addressed. The element id is GPO's own stable identifier and the
    XML digest pins the file it came from, so the identity survives a path move and carries no
    architecture-derived component. `MC.select` supplies the namespace, so N-A and N-B rank the
    SAME identity under different namespaces rather than two differently-shaped tuples.
    """
    return (
        "xml-account",
        row["xml_sha256"],
        row["element_id"],
        row["xml_document_ordinal"],
        row["page_number"],
    )


def select_na_sources(eligible: list[dict]) -> list[dict]:
    """Rank canonical identities under `na-source`/20260807 and take the first 8."""
    if len(eligible) < NA_TOTAL:
        raise ControlFixtureError(
            INSUFFICIENT_ELIGIBLE_SOURCES, {"control": "N-A", "eligible": len(eligible), "required": NA_TOTAL}
        )
    by_identity = {MC.canonical(source_identity(r)): r for r in eligible}
    ranked = MC.select(NA_NAMESPACE, [source_identity(r) for r in eligible], NA_TOTAL)
    return [by_identity[MC.canonical(i)] for i in ranked]


def select_nb_sources(eligible: list[dict]) -> list[dict]:
    """A39.3 -- N-B's own ranking, under `nb-source`/20260807."""
    if len(eligible) < NB_TOTAL:
        raise ControlFixtureError(
            INSUFFICIENT_ELIGIBLE_SOURCES, {"control": "N-B", "eligible": len(eligible), "required": NB_TOTAL}
        )
    by_identity = {MC.canonical(source_identity(r)): r for r in eligible}
    ranked = MC.select(NB_NAMESPACE, [source_identity(r) for r in eligible], NB_TOTAL)
    return [by_identity[MC.canonical(i)] for i in ranked]


# ------------------------------------------------------------- generated PDF material

HEADING_NOT_LOCATABLE = "HEADING_NOT_LOCATABLE"
REPLACEMENT_TOO_SMALL = "REPLACEMENT_TOO_SMALL"

#: The one replacement face, for every N-A control. Named once so no per-document choice exists.
REPLACEMENT_FONT = "tiro"
#: Below this the stimulus stops being a legible heading, so it REFUSES rather than shrinking on.
MIN_REPLACEMENT_FONTSIZE = 6.0


def replacement_placement(row: dict) -> tuple[tuple[float, float], float]:
    """A40.13 -- where the mutated heading is drawn, and at what size. GENERAL, no constants.

    THE DEFECT THIS REPLACES. The old rule took both facts off the line's bounding box:
    `insert_text((rect.x0, rect.y1), ...)` used the box's BOTTOM EDGE as a baseline, and
    `fontsize = rect.height` used the box HEIGHT as a font size. Measured on N-A #6, the real
    span origin is y=163.000 and the real size 10.8671, while the box gave 166.339 and 14.0 --
    a baseline 3.34 pt low and a face 29 % oversized. The 14.0 came from a trailing WHITESPACE
    span at a different size, which inflates the line box without inking anything. That heading
    is line 0 of its window, so the region's top edge IS the line's top edge, and the oversized
    glyphs escaped it by 0.742 pt.

    THE RULE. Draw at the independently observed span origin, at the source's own span size,
    reduced only as far as the replacement face's MEASURED metrics require in order to sit inside
    the source line's own box:

        size = min(source span size, above / ascender, below / -descender)

    `above`/`below` are the source line box's extent around its own baseline, and the ascender
    and descender are read from the font at run time -- so the rule is arithmetic over measured
    facts, identical for every N-A control, with no per-document or per-heading constant and no
    "nudge until it fits" search. Times-Roman's ascender is 1.0530, which is why preserving the
    baseline ALONE was not sufficient: 1.0530 x 10.8671 = 11.44 pt needs 10.661 pt of room.

    Fitting inside the SOURCE LINE box rather than the region is deliberate and stronger: the
    region is the union of its member lines' boxes, so a replacement that fits its own line
    necessarily fits the region, whichever position the heading holds in the window.

    Truncated rather than rounded to 3 dp: rounding can go UP and re-cross the bound it was
    computed to respect.
    """
    import pymupdf

    origin, size, box = row.get("span_origin"), row.get("span_size"), row.get("line_bbox_topleft")
    if not origin or not size or not box:
        raise ControlFixtureError(
            HEADING_NOT_LOCATABLE,
            {"why": "no inked span origin/size", "document": row["document"], "page": row["page_number"]},
        )
    baseline = origin[1]
    above, below = baseline - box[1], box[3] - baseline
    font = pymupdf.Font(REPLACEMENT_FONT)
    limits = [float(size)]
    if font.ascender > 0 and above > 0:
        limits.append(above / font.ascender)
    if font.descender < 0 and below > 0:
        limits.append(below / -font.descender)
    fitted = int(min(limits) * 1000) / 1000
    if fitted < MIN_REPLACEMENT_FONTSIZE:
        raise ControlFixtureError(
            REPLACEMENT_TOO_SMALL,
            {"fitted": fitted, "floor": MIN_REPLACEMENT_FONTSIZE, "document": row["document"]},
        )
    return (float(origin[0]), float(baseline)), fitted


def generate_na_pdf(row: dict, after_text: str, out_path: Path) -> dict:
    """Render the mutated heading into a copy of the source page. DEVELOPMENT source only.

    The heading is redacted and the mutated string re-drawn at the same origin and size, so the
    only thing that moves is the printed characters -- which is exactly what N-A must perturb.
    The control's TRUTH is the committed recipe, never this rendering and never H or X's output
    on it; the render exists so an adjudicator has something to transcribe.
    """
    import pymupdf

    doc = pymupdf.open(row["pdf_path"])
    try:
        page = doc[row["page_number"] - 1]
        x0, y0, x1, y1 = row["line_bbox_pdf"]
        height = page.rect.height
        # the committed neutral-line bbox is PDF space (y up); pymupdf Rect is top-left origin
        rect = pymupdf.Rect(x0, height - y1, x1, height - y0)
        if not (rect.width > 0 and rect.height > 0):
            raise ControlFixtureError(
                HEADING_NOT_LOCATABLE, {"document": row["document"], "page": row["page_number"], "bbox": list(rect)}
            )
        point, size = replacement_placement(row)
        page.add_redact_annot(rect)
        page.apply_redactions()
        page.insert_text(point, after_text, fontname=REPLACEMENT_FONT, fontsize=size)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.xref_set_key(-1, "ID", deterministic_pdf_id(out_path.name))
        doc.save(str(out_path), garbage=0, deflate=True, no_new_id=True)
    finally:
        doc.close()
    return {
        "generated_path": str(out_path.relative_to(EV)),
        "generated_sha256": sha256_file(out_path),
        "source_bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
        "drawn_origin": [point[0], point[1]],
        "drawn_fontsize": size,
        "drawn_font": REPLACEMENT_FONT,
    }


def generate_nc_pdf(index: int, out_path: Path) -> dict:
    """A39.3 / A40 -- a CONSTRUCTIONALLY heading-free body-only region.

    Purpose-built rather than harvested: "this region contains no heading" is then true by
    construction instead of true because nobody found one. Every line is lower-case running
    prose at body size, left-aligned on the body measure -- so none of the prompt's disjunctive
    heading cues (centered, capitals, italic, distinctly larger/heavier, otherwise separated)
    is present.
    """
    import pymupdf

    # F8 -- FOUR DISTINCT bodies, one per index. The previous generator ignored `index` and
    # wrote the same eight lines every time: the four PDFs differed only in container bytes,
    # and all four rendered to the IDENTICAL PNG through the real oracle renderer. Container
    # SHA uniqueness is not rendered uniqueness, and the adjudicator sees the render.
    bodies = [
        [
            "of the funds appropriated under this heading in the preceding fiscal year, the",
            "amounts made available shall remain available until expended, and shall be subject",
            "to the reporting requirements described in the accompanying statement, except that",
            "no such amount may be obligated before the date on which the plan is submitted to",
            "the committees, and any reprogramming shall follow the ordinary procedures that",
            "apply to accounts of a similar character under prior appropriations acts, provided",
            "that the limitation in this paragraph shall not apply to amounts transferred for",
            "administrative expenses within the same account during the period of availability.",
        ],
        [
            "notwithstanding any other provision of law, the amounts withheld under the terms",
            "of the preceding paragraph shall be released upon submission of the spending plan",
            "required by the accompanying report, and shall thereafter be available for the",
            "purposes described therein, except that not more than five percent may be used",
            "for administrative costs, and the head of the agency shall notify the committees",
            "not later than fifteen days before any obligation is incurred in excess of that",
            "limit, together with a written justification setting out the basis for the excess",
            "and the expected effect on the balance of the account for the fiscal year.",
        ],
        [
            "amounts provided under this heading shall be allocated in accordance with the",
            "table included in the explanatory statement accompanying this act, and no funds",
            "may be reprogrammed between the activities shown in that table without prior",
            "written approval, which shall be sought at least thirty days in advance of the",
            "proposed action, and shall describe the amounts involved, the activities that",
            "would be reduced, and the reasons that the original allocation is no longer",
            "adequate, provided that this requirement shall not apply to a transfer of less",
            "than one hundred thousand dollars within a single program element.",
        ],
        [
            "in addition to amounts otherwise made available under this heading, there are",
            "appropriated such sums as may be necessary to carry out the responsibilities",
            "described in the preceding subsection, to remain available through the end of",
            "the following fiscal year, of which a portion shall be transferred to the",
            "working capital fund for centrally provided services, and the remainder shall",
            "be apportioned among the offices in the manner determined by the secretary,",
            "who shall report the resulting distribution to the committees not later than",
            "sixty days after the date of enactment of this act.",
        ],
    ]
    body = bodies[index % len(bodies)]
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for i, line in enumerate(body):
        page.insert_text((90.0, 120.0 + i * 24.0), f"{i + 1}  {line}", fontname="tiro", fontsize=14)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.xref_set_key(-1, "ID", deterministic_pdf_id(out_path.name))
    doc.save(str(out_path), garbage=0, deflate=True, no_new_id=True)
    # The committed region is DERIVED from the drawn page, not from the layout constants
    # above: a constant that drifted from what was actually drawn would commit a bbox that
    # crops the stimulus, and the mismatch would be invisible until adjudication.
    blocks = [b[:4] for b in page.get_text("blocks")]
    height = page.rect.height
    top = min(b[1] for b in blocks)
    bottom = max(b[3] for b in blocks)
    left = min(b[0] for b in blocks)
    right = max(b[2] for b in blocks)
    doc.close()
    return {
        "generated_path": str(out_path.relative_to(EV)),
        "generated_sha256": sha256_file(out_path),
        "n_lines": len(body),
        "composition": "lower-case running prose, body size 14.0, left-aligned, margin-numbered",
        # PDF coordinates (y up), the form build_oracle.render_region consumes
        "region_bbox_pdf_points": [left, height - bottom, right, height - top],
    }


# ------------------------------------------------------------------- the manifest


_REPLAY_CACHE: dict = {}


def replay_source_selection(page_limit: int = SOURCE_PAGE_LIMIT) -> dict:
    """A40 F3 -- rebuild the ENTIRE selected source population from committed primary inputs.

    THE MANIFEST IS THE OBJECT UNDER TEST, NEVER AN INPUT. Nothing here reads
    `control_fixtures.json`, a generated N-A PDF, the oracle key, or any H/X output: the only
    authorities are the committed XML, the committed DEVELOPMENT PDF and the frozen methodology
    constants. That is what makes a coherent-but-wrong manifest detectable -- a validator that
    re-derived its expectations FROM the rows it is checking can only find self-inconsistency.

    Counts are deliberately NOT hardcoded. The replay recomputes the population and the draws, so
    a future change in the source corpus shows up as a manifest disagreement rather than as a
    constant nobody updated.
    """
    key = ("replay", page_limit)
    if key not in _REPLAY_CACHE:
        population = source_population(page_limit)
        rows = population["rows"]
        eligible = na_eligible(rows)
        _REPLAY_CACHE[key] = {
            "population": rows,
            "diagnostics": population["diagnostics"],
            "na_eligible": eligible,
            "nb_eligible": rows,
            "na_selected": select_na_sources(eligible),
            "nb_selected": select_nb_sources(rows),
        }
    return _REPLAY_CACHE[key]


def replay_na_expectations(page_limit: int = SOURCE_PAGE_LIMIT) -> list[dict]:
    """A40 F4 -- derive every N-A expectation from the REPLAYED source, not from the manifest.

    The chain is deliberately end-to-end:

        F3-replayed selected source -> independently observed rendered heading
        -> frozen index-derived variant -> frozen deterministic target -> after + recipe

    `expected_before` comes from the replayed physical observation and `variant` from the frozen
    `index mod 3` schedule -- NOT from the manifest's own fields. Taking either from the manifest
    is what would let a tampered record rewrite `expected_before`, `expected_after` and
    `mutation_recipe` *together* and still validate: internally consistent, deterministically
    wrong, and invisible.
    """
    out = []
    for index, row in enumerate(replay_source_selection(page_limit)["na_selected"]):
        variant = NA_SCHEDULE[index % 3]
        before = row["expected_text"]
        after, recipe = MUTATORS[variant](before)
        out.append(
            {
                "schedule_index": index,
                "source_canonical_identity": MC.canonical(source_identity(row)),
                "element_id": row["element_id"],
                "physical_line_index": row["line_index"],
                "variant": variant,
                "expected_before": before,
                "expected_after": after,
                "mutation_recipe": recipe,
                "region_bbox_pdf_points": row["region_bbox_pdf_points"],
            }
        )
    return out


def _replay_defects(manifest: dict, defect) -> None:
    """F3 + F4, reported through `defect`. Field-by-field so each failure names its own invariant."""
    replay = replay_source_selection()
    expectations = replay_na_expectations()

    for kind, replayed in (("N-A", replay["na_selected"]), ("N-B", replay["nb_selected"])):
        rows = sorted(
            (f for f in manifest.get("fixtures", []) if f.get("control_kind") == kind),
            key=lambda f: f.get("schedule_index", -1),
        )
        want = [MC.canonical(source_identity(r)) for r in replayed]
        got = [f.get("source_canonical_identity") for f in rows]
        if len(got) == len(want) and got != want and sorted(got) == sorted(want):
            # exactly the right members in the wrong deterministic order
            defect(SOURCE_SELECTION_ORDER_MISMATCH, control=kind, expected=want[:3], found=got[:3])
        for i, (f, r) in enumerate(zip(rows, replayed)):
            if f.get("element_id") != r["element_id"]:
                defect(
                    SOURCE_IDENTITY_MISMATCH, control=kind, index=i, expected=r["element_id"], found=f.get("element_id")
                )
            if f.get("physical_line_index") != r["line_index"]:
                defect(
                    PHYSICAL_SOURCE_MISMATCH,
                    control=kind,
                    index=i,
                    expected=r["line_index"],
                    found=f.get("physical_line_index"),
                )
            if f.get("source_canonical_identity") != MC.canonical(source_identity(r)):
                defect(
                    SOURCE_SELECTION_MISMATCH,
                    control=kind,
                    index=i,
                    expected=MC.canonical(source_identity(r)),
                    found=f.get("source_canonical_identity"),
                )
            # A40.16 -- N-B's PRIVATE TRUTH is replayed too, not just its source identity.
            #
            # Found by the freeze-verification stale-evidence probe: swapping the expected
            # headings between two valid N-B controls left BOTH x26 and G6 green once x26 was
            # regenerated. Each record stayed well-formed and the key agreed with the manifest,
            # because both were derived from the same mutated manifest -- so `verify_join` could
            # not see it. Only the independently replayed source can: N-B's expected heading IS
            # the rendered heading of its own source occurrence.
            if kind == "N-B":
                want = [{"text": r["expected_text"]}]
                if f.get("expected_adjudicated_headings") != want:
                    defect(
                        MUTATION_INPUT_MISMATCH,
                        control=kind,
                        index=i,
                        expected=want,
                        found=f.get("expected_adjudicated_headings"),
                    )
        if len(rows) != len(replayed):
            defect(SOURCE_POPULATION_MISMATCH, control=kind, expected=len(replayed), found=len(rows))

    by_index = {f.get("schedule_index"): f for f in manifest.get("fixtures", []) if f.get("control_kind") == "N-A"}
    for exp in expectations:
        f = by_index.get(exp["schedule_index"])
        if f is None:
            defect(SOURCE_POPULATION_MISMATCH, control="N-A", index=exp["schedule_index"], found=None)
            continue
        if f.get("variant") != exp["variant"]:
            defect(
                MUTATION_VARIANT_MISMATCH, index=exp["schedule_index"], expected=exp["variant"], found=f.get("variant")
            )
        if f.get("expected_before") != exp["expected_before"]:
            defect(
                MUTATION_INPUT_MISMATCH,
                index=exp["schedule_index"],
                expected=exp["expected_before"],
                found=f.get("expected_before"),
            )
        if f.get("expected_after") != exp["expected_after"]:
            defect(
                MUTATION_TARGET_MISMATCH,
                index=exp["schedule_index"],
                expected=exp["expected_after"],
                found=f.get("expected_after"),
            )
        if f.get("mutation_recipe") != exp["mutation_recipe"]:
            defect(
                MUTATION_RECIPE_MISMATCH,
                index=exp["schedule_index"],
                expected=exp["mutation_recipe"],
                found=f.get("mutation_recipe"),
            )
        evidence = mutation_evidence(exp["expected_before"], exp["expected_after"], exp["variant"])
        if not evidence["live"]:
            defect("REPLAYED_MUTATION_NOT_LIVE", index=exp["schedule_index"], evidence=evidence)


ORACLE_INTEGRATION_EVIDENCE = EV / "results" / "x26_control_oracle.json"
ORACLE_INTEGRATION_NOT_VERIFIED = "ORACLE_INTEGRATION_NOT_VERIFIED"


ORACLE_EVIDENCE_STALE = "ORACLE_EVIDENCE_STALE"


def _oracle_integration_defects(defect, manifest: dict) -> None:
    """A40 section 13 -- G6 may not go green on the manifest half of its contract alone.

    A manifest that DESCRIBES 20 controls is not evidence that 20 controls can be adjudicated:
    routes, blinding, leakage and the private truth binding are properties of the oracle path, not
    of the JSON. G6 therefore requires `x26`'s committed evidence to exist and to report zero
    failures, the same shape G2 uses for the X2 evidence. Without this, G6 would be green while
    half of section 13 was unverified -- the exact false green A40.12 was opened to remove.
    """
    if not ORACLE_INTEGRATION_EVIDENCE.exists():
        defect(ORACLE_INTEGRATION_NOT_VERIFIED, why="x26 evidence absent", path=str(ORACLE_INTEGRATION_EVIDENCE.name))
        return
    try:
        evidence = json.loads(ORACLE_INTEGRATION_EVIDENCE.read_text())
    except json.JSONDecodeError as exc:
        defect(ORACLE_INTEGRATION_NOT_VERIFIED, why="x26 evidence unreadable", detail=str(exc))
        return
    failures = evidence.get("failures") or []
    counts = evidence.get("counts") or {}
    if failures:
        defect(ORACLE_INTEGRATION_NOT_VERIFIED, why="x26 reported failures", failures=failures[:4])
    if evidence.get("n_controls") != NA_TOTAL + NB_TOTAL + NC_TOTAL:
        defect(
            ORACLE_INTEGRATION_NOT_VERIFIED, why="x26 did not execute all 20 controls", found=evidence.get("n_controls")
        )
    if counts != {"N-A": NA_TOTAL, "N-B": NB_TOTAL, "N-C": NC_TOTAL}:
        defect(ORACLE_INTEGRATION_NOT_VERIFIED, why="x26 control mix disagrees with the frozen 8/8/4", found=counts)

    # A40.16 -- THE BINDING. Without this the evidence certifies only itself: a x26 result whose
    # every value was garbage still left G6 green, and a stale PASS produced for a DIFFERENT valid
    # control state would have been accepted identically. Recomputed here from the manifest and
    # prompt ON DISK, so the evidence cannot outlive the state it ran on.
    import build_oracle as BO

    recorded = evidence.get("control_oracle_input_digest")
    current = BO.control_oracle_input_digest(manifest)
    if recorded != current:
        defect(
            ORACLE_EVIDENCE_STALE,
            recorded=recorded,
            current=current,
            why="x26 evidence was produced for a different control/oracle state",
        )


def region_realization(manifest: dict, defect) -> None:
    """A40 section 6 -- the PHYSICAL realization, checked separately from the logical replay.

    Occurrence-scoped, per A40.13: a duplicate of the original elsewhere on the page is a
    different occurrence the adjudicator never sees, so it is not a defect.
    """
    for f in manifest.get("fixtures", []):
        if f.get("control_kind") != "N-A" or not f.get("generated_path"):
            continue
        path = EV / f["generated_path"]
        if not path.exists():
            continue
        lines = [ln for ln in XS.physical_lines(path) if ln["page_number"] == f["page_number"]]
        rb, height = f["region_bbox_pdf_points"], f["page_height"]

        def inside(ln, rb=rb, height=height):
            y0, y1 = height - ln["bbox_topleft"][3], height - ln["bbox_topleft"][1]
            return y0 >= rb[1] - 0.5 and y1 <= rb[3] + 0.5

        after_in = sum(1 for ln in lines if XS.stripped_line(ln) == f["expected_after"].upper() and inside(ln))
        before_in = sum(1 for ln in lines if XS.stripped_line(ln) == f["expected_before"].upper() and inside(ln))
        if after_in != 1 or before_in != 0:
            defect(
                REGION_REALIZATION_MISMATCH,
                index=f.get("schedule_index"),
                after_in_region=after_in,
                before_in_region=before_in,
            )


def build_manifest(page_limit: int = SOURCE_PAGE_LIMIT, generated_dir: Path | None = None) -> dict:
    """Build all 20 control fixtures and the manifest. DEVELOPMENT + SYNTHETIC only."""
    generated_dir = Path(generated_dir) if generated_dir else GENERATED_DIR
    population = source_population(page_limit)
    sources = population["rows"]
    eligible = na_eligible(sources)
    na_sources = select_na_sources(eligible)

    na = []
    for index, row in enumerate(na_sources):
        variant = NA_SCHEDULE[index % 3]
        after, recipe = MUTATORS[variant](row["expected_text"])
        evidence = mutation_evidence(row["expected_text"], after, variant)
        if not evidence["live"]:
            # A40.5 -- a dead mutation never becomes a fixture. It STOPS here rather than
            # being quietly downgraded, because a control that cannot fire is worse than a
            # missing one: it reports coverage it does not have.
            raise ControlFixtureError(DEAD_MUTATION, {"index": index, "variant": variant, "evidence": evidence})
        generated = generate_na_pdf(row, after, generated_dir / f"na_{index:02d}_{variant.lower()}.pdf")
        na.append(
            {
                "control_kind": "N-A",
                "variant": variant,
                "schedule_index": index,
                "source_type": "DEVELOPMENT PDF, mutated",
                "canonical_identity": MC.canonical(
                    MC.control_stimulus_identity("N-A", row["source_sha256"], row["page_number"], index, variant)
                ),
                "source_document": row["document"],
                "source_path": str(Path(row["pdf_path"]).relative_to(REPO)),
                "source_sha256": row["source_sha256"],
                "parent_sha256": row["source_sha256"],
                "xml_path": str(Path(row["xml_path"]).relative_to(REPO)),
                "xml_sha256": row["xml_sha256"],
                "xml_evidence": row["xml_evidence"],
                "source_canonical_identity": MC.canonical(source_identity(row)),
                **_source_provenance(row),
                "expected_before": row["expected_text"],
                "expected_after": after,
                "mutation_recipe": recipe,
                "mutation_evidence": evidence,
                "expected_adjudicated_headings": [{"text": after}],
                **generated,
            }
        )

    nb = []
    for index, row in enumerate(select_nb_sources(sources)):
        nb.append(
            {
                "control_kind": "N-B",
                "variant": "XML_CORROBORATED_HEADING",
                "schedule_index": index,
                "source_type": "DEVELOPMENT PDF, unmodified",
                "canonical_identity": MC.canonical(
                    MC.control_stimulus_identity(
                        "N-B", row["source_sha256"], row["page_number"], index, "XML_CORROBORATED_HEADING"
                    )
                ),
                "source_document": row["document"],
                "source_path": str(Path(row["pdf_path"]).relative_to(REPO)),
                "source_sha256": row["source_sha256"],
                "parent_sha256": None,
                "generated_path": None,
                "generated_sha256": None,
                "xml_path": str(Path(row["xml_path"]).relative_to(REPO)),
                "xml_sha256": row["xml_sha256"],
                "xml_evidence": row["xml_evidence"],
                "source_canonical_identity": MC.canonical(source_identity(row)),
                **_source_provenance(row),
                "expected_adjudicated_headings": [{"text": row["expected_text"]}],
            }
        )

    nc = []
    for index in range(NC_TOTAL):
        generated = generate_nc_pdf(index, generated_dir / f"nc_{index:02d}_heading_free.pdf")
        nc.append(
            {
                "control_kind": "N-C",
                "variant": "SYNTHETIC_HEADING_FREE",
                "schedule_index": index,
                "source_type": "SYNTHETIC, generated",
                "canonical_identity": MC.canonical(
                    MC.control_stimulus_identity(
                        "N-C", generated["generated_sha256"], 1, index, "SYNTHETIC_HEADING_FREE"
                    )
                ),
                "source_document": f"SYNTHETIC/heading-free/{index}",
                "source_path": None,
                "source_sha256": generated["generated_sha256"],
                "parent_sha256": None,
                "page_number": 1,
                # F6 -- N-C's already-repaired region, carried in the SAME shape as N-A/N-B so
                # one adapter serves all three kinds and no caller special-cases a control.
                "region_ordinal": index,
                "region_line_mapping": [[1, i] for i in range(generated["n_lines"])],
                "expected_adjudicated_headings": [],
                **generated,
            }
        )

    return {
        "schema": "control_fixtures/1",
        "population": "DEVELOPMENT + SYNTHETIC -- no confirmatory holdout material anywhere",
        "na_namespace": NA_NAMESPACE,
        "nb_namespace": NB_NAMESPACE,
        "seed": MC.SELECTION_SEED,
        "na_schedule": {str(k): v for k, v in NA_SCHEDULE.items()},
        "retired_variant": RETIRED_VARIANT,
        "counts": {"N-A": len(na), "N-B": len(nb), "N-C": len(nc)},
        "source_truth": (
            "legacy-DTD appropriations-small under <title> -> approved XML->PDF bridge -> "
            "independently observed printed line. No run_hybrid, run_extended or extract_anchors."
        ),
        "account_position_rule": {
            "rule": "NONE -- the account role is keyed on the TAG, not on the parent element",
            "authority": (
                "bill DTD gives appropriations-major/intermediate/small identical content models "
                "(docs/bill-structure.md); billres-details.xsl convertToNeededCase branches on "
                "ancestor::appropriations-small with no parent predicate"
            ),
            "withdrawn": "A40.10's ACCOUNT_PARENT_ELEMENT was falsified and removed in A40.12",
        },
        "eligible_population": {
            "admitted_account_sources": len(sources),
            "na_eligible": len(eligible),
            "nb_eligible": len(sources),
            "per_document": population["diagnostics"],
        },
        "fixtures": na + nb + nc,
    }


def write_manifest(manifest: dict, out_path: Path | None = None) -> Path:
    out_path = Path(out_path) if out_path else MANIFEST_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=1, default=str))
    return out_path


# ------------------------------------------------------------- A39.4 / G6 validation


HOLDOUT_MEMBERSHIP = EV / "results" / "holdout_membership.json"


def holdout_source_sha256(path: Path | None = None) -> set[str]:
    """F7 -- the AUTHORITATIVE confirmatory source identities, read from the frozen manifest.

    Reads `holdout_membership.json` only; no holdout PDF is opened. Identity beats naming: a
    confirmatory file copied in under an innocuous document id and path would pass a
    name-based guard entirely, because nothing about the bytes has to change to defeat one.
    The recorded SHA-256 is what actually identifies the material.
    """
    p = Path(path) if path else HOLDOUT_MEMBERSHIP
    if not p.exists():
        return set()
    members = json.loads(p.read_text()).get("members", [])
    return {f["sha256"] for m in members for f in m.get("files", []) if f.get("sha256")}


def validate_manifest(manifest: dict, holdout_guard=None, holdout_shas=None) -> list[dict]:
    """A39.4 -- what G6 calls. Returns the list of defects; empty means valid.

    VERIFIES rather than records: every source and generated SHA is recomputed from the bytes
    on disk, so a changed file with a stale manifest hash FAILS. A manifest that merely stated
    hashes would certify provenance it never checked.
    """
    if holdout_guard is None:
        import build_oracle as BO

        holdout_guard = BO.HOLDOUT_GUARD
    if holdout_shas is None:
        holdout_shas = holdout_source_sha256()
    defects: list[dict] = []

    def defect(reason, **detail):
        defects.append({"reason": reason, **detail})

    # A40.15 -- F3 and F4. The manifest's own rows are NOT consulted to build the expectation;
    # everything is re-derived from the committed XML/PDF and the frozen constants. A disabled
    # replay makes G6 RED for that reason rather than silently skipping the strongest check.
    if SOURCE_SELECTION_REPLAY_IMPLEMENTED and MUTATION_TARGET_REPLAY_IMPLEMENTED:
        _replay_defects(manifest, defect)
        region_realization(manifest, defect)
        _oracle_integration_defects(defect, manifest)
    else:
        if not SOURCE_SELECTION_REPLAY_IMPLEMENTED:
            defect(SOURCE_REPLAY_NOT_IMPLEMENTED, contract="A40 F3")
        if not MUTATION_TARGET_REPLAY_IMPLEMENTED:
            defect(MUTATION_TARGET_REPLAY_NOT_IMPLEMENTED, contract="A40 F4")

    fixtures = manifest.get("fixtures", [])
    by_kind = {k: [f for f in fixtures if f.get("control_kind") == k] for k in ("N-A", "N-B", "N-C")}
    for kind, expected in (("N-A", NA_TOTAL), ("N-B", NB_TOTAL), ("N-C", NC_TOTAL)):
        if len(by_kind[kind]) != expected:
            defect("WRONG_CONTROL_COUNT", control=kind, expected=expected, found=len(by_kind[kind]))

    allocation = {v: 0 for v in NA_VARIANTS}
    for f in by_kind["N-A"]:
        variant = f.get("variant")
        if variant == RETIRED_VARIANT:
            defect("RETIRED_VARIANT_PRESENT", variant=variant, identity=f.get("canonical_identity"))
            continue
        if variant not in allocation:
            defect("UNKNOWN_NA_VARIANT", variant=variant)
            continue
        allocation[variant] += 1
        evidence = mutation_evidence(f.get("expected_before", ""), f.get("expected_after", ""), variant)
        if not evidence["live"]:
            defect("DEAD_OR_MISCLASSIFIED_MUTATION", variant=variant, evidence=evidence)
        recipe = f.get("mutation_recipe") or {}
        if recipe.get("variant") != variant:
            defect("MUTATION_RECIPE_VARIANT_MISMATCH", variant=variant, recipe=recipe.get("variant"))
    if allocation != NA_EXPECTED_ALLOCATION:
        defect("WRONG_NA_ALLOCATION", expected=NA_EXPECTED_ALLOCATION, found=allocation)

    identities = [f.get("canonical_identity") for f in fixtures]
    if len(set(identities)) != len(identities):
        dupes = sorted({i for i in identities if identities.count(i) > 1})
        defect("DUPLICATE_CONTROL_IDENTITY", duplicates=dupes[:4])

    for f in fixtures:
        kind = f.get("control_kind")
        if kind in ("N-A", "N-B") and not f.get("xml_evidence"):
            defect("MISSING_XML_CORROBORATION", control=kind, identity=f.get("canonical_identity"))
        if kind == "N-C" and f.get("expected_adjudicated_headings") != []:
            defect("NC_EXPECTED_HEADINGS_NOT_EMPTY", identity=f.get("canonical_identity"))
        if kind in ("N-A", "N-B") and not f.get("expected_adjudicated_headings"):
            defect("MISSING_EXPECTED_TRUTH", control=kind, identity=f.get("canonical_identity"))

        # provenance: every hash is recomputed from bytes, and no holdout may appear anywhere
        for field, root in (("source_path", REPO), ("generated_path", EV)):
            rel = f.get(field)
            if not rel:
                continue
            path = root / rel
            if not path.exists():
                defect("MISSING_ARTIFACT", field=field, path=str(rel))
                continue
            expected_sha = f.get("source_sha256") if field == "source_path" else f.get("generated_sha256")
            actual = sha256_file(path)
            if expected_sha and actual != expected_sha:
                defect("STALE_SHA256", field=field, path=str(rel), recorded=expected_sha, actual=actual)
        for field in ("xml_path", "xml_sha256"):
            if f.get("control_kind") in ("N-A", "N-B") and not f.get(field):
                defect("MISSING_XML_CORROBORATION", control=f.get("control_kind"), field=field)
        if f.get("xml_path"):
            xml_abs = REPO / f["xml_path"]
            if xml_abs.exists() and f.get("xml_sha256") and sha256_file(xml_abs) != f["xml_sha256"]:
                defect("STALE_SHA256", field="xml_path", path=f["xml_path"])

        # F7 -- IDENTITY first. A confirmatory file copied in under an innocuous name defeats
        # the string scan entirely, so every recorded source/parent hash is checked against the
        # authoritative SHA set from the frozen membership manifest.
        for field in ("source_sha256", "parent_sha256", "generated_sha256"):
            value = f.get(field)
            if value and value in holdout_shas:
                defect("HOLDOUT_SOURCE_IDENTITY", field=field, sha256=value, identity=f.get("canonical_identity"))

        # the name/path scan is kept as additional defence, not as the primary guard
        provenance = " ".join(
            str(f.get(k) or "")
            for k in ("source_document", "source_path", "generated_path", "xml_path", "canonical_identity")
        )
        for member in sorted(holdout_guard):
            if member in provenance:
                defect("HOLDOUT_PROVENANCE", member=member, identity=f.get("canonical_identity"))
    return defects
