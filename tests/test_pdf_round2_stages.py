"""Slice 4: PDF round 2 as four stages, running before classification.

The extraction this module guards moved round 2 off the classified hunk stream.
Pre-slice-4, ``diff_pdfs`` built classified ``PdfHunk``s and then handed them to
``_reconcile_moves``, which filtered them on ``change_type`` to decide which pairs were even
considered for a move. That is the ADR 0020 violation: a change to what classification emitted
could silently change what matching considered.

**The oracle is the whole legacy pipeline, transcribed here.** Not a spot check of the new
stages against themselves, and not a call into ``_align_blocks``: ``legacy_diff`` below rebuilds
the pre-slice-4 ``diff_pdfs`` from the parser output — its own opcode walk, its own split rule,
its own emit order — and finishes with ``_reconcile_moves``, which slice 4 deliberately left in
place for exactly this purpose. If the extraction changed which pairs correspond, or where a
record lands, these comparisons say so.

Two things are compared, because they can fail apart:

``test_the_staged_path_reproduces_the_legacy_hunk_stream``
    the whole output, hunk for hunk, over every adjacent committed pair.
``test_the_population_projection_matches_the_legacy_filtered_hunk_lists``
    the round-2 population specifically. The output could agree while the population was
    derived differently and happened to select the same links; this pins the projection ADR
    0020 actually cares about.

The record's §7.4 note — that PDF's move records land where the removal was, rather than
appended as in XML — is why ``PdfSettledCorrespondence`` carries a slot. That ordering is
covered by the hunk-stream comparison rather than asserted separately.
"""

from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from deltatrack import diff_pdf
from deltatrack.diff_pdf import (
    PdfHunk,
    _align_blocks,
    _AlignedPairing,
    _block_key,
    _hunk_for_added,
    _hunk_for_paired_blocks,
    _hunk_for_removed,
    _reconcile_moves,
    assign_pdf_moves,
    classify_pdf,
    diff_pdfs,
    pdf_move_evidence,
    pdf_unmatched_population,
    retrieve_pdf_move_candidates,
    settle_pdf_correspondences,
)
from deltatrack.matching import NEW, OLD, ObservationRef
from deltatrack.parsers.pdf_anchors import extract_anchors
from deltatrack.parsers.pdf_blocks import _Block, _flatten, _group_into_blocks, _IndexedLine
from deltatrack.pdf_observations import PdfObservationRegistry
from deltatrack.similarity import MOVE_THRESHOLD, SIMILARITY_THRESHOLD, text_similarity_at_least
from tests.pdf_corpus import adjacent_pdf_pairs, cached_pages

_PAIRS = adjacent_pdf_pairs()
_PAIR_IDS = [f"{bill}:{old.stem}->{new.stem}" for bill, old, new in _PAIRS]


# --- The oracle: the pre-slice-4 pipeline, transcribed -------------------------------------


def legacy_emit_pair(v1_b: _Block, v2_b: _Block, sink: list[PdfHunk]) -> None:
    """The pre-slice-4 ``_emit_pair``, appending classified hunks as it did then.

    Transcribed from the commit before slice 4, not imported. Production's version now appends
    pairings, so there is nothing left to import that would answer this question honestly.
    """
    if v1_b.text == v2_b.text:
        if v1_b.anchor and v2_b.anchor and v1_b.anchor.text != v2_b.anchor.text:
            sink.append(_hunk_for_paired_blocks(v1_b, v2_b, similarity=1.0))
        return
    sim = text_similarity_at_least(v1_b.text, v2_b.text, SIMILARITY_THRESHOLD)
    if sim < SIMILARITY_THRESHOLD:
        sink.append(_hunk_for_removed(v1_b))
        sink.append(_hunk_for_added(v2_b))
    else:
        sink.append(_hunk_for_paired_blocks(v1_b, v2_b, similarity=sim))


def legacy_hunks_before_round2(v1_blocks: list[_Block], v2_blocks: list[_Block]) -> list[PdfHunk]:
    """The pre-slice-4 classified hunk stream, before ``_reconcile_moves`` ran on it."""
    matcher = difflib.SequenceMatcher(
        a=[_block_key(b) for b in v1_blocks],
        b=[_block_key(b) for b in v2_blocks],
        autojunk=False,
    )
    hunks: list[PdfHunk] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for v1_b, v2_b in zip(v1_blocks[i1:i2], v2_blocks[j1:j2]):
                legacy_emit_pair(v1_b, v2_b, hunks)
        elif op == "delete":
            for v1_b in v1_blocks[i1:i2]:
                hunks.append(_hunk_for_removed(v1_b))
        elif op == "insert":
            for v2_b in v2_blocks[j1:j2]:
                hunks.append(_hunk_for_added(v2_b))
        else:
            v1_slice, v2_slice = v1_blocks[i1:i2], v2_blocks[j1:j2]
            for k in range(max(len(v1_slice), len(v2_slice))):
                v1_b = v1_slice[k] if k < len(v1_slice) else None
                v2_b = v2_slice[k] if k < len(v2_slice) else None
                if v1_b is not None and v2_b is not None:
                    legacy_emit_pair(v1_b, v2_b, hunks)
                elif v1_b is not None:
                    hunks.append(_hunk_for_removed(v1_b))
                else:
                    assert v2_b is not None
                    hunks.append(_hunk_for_added(v2_b))
    return hunks


def blocks_for(pdf: Path) -> list[_Block]:
    pages = cached_pages(pdf)
    return _group_into_blocks(_flatten(pages), extract_anchors(pages))


def legacy_hunks(old_pdf: Path, new_pdf: Path) -> list[PdfHunk]:
    """The pre-slice-4 pipeline end to end: classify, then reconcile moves on the records."""
    hunks = legacy_hunks_before_round2(blocks_for(old_pdf), blocks_for(new_pdf))
    return _reconcile_moves(hunks)


def test_the_corpus_pair_list_is_not_empty() -> None:
    """A parametrization list that silently empties is the fail-open shape (#542)."""
    assert len(_PAIRS) >= 20, f"only {len(_PAIRS)} adjacent PDF pairs discovered; the corpus holds more"


# --- Behaviour preservation over the corpus -----------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize(("bill", "old_pdf", "new_pdf"), _PAIRS, ids=_PAIR_IDS)
def test_the_staged_path_reproduces_the_legacy_hunk_stream(bill: str, old_pdf: Path, new_pdf: Path) -> None:
    """Every hunk, in order, identical to what the pre-slice-4 pipeline produced.

    Broader than the canonical baseline, deliberately: this runs on **every** adjacent pair
    including the six ``compare.pdf`` declines, which the baseline cannot cover because no user
    reaches them. A move-selection change confined to a declined pair would be invisible there.
    """
    assert list(diff_pdfs(cached_pages(old_pdf), cached_pages(new_pdf)).hunks) == legacy_hunks(old_pdf, new_pdf)


@pytest.mark.slow
@pytest.mark.parametrize(("bill", "old_pdf", "new_pdf"), _PAIRS, ids=_PAIR_IDS)
def test_the_population_projection_matches_the_legacy_filtered_hunk_lists(
    bill: str, old_pdf: Path, new_pdf: Path
) -> None:
    """Round 2's population, and its ``(ri, ai)`` order, derived without classification.

    The output could agree while the population was built differently and happened to select
    the same links, so this compares the population itself: the texts production's retriever
    receives, in the order it receives them, against the texts the legacy filter produced from
    the classified stream.

    That equality is the whole claim of ``pdf_unmatched_population``. Measured rather than
    argued, because the argument — "``_hunk_for_removed`` is the only producer of a ``removed``
    hunk" — is a statement about code that a later edit could quietly falsify.
    """
    old_blocks, new_blocks = blocks_for(old_pdf), blocks_for(new_pdf)
    legacy = legacy_hunks_before_round2(old_blocks, new_blocks)
    legacy_removed = [h.v1_text for h in legacy if h.change_type == "removed"]
    legacy_added = [h.v2_text for h in legacy if h.change_type == "added"]

    registry = PdfObservationRegistry(old_blocks, new_blocks)
    population = pdf_unmatched_population(_align_blocks(old_blocks, new_blocks), registry)

    assert [o.block.text for o in population.old] == legacy_removed
    assert [o.block.text for o in population.new] == legacy_added


@pytest.mark.slow
@pytest.mark.parametrize(("bill", "old_pdf", "new_pdf"), _PAIRS, ids=_PAIR_IDS)
def test_round_2_addresses_the_complete_parser_sequence(bill: str, old_pdf: Path, new_pdf: Path) -> None:
    """Every address entering round 2 is a complete-sequence ordinal, not a population index.

    ADR 0019's hazard, at the one place slice 4 creates new addresses. A population position is
    a different number that looks just as valid, and on a real bill the two diverge immediately
    because the first observation is rarely unmatched.
    """
    old_blocks, new_blocks = blocks_for(old_pdf), blocks_for(new_pdf)
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    population = pdf_unmatched_population(_align_blocks(old_blocks, new_blocks), registry)

    for side, observations, blocks in ((OLD, population.old, old_blocks), (NEW, population.new, new_blocks)):
        for observation in observations:
            assert observation.ref.side == side
            assert registry.block(observation.ref) is observation.block
            assert blocks[observation.ref.ordinal] is observation.block


@pytest.mark.slow
def test_the_corpus_actually_exercises_round_2() -> None:
    """Floor. The three sweeps above would agree vacuously on a corpus with no moves at all.

    Measured: 166 moved hunks, 8,182 unmatched observations, and 354 as the sum over pairs of
    ``min(len(old), len(new))`` — the count of moves round 2 could possibly make. Asserted as
    floors well under those, so a corpus addition does not force a fixture edit, and stated as
    two separate numbers because they fail apart: a change that emptied the population would
    leave the sweeps agreeing on nothing while ``moved`` stayed whatever it was.
    """
    moved = 0
    possible = 0
    for _bill, old_pdf, new_pdf in _PAIRS:
        hunks = diff_pdfs(cached_pages(old_pdf), cached_pages(new_pdf)).hunks
        moved += sum(1 for h in hunks if h.change_type == "moved")
        old_blocks, new_blocks = blocks_for(old_pdf), blocks_for(new_pdf)
        population = pdf_unmatched_population(
            _align_blocks(old_blocks, new_blocks), PdfObservationRegistry(old_blocks, new_blocks)
        )
        possible += min(len(population.old), len(population.new))
    assert moved >= 120, f"only {moved} moved hunks corpus-wide; the preservation sweeps assert little"
    assert possible >= 250, f"round 2 could make only {possible} moves corpus-wide; retrieval is barely exercised"


# --- Round 2 no longer reads classification ------------------------------------------------


@pytest.mark.slow
def test_the_production_path_does_not_run_the_legacy_reconciler(monkeypatch: pytest.MonkeyPatch) -> None:
    """The structural claim of slice 4, made executable.

    ``_reconcile_moves`` is the function that consumed classification output. Replacing it with
    a raise and running a real comparison end to end is what shows round 2 no longer passes
    through it — a claim that a docstring alone cannot keep true.
    """

    def _refuse(*_args, **_kwargs):
        raise AssertionError("diff_pdfs reached the legacy classified-hunk reconciler")

    monkeypatch.setattr(diff_pdf, "_reconcile_moves", _refuse)
    _bill, old_pdf, new_pdf = _PAIRS[0]
    assert diff_pdfs(cached_pages(old_pdf), cached_pages(new_pdf)).hunks


# --- The (ri, ai) equivalence the projection rests on --------------------------------------


def test_filtered_positions_order_candidates_exactly_as_absolute_indices_did() -> None:
    """``_reconcile_moves`` sorted on absolute hunk indices; the stages sort on positions.

    They order identically because the map from filtered position to absolute index is strictly
    increasing, so every pairwise comparison resolves the same way. Stated as an executable
    check rather than as reasoning in a docstring, and built to be able to fail: a
    non-monotonic map is included and must produce a different order.
    """
    absolute_removed = [3, 7, 11]  # ascending, as `enumerate` produces
    absolute_added = [4, 9, 12]
    candidates = [(0.9, 0, 1), (0.9, 2, 0), (0.7, 1, 2), (0.9, 0, 0)]

    by_position = sorted(candidates, reverse=True)
    by_absolute = sorted(
        ((s, absolute_removed[r], absolute_added[a]) for s, r, a in candidates),
        reverse=True,
    )
    assert [(r, a) for _s, r, a in by_position] == [
        (absolute_removed.index(r), absolute_added.index(a)) for _s, r, a in by_absolute
    ]

    scrambled = [11, 3, 7]
    by_scrambled = sorted(((s, scrambled[r], absolute_added[a]) for s, r, a in candidates), reverse=True)
    assert [(scrambled.index(r), absolute_added.index(a)) for _s, r, a in by_scrambled] != [
        (r, a) for _s, r, a in by_position
    ], "a non-monotonic map must reorder, or this control cannot distinguish the two rules"


# --- Retrieval and assignment read their own numbers ---------------------------------------


def _line(text: str, page: int, number: int) -> _IndexedLine:
    return _IndexedLine(text=text, page_number=page, line_number=number)


def _block(text: str, page: int, number: int = 1) -> _Block:
    return _Block(anchor=None, indexed_lines=(_line(text, page, number),))


_CORE = "None of the funds made available by this Act may be used to finalize implement or enforce the proposed rule"


def _pairings(old_blocks: list[_Block], new_blocks: list[_Block]) -> list[_AlignedPairing]:
    """One unmatched pairing per block — the shape a fully-split alignment produces."""
    return [_AlignedPairing(b, None) for b in old_blocks] + [_AlignedPairing(None, b) for b in new_blocks]


def _two_block_sides() -> tuple[list[_Block], list[_Block]]:
    old = [_block(f"{_CORE} concerning migratory bird habitat conservation published March 1 2024", 1)]
    new = [_block(f"{_CORE} concerning migratory bird habitat conservation published March 8 2024", 2)]
    return old, new


def test_assignment_can_refuse_what_retrieval_admitted() -> None:
    """The two numbers are separate inputs, shown by moving them apart.

    Production passes one constant to both, so a single shared cutoff would produce identical
    results forever and the separation would be untestable. Retrieving at a permissive bound
    and assigning at a strict one must select nothing.
    """
    old_blocks, new_blocks = _two_block_sides()
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    population = pdf_unmatched_population(_pairings(old_blocks, new_blocks), registry)

    candidates = retrieve_pdf_move_candidates(population, bound=0.1)
    evidence = pdf_move_evidence(candidates)
    assert evidence, "retrieval at a permissive bound must admit the pair, or this proves nothing"

    assert assign_pdf_moves(population, evidence, threshold=0.999) == ()
    assert len(assign_pdf_moves(population, evidence, threshold=0.1)) == 1


def test_retrieval_can_withhold_what_assignment_would_have_taken() -> None:
    """The other direction: a strict bound starves assignment even at a permissive threshold."""
    old_blocks, new_blocks = _two_block_sides()
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    population = pdf_unmatched_population(_pairings(old_blocks, new_blocks), registry)

    evidence = pdf_move_evidence(retrieve_pdf_move_candidates(population, bound=0.999))
    assert evidence == (), "a near-1.0 bound should admit nothing on this fixture"
    assert assign_pdf_moves(population, evidence, threshold=0.1) == ()


def test_a_settled_move_carries_the_evidence_that_selected_it() -> None:
    """ADR 0020: every selected link carries exactly one evidence record."""
    old_blocks, new_blocks = _two_block_sides()
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    pairings = _pairings(old_blocks, new_blocks)
    population = pdf_unmatched_population(pairings, registry)
    evidence = pdf_move_evidence(retrieve_pdf_move_candidates(population, bound=MOVE_THRESHOLD))
    moves = assign_pdf_moves(population, evidence, threshold=MOVE_THRESHOLD)

    assert len(moves) == 1
    move = moves[0]
    assert move.old == (ObservationRef(OLD, 0),) and move.new == (ObservationRef(NEW, 0),)
    assert len(move.evidence) == 1
    assert isinstance(move.evidence[0].get("word_overlap"), float)

    settled = settle_pdf_correspondences(pairings, registry, moves)
    assert [item.round for item in settled] == [2]
    assert [h.change_type for h in classify_pdf(settled, registry)] == ["moved"]
