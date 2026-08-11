"""What a pre-classification second retrieval round would have to reproduce exactly.

Investigation D for the #581 prerequisite. ADR 0020 forbids retrieval after
classification, so ``reconcile_moves`` -- a second retrieval plus assignment pass running
over already-classified changes -- eventually has to move ahead of classification. Two
things decide whether that is a behaviour-preserving move or a behaviour change, and
neither is measured by the probes committed with #586:

**A. The input population.** ``probe_splits.py`` measures that 327 path-matched pairings
are replaced by a removal plus an addition, and says explicitly that their overlap with
the move population is NOT measured. Without that overlap, "move the round earlier" is
unscoped. This measures how much of the candidate and selected-move population depends on
an observation that only exists because the similarity rule revoked its pairing.

**B. The ordering key.** Production sorts candidates by ``(similarity, ri, ai)``, where
``ri``/``ai`` are positions in the FILTERED removed/added lists. An extraction that
replaced that key with ADR 0019 ordinals would preserve behaviour only if the two
orderings agree. This runs both keys through the same greedy loop and compares the
selected correspondence -- set and order -- pair by pair.

    The answer is that they do NOT agree, so ``(similarity, ri, ai)`` is legacy filtered-list
    ordering policy that Phase 1 must preserve exactly. Parser ordinals are the
    architectural address; they are not a drop-in for this sort key, and substituting them
    is a behaviour change that moves canonical bytes. Sections C and D size that, and
    ``probe_canonical_sensitivity.py`` shows the canonical gate seeing it.

WHAT #591 CHANGED, because it changes what A *means* without moving a single number.
Before #591 the similarity cutoff ran inside ``diff_bills``' classification loop, so the
removal and the addition it produced did not exist until classification had run, and a
retrieval round placed before classification could not have seen them at all. #591 moved
that decision into :func:`~deltatrack.diff_bill.apply_similarity_revocation`, which runs
*ahead* of the loop. The two observations are now separated before classification, so a
round-2 pass placed after that stage does see them.

    The population figure is therefore no longer evidence that the round cannot move. It
    now sizes a SEQUENCING CONSTRAINT INSIDE ASSIGNMENT: round 2 must run after the
    similarity revocation, not merely before classification. What still blocks a literal
    relocation is representational, not populational -- ``reconcile_moves`` consumes
    ``NodeDiff`` records, which are classification output, so it would have to be
    re-expressed over observations. Every field it reads (``old_text``, ``new_text``,
    ``element_id_old``/``_new``, ``display_path_*``, ``match_path``, ``section_number``,
    the amount texts) is derivable from the ``BillNode`` pair, so that is a mechanical
    change owing its own evidence rather than an obstacle.

    This slice does not make #591 into ADR 0020's Assignment stage. ``match_nodes`` still
    owns ``match_path`` grouping, division subgrouping, the cross-division fallback and
    ``_similarity_pair``'s unthresholded greedy claim, and ``reconcile_moves`` still runs
    after classification.

Accordingly this says "revoked" and "revocation-produced" throughout. The pre-#591
architecture is the only place "classification-created" was ever true. The figures below
were first measured on this branch at c3b6387, whose base af83c28 differs from the last
pre-#591 develop (97f91ba) by documentation only; they are unchanged post-#591, which is
itself independent evidence that #591 preserved the population.

Section E then measures the "representational, not populational" claim above rather than
leaving it as reasoning, since it is the sentence the next slice rests on -- and it
compares ORDERED element-id sequences, not counts, because legacy ``(ri, ai)`` is a
position in those very lists.

FAIL-CLOSED THROUGHOUT, because the numbers are void without it:

    - The revocation population is derived from an exact STRUCTURAL WALK of
      ``match_nodes`` output to ``apply_similarity_revocation`` output, by object
      identity (:func:`revoked_pairings`). Equal cardinality is not enough: the same
      count of the wrong pairings is a false green, so every input tuple must appear
      either unchanged or as its own two halves, in place, carrying the same objects.
    - That structural population is then cross-checked against production's own
      ``pairing_survives_similarity_rule``, again by object identity rather than by count.
      A lookalike condition -- ``old_norm != new_norm`` in place of the ``diff_text``
      emptiness gate -- agrees on all 15,034 corpus pairings today, and that agreement is
      a measurement rather than a guarantee. Reading production removes the question.
    - ``element_id`` is used only as a MEASUREMENT BRIDGE from a ``NodeDiff`` back to the
      node it came from, since ``NodeDiff`` carries no node reference. It is not proposed
      as identity (ADR 0019 refuses that). The probe asserts uniqueness and non-emptiness
      per side and stops if either fails.
    - The duplicated greedy loop must reproduce production's selected set AND order under
      the production key before any comparison figure is printed. A drifted duplicate
      would be comparing the ordinal key against itself rather than against production.
    - Section E compares ordered element-id sequences per pair and stops on the first
      divergence, naming its index.
    - Every headline figure is PINNED (:data:`PINNED`, :data:`ORDINAL_SENSITIVE_PAIRS`).
      A drift fails the run rather than printing a new number for someone to notice.

Read-only, writes nothing. Exits non-zero on any failure. Run from the project root:

    uv run python scripts/probe_round2_migration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deltatrack.diff_bill as db  # noqa: E402
from deltatrack.compare.xml import compare_xml  # noqa: E402
from deltatrack.similarity import MOVE_THRESHOLD, move_candidates  # noqa: E402
from deltatrack.version_stems import label_from_stem  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs  # noqa: E402

REAL_MATCH_NODES = db.match_nodes
REAL_REVOCATION = db.apply_similarity_revocation
REAL_RECONCILE = db.reconcile_moves

#: The corpus pairs whose SELECTED MOVE SET changes when ADR 0019 parser ordinals are
#: substituted for the legacy ``(ri, ai)`` component of the sort key. Shared with
#: ``probe_canonical_sensitivity.py``, which requires exactly these to redden -- one home
#: for one fact, so the two probes cannot drift into disagreeing about which pairs matter.
ORDINAL_SENSITIVE_PAIRS = (
    "114-hr-2029/5_engrossed-amendment-senate->6_engrossed-amendment-house",
    "115-hr-5895/2_engrossed-in-house->4_engrossed-amendment-senate",
    "118-hr-4366/4_engrossed-amendment-senate->5_engrossed-amendment-house",
)

#: The Phase-1 preservation baseline: what the committed corpus measures TODAY.
#:
#: HISTORICAL BEHAVIOUR, NOT ADR POLICY. None of these numbers is a target, a requirement
#: or a thing ADR 0020 asks for. They are pinned for one reason: a Phase-1 slice claims to
#: preserve matching behaviour, so a figure that moves is either a regression or an
#: intentional change owing evidence -- and both deserve a failing run rather than a new
#: number printed where a reader has to remember the old one. Update deliberately, in a
#: commit that says which slice moved it and why.
PINNED = {
    "corpus pairs": 27,
    "move candidates": 1054,
    "pairs carrying candidates": 16,
    "selected moves": 496,
    "selected moves touching a revocation-produced side": 228,
    "selected moves with both sides revocation-produced": 145,
    "pairs where the ordinal key changes the selected set": 3,
    "pairs where the ordinal key changes only selection order": 0,
    "selected-link symmetric difference under the ordinal key": 20,
}


def capture() -> dict[str, dict]:
    """Per corpus pair: the trees, ``match_nodes`` output, the revocation stage's output,
    and ``reconcile_moves``' input.

    All captured by wrapping the production functions inside a real ``compare_xml`` run,
    so every value measured is the value production actually produced rather than a
    reconstruction of it.
    """
    captured: dict[str, dict] = {}
    holder: dict[str, str] = {}

    def match_spy(old, new):
        pairs = REAL_MATCH_NODES(old, new)
        captured.setdefault(holder["key"], {}).update(old_tree=old, new_tree=new, pairs=pairs)
        return pairs

    def revocation_spy(pairs):
        decided = REAL_REVOCATION(pairs)
        captured.setdefault(holder["key"], {})["decided"] = decided
        return decided

    def reconcile_spy(changes, threshold=MOVE_THRESHOLD):
        captured.setdefault(holder["key"], {})["changes"] = list(changes)
        return REAL_RECONCILE(changes, threshold)

    db.match_nodes = match_spy
    db.apply_similarity_revocation = revocation_spy
    db.reconcile_moves = reconcile_spy
    try:
        for key, old_path, new_path in baseline_pairs():
            holder["key"] = key
            compare_xml(
                old_path.read_bytes(),
                new_path.read_bytes(),
                start_label=label_from_stem(old_path.stem),
                end_label=label_from_stem(new_path.stem),
            )
    finally:
        db.match_nodes = REAL_MATCH_NODES
        db.apply_similarity_revocation = REAL_REVOCATION
        db.reconcile_moves = REAL_RECONCILE
    return captured


def ordinal_bridge(nodes: list, key: str) -> dict[str, int]:
    """``{element_id: ordinal}``, refusing to build if the bridge is not one-to-one."""
    ids = [node.element_id for node in nodes]
    if not all(ids):
        raise SystemExit(f"{key}: an element_id is empty; the measurement bridge is unusable")
    if len(set(ids)) != len(ids):
        raise SystemExit(f"{key}: element_id repeats; the measurement bridge would hit the wrong node")
    return {element_id: ordinal for ordinal, element_id in enumerate(ids)}


def revoked_pairings(pairs: list, decided: list, key: str) -> list[tuple]:
    """The pairings the revocation stage ACTUALLY revoked, by an exact structural walk.

    Counting the extra tuples would prove equal cardinality and nothing else: revoking the
    same NUMBER of different pairings would pass that check while every downstream
    population figure described the wrong observations. So this walks the input to the
    output by object identity and requires each input tuple to appear as exactly one of:

    unchanged
        the next output tuple, carrying the same two object identities;

    revoked
        the next TWO output tuples, exactly ``(old, None)`` then ``(None, new)``, carrying
        those same two objects, adjacent and in place.

    Any substitution, reordering, wrong partner, omission, duplication, unexpected shape or
    trailing output tuple exits non-zero.
    """
    revoked: list[tuple] = []
    out = 0
    for position, (old_node, new_node) in enumerate(pairs):
        if out >= len(decided):
            raise SystemExit(f"{key}: revocation output ran out at input tuple {position}; observations were dropped")
        first_old, first_new = decided[out]

        if first_old is old_node and first_new is new_node:
            out += 1
            continue

        if old_node is None or new_node is None:
            raise SystemExit(
                f"{key}: input tuple {position} was already unmatched but the stage did not pass it through "
                f"unchanged; only a two-sided pairing may be revoked"
            )
        if out + 1 >= len(decided):
            raise SystemExit(f"{key}: input tuple {position} looks revoked but its second half is missing")
        second_old, second_new = decided[out + 1]
        if not (first_old is old_node and first_new is None and second_old is None and second_new is new_node):
            raise SystemExit(
                f"{key}: input tuple {position} was not replaced by its own two halves in order. "
                f"Expected (old, None) then (None, new) carrying the same objects; a substitution, a "
                f"reordered replacement or a wrong partner is present."
            )
        revoked.append((old_node, new_node))
        out += 2

    if out != len(decided):
        raise SystemExit(f"{key}: {len(decided) - out} trailing revocation output tuple(s) match no input tuple")
    return revoked


def cross_check_revocations(pairs: list, revoked: list, key: str) -> None:
    """The structural population must be the population production's predicate names.

    Compared as sets of object identities, not as counts: the whole point of the
    structural walk is that a same-count/wrong-pairing result must not read as agreement.
    """
    structural = {(id(old), id(new)) for old, new in revoked}
    predicate = {
        (id(old), id(new))
        for old, new in pairs
        if old is not None and new is not None and not db.pairing_survives_similarity_rule(old, new)
    }
    if structural != predicate:
        raise SystemExit(
            f"{key}: the revocation stage and pairing_survives_similarity_rule name DIFFERENT populations. "
            f"stage revoked {len(structural)}, predicate revoked {len(predicate)}, "
            f"{len(structural - predicate)} revoked by the stage alone, "
            f"{len(predicate - structural)} by the predicate alone"
        )


def assert_ordered_identity(key: str, side: str, observed: list[str], expected: list[str]) -> None:
    """Two element-id sequences must be equal element-for-element AND in order.

    Set or count equality would pass a reordering, and legacy ``(ri, ai)`` is a position
    in exactly these lists, so a reordering is precisely the failure that matters.
    """
    if observed == expected:
        return
    if len(observed) != len(expected):
        raise SystemExit(f"{key} [{side}]: {len(observed)} unmatched observations but {len(expected)} change records")
    index = next(i for i, (a, b) in enumerate(zip(observed, expected)) if a != b)
    raise SystemExit(
        f"{key} [{side}]: same count, DIFFERENT sequence. First divergence at index {index}: "
        f"observation {observed[index]!r} vs change record {expected[index]!r}. "
        f"A substitution or a reorder, either of which moves the legacy (ri, ai) key."
    )


def filtered_sides(changes: list) -> tuple[list, list]:
    """The removed/added lists ``reconcile_moves`` builds, in its own order."""
    removed = [(i, c) for i, c in enumerate(changes) if c.change_type == "removed"]
    added = [(i, c) for i, c in enumerate(changes) if c.change_type == "added"]
    return removed, added


def greedy(ordered: list[tuple], removed: list, added: list) -> list[tuple[str, str]]:
    """Production's greedy exclusivity loop over an already-ordered candidate list."""
    claimed_r: set[int] = set()
    claimed_a: set[int] = set()
    selected: list[tuple[str, str]] = []
    for _sim, ri, ai in ordered:
        if ri in claimed_r or ai in claimed_a:
            continue
        claimed_r.add(ri)
        claimed_a.add(ai)
        selected.append((removed[ri][1].element_id_old, added[ai][1].element_id_new))
    return selected


def production_signature(changes: list) -> list[tuple[str, str]]:
    """The real function's selected moves, in emission order, keyed by element id."""
    return [(c.element_id_old, c.element_id_new) for c in REAL_RECONCILE(list(changes)) if c.change_type == "moved"]


def report_input_availability(captured: dict[str, dict]) -> None:
    """Section E: do the unmatched observations survive classification in identity AND order?

    Section B says the remaining obstacle to relocating round 2 is representational rather
    than populational. That is a claim about availability, so it is measured rather than
    argued -- and measured as ORDERED SEQUENCES, because equal counts would leave the
    useful part unproven. Legacy ``(ri, ai)`` is a position in the filtered removed/added
    lists, so "the same observations, in the same order" is the preservation fact the
    relocation actually needs; "the same number of them" is not.

    Establishes: *classification preserves the exact identity and order of the unmatched
    observations that form round 2's filtered removal and addition lists.*
    """
    old_total = new_total = 0

    for key in sorted(captured):
        decided = captured[key]["decided"]
        removed, added = filtered_sides(captured[key]["changes"])

        observed_old = [old.element_id for old, new in decided if old is not None and new is None]
        observed_new = [new.element_id for old, new in decided if old is None and new is not None]
        expected_old = [change.element_id_old for _, change in removed]
        expected_new = [change.element_id_new for _, change in added]

        assert_ordered_identity(key, "old side", observed_old, expected_old)
        assert_ordered_identity(key, "new side", observed_new, expected_new)
        old_total += len(observed_old)
        new_total += len(observed_new)

    print("\n===== E: IS ROUND 2's INPUT AVAILABLE BEFORE CLASSIFICATION? =====")
    print(f"unmatched OLD observations, identical and in order through classification: {old_total}")
    print(f"unmatched NEW observations, identical and in order through classification: {new_total}")
    print(f"pairs compared as ordered element-id sequences: {len(captured)} (not counts, not sets)")
    print("Every removal and addition round 2 consumes is already an unmatched observation")
    print("before classification runs, in the same order, so what a relocation has to")
    print("rebuild is the NodeDiff representation, not the population or its ordering.")


def check_pinned(observed: dict[str, int], ordinal_pairs: list[str]) -> None:
    """Fail on any drift from the recorded Phase-1 baseline."""
    drifted = [(name, PINNED[name], observed[name]) for name in PINNED if PINNED[name] != observed[name]]
    keys_ok = tuple(sorted(ordinal_pairs)) == tuple(sorted(ORDINAL_SENSITIVE_PAIRS))
    if not drifted and keys_ok:
        print("\nPINNED: every headline figure matches the recorded Phase-1 baseline.")
        return

    print("\nPINNED BASELINE DRIFT -- this is a review gate, not a number to update in passing:")
    for name, expected, actual in drifted:
        print(f"  {name}: expected {expected}, observed {actual}")
    if not keys_ok:
        print(f"  ordinal-sensitive pairs: expected {list(ORDINAL_SENSITIVE_PAIRS)}, observed {ordinal_pairs}")
    raise SystemExit(
        "matching behaviour moved. Phase 1 claims to preserve it, so this is either a regression "
        "or an intentional change owing evidence; both need a human, not a silent new number."
    )


def main() -> None:
    captured = capture()

    total_candidates = 0
    total_selected = 0
    cand_revoked_removal = 0
    cand_revoked_addition = 0
    cand_revoked_either = 0
    cand_revoked_both = 0
    sel_revoked_removal = 0
    sel_revoked_addition = 0
    sel_revoked_either = 0
    sel_revoked_both = 0
    revoked_removals_in_input = 0
    revoked_additions_in_input = 0
    removals_in_input = 0
    additions_in_input = 0

    monotone_removed = 0
    monotone_added = 0
    pairs_with_candidates = 0

    agreement_failures: list[str] = []
    ordinal_key_differs: list[str] = []
    ordinal_key_order_only: list[str] = []
    ordinal_selection_delta = 0

    for key in sorted(captured):
        record = captured[key]
        changes = record["changes"]
        old_at = ordinal_bridge(record["old_tree"].nodes, key + " [old]")
        new_at = ordinal_bridge(record["new_tree"].nodes, key + " [new]")

        revoked = revoked_pairings(record["pairs"], record["decided"], key)
        cross_check_revocations(record["pairs"], revoked, key)
        revoked_old = {old.element_id for old, _ in revoked}
        revoked_new = {new.element_id for _, new in revoked}

        removed, added = filtered_sides(changes)
        removals_in_input += len(removed)
        additions_in_input += len(added)
        revoked_removals_in_input += sum(1 for _, c in removed if c.element_id_old in revoked_old)
        revoked_additions_in_input += sum(1 for _, c in added if c.element_id_new in revoked_new)

        if not removed or not added:
            continue

        candidates = move_candidates(
            [db._normalize_text(rc.old_text or "") for _, rc in removed],
            [db._normalize_text(ac.new_text or "") for _, ac in added],
            MOVE_THRESHOLD,
        )
        if not candidates:
            continue
        pairs_with_candidates += 1
        total_candidates += len(candidates)

        removed_is_revoked = [c.element_id_old in revoked_old for _, c in removed]
        added_is_revoked = [c.element_id_new in revoked_new for _, c in added]
        for _sim, ri, ai in candidates:
            r_revoked = removed_is_revoked[ri]
            a_revoked = added_is_revoked[ai]
            cand_revoked_removal += r_revoked
            cand_revoked_addition += a_revoked
            cand_revoked_either += r_revoked or a_revoked
            cand_revoked_both += r_revoked and a_revoked

        # --- ordering: is the filtered-list order the parser-ordinal order? -----------
        removed_ordinals = [old_at[c.element_id_old] for _, c in removed]
        added_ordinals = [new_at[c.element_id_new] for _, c in added]
        monotone_removed += removed_ordinals == sorted(removed_ordinals)
        monotone_added += added_ordinals == sorted(added_ordinals)

        # --- the two keys, through one greedy loop ------------------------------------
        production_order = sorted(candidates, reverse=True)
        replayed = greedy(production_order, removed, added)
        actual = production_signature(changes)
        if replayed != actual:
            agreement_failures.append(key)
            continue

        total_selected += len(actual)
        selected_index = {
            (removed[ri][1].element_id_old, added[ai][1].element_id_new): (ri, ai) for _sim, ri, ai in production_order
        }
        for link in actual:
            ri, ai = selected_index[link]
            r_revoked = removed_is_revoked[ri]
            a_revoked = added_is_revoked[ai]
            sel_revoked_removal += r_revoked
            sel_revoked_addition += a_revoked
            sel_revoked_either += r_revoked or a_revoked
            sel_revoked_both += r_revoked and a_revoked

        ordinal_order = sorted(
            candidates,
            key=lambda c: (c[0], removed_ordinals[c[1]], added_ordinals[c[2]]),
            reverse=True,
        )
        by_ordinal = greedy(ordinal_order, removed, added)
        if by_ordinal != actual:
            if set(by_ordinal) == set(actual):
                ordinal_key_order_only.append(key)
            else:
                ordinal_key_differs.append(key)
                ordinal_selection_delta += len(set(actual) ^ set(by_ordinal))

    if agreement_failures:
        print("DUPLICATE-LOOP AGREEMENT FAILURES -- every figure below would be void:")
        for key in agreement_failures:
            print(f"  {key}")
        raise SystemExit("duplicated greedy loop disagrees with production")

    print("===== A: INPUT POPULATION OF THE SECOND PASS =====")
    print(f"removals reaching reconcile_moves: {removals_in_input}")
    print(f"  of those, LEFT UNMATCHED BY THE SIMILARITY RULE (path-matched then revoked): {revoked_removals_in_input}")
    print(f"additions reaching reconcile_moves: {additions_in_input}")
    print(f"  of those, LEFT UNMATCHED BY THE SIMILARITY RULE: {revoked_additions_in_input}")

    print("\n===== B: HOW MUCH OF THE MOVE POPULATION DEPENDS ON A REVOKED PAIRING =====")
    print(f"candidates: {total_candidates}")
    print(f"  with a revocation-produced REMOVAL: {cand_revoked_removal}")
    print(f"  with a revocation-produced ADDITION: {cand_revoked_addition}")
    print(f"  with either side revocation-produced: {cand_revoked_either}")
    print(f"  with BOTH sides revocation-produced: {cand_revoked_both}")
    print(f"selected moves: {total_selected}")
    print(f"  with a revocation-produced REMOVAL: {sel_revoked_removal}")
    print(f"  with a revocation-produced ADDITION: {sel_revoked_addition}")
    print(f"  with either side revocation-produced: {sel_revoked_either}")
    print(f"  with BOTH sides revocation-produced: {sel_revoked_both}")
    if total_selected:
        print(
            f"  share of selected moves touching a revoked pairing: {100.0 * sel_revoked_either / total_selected:.1f}%"
        )
    print("  (post-#591 this sizes an ORDERING constraint inside assignment -- round 2 must")
    print("   run after the revocation stage -- not a dependency on classification output.)")

    print("\n===== C: IS THE (ri, ai) ORDER THE PARSER-ORDINAL ORDER? =====")
    print(f"pairs carrying candidates: {pairs_with_candidates}")
    print(f"  removed list already in parser-ordinal order: {monotone_removed}")
    print(f"  added list already in parser-ordinal order: {monotone_added}")

    print("\n===== D: SUBSTITUTING ORDINALS FOR (ri, ai) IN THE SORT KEY =====")
    print(f"pairs where the SELECTED SET changes: {len(ordinal_key_differs)} {ordinal_key_differs}")
    print(f"pairs where only the SELECTION ORDER changes: {len(ordinal_key_order_only)} {ordinal_key_order_only}")
    print(f"selected links added or lost by the ordinal key: {ordinal_selection_delta}")
    print("So (similarity, ri, ai) is legacy ordering POLICY, not an incidental tiebreak:")
    print("Phase 1 must carry it across unchanged rather than re-derive it from ordinals.")
    print("\nGUARD: the replay reproduced production's set AND order on every pair above,")
    print("and the revocation stage's structural population matched the predicate exactly.")

    report_input_availability(captured)

    check_pinned(
        {
            "corpus pairs": len(captured),
            "move candidates": total_candidates,
            "pairs carrying candidates": pairs_with_candidates,
            "selected moves": total_selected,
            "selected moves touching a revocation-produced side": sel_revoked_either,
            "selected moves with both sides revocation-produced": sel_revoked_both,
            "pairs where the ordinal key changes the selected set": len(ordinal_key_differs),
            "pairs where the ordinal key changes only selection order": len(ordinal_key_order_only),
            "selected-link symmetric difference under the ordinal key": ordinal_selection_delta,
        },
        ordinal_key_differs,
    )


if __name__ == "__main__":
    main()
