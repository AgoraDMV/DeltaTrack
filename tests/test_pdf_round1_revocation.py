"""Slice 5: the round-1 similarity revocation, as evidence plus a rule that owns its threshold.

``_emit_pair`` used to do three things in one place — measure the two block texts, decide
whether the aligned pair survived, and emit the records. Slice 5 separates them into
``pdf_similarity_correspondence_evidence`` (describes), ``pdf_pairing_survives_similarity_rule``
(decides, owns the threshold) and ``apply_pdf_similarity_revocation`` (applies).

**What gate 4 already covers, and is not repeated here.** ``test_pdf_matching_boundary`` pins
the split *rule* against an independently transcribed oracle, over the corpus and at two
synthetic points either side of the cutoff. That establishes what the rule is. It cannot
establish that the extracted stages are what apply it, because it runs ``diff_pdfs`` end to end
with the production constant — one number reaching one behaviour, with no way to tell which
code read it.

So the control this module adds is the one gate 4 structurally cannot: **move the threshold at
the stage boundary and watch the split population respond**. A revocation rule that had been
left behind in ``_align_blocks``, or a stage reading ``SIMILARITY_THRESHOLD`` directly instead
of its parameter, passes every existing gate and fails here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deltatrack import diff_pdf
from deltatrack.diff_pdf import (
    TEXT_IDENTICAL,
    WORD_OVERLAP,
    _align_blocks,
    _AlignedPairing,
    _pdf_similarity_signals,
    apply_pdf_similarity_revocation,
    pdf_pairing_survives_similarity_rule,
    pdf_similarity_correspondence_evidence,
)
from deltatrack.matching import NEW, OLD, CorrespondenceEvidence, ObservationRef
from deltatrack.parsers.pdf_anchors import extract_anchors
from deltatrack.parsers.pdf_blocks import _Block, _flatten, _group_into_blocks, _IndexedLine
from deltatrack.pdf_observations import PdfObservationRegistry
from deltatrack.similarity import SIMILARITY_THRESHOLD
from tests.pdf_corpus import adjacent_pdf_pairs, cached_pages

_PAIRS = adjacent_pdf_pairs()


def _blocks(pdf: Path) -> list[_Block]:
    pages = cached_pages(pdf)
    return _group_into_blocks(_flatten(pages), extract_anchors(pages))


def _unmatched(pairings: list[_AlignedPairing]) -> int:
    return sum(1 for p in pairings if p.old is None or p.new is None)


def _revocations_by_threshold(thresholds: tuple[float, ...]) -> dict[float, int]:
    """Corpus-wide revocation counts at each threshold, from one pass over the evidence.

    Evidence is computed once per pair and each threshold evaluated against it, rather than
    re-aligning three times: the rule reads only the evidence, so re-deriving it per threshold
    would measure the same thing three times more slowly, and would quietly let a rule that
    recomputed its own signals pass.
    """
    counts = dict.fromkeys(thresholds, 0)
    for _bill, old_pdf, new_pdf in _PAIRS:
        old_blocks, new_blocks = _blocks(old_pdf), _blocks(new_pdf)
        registry = PdfObservationRegistry(old_blocks, new_blocks)
        provisional = _align_blocks(old_blocks, new_blocks)
        evidence = pdf_similarity_correspondence_evidence(provisional, registry)
        before = _unmatched(provisional)
        for threshold in thresholds:
            decided = apply_pdf_similarity_revocation(provisional, evidence, registry, threshold=threshold)
            counts[threshold] += (_unmatched(decided) - before) // 2
    return counts


# --- The control gate 4 cannot give ------------------------------------------------------


@pytest.mark.slow
def test_moving_the_threshold_moves_the_split_population() -> None:
    """THE slice 5 negative control: the stage's own parameter decides the splits.

    Corpus-wide at three thresholds. At 0.0 nothing can be revoked; at production's cutoff the
    count is production's split population; at 0.99 every aligned pair whose bodies differ and
    do not nearly match is revoked as well. A rule still wired to the module constant, or left
    behind inside ``_align_blocks``, returns the same number three times.

    Aggregated over the corpus rather than one pair, deliberately: a single pair can have every
    non-identical pairing already below production's cutoff, in which case raising the threshold
    changes nothing there and the control would report a false alarm.

    Measured: 0 / 230 / 813.

    The middle figure is close to but not identical with the 224 splits the research record's
    §3.2 reports, and the difference is not reconciled here. This counts revocations over
    **every** adjacent committed pair, including the six ``compare.pdf`` declines that §3.2's
    population excludes; that is the likely account, and it is left as a stated discrepancy
    rather than an assumed one, because asserting equality on an unverified explanation is how
    a wrong number gets a citation.
    """
    counts = _revocations_by_threshold((0.0, SIMILARITY_THRESHOLD, 0.99))

    assert counts[0.0] == 0, f"a 0.0 threshold revoked {counts[0.0]} pairings; nothing can score below it"
    assert counts[SIMILARITY_THRESHOLD] >= 150, (
        f"only {counts[SIMILARITY_THRESHOLD]} revoked pairings corpus-wide; the split population is "
        "barely exercised and the comparison below would rest on nothing"
    )
    assert counts[0.0] < counts[SIMILARITY_THRESHOLD] < counts[0.99], (
        f"the split population did not respond to the threshold: {counts}. The revocation rule is "
        "reading something other than the parameter it was handed."
    )


# --- The rule reads evidence, and only evidence ------------------------------------------


def _evidence(**signals) -> CorrespondenceEvidence:
    return CorrespondenceEvidence.of(ObservationRef(OLD, 0), ObservationRef(NEW, 0), **signals)


def test_identical_text_is_kept_at_any_threshold() -> None:
    """The short-circuit branch, as a rule: identical bodies are never revoked.

    Transcribed from ``_emit_pair``'s first branch, which returned before the ratio was ever
    computed. A threshold above 1.0 is the decisive case — if the rule fell through to the
    numeric comparison, this would revoke.
    """
    evidence = _evidence(**{TEXT_IDENTICAL: True, WORD_OVERLAP: 1.0})
    assert pdf_pairing_survives_similarity_rule(evidence, 1.5) is True


def test_the_numeric_branch_is_inclusive_at_the_threshold() -> None:
    """``>=``, not ``>``. One character, and it decides a pairing exactly at the cutoff."""
    assert pdf_pairing_survives_similarity_rule(_evidence(**{TEXT_IDENTICAL: False, WORD_OVERLAP: 0.4}), 0.4)
    assert not pdf_pairing_survives_similarity_rule(_evidence(**{TEXT_IDENTICAL: False, WORD_OVERLAP: 0.399}), 0.4)


@pytest.mark.parametrize(
    ("signals", "match"),
    [
        ({}, f"carries no {TEXT_IDENTICAL} signal"),
        ({TEXT_IDENTICAL: "yes", WORD_OVERLAP: 0.9}, f"non-bool {TEXT_IDENTICAL}"),
        ({TEXT_IDENTICAL: False}, f"no {WORD_OVERLAP} signal"),
        ({TEXT_IDENTICAL: False, WORD_OVERLAP: 1}, f"non-float {WORD_OVERLAP}"),
    ],
)
def test_malformed_evidence_raises_rather_than_revoking(signals: dict, match: str) -> None:
    """Never silently revoke. A split reported on the strength of a bug is a removal plus an
    addition in the user's report, and nothing downstream can tell it from a real one.

    The ``WORD_OVERLAP: 1`` case is the subtle one: ``isinstance(True, int)`` is true in Python,
    so a rule checking ``float`` loosely would read a bool as a score.
    """
    with pytest.raises(ValueError, match=match):
        pdf_pairing_survives_similarity_rule(_evidence(**signals), 0.4)


# --- The evidence stage ------------------------------------------------------------------


def _line(text: str, page: int) -> _IndexedLine:
    return _IndexedLine(text=text, page_number=page, line_number=1)


def _block(text: str, page: int) -> _Block:
    return _Block(anchor=None, indexed_lines=(_line(text, page),))


def test_the_short_circuit_never_measures_identical_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Preserving WHICH similarity calls the engine makes, not just what it concludes.

    Computing the ratio unconditionally would be tidier and would reach the same verdict, so no
    output comparison could catch it. It would still be a behaviour change: the set of
    ``text_similarity_at_least`` calls would differ from the set production makes today, and
    that function is itself gated and returns 0.0 rather than the true ratio below its bound.
    """

    def _refuse(*_args, **_kwargs):
        raise AssertionError("identical block texts must not be measured")

    monkeypatch.setattr(diff_pdf, "text_similarity_at_least", _refuse)
    signals = _pdf_similarity_signals(_block("same body", 1), _block("same body", 2))
    assert signals == {TEXT_IDENTICAL: True, WORD_OVERLAP: 1.0}


def test_evidence_is_retained_for_a_revoked_pairing() -> None:
    """ADR 0020 invariant 8: a rejected candidate's evidence stays inspectable.

    Retained and unattached, never discarded — the same rule round 2's rejected candidates
    follow. Without this, the reason a provision was split would exist nowhere after the split.
    """
    old_blocks = [_block("alpha beta gamma delta epsilon", 1)]
    new_blocks = [_block("wholly unrelated words entirely", 2)]
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    provisional = [_AlignedPairing(old_blocks[0], new_blocks[0])]

    evidence = pdf_similarity_correspondence_evidence(provisional, registry)
    decided = apply_pdf_similarity_revocation(provisional, evidence, registry, threshold=SIMILARITY_THRESHOLD)

    assert [(p.old, p.new) for p in decided] == [(old_blocks[0], None), (None, new_blocks[0])], (
        "a revoked pairing must become the removal then the addition, adjacent and in place"
    )
    assert len(evidence) == 1, "the revoked pairing's evidence must survive the revocation"
    assert evidence[0].link == (ObservationRef(OLD, 0), ObservationRef(NEW, 0))
    assert evidence[0].get(TEXT_IDENTICAL) is False


def test_an_unmatched_pairing_carries_no_evidence() -> None:
    """A ``(block, None)`` names no pair, so there is nothing for evidence to describe."""
    blocks = [_block("alpha", 1)]
    registry = PdfObservationRegistry(blocks, [])
    assert pdf_similarity_correspondence_evidence([_AlignedPairing(blocks[0], None)], registry) == ()


def test_a_surviving_pairing_without_evidence_is_refused() -> None:
    """The stages disagreeing about the population is a bug, not a reason to guess.

    Revoking on missing evidence would split a provision silently; keeping it would attach no
    record to a selected link, which ADR 0020 forbids. So it raises.
    """
    old_blocks, new_blocks = [_block("alpha", 1)], [_block("beta", 2)]
    registry = PdfObservationRegistry(old_blocks, new_blocks)
    with pytest.raises(ValueError, match="no correspondence evidence"):
        apply_pdf_similarity_revocation(
            [_AlignedPairing(old_blocks[0], new_blocks[0])], (), registry, threshold=SIMILARITY_THRESHOLD
        )


def test_alignment_no_longer_revokes_anything() -> None:
    """Retrieval stopped deciding correspondence, which is the whole point of the slice.

    Every aligned pair leaves ``_align_blocks`` as a provisional 1:1, however dissimilar. Before
    slice 5 this fixture produced two unmatched pairings straight out of alignment.
    """
    old_blocks = [_block("alpha beta gamma delta epsilon", 1)]
    new_blocks = [_block("wholly unrelated words entirely", 2)]
    pairings = _align_blocks(old_blocks, new_blocks)

    assert [(p.old, p.new) for p in pairings] == [(old_blocks[0], new_blocks[0])], (
        "alignment split a dissimilar pair; the revocation rule has leaked back into retrieval"
    )
    assert _unmatched(pairings) == 0
