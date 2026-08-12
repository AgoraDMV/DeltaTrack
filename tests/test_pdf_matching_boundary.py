"""The PDF matching decisions that no gate could previously detect a change to.

Slice 0 of the ADR 0020 PDF convergence work
(``docs/research/pdf-matching-convergence/``). Four production mutations —
``SIMILARITY_THRESHOLD`` to 0.45 and 0.35, ``MOVE_THRESHOLD`` to 0.65 and 0.55, each
changing real corpus output — were run against the full suite and **all four stayed
green**, 3227 tests apiece. The canonical baseline (``tests/test_pdf_canonical_baseline``)
now catches any of them that moves a committed pair. This module catches the *rules*, at
the sites that decide them, including on inputs the corpus does not contain.

**Every gate here carries its own falsification.** ADR 0020 invariant 12 is called out in
the record as "a green-by-default gate of the kind that has passed while checking nothing
before (#299, #542)", so a control that has never produced a positive result is not
trusted. Each rule below is paired with a test that applies a NAMED mutation and asserts
the result changes. Those mutation tests are permanent, not one-off probes: if a future
refactor makes a mutation stop mattering, the mutation test fails and says so.

The four gates, and the mutation each is falsified by:

``test_transcribed_*``      the split and move rules, transcribed independently.
                            Falsified by feeding a hunk that violates each rule.
``test_split_population*``  a real below-cutoff split carrying money on both sides.
                            Falsified by the boundary pair either side of the cutoff.
``test_positional_replace`` the positional ``replace`` zip.
                            Falsified by global best-similarity assignment.
``test_greedy_*``           round-2 competition and exclusivity.
                            Falsified by four separate mutations, one at a time.

**The transcribed rules exist to disagree with production.** They compose the same
primitives deliberately — what they guard is the *composition*: an inverted comparison, a
dropped gate, the wrong constant. They must never be replaced by a call to
``_emit_pair`` or ``_hunk_for_paired_blocks``, and production must never import them. An
oracle that asked the production helper what the rule is could not detect that the rule
changed, which is the one failure this slice can actually have.

No production code is changed by this module. It pins current behaviour so that the stage
extraction in later slices has something to be behaviour-preserving *against*.
"""

from __future__ import annotations

import pytest

from deltatrack.diff_bill import extract_amounts
from deltatrack.diff_pdf import PdfHunk, _reconcile_moves, diff_pdfs
from deltatrack.parsers.pdf_text import Line, Page
from deltatrack.similarity import MOVE_THRESHOLD, SIMILARITY_THRESHOLD, move_candidates, text_similarity
from tests.pdf_corpus import adjacent_pdf_pairs, cached_pages

pytestmark = pytest.mark.slow


# --- The oracle: the two rules, transcribed, never imported from production -----------


def legacy_pair_survives(v1_text: str, v2_text: str) -> bool:
    """Whether ``_emit_pair`` keeps an aligned pair rather than splitting it.

    Transcribed from ``diff_pdf._emit_pair`` as it stands: identical texts are kept, and
    otherwise the word-level ratio must reach ``SIMILARITY_THRESHOLD``. Written in the
    positive, and using ``text_similarity`` rather than ``text_similarity_at_least`` —
    the gated form returns 0.0 below the cutoff, so composing the oracle from it would
    make the oracle inherit the very short-circuit it is meant to check.
    """
    if v1_text == v2_text:
        return True
    return text_similarity(v1_text, v2_text) >= SIMILARITY_THRESHOLD


def legacy_is_moved(v1_anchor_text: str | None, v2_anchor_text: str | None, v1_text: str, v2_text: str) -> bool:
    """Whether ``_hunk_for_paired_blocks`` calls an aligned pair moved rather than modified.

    Transcribed: both anchors present, their texts differ, and body similarity reaches
    ``MOVE_THRESHOLD``. Identical bodies score 1.0, which is how the renamed-account case
    reaches ``moved``.
    """
    if v1_anchor_text is None or v2_anchor_text is None:
        return False
    if v1_anchor_text == v2_anchor_text:
        return False
    return text_similarity(v1_text, v2_text) >= MOVE_THRESHOLD


def _page(page_number: int, *lines: tuple[int, str]) -> Page:
    return Page(page_number, tuple(Line(n, t) for n, t in lines))


def _text_hunk(change_type: str, text: str, position: int) -> PdfHunk:
    """A removed/added hunk carrying only what round-2 reads: its text and a range."""
    removed = change_type == "removed"
    return PdfHunk(
        change_type=change_type,
        v1_anchor=None,
        v2_anchor=None,
        v1_range=(position, 1, position, 1) if removed else None,
        v2_range=(position, 1, position, 1) if not removed else None,
        v1_text=text if removed else "",
        v2_text=text if not removed else "",
    )


# --- Gate 2: the transcribed rules hold over the committed corpus ---------------------

_ACCEPTED = [
    (bill, old, new)
    for bill, old, new in adjacent_pdf_pairs()
    # The pairs production will actually diff. `compare.pdf` declines an unnumbered
    # (enrolled) layout; `diff_pdfs` does not, so iterating every adjacent pair would
    # pin a path no user can reach. Detected by the collapse it produces rather than by
    # importing the private predicate.
    if len(cached_pages(old)) > 1 and len(cached_pages(new)) > 1
]


@pytest.fixture(scope="module")
def diff_for():
    cache: dict[tuple, object] = {}

    def _get(old, new):
        key = (old, new)
        if key not in cache:
            cache[key] = diff_pdfs(cached_pages(old), cached_pages(new))
        return cache[key]

    return _get


def test_the_corpus_pair_list_is_not_empty() -> None:
    """A parametrization list that silently empties is the fail-open shape (#542)."""
    assert len(_ACCEPTED) >= 15, f"only {len(_ACCEPTED)} PDF pairs collected; the committed corpus holds more"


@pytest.mark.parametrize(("bill", "old", "new"), _ACCEPTED, ids=[f"{b}/{o.stem}->{n.stem}" for b, o, n in _ACCEPTED])
def test_transcribed_split_rule_agrees_with_production(bill, old, new, diff_for) -> None:
    """Every surviving pair clears the split cutoff, per the independently written rule.

    A ``modified`` or ``moved`` hunk carrying text on both sides is a pair the split rule
    kept. If production's cutoff moved, or its comparison inverted, a pair below the
    transcribed cutoff would appear here.
    """
    for hunk in diff_for(old, new).hunks:
        if hunk.change_type not in ("modified", "moved") or not (hunk.v1_text and hunk.v2_text):
            continue
        assert legacy_pair_survives(hunk.v1_text, hunk.v2_text), (
            f"{bill}: a {hunk.change_type} pair scores below SIMILARITY_THRESHOLD "
            f"({text_similarity(hunk.v1_text, hunk.v2_text):.4f} < {SIMILARITY_THRESHOLD}); "
            "production kept a pair the transcribed split rule would have split"
        )


@pytest.mark.parametrize(("bill", "old", "new"), _ACCEPTED, ids=[f"{b}/{o.stem}->{n.stem}" for b, o, n in _ACCEPTED])
def test_transcribed_move_rule_agrees_with_production(bill, old, new, diff_for) -> None:
    """Every ``moved`` hunk clears MOVE_THRESHOLD, and no ``modified`` one should have.

    The second half is the sharper direction: a ``modified`` hunk whose anchors differ and
    whose bodies clear the move cutoff is exactly what ``_hunk_for_paired_blocks`` is
    supposed to have labelled ``moved``, so its presence means the rule changed.
    """
    for hunk in diff_for(old, new).hunks:
        if not (hunk.v1_text and hunk.v2_text):
            continue
        similarity = text_similarity(hunk.v1_text, hunk.v2_text)
        if hunk.change_type == "moved":
            assert similarity >= MOVE_THRESHOLD, (
                f"{bill}: a moved hunk scores {similarity:.4f} < {MOVE_THRESHOLD}; both the "
                "aligned-pair rule and round-2 assignment require the move cutoff"
            )
        elif hunk.change_type == "modified":
            v1_anchor = hunk.v1_anchor.text if hunk.v1_anchor else None
            v2_anchor = hunk.v2_anchor.text if hunk.v2_anchor else None
            assert not legacy_is_moved(v1_anchor, v2_anchor, hunk.v1_text, hunk.v2_text), (
                f"{bill}: a modified hunk ({v1_anchor} -> {v2_anchor}, similarity "
                f"{similarity:.4f}) satisfies the transcribed moved rule; production and the "
                "transcription disagree about what a move is"
            )


def test_the_transcribed_rules_can_fail() -> None:
    """Prove both checks fire, rather than trusting two absence assertions (#299).

    Feeds each rule the input it exists to reject. Without this the two corpus sweeps above
    are green-by-default: they assert that nothing violates a rule, and a check structurally
    incapable of matching would report exactly the same thing.
    """
    assert not legacy_pair_survives("alpha bravo charlie delta echo", "one two three four five")
    assert legacy_pair_survives("alpha bravo charlie", "alpha bravo charlie")

    assert legacy_is_moved("SEC. 101", "SEC. 202", "same body text here", "same body text here")
    assert not legacy_is_moved("SEC. 101", "SEC. 101", "same body text here", "same body text here")
    assert not legacy_is_moved(None, "SEC. 202", "same body text here", "same body text here")
    assert not legacy_is_moved("SEC. 101", "SEC. 202", "alpha bravo charlie delta", "one two three four")


# --- Gate 4: the split population, which no committed fixture exercised ----------------

_SPLIT_BILL = ("118-hr-4366", "4_engrossed-amendment-senate", "5_engrossed-amendment-house")


def test_split_population_exists_and_carries_money_on_both_sides() -> None:
    """A real below-cutoff split, on a real pair, with dollar amounts on both sides.

    This is the population ADR 0020 built its money argument on, measured for PDF for the
    first time: an aligned pair scoring below the cutoff becomes a removal plus an
    addition, and money extraction then runs one-sided on each. The record measures 224
    splits over the accepted corpus, 23 of them with amounts on both sides. **None has
    been adjudicated** — what is asserted here is that the mechanism is live, not that any
    instance is wrong.

    Asserted as a floor rather than an exact count, because the exact number is a
    drift-prone value that would turn a legitimate retune into a fixture edit.
    """
    bill, old_stem, new_stem = _SPLIT_BILL
    pairs = {(b, o.stem, n.stem): (o, n) for b, o, n in adjacent_pdf_pairs()}
    old, new = pairs[(bill, old_stem, new_stem)]

    import difflib

    from deltatrack.diff_pdf import _block_key, _flatten, _group_into_blocks
    from deltatrack.parsers.pdf_anchors import extract_anchors

    v1_blocks = _group_into_blocks(_flatten(cached_pages(old)), extract_anchors(cached_pages(old)))
    v2_blocks = _group_into_blocks(_flatten(cached_pages(new)), extract_anchors(cached_pages(new)))
    matcher = difflib.SequenceMatcher(
        a=[_block_key(b) for b in v1_blocks], b=[_block_key(b) for b in v2_blocks], autojunk=False
    )

    splits = 0
    splits_with_money = 0
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            aligned = list(zip(v1_blocks[i1:i2], v2_blocks[j1:j2]))
        elif op == "replace":
            aligned = list(zip(v1_blocks[i1:i2], v2_blocks[j1:j2]))
        else:
            continue
        for a, b in aligned:
            if a.text == b.text or legacy_pair_survives(a.text, b.text):
                continue
            splits += 1
            if extract_amounts(a.text) and extract_amounts(b.text):
                splits_with_money += 1

    assert splits >= 20, f"expected a substantial split population on {bill}, found {splits}"
    assert splits_with_money >= 5, (
        f"{bill} produced {splits} splits but only {splits_with_money} with amounts on both "
        "sides; this fixture exists to keep that population non-empty"
    )


def test_split_boundary_falsifies_the_cutoff() -> None:
    """Two synthetic pairs straddling the cutoff, so the rule is pinned off-corpus too.

    The corpus case above proves the population exists; this proves the *cutoff* is what
    decides it. A change to ``SIMILARITY_THRESHOLD`` in either direction moves one of
    these two.
    """
    shared = " ".join(f"word{i}" for i in range(12))
    just_above = (f"{shared} alpha bravo charlie delta echo", f"{shared} alpha bravo charlie delta foxtrot")
    just_below = (f"{shared} alpha bravo", " ".join(f"other{i}" for i in range(14)))

    assert text_similarity(*just_above) >= SIMILARITY_THRESHOLD
    assert legacy_pair_survives(*just_above)
    assert text_similarity(*just_below) < SIMILARITY_THRESHOLD
    assert not legacy_pair_survives(*just_below)


# --- Gate 6: the positional `replace` zip ----------------------------------------------
#
# Inside a `replace` opcode, production pairs by POSITION: v1_slice[k] with v2_slice[k].
# Nothing consults similarity to form that pairing. The fixture below is built so global
# best-similarity assignment would pair the blocks the other way round, which is exactly
# the substitution a future shared XML/PDF assignment implementation might make.
#
# Similarities are asserted rather than assumed, because the fixture is only meaningful
# while the positional pairing stays ABOVE the split cutoff (so production keeps it and
# round 2 never runs) and the crossed pairing scores higher.

_SHARED_HEAD = "For necessary expenses necessary to carry out the"
_ALPHA_OLD = "for the Alpha Directorate salaries and expenses account, $1,000,000, to remain available until expended"
_ALPHA_NEW = "for the Alpha Directorate salaries and expenses account, $1,500,000, to remain available until expended"
_BRAVO_OLD = "for the Bravo Commission construction and land acquisition account, $9,000,000, until September 30"
_BRAVO_NEW = "for the Bravo Commission construction and land acquisition account, $9,900,000, until September 30"

_OLD_1 = f"SEC. 101. {_SHARED_HEAD} {_ALPHA_OLD}"
_OLD_2 = f"SEC. 102. {_SHARED_HEAD} {_BRAVO_OLD}"
_NEW_1 = f"SEC. 201. {_SHARED_HEAD} {_BRAVO_NEW}"
_NEW_2 = f"SEC. 202. {_SHARED_HEAD} {_ALPHA_NEW}"


def test_positional_replace_fixture_has_the_shape_it_claims() -> None:
    """The fixture's preconditions, asserted so it cannot rot into a tautology.

    If a future extraction change made the positional pairing fall below the split cutoff,
    production would split and reconcile instead, and the gate below would be testing a
    different mechanism while still passing.
    """
    positional = min(text_similarity(_OLD_1, _NEW_1), text_similarity(_OLD_2, _NEW_2))
    crossed = min(text_similarity(_OLD_1, _NEW_2), text_similarity(_OLD_2, _NEW_1))
    assert positional >= SIMILARITY_THRESHOLD, f"positional {positional:.4f} would split, not pair"
    assert crossed > positional, f"crossed {crossed:.4f} must beat positional {positional:.4f} to discriminate"


def test_positional_replace_pairing_is_what_production_emits() -> None:
    """Production pairs by position inside a ``replace``, not by best similarity."""
    diff = diff_pdfs([_page(1, (1, _OLD_1), (2, _OLD_2))], [_page(1, (1, _NEW_1), (2, _NEW_2))])
    paired = {
        (h.v1_anchor.text, h.v2_anchor.text) for h in diff.hunks if h.v1_anchor is not None and h.v2_anchor is not None
    }
    assert paired == {("SEC. 101", "SEC. 201"), ("SEC. 102", "SEC. 202")}, (
        f"production no longer pairs positionally inside a replace: {sorted(paired)}"
    )


def test_global_best_similarity_would_cross_the_positional_pairing() -> None:
    """MUTATION: replace the positional rule with global best-similarity assignment.

    Named fault injection for gate 6. The mutation is applied to a local re-implementation
    of the pairing step rather than to production, because production is not being changed
    in this slice; what it establishes is that the two rules disagree on this fixture, so
    the gate above is capable of failing when a later slice substitutes one for the other.
    """
    old_blocks = [_OLD_1, _OLD_2]
    new_blocks = [_NEW_1, _NEW_2]

    positional = {(0, 0), (1, 1)}
    scored = sorted(
        ((text_similarity(o, n), i, j) for i, o in enumerate(old_blocks) for j, n in enumerate(new_blocks)),
        reverse=True,
    )
    claimed_old: set[int] = set()
    claimed_new: set[int] = set()
    global_best: set[tuple[int, int]] = set()
    for _score, i, j in scored:
        if i in claimed_old or j in claimed_new:
            continue
        claimed_old.add(i)
        claimed_new.add(j)
        global_best.add((i, j))

    assert global_best == {(0, 1), (1, 0)}, f"the mutation did not cross as designed: {sorted(global_best)}"
    assert global_best != positional, "the mutation must change the pairing, or gate 6 pins nothing"


# --- Gate 7: round-2 greedy competition and exclusivity --------------------------------
#
# Production sorts `(similarity, removed_index, added_index)` descending and claims greedily
# with one-to-one exclusivity. Four mutations are applied one at a time, each to a local
# re-implementation, and each must change the selected link set.

_CORE = "None of the funds made available by this Act may be used to finalize implement or enforce the proposed rule"
_X = f"{_CORE} concerning migratory bird habitat conservation published in the Federal Register on March 1 2024"
_Y = f"{_CORE} concerning migratory bird habitat conservation published in the Register on March 1 2024"
_P = f"{_CORE} concerning migratory bird habitat conservation published in the Federal Register on March 8 2024"
_Q = f"{_CORE} concerning migratory bird habitat conservation published in the Register"


def _candidates() -> list[tuple[float, str, str]]:
    """Round-2 candidates for the fixture, labelled, from production's own retriever.

    ``move_candidates`` is production's, so the scores and the eligibility cutoff are
    production's too; only the labelling is local. The mutations below then differ from
    production in exactly one respect each — the selection rule — rather than also in how
    the candidates were scored.
    """
    labels_removed = ["X", "Y"]
    labels_added = ["P", "Q"]
    return [
        (score, labels_removed[r], labels_added[a])
        for score, r, a in move_candidates([_X, _Y], [_P, _Q], MOVE_THRESHOLD)
    ]


def _greedy(candidates, *, reverse: bool = True) -> set[tuple[str, str]]:
    claimed_r: set[str] = set()
    claimed_a: set[str] = set()
    out: set[tuple[str, str]] = set()
    for _score, r, a in sorted(candidates, reverse=reverse):
        if r in claimed_r or a in claimed_a:
            continue
        claimed_r.add(r)
        claimed_a.add(a)
        out.add((r, a))
    return out


def test_competition_fixture_has_four_distinct_scores() -> None:
    """Preconditions for the mutations below, asserted rather than assumed.

    Distinct scores are what let the ordering mutation be tested separately from the tie
    mutation; a fixture that quietly collapsed to a tie would make two of the four
    mutations the same experiment while both still passed.
    """
    scores = [round(s, 6) for s, _r, _a in _candidates()]
    assert len(scores) == 4, f"expected all four pairings above the move cutoff, got {len(scores)}"
    assert len(set(scores)) == 4, f"scores must be distinct to separate the mutations: {scores}"


def test_greedy_selection_is_what_production_emits() -> None:
    """Production's round-2 selection on the fixture, through ``_reconcile_moves`` itself."""
    hunks = [
        _text_hunk("removed", _X, 1),
        _text_hunk("removed", _Y, 2),
        _text_hunk("added", _P, 3),
        _text_hunk("added", _Q, 4),
    ]
    result = _reconcile_moves(list(hunks))
    moved = {(h.v1_text, h.v2_text) for h in result if h.change_type == "moved"}
    assert moved == {(_X, _P), (_Y, _Q)}, (
        "round-2 selection changed; production paired "
        f"{[('X' if v1 == _X else 'Y', 'P' if v2 == _P else 'Q') for v1, v2 in sorted(moved)]}"
    )
    assert all(h.change_type == "moved" for h in result), "every input hunk should have been consumed by a move"


@pytest.mark.parametrize(
    "mutation",
    ["ascending_order", "independent_best_partner", "no_exclusivity", "tie_broken_the_other_way"],
)
def test_each_greedy_mutation_changes_the_selection(mutation: str) -> None:
    """MUTATION: four separate changes to round-2 competition, one at a time.

    Named fault injections for gate 7. Each must change the selected link set, or the gate
    above is pinning a decision that nothing actually depends on. ``no_exclusivity`` and
    ``independent_best_partner`` are deliberately distinct: the first lets one observation
    take several partners, the second keeps one partner each but removes the competition
    between them.
    """
    candidates = _candidates()
    production = _greedy(candidates)
    assert production == {("X", "P"), ("Y", "Q")}

    if mutation == "ascending_order":
        mutated = _greedy(candidates, reverse=False)
    elif mutation == "independent_best_partner":
        mutated = {(r, max((c for c in candidates if c[1] == r), key=lambda c: c[0])[2]) for _s, r, _a in candidates}
    elif mutation == "no_exclusivity":
        mutated = {(r, a) for _s, r, a in candidates}
    else:  # tie_broken_the_other_way
        # The tie has to be on the CONTESTED partner to mean anything. Collapsing all four
        # scores does not discriminate: exclusivity still admits two disjoint pairs and
        # ascending selects the same set, so that experiment would pass while testing
        # nothing. Instead tie only X->P against Y->P, which forces the tiebreak to decide
        # who takes P.
        top = max(score for score, _r, a in candidates if a == "P")
        tied = [(top if a == "P" else score, r, a) for score, r, a in candidates]

        # Production's key is (score, removed, added) sorted descending, so a tie falls to
        # the LATER removal. The mutation flips ONLY the index component -- highest score
        # still first, but a tie now falls to the earlier removal. Sorting everything
        # ascending instead would not isolate the tiebreak: on this fixture the Q scores
        # reorder to compensate and the selected set comes out identical, which would make
        # the experiment pass while testing nothing.
        production_tied = _greedy(tied)
        assert ("Y", "P") in production_tied, (
            f"descending tiebreak should give the contested partner to the later removal, got {production_tied}"
        )

        claimed_r: set[str] = set()
        claimed_a: set[str] = set()
        mutated = set()
        for _score, r, a in sorted(tied, key=lambda c: (-c[0], c[1], c[2])):
            if r in claimed_r or a in claimed_a:
                continue
            claimed_r.add(r)
            claimed_a.add(a)
            mutated.add((r, a))
        assert ("X", "P") in mutated, f"the flipped tiebreak should give P to the earlier removal, got {mutated}"
        assert mutated != production_tied, (
            "flipping the tiebreak must change the selection, or the descending index rule is decorative"
        )
        # This branch returns rather than falling through to the shared comparison below.
        # It perturbs the SCORES (to manufacture a tie) as well as the rule, so the right
        # control is production's rule on the tied fixture -- asserted just above. Comparing
        # it against production's selection on the UNTIED fixture would conflate the two
        # changes, and on this fixture the two happen to coincide, so that comparison would
        # report a failure that means nothing.
        return

    assert mutated != production, (
        f"mutation {mutation!r} produced the same selection as production ({sorted(production)}); "
        "gate 7 would pass whether or not this rule held"
    )
