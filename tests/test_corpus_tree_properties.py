"""Corpus-wide property gate for the leveled structure tree (#108, step 5).

The per-fixture gates in ``test_structure_tree.py`` and ``test_canonical_tree.py``
prove the tree's invariants on a handful of hand-picked bills. This module
parametrizes the SAME invariants over every parseable bill version in the corpus,
so a parser change that breaks one of them on an un-pinned bill trips here instead
of in production. It asserts on the **contract-shaped tree** (the canonical JSON
nodes both pipelines emit), not an internal ``TreeNode`` dump — the consumed output
(``feedback_measure_at_consumed_output``).

Five invariants per bill version:

1. **Schema-valid** — every node validates against the published ``TreeNode`` def.
2. **Valid level** — every node's ``level`` is in the shared GPO enum.
3. **Money conservation** — the union of per-node ``own_amounts`` never over-counts;
   drops are bounded by a documented per-bill registry. XML measures against the
   INDEPENDENT raw-XML body (the strong gate — ``full_text`` is derived from the same
   nodes, so measuring there would tautologically pass over dropped money). PDF has
   no independent ground truth, so it measures against its own ``full_text`` (the
   documented carve-out) — a labeled span check, weaker by construction.
4. **No blank-label TOC rows** — the leveled TOC the tree renders carries no blank
   clickable rows or empty groups (``feedback_validate_against_hard_fixture``: the
   consumed-output form of the blank-row invariant).
5. **Well-behaved subtree extents** — the prerequisite for #172's span-containment
   join (epic #175, step 1). A tree node's ``full_text_span`` is NOT a container span
   (an interior node's span is its heading line only; a content node's is its own body
   slice, excluding children — see ``_xml_tree_payload`` / ``_pdf_tree_payload`` and the
   doc note in ``formatters/diff_html.py``). So #172 must derive a per-node *subtree
   extent* = ``(min start, max end)`` over the node's own span and all descendants'.
   The join is only correct if extents are well-behaved: sibling extents pairwise
   disjoint + document-ordered, and every content child's span inside its parent's
   extent. This gate tests that corpus-wide BEFORE the join is built on it. See
   ``_assert_subtree_extents_well_behaved`` for what the corpus actually does (spoiler:
   sibling disjointness trips, and that is a design input to #172, not a test bug).

``bills/`` is gitignored (fetched via ``fetch_bills.py``), so every case skips
cleanly on a clean clone / in CI; local runs gate.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest

from bill_tree import extract_text_content, find_bill_body, normalize_bill
from diff_bill import extract_amounts
from formatters.canonical import _pdf_tree_payload
from formatters.diff_html import _build_toc_from_tree
from formatters.text_serializer import _xml_tree_payload, serialize_tree_for_tree
from parsers.pdf_anchors import extract_anchors
from parsers.pdf_text import pdf_full_text
from tests.conftest import require_corpus_or_skip
from tests.pdf_corpus import cached_pages

pytestmark = pytest.mark.slow

BILLS_DIR = Path(__file__).parent.parent / "bills"
_SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "canonical-diff.schema.json"

# Scope to the corpus version-file naming (see test_corpus_properties for why a
# recursive **/*.xml would sweep in non-bill metadata XML).
ALL_XML_FILES = sorted(BILLS_DIR.glob("*/[0-9]*_*.xml"))
ALL_PDF_FILES = sorted(BILLS_DIR.glob("*/[0-9]*_*.pdf"))

_LEVELS = {"division", "title", "major", "agency", "account", "section", "grouping", "preamble", "heading"}


def _corpus_id(path: Path) -> str:
    return f"{path.parent.name}/{path.name}"


# --- Documented money-drop budgets (feedback_validate_against_hard_fixture) ------
# over-count is never tolerated ANYWHERE (a tree double-count is always a bug) and
# holds == 0 corpus-wide; these budgets bound only DROPS. A version not listed must
# conserve EXACTLY (drop == 0). Listed versions carry a documented residue equal to
# the observed drop, so any future regression that drops MORE trips the gate.
#
# The drops are PRE-EXISTING parser body-coverage residue, NOT introduced by the
# tree: own_amounts come from each node's display_text, so a drop is an amount the
# parser never placed in a node — the same gap test_every_dollar_amount_appears_in_a_
# node already tolerates at its 0.80 floor. The shapes are the hard ones the plan's
# 0009 posture flags: engrossed/enrolled amendment docs, multi-division omnibus, and
# the 119-hr-1 reconciliation bill (not an appropriations bill; in the corpus only as
# an overfitting smoke test). Chasing them is the financial-semantics epic (#147), not
# #108 — #108's job is conservation (no double-count) + documented residue.

# XML: union(own_amounts) vs the INDEPENDENT raw-XML body (the strong gate).
# Calibrated against the FULL local corpus (every fetched version, not just the
# committed-reproducible subset); a clean clone simply won't reach the absent entries.
# Note the shape: the product's actual diff targets — reported / engrossed / introduced
# working versions — conserve EXACTLY (none listed); residue lives only in the
# secondary enrolled / engrossed-amendment / reconciliation shapes.
_XML_DROP_BUDGET: dict[str, int] = {
    # Amendment docs — deeply nested clause edges (0009 amendment-shape posture).
    "113-hr-83/6_engrossed-amendment-house.xml": 4,
    "113-hr-83/7_enrolled-bill.xml": 4,
    "113-hr-3547/5_engrossed-amendment-house.xml": 1,
    "114-hr-2029/5_engrossed-amendment-senate.xml": 3,
    "114-hr-2029/6_engrossed-amendment-house.xml": 4,
    "116-hr-1865/5_engrossed-amendment-house.xml": 17,
    "116-hr-133/6_engrossed-amendment-house.xml": 21,
    # Enrolled multi-division omnibus — cross-division residue + amendment carryover.
    "113-hr-3547/6_enrolled-bill.xml": 1,
    "114-hr-2029/7_enrolled-bill.xml": 4,
    "115-hr-244/6_enrolled-bill.xml": 4,
    "115-hr-1625/7_enrolled-bill.xml": 16,
    "116-hr-133/7_enrolled-bill.xml": 21,
    "116-hr-1865/6_enrolled-bill.xml": 17,
    "117-hr-2471/6_enrolled-bill.xml": 20,
    # 119-hr-1 reconciliation (not appropriations; corpus smoke bill) — amounts in
    # provision body text the appropriations-focused parser doesn't node-ize.
    "119-hr-1/1_reported-in-house.xml": 15,
    "119-hr-1/2_engrossed-in-house.xml": 15,
    "119-hr-1/3_placed-on-calendar-senate.xml": 15,
}

# PDF: union(own_amounts) vs the rendered full_text (the carve-out reference — PDF
# has no independent ground truth). A normal bill's only structurally-allowed drop is
# $ before the first anchor (front matter), so the budget is 0 for all of them, INCL.
# every other omnibus PDF (they conserve exactly). The one exception:
_PDF_DROP_BUDGET: dict[str, int] = {}

# 116-hr-133 enrolled is the ~5,500-page COVID omnibus; its PDF anchor/offset
# extraction is severely degraded (a mis-detected `PANDEMIC.—` body line anchors a
# multi-megabyte block; most anchors' (page, line) don't resolve into the offset
# table, leaving empty blocks). over==0 still holds (no double-count), but the
# partition covers little of full_text, so the money gate is meaningless here. This is
# the known PDF-omnibus degradation (anchors degrade, they don't gate); the structural
# invariants (schema, levels, no-blank-TOC) still run. Excluded from the money gate
# only, with this reason, rather than carrying a meaningless ~3,500 budget.
_PDF_MONEY_SKIP: set[str] = {"116-hr-133/7_enrolled-bill.pdf"}


# --- Subtree-extent overlap budgets (invariant 5) ------------------------------
# A node's SUBTREE EXTENT is (min start, max end) over its own span and all
# descendants' — the quantity #172's span-containment join will use ("deepest node
# whose extent contains the change start"). For that join to be deterministic,
# sibling extents must be pairwise DISJOINT and document-ordered; a change that lands
# in two overlapping sibling extents has to escalate to their common ancestor.
#
# The corpus does NOT uphold sibling disjointness by construction, and this gate
# measures how far off it is. Mechanism (the fresh-eyes prediction on #172, confirmed
# here): the tree nests every item sharing a path prefix under the FIRST occurrence's
# node, while the serializer / anchor stream revisit that prefix in document order — so
# a parent's subtree extent stretches across intervening siblings. Two concrete shapes:
#   - XML: a repeated account heading yields two sibling nodes with the same label, the
#     later one's small extent nested inside the earlier one's wide extent (e.g. two
#     "Legal Activities" under Dept. of Justice); or a genuinely different agency whose
#     subtree extent swallows the next sibling (Architect of the Capitol over Library of
#     Congress).
#   - PDF: a division whose title anchors arrive out of numeric order (TITLE IV before
#     TITLE I), or root-level title extents that overlap on a degraded omnibus scan.
#
# This is a DESIGN INPUT to #172, not a test bug: the escalation-to-common-ancestor
# rule is load-bearing, not a rare edge. The budgets below LOCK IN the current overlap
# counts (calibrated on the FULL local corpus, every fetched version — a clean clone
# won't reach the absent entries) so a parser change that INCREASES structural overlap
# trips the gate. A version not listed must have ZERO sibling-extent overlaps. The
# CONTAINMENT half of the invariant (content child inside parent extent) holds EXACTLY
# corpus-wide (0 violations, both pipelines) and is asserted strictly, no budget.
#
# Overlaps concentrate in enrolled / engrossed-amendment / reconciliation shapes but
# are present in some working reported / engrossed-in-house versions too, so this is a
# general structural property of the tree, not a secondary-shape artifact.
_XML_EXTENT_OVERLAP_BUDGET: dict[str, int] = {
    "113-hr-3547/5_engrossed-amendment-house.xml": 18,
    "113-hr-3547/6_enrolled-bill.xml": 18,
    "113-hr-83/6_engrossed-amendment-house.xml": 19,
    "113-hr-83/7_enrolled-bill.xml": 19,
    "114-hr-2029/6_engrossed-amendment-house.xml": 26,
    "114-hr-2029/7_enrolled-bill.xml": 26,
    "115-hr-1625/7_enrolled-bill.xml": 20,
    "115-hr-244/6_enrolled-bill.xml": 19,
    "115-hr-5895/4_engrossed-amendment-senate.xml": 2,
    "115-hr-5895/5_enrolled-bill.xml": 1,
    "116-hr-1865/5_engrossed-amendment-house.xml": 14,
    "116-hr-1865/6_enrolled-bill.xml": 14,
    "117-hr-2471/6_enrolled-bill.xml": 1,
    "117-hr-4502/1_reported-in-house.xml": 1,
    "117-hr-4502/2_engrossed-in-house.xml": 8,
    "117-hr-4502/3_received-in-senate.xml": 8,
    "118-hr-4366/4_engrossed-amendment-senate.xml": 3,
    "118-hr-4366/5_engrossed-amendment-house.xml": 3,
    "118-hr-4366/6_enrolled-bill.xml": 3,
    "118-hr-4820/1_reported-in-house.xml": 3,
    "118-s-4796/1_reported-in-senate.xml": 3,
    "118-s-4927/1_reported-in-senate.xml": 1,
}

_PDF_EXTENT_OVERLAP_BUDGET: dict[str, int] = {
    "114-hr-2029/4_reported-to-senate.pdf": 4,
    "114-hr-2029/6_engrossed-amendment-house.pdf": 2,
    "115-hr-244/5_engrossed-amendment-house.pdf": 1,
    "116-hr-133/6_engrossed-amendment-house.pdf": 2,
    "117-hr-2471/5_engrossed-amendment-house.pdf": 1,
    "119-hr-1/1_reported-in-house.pdf": 1,
}


def _xml_tree_payload_for(path: Path) -> tuple[list[dict], str]:
    """The contract-shaped XML tree for one version, plus its full_text — built the
    way ``build_xml_full_text`` does, without the diff (the tree is per-side)."""
    bill = normalize_bill(path)
    text, _sections, spans, heading_offsets = serialize_tree_for_tree(bill)
    return _xml_tree_payload(bill, spans, heading_offsets), text


def _pdf_tree_payload_for(path: Path) -> tuple[list[dict], str]:
    """The contract-shaped PDF tree for one version, plus its full_text — built the
    way the shipped canonical does. Uses ``pdf_full_text`` (the merged whole-word
    variant), NOT ``pdf_full_text_print``: ``compare_pdfs`` builds the contract tree
    from the non-print text (``_build_canonical(printed=False)``); the print variant
    is display-only, and a dollar amount broken across a printed line would extract
    differently there — so the print variant would measure a tree the consumer never
    sees (feedback_measure_at_consumed_output)."""
    pages = cached_pages(path)
    full_text, offsets = pdf_full_text(pages)
    anchors = tuple(extract_anchors(pages))
    return _pdf_tree_payload(anchors, offsets, full_text), full_text


def _walk(nodes: list[dict]):
    for n in nodes:
        yield n
        yield from _walk(n["children"])


def _raw_xml_body_amounts(path: Path) -> Counter:
    """Independent reference: amounts in the raw XML body, parsed directly (NOT via
    the tree's nodes) so the gate can't tautologically pass over dropped money."""
    body = find_bill_body(ET.parse(path).getroot())
    return Counter(extract_amounts(extract_text_content(body)))


def _assert_schema_and_levels(roots: list[dict]) -> None:
    """Invariants 1 + 2: every node validates against the published TreeNode def
    and carries a level in the shared enum."""
    nodes = list(_walk(roots))
    # Invariant 2 first (unconditional, clear message even without jsonschema).
    for n in nodes:
        assert n["level"] in _LEVELS, f"node {n['label']!r} has level {n['level']!r} not in the GPO enum"
    # Invariant 1: schema-validate each root against the TreeNode $def.
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_SCHEMA_PATH.read_text())
    node_schema = {"$ref": "#/$defs/TreeNode", "$defs": schema["$defs"]}
    for r in roots:
        jsonschema.validate(r, node_schema)


def _assert_no_blank_toc_rows(roots: list[dict], full_text: str) -> None:
    """Invariant 4: the leveled TOC the tree renders has no blank clickable rows
    and no empty collapsible groups (the consumed-output blank-row check)."""
    html = _build_toc_from_tree(roots, full_text)
    leaves = re.findall(r'<li class="toc-child">(.*?)</li>', html, re.S)
    blank_leaves = [leaf for leaf in leaves if not re.sub(r"<[^>]+>", "", leaf).strip()]
    assert not blank_leaves, f"{len(blank_leaves)} blank TOC leaf row(s)"
    summaries = re.findall(r"<summary>(.*?)</summary>", html, re.S)
    blank_groups = [s for s in summaries if not re.sub(r"<[^>]+>", "", s).strip()]
    assert not blank_groups, f"{len(blank_groups)} blank TOC group heading(s)"
    # Completeness floor: the renderer DROPS unlabeled leaves and HOISTS the children
    # of unlabeled groups, so wholesale label loss would yield an empty TOC with no
    # blank rows — passing the checks above while rendering nothing. If the tree
    # carries any labeled node, the TOC must render at least one entry.
    if any((n["label"] or "").strip() for n in _walk(roots)):
        assert "toc-child" in html or "toc-group" in html, "labeled tree rendered an empty TOC"


def _assert_money_conserves(roots: list[dict], reference: Counter, max_drop: int, label: str) -> None:
    """Invariant 3: union(own_amounts) never over-counts; drops within budget."""
    union: Counter = Counter()
    for n in _walk(roots):
        union.update(n["own_amounts"])
    over = sum((union - reference).values())
    dropped = sum((reference - union).values())
    assert over == 0, f"{label}: tree over-counts {over} amount(s) — double-count"
    assert dropped <= max_drop, f"{label}: dropped {dropped} > documented budget {max_drop}"


# --- Subtree extents (invariant 5) ---------------------------------------------


def _span_valid(span: dict | None) -> bool:
    """A span contributes to an extent only if it is present and non-empty. Extents are
    half-open ``[start, end)``; a null or zero-length span matches nothing (mirrors the
    collision / non-monotonic guards in ``formatters/canonical.py``)."""
    return span is not None and span["end"] > span["start"]


def _subtree_extent(node: dict) -> tuple[int, int] | None:
    """The (min start, max end) over the node's own valid span and every descendant's —
    the quantity #172's join will use. ``None`` when nothing in the subtree has a valid
    span. This is the *reference* implementation of the extent the join must compute;
    the gate asserts extents built this way are well-behaved."""
    lo = hi = None
    span = node["full_text_span"]
    if _span_valid(span):
        lo, hi = span["start"], span["end"]
    for child in node["children"]:
        ext = _subtree_extent(child)
        if ext is None:
            continue
        lo = ext[0] if lo is None else min(lo, ext[0])
        hi = ext[1] if hi is None else max(hi, ext[1])
    return None if lo is None else (lo, hi)


def _span_within_extent(extent: tuple[int, int] | None, span: dict | None) -> bool:
    """Whether a (valid) span lies inside an extent, half-open. A null extent or an
    invalid/zero-length span vacuously satisfies (nothing to contain / matches nothing).

    NOTE: under ``_subtree_extent`` a content child's own span is ALWAYS within its
    parent's extent (the extent folds the child in), so the containment check below
    never trips on any tree the current extent function produces — it is an executable
    spec of the precondition #172's own extent code must satisfy, and a guard against a
    future change to the extent definition. The FALSIFIABLE half of invariant 5 (the one
    that actually trips on the corpus) is sibling disjointness. This predicate is factored
    out so its detection logic is unit-testable independent of that construction fact."""
    if extent is None or not _span_valid(span):
        return True
    return extent[0] <= span["start"] and span["end"] <= extent[1]


def _extent_violations(roots: list[dict]) -> tuple[list[str], list[str], int, int]:
    """Walk the tree and collect invariant-5 violations.

    Returns ``(sibling_overlaps, containment_violations, interior_nodes, sibling_cmps)``.
    A *sibling overlap* is a consecutive pair of siblings (in document / child order,
    the order the join descends) whose extents are not disjoint-and-increasing
    (``prev.end <= next.start``, half-open — touching is allowed). Consecutive checking
    is sufficient: if every consecutive pair is ordered-disjoint, all pairs are. A
    *containment violation* is a content child whose own valid span falls outside its
    parent's extent. ``interior_nodes`` / ``sibling_cmps`` feed the completeness floor.
    """
    overlaps: list[str] = []
    containment: list[str] = []
    interior = 0
    sibling_cmps = 0

    def visit(siblings: list[dict], parent_label: str) -> None:
        nonlocal interior, sibling_cmps
        # Sibling disjointness + document order, over siblings with a real extent.
        real = [(n, ext) for n in siblings if (ext := _subtree_extent(n)) is not None]
        for (a, ea), (b, eb) in zip(real, real[1:]):
            sibling_cmps += 1
            if not (ea[1] <= eb[0]):
                overlaps.append(
                    f"under {parent_label!r}: {a['label']!r} extent {ea} then "
                    f"{b['label']!r} extent {eb} (not disjoint/ordered)"
                )
        for node in siblings:
            if not node["children"]:
                continue
            interior += 1
            parent_ext = _subtree_extent(node)
            for child in node["children"]:
                span = child["full_text_span"]
                if not _span_within_extent(parent_ext, span):
                    containment.append(
                        f"child {child['label']!r} span "
                        f"[{span['start']}, {span['end']}) outside parent "
                        f"{node['label']!r} extent {parent_ext}"
                    )
            visit(node["children"], node["label"])

    visit(roots, "<roots>")
    return overlaps, containment, interior, sibling_cmps


def _assert_subtree_extents_well_behaved(roots: list[dict], max_overlaps: int, label: str) -> int:
    """Invariant 5. CONTAINMENT is strict (0 corpus-wide); sibling DISJOINTNESS is
    bounded by the documented per-bill overlap budget — a version not in the registry
    must have zero overlaps, and a regression that adds structural overlap trips here.
    Returns the interior-node count so the caller can feed the completeness floor."""
    overlaps, containment, interior, _cmps = _extent_violations(roots)
    assert not containment, (
        f"{label}: {len(containment)} content child span(s) outside the parent's subtree "
        f"extent (invariant 5 containment is strict): {containment[:3]}"
    )
    assert len(overlaps) <= max_overlaps, (
        f"{label}: {len(overlaps)} sibling-extent overlap(s) > documented budget "
        f"{max_overlaps}. Overlaps are a known design input to #172 (escalate to the "
        f"common ancestor); a NEW one means the parser deepened the interleaving — "
        f"investigate before widening the budget. Samples: {overlaps[:3]}"
    )
    return interior


def test_corpus_present_when_required() -> None:
    """Fail-loud completeness floor for the tree property gates (#167).

    The XML and PDF invariant gates parametrize over ALL_XML_FILES / ALL_PDF_FILES; an
    unfetched checkout makes those empty and the suite passes green. In REQUIRE_CORPUS
    mode this asserts the pinned XML baselines are present and both parametrizations
    discovered at least one case.
    """
    require_corpus_or_skip(ALL_XML_FILES, "tree-properties (XML)")
    require_corpus_or_skip(ALL_PDF_FILES, "tree-properties (PDF)")


def test_extent_gate_runs_on_interior_nodes() -> None:
    """Completeness floor for invariant 5 (the #167 fail-open pattern).

    The overlap budgets and the containment assertion only bite when the tree has
    interior (parent) nodes with siblings — a corpus of flat shells, or an extent walker
    that silently visited nothing, would pass invariant 5 vacuously. Outside
    REQUIRE_CORPUS this skips (clean-clone). In REQUIRE_CORPUS mode it asserts the gate
    machinery actually exercises interior nodes AND sibling comparisons on real
    structure, on BOTH pipelines, so a green run proves the invariant ran. It builds the
    trees independently of the parametrized cases, so it holds even run in isolation.
    """
    require_corpus_or_skip(ALL_XML_FILES, "extent gate (XML)")
    require_corpus_or_skip(ALL_PDF_FILES, "extent gate (PDF)")

    # XML: a pinned, structurally-rich baseline (guaranteed present in REQUIRE_CORPUS).
    xml_roots, _ = _xml_tree_payload_for(BILLS_DIR / "118-hr-4366" / "1_reported-in-house.xml")
    _overlaps, _containment, xml_interior, xml_cmps = _extent_violations(xml_roots)
    assert xml_interior > 0 and xml_cmps > 0, (
        "extent gate visited no XML interior nodes / sibling pairs — invariant 5 would pass vacuously"
    )

    # PDF: not in the pinned baseline, so scan discovered files for structure and assert
    # at least one case exercises the walk (accumulate until both counts are positive).
    pdf_interior = pdf_cmps = 0
    for pdf_path in ALL_PDF_FILES:
        roots, _ = _pdf_tree_payload_for(pdf_path)
        if not roots:
            continue
        _o, _c, interior, cmps = _extent_violations(roots)
        pdf_interior += interior
        pdf_cmps += cmps
        if pdf_interior and pdf_cmps:
            break
    assert pdf_interior > 0 and pdf_cmps > 0, (
        "extent gate visited no PDF interior nodes / sibling pairs — invariant 5 would pass vacuously"
    )


# --- XML corpus ----------------------------------------------------------------


@pytest.mark.parametrize("xml_path", ALL_XML_FILES, ids=[_corpus_id(p) for p in ALL_XML_FILES])
def test_xml_tree_invariants_hold_corpus_wide(xml_path: Path) -> None:
    test_id = _corpus_id(xml_path)
    try:
        roots, full_text = _xml_tree_payload_for(xml_path)
    except ValueError:
        pytest.skip("no bill body found")
    if not roots:
        pytest.skip("no nodes parsed")

    _assert_schema_and_levels(roots)
    _assert_no_blank_toc_rows(roots, full_text)
    # Strong gate: against the INDEPENDENT raw-XML body, not the derived full_text.
    # Asserted unconditionally (even on a no-amount shell, where over==0 / drop==0
    # both hold) so a spurious over-count on an empty body can't slip through.
    reference = _raw_xml_body_amounts(xml_path)
    _assert_money_conserves(roots, reference, _XML_DROP_BUDGET.get(test_id, 0), test_id)
    # Invariant 5: subtree extents well-behaved (the #172 join prerequisite).
    _assert_subtree_extents_well_behaved(roots, _XML_EXTENT_OVERLAP_BUDGET.get(test_id, 0), test_id)


# --- PDF corpus ----------------------------------------------------------------


@pytest.mark.parametrize("pdf_path", ALL_PDF_FILES, ids=[_corpus_id(p) for p in ALL_PDF_FILES])
def test_pdf_tree_invariants_hold_corpus_wide(pdf_path: Path) -> None:
    test_id = _corpus_id(pdf_path)
    roots, full_text = _pdf_tree_payload_for(pdf_path)
    if not roots:
        pytest.skip("no anchors / no offset table")

    _assert_schema_and_levels(roots)
    _assert_no_blank_toc_rows(roots, full_text)
    # Invariant 5: subtree extents well-behaved (the #172 join prerequisite). Runs even
    # on the money-skip bill below — extent geometry is independent of amount coverage.
    _assert_subtree_extents_well_behaved(roots, _PDF_EXTENT_OVERLAP_BUDGET.get(test_id, 0), test_id)
    # Carve-out: PDF has no independent ground truth, so it measures against its own
    # rendered full_text (a labeled span-coverage check, weaker by construction).
    if test_id in _PDF_MONEY_SKIP:
        return  # known degraded extraction — see _PDF_MONEY_SKIP for the reason
    reference = Counter(extract_amounts(full_text))
    _assert_money_conserves(roots, reference, _PDF_DROP_BUDGET.get(test_id, 0), test_id)
