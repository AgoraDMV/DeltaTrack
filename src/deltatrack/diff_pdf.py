"""Block-level diff for PDF bill versions, parallel to diff_bill.py for XML.

No shebang since #398 -- see `diff_bill`'s module docstring for why a module inside a
package cannot be executed directly. `./diff_pdf.py` at the repo root wraps this.

A bill is grouped into anchor-delimited blocks (TITLE / SEC. / account heading)
on each side, then aligned section-by-section. Lines before the first anchor
form a preamble block. The block is the natural unit of comparison — it mirrors
how `diff_bill.match_nodes` operates on BillTree nodes for XML and avoids the
SequenceMatcher line-level fragmentation that produced over-counted hunks and
missed added/moved sections.

**The blocks themselves are produced by `parsers.pdf_blocks`, not here.** That module
owns observation production — flattening, cross-page hyphen rejoin, anchor-delimited
grouping, heading-chrome stripping — and this one owns matching and classification
policy. The split is ADR 0020 slice 1, and it is what lets an ADR 0019 PDF parser
revision be derived without hashing the matcher; see that module's docstring. This
module consumes those blocks and must remain downstream of them.

Within matched blocks, the renderer applies word-level diff against the joined
block text. The classifier produces:

- `added` — block present only in v2
- `removed` — block present only in v1
- `moved` — block bodies similar but anchors differ (renumbered SEC.)
- `modified` — paired blocks with different bodies

Reuses amount matching (`match_amounts`) from diff_bill.py and text similarity
(`text_similarity_at_least`, `move_candidates`) plus both cutoffs from similarity.py.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from deltatrack.diff_bill import match_amounts
from deltatrack.matching import (
    NEW,
    OLD,
    CandidateSet,
    Correspondence,
    CorrespondenceEvidence,
    CorrespondenceSet,
    RetrieverInvocation,
)
from deltatrack.parsers.pdf_anchors import Anchor, extract_anchors
from deltatrack.parsers.pdf_blocks import (
    PageLineRange,
    _Block,
    _flatten,
    _group_into_blocks,
    _with_front_matter,
)
from deltatrack.parsers.pdf_text import Page
from deltatrack.pdf_observations import PdfObservation, PdfObservationRegistry
from deltatrack.similarity import (
    MOVE_THRESHOLD,
    SIMILARITY_THRESHOLD,
    move_candidates,
    text_similarity_at_least,
)
from deltatrack.version_stems import label_from_stem

ChangeType = Literal["added", "removed", "modified", "moved"]

_AMENDMENT_RE_DETAIL = re.compile(r"\((increased|reduced|decreased) by\s+\$([\d,]+)\)")

# What the two shared cutoffs mean HERE (they are defined in deltatrack.similarity,
# #492, and were re-declared in this module until then — two copies kept in step by a
# comment saying they were, which is not a mechanism).
#
# MOVE_THRESHOLD: body similarity needed to call a block-pair "moved" rather than
# "modified", and to reconcile a removed+added pair as moved.
#
# SIMILARITY_THRESHOLD: below it, two blocks paired by alignment aren't really a
# modified pair — they're an unrelated removal + addition that happen to share an
# anchor (e.g. v1 SEC. 413 = H-2A waiver, v2 SEC. 413 = Asylum Fee renumbered from
# SEC. 414). Split them so reconcile_moves can pair v1 SEC. 414 with v2 SEC. 413 by
# body similarity.


@dataclass(frozen=True)
class PdfHunk:
    change_type: ChangeType
    v1_anchor: Anchor | None
    v2_anchor: Anchor | None
    v1_range: PageLineRange | None
    v2_range: PageLineRange | None
    v1_text: str
    v2_text: str
    amount_pairs: tuple[tuple[int | None, int | None], ...] = ()
    has_amendment_annotations: bool = False  # mirrors FinancialChange field for XML parity


@dataclass(frozen=True)
class PdfDiff:
    hunks: tuple[PdfHunk, ...]
    v1_anchors: tuple[Anchor, ...] = ()
    v2_anchors: tuple[Anchor, ...] = ()

    @property
    def summary(self) -> dict[str, int]:
        return dict(Counter(h.change_type for h in self.hunks))


# ---- ADR 0020 stage vocabulary (slice 4) -------------------------------------
#
# The PDF mirror of `diff_bill`'s round constants and stage types. Round 1 is the
# `_block_key` + SequenceMatcher alignment followed by the split rule, still fused inside
# `_align_blocks` (slice 5 extracts the split). Round 2 is the move pass, and slice 4 is
# what moved it OFF the classified hunk stream and in front of classification.

#: The assignment rounds this pipeline runs, in order. Carried on a
#: :class:`PdfSettledCorrespondence` so classification can reproduce the legacy record order
#: and label a move -- not a ranking and not a quality signal, exactly as in ``diff_bill``.
PATH_ROUND = 1
MOVE_ROUND = 2

#: Word-level overlap of two block bodies, the one signal both rounds' evidence carries.
#: Round 2 promotes a retrieval score to it (ADR 0020: a score is not evidence until named);
#: round 1 computes it for the express purpose of deciding the pairing, so it is natively
#: evidence there. One name for one measure, as in ``diff_bill``.
WORD_OVERLAP = "word_overlap"


@dataclass(frozen=True)
class _AlignedPairing:
    """One round-1 outcome, before anything is settled.

    A surviving 1:1 carries both blocks and the word overlap the split rule read; an
    unmatched side carries one block and no overlap. A split emits two of these, the removal
    first, which is the order the legacy hunk stream produced and what makes the round-2
    population projection below positionally identical to it.

    Provisional throughout: an ``(old, None)`` here is an *unmatched* observation, not a
    settled removal, because round 2 may still claim it.
    """

    old: _Block | None
    new: _Block | None
    word_overlap: float | None = None


@dataclass(frozen=True)
class PdfUnmatchedPopulation:
    """Round 2's retrieval population: each side's unmatched observations, in stream order.

    The index into ``old``/``new`` is the legacy ``(ri, ai)``. Production computed those as
    positions in the filtered *hunk* list; this computes them as positions in the filtered
    *pairing* stream, and the two are the same numbers -- see
    :func:`pdf_unmatched_population` for why that is true by construction rather than by
    coincidence.
    """

    old: tuple[PdfObservation, ...]
    new: tuple[PdfObservation, ...]


@dataclass(frozen=True)
class PdfSettledCorrespondence:
    """One settled correspondence, the round that selected it, and the slot it occupies.

    ``position`` is the index in the round-1 pairing stream whose slot this record fills. It
    exists because PDF's record order is not XML's: a round-2 move lands **where the removal
    was**, and the addition's slot disappears, rather than being appended after every round-1
    record. That is classification's ordering policy (:func:`classify_pdf` applies it), and
    carrying the slot is what lets the policy live there instead of being an accident of the
    order this function happens to append in.
    """

    correspondence: Correspondence
    round: int
    position: int


# ---- Internal helpers --------------------------------------------------------


def _block_key(block: _Block) -> str:
    """Alignment key for SequenceMatcher.

    Combines anchor text (e.g. "SEC. 101", "OPERATIONS AND SUPPORT") with the
    first ~80 chars of the block's body to disambiguate non-unique account
    headings while staying stable to amendment annotations appearing later
    in the body.
    """
    anchor_text = block.anchor.text if block.anchor else "(preamble)"
    body_preview = block.text[:80].strip()
    return f"{anchor_text}::{body_preview}"


def _extract_amount_pairs(v1_text: str, v2_text: str) -> tuple[tuple[int | None, int | None], ...]:
    """All amount pairs from match_amounts as a tuple, including unchanged pairs.

    The full pair list (changed / added / removed / unchanged) is carried on the
    hunk. The canonical producer categorizes it into `amount_entries` — the export's
    only money field since v2.0 (#274) — dropping unchanged (`old == new`) pairs
    there (`formatters/canonical.py:_amount_entries`). Preserving the unchanged
    pairs here keeps this function a lossless view of match_amounts.
    """
    return tuple(match_amounts(v1_text, v2_text))


def _has_amendment_annotations(v1_text: str, v2_text: str) -> bool:
    """True if either side carries a floor amendment annotation.

    Mirrors `FinancialChange.has_amendment_annotations` in diff_bill.py.
    """
    return bool(_AMENDMENT_RE_DETAIL.search(v1_text) or _AMENDMENT_RE_DETAIL.search(v2_text))


def _hunk_for_paired_blocks(v1_block: _Block, v2_block: _Block, similarity: float) -> PdfHunk:
    """Emit a hunk for two blocks paired by alignment.

    Classifies as `moved` when anchors differ and bodies are highly similar
    (renumbered SEC.), else `modified`. Caller has already confirmed v1 and v2
    block texts differ AND has computed `similarity` (the
    `text_similarity` between the two block texts) to decide split-vs-pair.
    """
    v1_text = v1_block.text
    v2_text = v2_block.text
    v1_anchor = v1_block.anchor
    v2_anchor = v2_block.anchor
    if v1_anchor and v2_anchor and v1_anchor.text != v2_anchor.text and similarity >= MOVE_THRESHOLD:
        change_type: ChangeType = "moved"
    else:
        change_type = "modified"
    return PdfHunk(
        change_type=change_type,
        v1_anchor=v1_anchor,
        v2_anchor=v2_anchor,
        v1_range=v1_block.page_range,
        v2_range=v2_block.page_range,
        v1_text=v1_text,
        v2_text=v2_text,
        amount_pairs=_extract_amount_pairs(v1_text, v2_text),
        has_amendment_annotations=_has_amendment_annotations(v1_text, v2_text),
    )


def _hunk_for_added(v2_block: _Block) -> PdfHunk:
    # A whole account added on the PDF side carries real dollars; match against the
    # empty other side so they surface as `added` amount entries (#86). Previously
    # hardcoded to (), leaving PDF added/removed hunks silent on the money axis.
    return PdfHunk(
        change_type="added",
        v1_anchor=None,
        v2_anchor=v2_block.anchor,
        v1_range=None,
        v2_range=v2_block.page_range,
        v1_text="",
        v2_text=v2_block.text,
        amount_pairs=tuple(match_amounts("", v2_block.text)),
        has_amendment_annotations=_has_amendment_annotations("", v2_block.text),
    )


def _hunk_for_removed(v1_block: _Block) -> PdfHunk:
    # Mirror of _hunk_for_added: a whole account removed surfaces its dollars as
    # `removed` entries (#86).
    return PdfHunk(
        change_type="removed",
        v1_anchor=v1_block.anchor,
        v2_anchor=None,
        v1_range=v1_block.page_range,
        v2_range=None,
        v1_text=v1_block.text,
        v2_text="",
        amount_pairs=tuple(match_amounts(v1_block.text, "")),
        has_amendment_annotations=_has_amendment_annotations(v1_block.text, ""),
    )


def _hunk_for_move(v1_block: _Block, v2_block: _Block) -> PdfHunk:
    """A round-2 move: the removal's old side and the addition's new side, in one hunk.

    Transcribed field for field from the hunk ``_reconcile_moves`` built when it consumed a
    removed/added pair, so the record a move produces does not depend on which path settled
    it. Deliberately not ``_hunk_for_paired_blocks`` with a forced type: that function's job
    is to *decide* moved-vs-modified from a similarity, and a round-2 move is already decided
    by assignment.
    """
    return PdfHunk(
        change_type="moved",
        v1_anchor=v1_block.anchor,
        v2_anchor=v2_block.anchor,
        v1_range=v1_block.page_range,
        v2_range=v2_block.page_range,
        v1_text=v1_block.text,
        v2_text=v2_block.text,
        amount_pairs=_extract_amount_pairs(v1_block.text, v2_block.text),
        has_amendment_annotations=_has_amendment_annotations(v1_block.text, v2_block.text),
    )


def _reconcile_moves(hunks: list[PdfHunk], threshold: float = MOVE_THRESHOLD) -> list[PdfHunk]:
    """Pair `removed`+`added` hunks whose bodies are highly similar into `moved` hunks.

    Catches renumbered sections (e.g. SEC. 414 in v1 → SEC. 413 in v2) when block
    keys diverge enough that SequenceMatcher emitted them as separate insert
    and delete rather than aligning them.

    **This is the pre-slice-4 round 2, retained unchanged as the preservation oracle.**
    ``diff_pdfs`` no longer calls it: round 2 now runs before classification, through
    ``pdf_unmatched_population`` -> ``retrieve_pdf_move_candidates`` -> ``pdf_move_evidence``
    -> ``assign_pdf_moves``. This function is kept because it is the independent statement of
    the rule those four must preserve, and ``tests/test_pdf_round2_stages`` asserts the two
    produce the same output over the committed corpus.

    Deliberately NOT rewired to delegate to the new stages. ``test_pdf_matching_boundary``
    exercises the round-2 competition and its four named mutations *through this function*; a
    thin wrapper would turn that gate from an oracle into a helper, leaving it unable to
    detect the one failure the extraction can actually have. Same reasoning as that module's
    own rule that its transcribed rules must never call ``_emit_pair``.
    """
    removed_idx = [i for i, h in enumerate(hunks) if h.change_type == "removed"]
    added_idx = [i for i, h in enumerate(hunks) if h.change_type == "added"]
    if not removed_idx or not added_idx:
        return hunks

    # Gated + matcher-reused pairwise similarity; move_candidates returns local
    # indices, so map them back to absolute hunk indices. Identical result to the
    # naive removed×added loop for every pair with text on both sides (same tuples;
    # the sort below is what orders them).
    #
    # Text-free hunks yield no candidate, so they are never paired here (#357). That
    # rule was added for the XML side, where a section whose subsections all became
    # their own nodes keeps the SEC. heading and an empty body (#188); difflib scores
    # two empty sequences as a perfect 1.0, so such pairs used to be claimed as moves
    # on no evidence. Blocks here do not reach that state today -- `_strip_heading_lines`
    # returns the lines untouched rather than empty a body -- and no committed PDF pair
    # produces a text-free hunk, so this path is unchanged in practice. The rule is kept
    # uniform across both callers because a hunk with no text carries no evidence of
    # having moved anywhere either way.
    local = move_candidates(
        [hunks[ri].v1_text for ri in removed_idx],
        [hunks[ai].v2_text for ai in added_idx],
        threshold,
    )
    candidates = [(sim, removed_idx[r], added_idx[a]) for sim, r, a in local]
    if not candidates:
        return hunks

    candidates.sort(reverse=True)
    claimed_r: set[int] = set()
    claimed_a: set[int] = set()
    moved_pairs: list[tuple[int, int]] = []
    for _, ri, ai in candidates:
        if ri in claimed_r or ai in claimed_a:
            continue
        claimed_r.add(ri)
        claimed_a.add(ai)
        moved_pairs.append((ri, ai))

    consumed = claimed_r | claimed_a
    moved_lookup = {ri: ai for ri, ai in moved_pairs}
    result: list[PdfHunk] = []
    for i, h in enumerate(hunks):
        if i in moved_lookup:
            removed = h
            added = hunks[moved_lookup[i]]
            result.append(
                PdfHunk(
                    change_type="moved",
                    v1_anchor=removed.v1_anchor,
                    v2_anchor=added.v2_anchor,
                    v1_range=removed.v1_range,
                    v2_range=added.v2_range,
                    v1_text=removed.v1_text,
                    v2_text=added.v2_text,
                    amount_pairs=_extract_amount_pairs(removed.v1_text, added.v2_text),
                    has_amendment_annotations=_has_amendment_annotations(removed.v1_text, added.v2_text),
                )
            )
        elif i in consumed:
            continue
        else:
            result.append(h)
    return result


# ---- Public entry point ------------------------------------------------------


def _emit_pair(v1_b: _Block, v2_b: _Block, sink: list[_AlignedPairing]) -> None:
    """Record an aligned pair as a surviving 1:1, or split it into a removal + an addition.

    When v1/v2 block texts are very dissimilar, treat the pair as an unrelated removal and
    addition that happen to share alignment — emit two pairings so round 2 can later pair
    each with its right counterpart.

    **The rule is unchanged from the pre-slice-4 version; only what it appends changed.** It
    used to append classified ``PdfHunk``s directly, which is what forced round 2 to run on
    classification output. It now appends provisional pairings, so round 2 has a population
    that exists before anything is classified. The comparisons, the constants and the order
    of the two split records are identical, and slice 5 is what extracts this rule into
    ``pdf_pairing_survives_similarity_rule`` + ``apply_pdf_similarity_revocation``.

    The surviving-pair word overlap is carried rather than recomputed later: classification
    needs it for the moved-vs-modified call, and recomputing would be a second measurement
    free to disagree with the one that decided the pairing.
    """
    if v1_b.text == v2_b.text:
        # Stripping headings from the body (#56) can equalize two blocks that
        # differ only by a renamed anchor (an account renamed with otherwise
        # identical prose). With the heading gone from the body, that rename
        # would vanish; surface it as a moved/renamed hunk instead.
        #
        # Both cases are one 1:1 correspondence: the blocks are claimed and neither may reach
        # round 2. What differs is only whether classification emits a record — a renamed
        # anchor becomes a `moved` hunk, an identical one becomes nothing at all (research
        # record §7.3: `unchanged` is not a PDF record). That is classification's call, made
        # from the anchors it can already see, so nothing distinguishes them here.
        #
        # 1.0 is transcribed from the legacy call, not derived. `text_similarity` of two
        # identical texts is also 1.0, but production passed the literal, so the literal is
        # what travels; deriving it here would be a new measurement wearing the old value.
        sink.append(_AlignedPairing(v1_b, v2_b, word_overlap=1.0))
        return
    # Gate at the lower (split) threshold: at or above it the exact ratio is
    # needed downstream for the MOVE_THRESHOLD moved/modified split in _hunk_for_paired_blocks.
    sim = text_similarity_at_least(v1_b.text, v2_b.text, SIMILARITY_THRESHOLD)
    if sim < SIMILARITY_THRESHOLD:
        sink.append(_AlignedPairing(v1_b, None))
        sink.append(_AlignedPairing(None, v2_b))
    else:
        sink.append(_AlignedPairing(v1_b, v2_b, word_overlap=sim))


def _align_blocks(v1_blocks: list[_Block], v2_blocks: list[_Block]) -> list[_AlignedPairing]:
    """ROUND 1, retrieval and assignment still fused: which blocks are provisionally paired.

    Unchanged from the pre-slice-4 opcode walk except that it produces pairings rather than
    classified hunks. `_block_key` + `SequenceMatcher` decide what is *considered*; the
    positional zip inside a ``replace`` is retrieval too (research record §9), and
    :func:`_emit_pair`'s similarity rule is the one assignment act that can revoke a pairing.
    Slice 5 is what separates those.
    """
    matcher = difflib.SequenceMatcher(
        a=[_block_key(b) for b in v1_blocks],
        b=[_block_key(b) for b in v2_blocks],
        autojunk=False,
    )

    pairings: list[_AlignedPairing] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            # Block keys match. Bodies might still differ (e.g. amendment
            # annotations appearing past the 80-char preview).
            for v1_b, v2_b in zip(v1_blocks[i1:i2], v2_blocks[j1:j2]):
                _emit_pair(v1_b, v2_b, pairings)
        elif op == "delete":
            for v1_b in v1_blocks[i1:i2]:
                pairings.append(_AlignedPairing(v1_b, None))
        elif op == "insert":
            for v2_b in v2_blocks[j1:j2]:
                pairings.append(_AlignedPairing(None, v2_b))
        else:  # replace
            v1_slice = v1_blocks[i1:i2]
            v2_slice = v2_blocks[j1:j2]
            # Pair positionally; surplus on either side becomes added/removed.
            for k in range(max(len(v1_slice), len(v2_slice))):
                v1_b = v1_slice[k] if k < len(v1_slice) else None
                v2_b = v2_slice[k] if k < len(v2_slice) else None
                if v1_b is not None and v2_b is not None:
                    _emit_pair(v1_b, v2_b, pairings)
                elif v1_b is not None:
                    pairings.append(_AlignedPairing(v1_b, None))
                else:
                    assert v2_b is not None
                    pairings.append(_AlignedPairing(None, v2_b))
    return pairings


def pdf_unmatched_population(
    pairings: list[_AlignedPairing],
    registry: PdfObservationRegistry,
) -> PdfUnmatchedPopulation:
    """Round 2's retrieval population, projected from the round-1 pairing stream.

    **This projection is what slice 4 is for.** Production derived the same two lists by
    filtering the *classified* hunk stream on ``change_type in {"removed", "added"}``, which
    made round 2 a consumer of classification output — the ADR 0020 violation the slice
    removes. Deriving them from the pairings makes the equality true by construction: every
    ``removed`` hunk came from an ``(old, None)`` pairing and every ``added`` one from a
    ``(None, new)``, one for one and in the same order, because ``_hunk_for_removed`` /
    ``_hunk_for_added`` are the only producers of those two types and each was called exactly
    where a pairing names one side.

    The order is the stream's, which is what keeps the legacy ``(ri, ai)`` positions the same
    numbers. Production's ``(ri, ai)`` were *absolute hunk indices*; these are positions in
    the filtered lists. The two order candidates identically, because the map from filtered
    position to absolute index is strictly increasing — ``removed_idx`` was built by an
    ascending ``enumerate`` scan — so any comparison of two candidates resolves the same way
    under either. ``tests/test_pdf_round2_stages`` measures that rather than trusting it.

    A pairing naming neither side is refused: ``_align_blocks`` cannot emit one, and a silent
    one would break exactly the positional correspondence this projection depends on.
    """
    old_unmatched: list[PdfObservation] = []
    new_unmatched: list[PdfObservation] = []
    for position, pairing in enumerate(pairings):
        if pairing.old is not None and pairing.new is not None:
            continue
        if pairing.old is not None:
            old_unmatched.append(registry.observation(OLD, pairing.old))
        elif pairing.new is not None:
            new_unmatched.append(registry.observation(NEW, pairing.new))
        else:
            raise ValueError(f"pairing {position} names no observation on either side")
    return PdfUnmatchedPopulation(old=tuple(old_unmatched), new=tuple(new_unmatched))


def retrieve_pdf_move_candidates(population: PdfUnmatchedPopulation, *, bound: float) -> CandidateSet:
    """RETRIEVAL, round 2: which unmatched block pairs are worth evaluating.

    ``bound`` is retrieval's own control, recorded in the invocation config so it travels with
    every proposal (ADR 0020 requires the control to be explicit). It is a separate parameter
    from assignment's threshold even though production passes one constant to both — which is
    what lets a test move them apart and show each stage reading its own input.

    Scoring is ``similarity.move_candidates`` unchanged, so the pairing population, the
    normalization, the empty-text skip (#357) and the numbers are production's own.
    """
    candidates = CandidateSet()
    if not population.old or not population.new:
        return candidates

    invocation = RetrieverInvocation.of("unmatched_block_text_overlap", round=MOVE_ROUND, threshold=bound)
    for score, ri, ai in move_candidates(
        [observation.block.text for observation in population.old],
        [observation.block.text for observation in population.new],
        bound,
    ):
        candidates.propose(population.old[ri].ref, population.new[ai].ref, invocation, score=score)
    return candidates


def pdf_move_evidence(candidates: CandidateSet) -> tuple[CorrespondenceEvidence, ...]:
    """CORRESPONDENCE EVIDENCE, round 2: promote the retrieval score to a named signal.

    ADR 0020 is explicit that a retrieval score is not correspondence evidence until it is
    named as a signal. This is that promotion and the only place it happens; assignment reads
    the signal and never ``Proposal.score``, so the two can be perturbed independently.

    No verdict, no confidence, no threshold — what the number means is assignment's to decide.
    """
    evidence: list[CorrespondenceEvidence] = []
    for candidate in candidates.candidates():
        if len(candidate.proposals) != 1:
            raise ValueError(
                f"candidate {candidate.ordinal_pair} carries {len(candidate.proposals)} proposals; "
                "round 2 runs exactly one retriever invocation"
            )
        score = candidate.proposals[0].score
        if not isinstance(score, float):
            raise ValueError(f"candidate {candidate.ordinal_pair} was retrieved without a score to promote")
        evidence.append(CorrespondenceEvidence.of(candidate.old, candidate.new, **{WORD_OVERLAP: score}))
    return tuple(evidence)


def _pdf_word_overlap(evidence: CorrespondenceEvidence) -> float:
    """The one evidence signal round-2 assignment reads."""
    value = evidence.get(WORD_OVERLAP)
    if not isinstance(value, float):
        raise ValueError(f"evidence for {evidence.old}->{evidence.new} carries no {WORD_OVERLAP} signal")
    return value


def _greedy_pdf_move_links(
    population: PdfUnmatchedPopulation,
    evidence: tuple[CorrespondenceEvidence, ...],
    threshold: float,
) -> list[CorrespondenceEvidence]:
    """The legacy competition, kept whole and kept private.

    ``_reconcile_moves`` sorts ``(similarity, ri, ai)`` with ``reverse=True``, so a tie on
    similarity breaks on **descending** ``ri`` then **descending** ``ai``. Sorting on
    similarity alone and leaning on a stable secondary order is a different rule, and
    ``test_pdf_matching_boundary``'s four named mutations are what pin that.

    ``(ri, ai)`` are positions in ``population`` and never leave this function.
    """
    ri_of = {observation.ref: index for index, observation in enumerate(population.old)}
    ai_of = {observation.ref: index for index, observation in enumerate(population.new)}

    eligible = [item for item in evidence if _pdf_word_overlap(item) >= threshold]
    ordered = sorted(
        eligible,
        key=lambda item: (_pdf_word_overlap(item), ri_of[item.old], ai_of[item.new]),
        reverse=True,
    )

    claimed_old: set[int] = set()
    claimed_new: set[int] = set()
    selected: list[CorrespondenceEvidence] = []
    for item in ordered:
        ri, ai = ri_of[item.old], ai_of[item.new]
        if ri in claimed_old or ai in claimed_new:
            continue
        claimed_old.add(ri)
        claimed_new.add(ai)
        selected.append(item)
    return selected


def assign_pdf_moves(
    population: PdfUnmatchedPopulation,
    evidence: tuple[CorrespondenceEvidence, ...],
    *,
    threshold: float,
) -> tuple[Correspondence, ...]:
    """ASSIGNMENT, round 2: which retrieved pairs actually correspond.

    Settled 1:1 correspondences in greedy selection order, each carrying the one evidence
    record that selected it. ``threshold`` is assignment's own, because every rule deciding
    whether a candidate *becomes* a correspondence lives here (ADR 0020 invariant 6).
    Production passes one constant to both it and retrieval's bound, so re-applying it selects
    exactly what it selected before; give the two different values and this refuses the
    difference, which is what makes the separation testable rather than decorative.
    """
    return tuple(
        Correspondence(old=(item.old,), new=(item.new,), evidence=(item,))
        for item in _greedy_pdf_move_links(population, evidence, threshold)
    )


def settle_pdf_correspondences(
    pairings: list[_AlignedPairing],
    registry: PdfObservationRegistry,
    moves: tuple[Correspondence, ...],
) -> tuple[PdfSettledCorrespondence, ...]:
    """Every correspondence settled for one comparison, with its round and its output slot.

    **Nothing is settled before this point.** ``CorrespondenceSet`` refuses an observation
    that already corresponds, so settling an unmatched block as a 1:0 and later revising it
    into a move would be inexpressible — the round-1 stream stays provisional and round 2 runs
    before any of it is committed.

    A round-2 move takes the **slot of its removal**, and the addition's slot is dropped. That
    reproduces ``_reconcile_moves``' output placement, which rewrote the removed hunk in place
    and skipped the consumed added one. Carrying the slot rather than sorting by round is the
    difference from ``diff_bill``, whose legacy output appends moves instead.

    A surviving 1:1 carries its round-1 word overlap as the evidence that selected it, so
    classification can make the moved-vs-modified call from evidence rather than by
    recomputing a second measurement free to disagree with the first.
    """
    claimed = {ref for move in moves for ref in (*move.old, *move.new)}
    move_by_old = {move.old[0]: move for move in moves}

    settled: list[PdfSettledCorrespondence] = []
    for position, pairing in enumerate(pairings):
        if pairing.old is not None and pairing.new is not None:
            old_ref = registry.ref(OLD, pairing.old)
            new_ref = registry.ref(NEW, pairing.new)
            if pairing.word_overlap is None:
                raise ValueError(f"the surviving 1:1 pairing {old_ref}->{new_ref} carries no word overlap")
            item = CorrespondenceEvidence.of(old_ref, new_ref, **{WORD_OVERLAP: pairing.word_overlap})
            settled.append(
                PdfSettledCorrespondence(
                    Correspondence(old=(old_ref,), new=(new_ref,), evidence=(item,)),
                    PATH_ROUND,
                    position,
                )
            )
        elif pairing.old is not None:
            old_ref = registry.ref(OLD, pairing.old)
            move = move_by_old.get(old_ref)
            if move is not None:
                settled.append(PdfSettledCorrespondence(move, MOVE_ROUND, position))
            elif old_ref not in claimed:
                settled.append(PdfSettledCorrespondence(Correspondence(old=(old_ref,)), PATH_ROUND, position))
        elif pairing.new is not None:
            new_ref = registry.ref(NEW, pairing.new)
            if new_ref not in claimed:
                settled.append(PdfSettledCorrespondence(Correspondence(new=(new_ref,)), PATH_ROUND, position))
        else:
            raise ValueError(f"pairing {position} names no observation on either side")

    exclusive = CorrespondenceSet()
    for item in settled:
        exclusive.add(item.correspondence)
    return tuple(settled)


def _classified_pdf(item: PdfSettledCorrespondence, registry: PdfObservationRegistry) -> PdfHunk | None:
    """One settled correspondence as one hunk, or ``None`` where PDF emits no record.

    ``None`` is the ``unchanged`` case: two blocks with identical bodies under the same
    anchor. PDF has never emitted a record for it (research record §7.3) and this is where
    that policy is applied — classification decides what to emit, and the correspondence still
    exists, which is what keeps both blocks out of round 2's population.
    """
    correspondence = item.correspondence
    if not correspondence.is_binary:
        raise ValueError(
            f"classification received a {correspondence.shape} correspondence; the canonical contract "
            "is a binary row and ADR 0020 requires a non-binary one to be projected explicitly"
        )
    old_block = registry.block(correspondence.old[0]) if correspondence.old else None
    new_block = registry.block(correspondence.new[0]) if correspondence.new else None

    if old_block is None:
        return _hunk_for_added(new_block)
    if new_block is None:
        return _hunk_for_removed(old_block)
    if item.round == MOVE_ROUND:
        return _hunk_for_move(old_block, new_block)

    if old_block.text == new_block.text and not (
        old_block.anchor and new_block.anchor and old_block.anchor.text != new_block.anchor.text
    ):
        return None
    return _hunk_for_paired_blocks(old_block, new_block, _pdf_word_overlap(correspondence.evidence[0]))


def classify_pdf(
    settled: tuple[PdfSettledCorrespondence, ...],
    registry: PdfObservationRegistry,
) -> list[PdfHunk]:
    """CLASSIFICATION: what changed, given settled correspondence.

    Decides nothing about correspondence: no partner is changed and every block is resolved
    through the complete :class:`PdfObservationRegistry` rather than through a filtered-list
    position. It does still apply the moved-vs-modified threshold to a round-1 pairing's
    evidence, which is a classification act ADR 0020 wants moved into assignment — that is
    slice 6, and it is design work rather than extraction because 20 of 165 PDF moves are
    threshold verdicts on round-1 pairs rather than round-2 provenance (§3.4).

    **Record order is this stage's policy.** Output follows the round-1 stream slot, so a
    round-2 move appears where its removal was and the consumed addition is gone. Sorted on
    the slot alone, so the result depends on the stream and not on the order assignment
    happened to produce the moves in.
    """
    ordered = sorted(settled, key=lambda item: item.position)
    return [hunk for hunk in (_classified_pdf(item, registry) for item in ordered) if hunk is not None]


def diff_pdfs(v1_pages: list[Page], v2_pages: list[Page]) -> PdfDiff:
    """Block-level diff of two extracted PDF page sequences.

    The body is the ADR 0020 stage sequence. Both rounds now run **before** classification,
    which is what slice 4 exists to satisfy: a later retrieval round may consult earlier
    matching state, but none of it may run after classification. Round 2 previously read the
    classified hunk stream, so a change to what ``_hunk_for_removed`` emitted could silently
    change which pairs were even considered for a move.

    Round 2 stays after the round-1 split rule, and that ordering is load-bearing rather than
    incidental: a split is what puts most of round 2's population on the table at all.

    What remains fused: round-1 retrieval and the split rule inside :func:`_align_blocks`
    (slice 5), and the moved-vs-modified call inside classification (slice 6).
    """
    v1_indexed = _flatten(v1_pages)
    v2_indexed = _flatten(v2_pages)
    v1_anchors = extract_anchors(v1_pages)
    v2_anchors = extract_anchors(v2_pages)

    v1_blocks = _group_into_blocks(v1_indexed, v1_anchors)
    v2_blocks = _group_into_blocks(v2_indexed, v2_anchors)

    # Surface the front-matter anchor synthesized per-block (issue #33) into the
    # anchor lists so the full-bill section TOC links to it like any other anchor.
    v1_anchors = _with_front_matter(v1_blocks, v1_anchors)
    v2_anchors = _with_front_matter(v2_blocks, v2_anchors)

    registry = PdfObservationRegistry(v1_blocks, v2_blocks)
    pairings = _align_blocks(v1_blocks, v2_blocks)
    population = pdf_unmatched_population(pairings, registry)
    candidates = retrieve_pdf_move_candidates(population, bound=MOVE_THRESHOLD)
    evidence = pdf_move_evidence(candidates)
    moves = assign_pdf_moves(population, evidence, threshold=MOVE_THRESHOLD)
    settled = settle_pdf_correspondences(pairings, registry, moves)
    hunks = classify_pdf(settled, registry)

    return PdfDiff(
        hunks=tuple(hunks),
        v1_anchors=tuple(v1_anchors),
        v2_anchors=tuple(v2_anchors),
    )


# ---- CLI ---------------------------------------------------------------------


def render_pdf_diff_html(
    v1_pdf: Path,
    v2_pdf: Path,
    *,
    v1_label: str | None = None,
    v2_label: str | None = None,
) -> str:
    """Render an HTML diff page for two PDF paths.

    Delegates to ``compare.pdf.compare_pdfs_html`` — the same pipeline
    the web app uses — so the report carries the full-bill text view, in-page
    search, section TOC, and embedded export. Title and Congress are derived
    from the PDF front matter; labels default to the (de-prefixed) filename
    stems. Imported lazily to avoid a circular import (compare.pdf imports
    diff_pdf).
    """
    from deltatrack.compare.pdf import compare_pdfs_html

    return compare_pdfs_html(
        v1_pdf.read_bytes(),
        v2_pdf.read_bytes(),
        start_label=v1_label if v1_label is not None else label_from_stem(v1_pdf.stem),
        end_label=v2_label if v2_label is not None else label_from_stem(v2_pdf.stem),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diff two PDF bill versions and produce an HTML diff page "
        "(full-bill view, search, and export included).",
    )
    parser.add_argument("v1_pdf", type=Path, help="Path to the older PDF")
    parser.add_argument("v2_pdf", type=Path, help="Path to the newer PDF")
    parser.add_argument("-o", "--output", type=Path, help="Output HTML file (default: stdout)")
    parser.add_argument("--v1-label", help="Label for the older version (default: filename stem)")
    parser.add_argument("--v2-label", help="Label for the newer version (default: filename stem)")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    html = render_pdf_diff_html(
        args.v1_pdf,
        args.v2_pdf,
        v1_label=args.v1_label,
        v2_label=args.v2_label,
    )
    if args.output:
        args.output.write_text(html)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(html)


if __name__ == "__main__":
    main()
