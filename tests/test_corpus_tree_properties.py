"""Corpus-wide property gate for the leveled structure tree (#108, step 5).

The per-fixture gates in ``test_structure_tree.py`` and ``test_canonical_tree.py``
prove the tree's invariants on a handful of hand-picked bills. This module
parametrizes the SAME invariants over every parseable bill version in the corpus,
so a parser change that breaks one of them on an un-pinned bill trips here instead
of in production. It asserts on the **contract-shaped tree** (the canonical JSON
nodes both pipelines emit), not an internal ``TreeNode`` dump — the consumed output
(``feedback_measure_at_consumed_output``).

Four invariants per bill version:

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
_XML_DROP_BUDGET: dict[str, int] = {
    # Amendment docs — deeply nested clause edges (0009 amendment-shape posture).
    "113-hr-83/6_engrossed-amendment-house.xml": 4,
    "113-hr-83/7_enrolled-bill.xml": 4,
    "114-hr-2029/5_engrossed-amendment-senate.xml": 3,
    "114-hr-2029/6_engrossed-amendment-house.xml": 4,
    "116-hr-1865/5_engrossed-amendment-house.xml": 17,
    "116-hr-133/6_engrossed-amendment-house.xml": 21,
    # Enrolled multi-division omnibus — cross-division residue + amendment carryover.
    "113-hr-3547/6_enrolled-bill.xml": 1,
    "114-hr-2029/7_enrolled-bill.xml": 4,
    "115-hr-1625/7_enrolled-bill.xml": 16,
    "116-hr-133/7_enrolled-bill.xml": 21,
    "116-hr-1865/6_enrolled-bill.xml": 17,
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


# --- PDF corpus ----------------------------------------------------------------


@pytest.mark.parametrize("pdf_path", ALL_PDF_FILES, ids=[_corpus_id(p) for p in ALL_PDF_FILES])
def test_pdf_tree_invariants_hold_corpus_wide(pdf_path: Path) -> None:
    test_id = _corpus_id(pdf_path)
    roots, full_text = _pdf_tree_payload_for(pdf_path)
    if not roots:
        pytest.skip("no anchors / no offset table")

    _assert_schema_and_levels(roots)
    _assert_no_blank_toc_rows(roots, full_text)
    # Carve-out: PDF has no independent ground truth, so it measures against its own
    # rendered full_text (a labeled span-coverage check, weaker by construction).
    if test_id in _PDF_MONEY_SKIP:
        return  # known degraded extraction — see _PDF_MONEY_SKIP for the reason
    reference = Counter(extract_amounts(full_text))
    _assert_money_conserves(roots, reference, _PDF_DROP_BUDGET.get(test_id, 0), test_id)
