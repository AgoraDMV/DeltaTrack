"""Unit-level proof that the corpus subtree-extent gate (invariant 5, #177) fires.

The corpus gate in ``test_corpus_tree_properties`` parametrizes over real bills; a gate
that has never been observed RED proves nothing. These synthetic-tree tests exercise the
extent math and the assertion directly, with no corpus dependency (so they run in the
fast suite, not just under ``-m slow``). They pin the extent computation and demonstrate
that the FALSIFIABLE half of invariant 5 — sibling-extent disjointness — actually trips.

Containment (a content child inside its parent's extent) holds by construction of
``_subtree_extent`` and cannot be tripped by any tree; only its detection predicate is
unit-testable, which is what ``test_containment_predicate_*`` do. See the invariant-5
docstring and ``_span_within_extent`` in ``test_corpus_tree_properties`` for why.
"""

from __future__ import annotations

import pytest

from tests.test_corpus_tree_properties import (
    _assert_subtree_extents_well_behaved,
    _extent_violations,
    _span_within_extent,
    _subtree_extent,
)


def node(label: str, span: tuple[int, int] | None, children: list[dict] | None = None) -> dict:
    """A contract-shaped tree node. ``span`` is ``(start, end)`` or ``None``."""
    return {
        "label": label,
        "level": "section",
        "own_amounts": [],
        "full_text_span": None if span is None else {"start": span[0], "end": span[1]},
        "children": children or [],
    }


# --- extent computation --------------------------------------------------------


def test_subtree_extent_is_min_max_over_descendants() -> None:
    tree = node("parent", (10, 20), [node("a", (30, 40)), node("b", (5, 8))])
    # min start over {10, 30, 5} = 5; max end over {20, 40, 8} = 40.
    assert _subtree_extent(tree) == (5, 40)


def test_extent_ignores_null_and_zero_length_spans() -> None:
    # Parent own span null; one child zero-length (matches nothing), one valid.
    tree = node("parent", None, [node("zero", (50, 50)), node("real", (12, 18))])
    assert _subtree_extent(tree) == (12, 18)
    # A subtree with no valid span anywhere has no extent.
    assert _subtree_extent(node("empty", None, [node("z", (7, 7))])) is None


# --- sibling disjointness: the falsifiable gate --------------------------------


def _title(label: str, span: tuple[int, int], kids: list[tuple[int, int]]) -> dict:
    return node(label, span, [node(f"{label}.{i}", k) for i, k in enumerate(kids)])


def test_well_behaved_tree_passes() -> None:
    roots = [
        _title("I", (0, 5), [(10, 20), (20, 30)]),
        _title("II", (40, 45), [(50, 60)]),
    ]
    overlaps, containment, interior, cmps = _extent_violations(roots)
    assert overlaps == [] and containment == []
    assert interior == 2 and cmps > 0
    # Budget 0: a clean tree must not raise.
    _assert_subtree_extents_well_behaved(roots, 0, "clean")


def test_touching_extents_are_disjoint_half_open() -> None:
    # I ends exactly where II begins — half-open [start, end) means no overlap.
    roots = [node("I", (0, 30)), node("II", (30, 60))]
    overlaps, _c, _i, _cmp = _extent_violations(roots)
    assert overlaps == []


def test_nested_sibling_extent_trips_the_gate() -> None:
    # Sibling II's extent (12, 18) sits INSIDE sibling I's extent (0, 40) — the
    # duplicate-heading / prefix-revisit shape the corpus exhibits.
    roots = [node("I", (0, 40)), node("II", (12, 18))]
    overlaps, _c, _i, _cmp = _extent_violations(roots)
    assert len(overlaps) == 1
    with pytest.raises(AssertionError, match="sibling-extent overlap"):
        _assert_subtree_extents_well_behaved(roots, 0, "nested")
    # Within budget: the same overlap is tolerated when documented.
    _assert_subtree_extents_well_behaved(roots, 1, "nested-budgeted")


def test_misordered_siblings_trip_the_gate() -> None:
    # Document order II-before-I but extents run backwards (I starts after II) — the
    # PDF "TITLE IV before TITLE I" shape. Not disjoint-and-increasing → violation.
    roots = [node("II", (200, 300)), node("I", (0, 100))]
    overlaps, _c, _i, _cmp = _extent_violations(roots)
    assert len(overlaps) == 1
    with pytest.raises(AssertionError, match="sibling-extent overlap"):
        _assert_subtree_extents_well_behaved(roots, 0, "misordered")


def test_overlap_over_budget_trips_even_when_budget_positive() -> None:
    # Two overlaps but a budget of 1 → still red (a regression that ADDS overlap trips).
    roots = [node("I", (0, 40)), node("II", (12, 18)), node("III", (10, 15))]
    overlaps, _c, _i, _cmp = _extent_violations(roots)
    assert len(overlaps) >= 2
    with pytest.raises(AssertionError, match="> documented budget"):
        _assert_subtree_extents_well_behaved(roots, 1, "over-budget")


# --- containment predicate (detection logic only; see module docstring) --------


def test_containment_predicate_flags_out_of_extent_span() -> None:
    assert _span_within_extent((0, 100), {"start": 10, "end": 20}) is True
    assert _span_within_extent((0, 100), {"start": 90, "end": 120}) is False  # end past extent
    assert _span_within_extent((50, 100), {"start": 10, "end": 60}) is False  # start before extent


def test_containment_predicate_vacuous_on_null_or_zero_length() -> None:
    assert _span_within_extent(None, {"start": 10, "end": 20}) is True
    assert _span_within_extent((0, 100), None) is True
    assert _span_within_extent((0, 100), {"start": 5, "end": 5}) is True  # zero-length matches nothing


def test_containment_holds_on_any_min_max_tree() -> None:
    # By construction of _subtree_extent, a child's own span is always within the
    # parent's extent — no synthetic tree can trip the containment half.
    tree = [node("p", (10, 12), [node("c1", (0, 5)), node("c2", (100, 200))])]
    _overlaps, containment, _i, _cmp = _extent_violations(tree)
    assert containment == []
