"""What the pre-classification second retrieval round had to reproduce, and now does.

Investigation D for the #581 prerequisite, re-aimed once the migration landed. ADR 0020 forbids
retrieval after classification, so ``reconcile_moves`` -- a second retrieval plus assignment pass
running over already-classified changes -- had to move ahead of classification. It has: round 2 is
now ``diff_bill``'s ``unmatched_population`` -> ``retrieve_move_candidates`` ->
``move_correspondence_evidence`` -> ``assign_moves``, all before ``classify``.

This keeps measuring the corpus characteristics that decided whether that move could be
behaviour-preserving, against the LIVE stages rather than against the retired function:

**A. The input population.** How much of the candidate and selected-move population depends on an
observation that exists only because the similarity rule revoked its pairing. Post-#591 this sizes
a SEQUENCING constraint inside matching -- round 2 must run after the revocation stage -- rather
than a dependency on classification output.

**B. The ordering key.** Production sorts candidates by ``(similarity, ri, ai)``, where ``ri``/``ai``
are positions in the unmatched population. An extraction that replaced that key with ADR 0019
ordinals would preserve behaviour only if the two orderings agreed.

    They do NOT agree, so ``(similarity, ri, ai)`` is legacy filtered-list ordering policy that
    Phase 1 had to preserve exactly. Parser ordinals are the architectural address; they are not a
    drop-in for this sort key, and substituting them is a behaviour change that moves canonical
    bytes. ``probe_canonical_sensitivity.py`` shows the canonical gate seeing it.

WHAT THE SLICE CHANGED HERE, because it removes work rather than adding it. This probe used to
carry its own copy of ``reconcile_moves``' greedy loop, plus a guard that the copy reproduced
production's selected set and order before any comparison figure was printed -- without that guard
it would have been comparing the ordinal key against a drifted duplicate. Both are gone. The
legacy transcription now has ONE home, in ``tests/test_assignment_classification_boundary.py``,
where a standing test asserts it agrees with production on every corpus pair. Importing it from
there means this probe and that gate cannot drift into disagreeing about what the pre-slice
engine did.

Section E is likewise retired. It asked whether round 2's input survived classification in
identity and order, because the answer decided whether the round could be relocated at all. The
round no longer runs after classification, so the question is closed: ``unmatched_population``
derives the population from the pairing stream directly, and its equality with the legacy
filtered lists is now a test rather than a measurement.

FAIL-CLOSED THROUGHOUT, because the numbers are void without it:

    - The revocation population is derived from an exact STRUCTURAL WALK of ``match_nodes`` output
      to ``apply_similarity_assignment_rule`` output, by object identity (:func:`revoked_pairings`).
      Equal cardinality is not enough: the same count of the wrong pairings is a false green, so
      every input tuple must appear either unchanged or as its own two halves, in place, carrying
      the same objects.
    - That structural population is then cross-checked against production's own
      ``_similarity_rule_keeps``, reading the evidence by ADR 0019 observation address and
      comparing by object identity rather than by count. A lookalike condition --
      ``old_norm != new_norm`` in place of the ``diff_text`` emptiness gate -- agrees on all
      15,034 corpus pairings today, and that agreement is a measurement rather than a guarantee.
      Reading production removes the question.
    - Every headline figure is PINNED (:data:`PINNED`, :data:`ORDINAL_SENSITIVE_PAIRS`). A drift
      fails the run rather than printing a new number for someone to notice.

Read-only, writes nothing. Exits non-zero on any failure. Run from the project root:

    uv run python scripts/probe_round2_migration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deltatrack.diff_bill as db  # noqa: E402
from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import (  # noqa: E402
    WORD_OVERLAP,
    apply_similarity_assignment_rule,
    assign_moves,
    match_nodes,
    move_correspondence_evidence,
    observation_registry,
    retrieve_move_candidates,
    similarity_correspondence_evidence,
    unmatched_population,
)
from deltatrack.matching import NEW, OLD  # noqa: E402
from deltatrack.similarity import MOVE_THRESHOLD, SIMILARITY_THRESHOLD  # noqa: E402
from tests.test_assignment_classification_boundary import (  # noqa: E402
    legacy_change_records,
    legacy_selected_links,
)
from tests.test_canonical_baseline import baseline_pairs  # noqa: E402

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


def cross_check_revocations(pairs: list, revoked: list, registry, round1_evidence, key: str) -> None:
    """The structural population must be the population production's rule names.

    Compared as sets of object identities, not as counts: the whole point of the
    structural walk is that a same-count/wrong-pairing result must not read as agreement.

    The rule is now ``_similarity_rule_keeps`` reading a ``CorrespondenceEvidence`` rather than a
    predicate over two nodes, so this resolves each pairing to its evidence the way production
    does -- by ADR 0019 observation address, never by position in either list.
    """
    by_link = {item.link: item for item in round1_evidence}
    structural = {(id(old), id(new)) for old, new in revoked}
    predicate = set()
    for old, new in pairs:
        if old is None or new is None:
            continue
        link = (registry.ref(OLD, old), registry.ref(NEW, new))
        if not db._similarity_rule_keeps(by_link[link], SIMILARITY_THRESHOLD):
            predicate.add((id(old), id(new)))
    if structural != predicate:
        raise SystemExit(
            f"{key}: the assignment stage and the similarity rule name DIFFERENT populations. "
            f"stage revoked {len(structural)}, rule revoked {len(predicate)}, "
            f"{len(structural - predicate)} revoked by the stage alone, "
            f"{len(predicate - structural)} by the rule alone"
        )


def greedy_by_ordinal(population, evidence, threshold: float) -> list[tuple[str, str]]:
    """The production loop with parser ordinals substituted for the ``(ri, ai)`` sort component.

    The fault under study, and the only thing that differs from ``diff_bill._greedy_move_links``.
    Returns element ids so the result is comparable with the legacy transcription's.
    """
    ri_of = {observation.ref: index for index, observation in enumerate(population.old)}
    ai_of = {observation.ref: index for index, observation in enumerate(population.new)}
    node_of = {observation.ref: observation.node for observation in (*population.old, *population.new)}

    eligible = [item for item in evidence if item.get(WORD_OVERLAP) >= threshold]
    ordered = sorted(eligible, key=lambda i: (i.get(WORD_OVERLAP), i.old.ordinal, i.new.ordinal), reverse=True)

    claimed_old: set[int] = set()
    claimed_new: set[int] = set()
    links: list[tuple[str, str]] = []
    for item in ordered:
        ri, ai = ri_of[item.old], ai_of[item.new]
        if ri in claimed_old or ai in claimed_new:
            continue
        claimed_old.add(ri)
        claimed_new.add(ai)
        links.append((node_of[item.old].element_id, node_of[item.new].element_id))
    return links


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
    total_candidates = total_selected = pairs_with_candidates = 0
    cand_revoked_either = cand_revoked_both = 0
    sel_revoked_either = sel_revoked_both = 0
    removals_in_input = additions_in_input = 0
    revoked_removals_in_input = revoked_additions_in_input = 0
    monotone_removed = monotone_added = 0

    ordinal_key_differs: list[str] = []
    ordinal_key_order_only: list[str] = []
    ordinal_selection_delta = 0
    corpus_pairs = 0

    for key, old_path, new_path in baseline_pairs():
        corpus_pairs += 1
        old_tree, new_tree = normalize_bill(old_path), normalize_bill(new_path)

        registry = observation_registry(old_tree, new_tree)
        pairs = match_nodes(old_tree, new_tree)
        round1_evidence = similarity_correspondence_evidence(pairs, registry)
        decided = apply_similarity_assignment_rule(pairs, round1_evidence, registry, threshold=SIMILARITY_THRESHOLD)

        revoked = revoked_pairings(pairs, decided, key)
        cross_check_revocations(pairs, revoked, registry, round1_evidence, key)
        revoked_old = {id(old) for old, _ in revoked}
        revoked_new = {id(new) for _, new in revoked}

        population = unmatched_population(decided, registry)
        removals_in_input += len(population.old)
        additions_in_input += len(population.new)
        old_is_revoked = [id(o.node) in revoked_old for o in population.old]
        new_is_revoked = [id(n.node) in revoked_new for n in population.new]
        revoked_removals_in_input += sum(old_is_revoked)
        revoked_additions_in_input += sum(new_is_revoked)

        evidence = move_correspondence_evidence(retrieve_move_candidates(population, bound=MOVE_THRESHOLD))
        if not evidence:
            continue
        pairs_with_candidates += 1
        total_candidates += len(evidence)

        ri_of = {o.ref: i for i, o in enumerate(population.old)}
        ai_of = {n.ref: i for i, n in enumerate(population.new)}
        for item in evidence:
            r_revoked = old_is_revoked[ri_of[item.old]]
            a_revoked = new_is_revoked[ai_of[item.new]]
            cand_revoked_either += r_revoked or a_revoked
            cand_revoked_both += r_revoked and a_revoked

        # --- ordering: is the population order the parser-ordinal order? ------------------
        monotone_removed += [o.ref.ordinal for o in population.old] == sorted(o.ref.ordinal for o in population.old)
        monotone_added += [n.ref.ordinal for n in population.new] == sorted(n.ref.ordinal for n in population.new)

        # --- the live stages against the independent transcription of the pre-slice engine --
        moves = assign_moves(population, evidence, threshold=MOVE_THRESHOLD)
        node_of = {o.ref: o.node for o in (*population.old, *population.new)}
        actual = [(node_of[m.old[0]].element_id, node_of[m.new[0]].element_id) for m in moves]
        expected = legacy_selected_links(legacy_change_records(decided))
        if actual != expected:
            raise SystemExit(
                f"{key}: the migrated assignment and the pre-slice transcription disagree on the selected "
                f"links, so every figure here is void. migrated {actual[:4]}, pre-slice {expected[:4]}"
            )

        total_selected += len(actual)
        selected_index = {link: (ri_of[m.old[0]], ai_of[m.new[0]]) for link, m in zip(actual, moves)}
        for link in actual:
            ri, ai = selected_index[link]
            r_revoked, a_revoked = old_is_revoked[ri], new_is_revoked[ai]
            sel_revoked_either += r_revoked or a_revoked
            sel_revoked_both += r_revoked and a_revoked

        by_ordinal = greedy_by_ordinal(population, evidence, MOVE_THRESHOLD)
        if by_ordinal != actual:
            if set(by_ordinal) == set(actual):
                ordinal_key_order_only.append(key)
            else:
                ordinal_key_differs.append(key)
                ordinal_selection_delta += len(set(actual) ^ set(by_ordinal))

    print("===== A: INPUT POPULATION OF THE SECOND ROUND =====")
    print(f"unmatched OLD observations reaching round 2: {removals_in_input}")
    print(f"  of those, LEFT UNMATCHED BY THE SIMILARITY RULE (path-matched then revoked): {revoked_removals_in_input}")
    print(f"unmatched NEW observations reaching round 2: {additions_in_input}")
    print(f"  of those, LEFT UNMATCHED BY THE SIMILARITY RULE: {revoked_additions_in_input}")

    print("\n===== B: HOW MUCH OF THE MOVE POPULATION DEPENDS ON A REVOKED PAIRING =====")
    print(f"candidates: {total_candidates}")
    print(f"  with either side revocation-produced: {cand_revoked_either}")
    print(f"  with BOTH sides revocation-produced: {cand_revoked_both}")
    print(f"selected moves: {total_selected}")
    print(f"  with either side revocation-produced: {sel_revoked_either}")
    print(f"  with BOTH sides revocation-produced: {sel_revoked_both}")
    if total_selected:
        print(f"  share touching a revoked pairing: {100.0 * sel_revoked_either / total_selected:.1f}%")
    print("  (this sizes an ORDERING constraint inside matching -- round 2 must run after the")
    print("   revocation stage -- not a dependency on classification output.)")

    print("\n===== C: IS THE (ri, ai) ORDER THE PARSER-ORDINAL ORDER? =====")
    print(f"pairs carrying candidates: {pairs_with_candidates}")
    print(f"  unmatched OLD population already in parser-ordinal order: {monotone_removed}")
    print(f"  unmatched NEW population already in parser-ordinal order: {monotone_added}")

    print("\n===== D: SUBSTITUTING ORDINALS FOR (ri, ai) IN THE SORT KEY =====")
    print(f"pairs where the SELECTED SET changes: {len(ordinal_key_differs)} {ordinal_key_differs}")
    print(f"pairs where only the SELECTION ORDER changes: {len(ordinal_key_order_only)} {ordinal_key_order_only}")
    print(f"selected links added or lost by the ordinal key: {ordinal_selection_delta}")
    print("So (similarity, ri, ai) is legacy ordering POLICY, not an incidental tiebreak:")
    print("Phase 1 carried it across unchanged rather than re-deriving it from ordinals.")
    print("\nGUARD: on every pair above, the LIVE migrated stages reproduced the pre-slice")
    print("transcription's selected links exactly, and the revocation stage's structural")
    print("population matched the predicate exactly.")

    check_pinned(
        {
            "corpus pairs": corpus_pairs,
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
