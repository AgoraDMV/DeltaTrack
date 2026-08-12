"""Where an ADR 0019 ordinal can still be recovered, and which recovery mechanisms are wrong.

Investigation B for the #581 prerequisite. ``ObservationRef.ordinal`` must index the
parser's **complete emitted sequence**. This measures four things and tries to break three
of them:

1. **Does ``match_nodes`` pass node objects through by identity?** If every node it
   returns *is* (``id()``) a node of its source ``BillTree.nodes``, the ordinal is
   recoverable there without any new field. If it reconstructs or copies, it is not.
2. **Is the recovery a bijection?** Every node claimed exactly once, and none omitted.
3. **Does identity survive the whole pre-classification sequence?** Since #591 that
   sequence is more than one stage: ``match_nodes`` then the similarity rule, now spelled
   ``apply_similarity_assignment_rule(...)`` over the evidence
   ``similarity_correspondence_evidence(...)`` produced. The second stage rebuilds the tuple
   list, which is exactly where a copy would be introduced without anyone noticing. Measuring
   only ``match_nodes`` would leave a future ObservationRef wired at a seam one stage short of
   classification.
4. **Where does that mechanism stop working?** ``NodeDiff`` carries no node reference, so
   identity is available up to the end of that sequence and gone the moment classification
   emits records.

**SCOPE, because the word "identity" is doing narrow work here.** Object identity is a
*run-local recovery mechanism* for the complete parser-sequence ordinal, and nothing more.
It is not ADR 0019 Observation identity, which is
``(source_sha256, parser_revision, node_ordinal)`` and is stable across runs and processes.
``id()`` is meaningful only inside one interpreter with the tree alive; the point proved
here is that no new field has to be threaded through the matcher to reach the ordinal, not
that ``id()`` could ever be stored or compared across runs.

**FAIL-CLOSED, not merely reported.** :func:`validate_identity` raises
:class:`IdentityFailure` unless a stage's tuples address their source trees with zero
foreign objects, zero observations claimed twice, and zero omitted. Both production stages
go through it on every corpus pair, so a regression stops the run rather than printing a
non-zero counter that a reader has to notice.

NEGATIVE CONTROLS, because a validator that has never rejected anything is
indistinguishable from one that cannot:

control A (copy), the argument for identity over value equality
    A ``dataclasses.replace(node)`` -- a distinct object carrying identical field values --
    is substituted into an *otherwise real* tuple sequence, and that sequence is sent
    through the **same** :func:`validate_identity` used for production. It must raise. The
    same impostor is then looked up in a value-keyed map, which answers with an address it
    did not earn. Checking ``id(impostor) not in index`` directly would test the expression,
    not the validator; this tests the validator.

control B (value collision), observational only
    Nodes within one tree that are value-equal to another. ``BillNode`` is a frozen
    dataclass hashing by field values, so a colliding pair means a ``{node: ordinal}`` map
    silently holds one address for two observations. Reported as a measured population and
    nothing more: zero collisions today is not the argument, control A is.

control C (output position as ordinal)
    Derive the ordinal from the node's position in the stage output instead of from the
    identity index, and count how many nodes then carry a WRONG address. This is ADR
    0019's named hazard -- indexing a re-sorted view -- measured rather than described.

    Run against both stages, and the two figures MUST come out equal. That is not a
    coincidence to report as if it were a second measurement: the revocation stage
    replaces a pairing with its two halves *in place*, so each side's observation
    sequence is untouched and the per-side positions cannot move. Asserting the equality
    turns the second run into a tripwire for the one mutation #591's own docstring flags
    as dangerous -- reversing the two replacements, or appending them elsewhere, which
    moves canonical output while leaving every change count untouched.

Read-only, writes nothing. Exits non-zero on any failure. Run from the project root:

    uv run python scripts/probe_node_identity.py

``id()`` is safe as a key here only because each tree is held alive for the whole of its
own measurement: CPython may reuse the id of a collected object, and a map outliving its
nodes would be reading addresses that no longer mean anything.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deltatrack.bill_tree import (
    BillTree,  # noqa: E402
    normalize_bill,  # noqa: E402
)
from deltatrack.diff_bill import (  # noqa: E402
    apply_similarity_assignment_rule,
    match_nodes,
    observation_registry,
    similarity_correspondence_evidence,
)
from deltatrack.similarity import SIMILARITY_THRESHOLD  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs  # noqa: E402

STAGES = ("match_nodes", "after the similarity rule")


class IdentityFailure(RuntimeError):
    """A stage's tuples do not address their source trees exactly once each."""


def identity_index(nodes: list) -> dict[int, int]:
    """``{id(node): ordinal}`` over the complete emitted sequence."""
    return {id(node): ordinal for ordinal, node in enumerate(nodes)}


def validate_identity(label: str, key: str, tuples: list, old_tree: BillTree, new_tree: BillTree) -> None:
    """Raise unless every node in ``tuples`` is an object of its source tree, claimed once.

    The production check and the copied-node negative control both run through here, which
    is what makes the control a test of the validator rather than of a restated expression.
    """
    old_at = identity_index(old_tree.nodes)
    new_at = identity_index(new_tree.nodes)

    foreign = 0
    old_seen: Counter[int] = Counter()
    new_seen: Counter[int] = Counter()
    for old_node, new_node in tuples:
        for node, index, seen in ((old_node, old_at, old_seen), (new_node, new_at, new_seen)):
            if node is None:
                continue
            if id(node) not in index:
                foreign += 1
                continue
            seen[index[id(node)]] += 1

    claimed_twice = sum(n - 1 for n in old_seen.values() if n > 1)
    claimed_twice += sum(n - 1 for n in new_seen.values() if n > 1)
    omitted = (len(old_tree.nodes) - len(old_seen)) + (len(new_tree.nodes) - len(new_seen))

    if foreign or claimed_twice or omitted:
        raise IdentityFailure(
            f"{key} [{label}]: foreign/copied objects={foreign}, "
            f"observations claimed more than once={claimed_twice}, observations omitted={omitted}"
        )


def position_errors(tuples: list, old_at: dict[int, int], new_at: dict[int, int]) -> tuple[int, int]:
    """``(total, wrong)`` addresses if a node's position in this list were its ordinal."""
    total = wrong = 0
    for side, index in ((0, old_at), (1, new_at)):
        for position, node in enumerate(t[side] for t in tuples if t[side] is not None):
            total += 1
            if index[id(node)] != position:
                wrong += 1
    return total, wrong


def main() -> None:
    pairs_checked = 0
    validated = dict.fromkeys(STAGES, 0)
    position_totals = {label: [0, 0] for label in STAGES}
    revocation_added = 0
    value_collision_sides = 0
    value_collision_nodes = 0
    control_a_rejected = 0
    control_a_value_silent = 0
    control_a_missed: list[str] = []

    for key, old_path, new_path in baseline_pairs():
        old_tree = normalize_bill(old_path)
        new_tree = normalize_bill(new_path)
        old_at = identity_index(old_tree.nodes)
        new_at = identity_index(new_tree.nodes)

        # Control B, observational: a shorter value-keyed dict means two nodes collapsed.
        old_by_value = {node: ordinal for ordinal, node in enumerate(old_tree.nodes)}
        new_by_value = {node: ordinal for ordinal, node in enumerate(new_tree.nodes)}
        for by_value, tree in ((old_by_value, old_tree), (new_by_value, new_tree)):
            lost = len(tree.nodes) - len(by_value)
            if lost:
                value_collision_sides += 1
                value_collision_nodes += lost

        pairs = match_nodes(old_tree, new_tree)
        registry = observation_registry(old_tree, new_tree)
        decided = apply_similarity_assignment_rule(
            pairs,
            similarity_correspondence_evidence(pairs, registry),
            registry,
            threshold=SIMILARITY_THRESHOLD,
        )
        revocation_added += len(decided) - len(pairs)

        # PRODUCTION VALIDATION -- raises rather than accumulating a counter.
        for label, tuples in zip(STAGES, (pairs, decided)):
            validate_identity(label, key, tuples, old_tree, new_tree)
            validated[label] += 1
            total, wrong = position_errors(tuples, old_at, new_at)
            position_totals[label][0] += total
            position_totals[label][1] += wrong

        # CONTROL A: a value-equal copy inside an otherwise real sequence, through the
        # SAME validator. It must reject; a value-keyed map must accept.
        position = next(i for i, (old_node, _) in enumerate(pairs) if old_node is not None)
        original = pairs[position][0]
        impostor = replace(original)
        mutated = list(pairs)
        mutated[position] = (impostor, pairs[position][1])
        try:
            validate_identity("control A (copied node)", key, mutated, old_tree, new_tree)
        except IdentityFailure:
            control_a_rejected += 1
        else:
            control_a_missed.append(key)
        if old_by_value.get(impostor) is not None:
            control_a_value_silent += 1

        pairs_checked += 1

    print("===== IDENTITY SURVIVAL THROUGH THE PRE-CLASSIFICATION SEQUENCE =====")
    print(f"corpus pairs checked: {pairs_checked}")
    print(f"tuples added by the revocation stage (one per revoked pairing): {revocation_added}")
    for label in STAGES:
        print(f"  {label}: VALIDATED on {validated[label]}/{pairs_checked} pairs")
    print("  (validation raises IdentityFailure on any foreign object, double claim or")
    print("   omission; reaching this line means all three were zero on every pair.)")

    print("\n===== CONTROL A: A COPY IS SUBSTITUTED INTO A REAL SEQUENCE =====")
    print(f"pairs where the SAME validator REJECTED the copy (correct): {control_a_rejected}/{pairs_checked}")
    print(f"pairs where a VALUE-EQUALITY lookup accepted it anyway (unearned address): {control_a_value_silent}")

    print("\n===== CONTROL B (OBSERVATIONAL): VALUE-EQUAL NODES WITHIN ONE TREE =====")
    print(f"tree sides holding at least one value-collision: {value_collision_sides}")
    print(f"observations a value-keyed map would silently lose: {value_collision_nodes}")
    print("Reported, not relied on: control A is the argument, not this count.")

    print("\n===== CONTROL C: OUTPUT POSITION USED AS THE ORDINAL =====")
    for label in STAGES:
        total, wrong = position_totals[label]
        share = f"{100.0 * wrong / total:.1f}%" if total else "n/a"
        print(f"  {label}: {wrong} WRONG of {total} addresses derived from position ({share})")

    failures: list[str] = []
    if control_a_missed:
        failures.append(f"the validator ACCEPTED a copied node on {len(control_a_missed)} pair(s): {control_a_missed}")
    if control_a_value_silent != pairs_checked:
        failures.append(
            f"value-equality accepted the impostor on only {control_a_value_silent}/{pairs_checked} pairs; "
            "the argument for identity over value equality is not demonstrated"
        )
    if any(validated[label] != pairs_checked for label in STAGES):
        failures.append(f"not every stage was validated on every pair: {validated}")
    if position_totals[STAGES[0]] != position_totals[STAGES[1]]:
        failures.append(
            "the revocation stage moved a per-side observation position. Its replacements are "
            "supposed to be adjacent and in place, and canonical output depends on that "
            f"({STAGES[0]}={position_totals[STAGES[0]]}, {STAGES[1]}={position_totals[STAGES[1]]})"
        )
    if failures:
        raise SystemExit("PROBE FAILED:\n  " + "\n  ".join(failures))

    print("  equal by construction: the revocation stage replaces a pairing in place, so")
    print("  per-side observation order is untouched. A difference would mean it reordered.")


if __name__ == "__main__":
    main()
