"""Where an ADR 0019 ordinal can still be recovered, and which recovery mechanisms are wrong.

Investigation B for the #581 prerequisite. ``ObservationRef.ordinal`` must index the
parser's **complete emitted sequence**. This measures three things and tries to break two
of them:

1. **Does ``match_nodes`` pass node objects through by identity?** If every node it
   returns *is* (``id()``) a node of its source ``BillTree.nodes``, the ordinal is
   recoverable there without any new field. If it reconstructs or copies, it is not.
2. **Is the recovery a bijection?** Every node claimed at most once, and no node omitted.
3. **Where does that mechanism stop working?** ``NodeDiff`` carries no node reference, so
   the question is whether identity survives past ``match_nodes`` at all.

NEGATIVE CONTROLS, because a green identity check proves nothing on its own — a lookup
that always hits is indistinguishable from one that cannot miss. Three faults are injected
and each must turn the check red:

control A (copy)
    Substitute a ``dataclasses.replace(node)`` — a distinct object with identical field
    values — into the output. Identity lookup must raise; value-equality lookup must
    silently succeed with an address it did not earn. This is the whole argument for
    identity over value equality, run rather than asserted.

control B (value collision)
    Count nodes within one tree that are value-equal to another. ``BillNode`` is a frozen
    dataclass, so it hashes by field values: wherever two nodes collide, a ``{node:
    ordinal}`` dict silently holds one address for two observations. Reported as a
    measured population, and control A covers the case where that population is zero —
    zero collisions today is not a guarantee, and the mechanism is wrong either way.

control C (output position as ordinal)
    Derive the ordinal from the node's position in ``match_nodes`` output instead of from
    the identity index, and count how many nodes then carry a WRONG address. This is ADR
    0019's named hazard — indexing a re-sorted view — measured rather than described.

Read-only, writes nothing. Run from the project root:

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

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import match_nodes  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs  # noqa: E402


def identity_index(nodes: list) -> dict[int, int]:
    """``{id(node): ordinal}`` over the complete emitted sequence."""
    return {id(node): ordinal for ordinal, node in enumerate(nodes)}


def main() -> None:
    pairs_checked = 0
    foreign_objects = 0
    claimed_twice = 0
    omitted = 0
    value_collision_sides = 0
    value_collision_nodes = 0
    position_wrong = 0
    position_total = 0
    control_a_red = 0
    control_a_value_silent = 0

    for _key, old_path, new_path in baseline_pairs():
        old_tree = normalize_bill(old_path)
        new_tree = normalize_bill(new_path)
        old_at = identity_index(old_tree.nodes)
        new_at = identity_index(new_tree.nodes)

        # Value-keyed maps, for control B. A shorter dict means two nodes collapsed.
        old_by_value = {node: ordinal for ordinal, node in enumerate(old_tree.nodes)}
        new_by_value = {node: ordinal for ordinal, node in enumerate(new_tree.nodes)}
        for by_value, tree in ((old_by_value, old_tree), (new_by_value, new_tree)):
            lost = len(tree.nodes) - len(by_value)
            if lost:
                value_collision_sides += 1
                value_collision_nodes += lost

        pairs = match_nodes(old_tree, new_tree)

        old_seen: Counter[int] = Counter()
        new_seen: Counter[int] = Counter()
        for old_node, new_node in pairs:
            for node, index, seen in ((old_node, old_at, old_seen), (new_node, new_at, new_seen)):
                if node is None:
                    continue
                if id(node) not in index:
                    foreign_objects += 1
                    continue
                seen[index[id(node)]] += 1

        claimed_twice += sum(n - 1 for n in old_seen.values() if n > 1)
        claimed_twice += sum(n - 1 for n in new_seen.values() if n > 1)
        omitted += len(old_tree.nodes) - len(old_seen)
        omitted += len(new_tree.nodes) - len(new_seen)

        # Control C: position in match_nodes output, used as if it were the ordinal.
        for position, node in enumerate(n for n, _ in pairs if n is not None):
            position_total += 1
            if old_at[id(node)] != position:
                position_wrong += 1
        for position, node in enumerate(n for _, n in pairs if n is not None):
            position_total += 1
            if new_at[id(node)] != position:
                position_wrong += 1

        # Control A: a copy carrying identical field values, in place of the real node.
        original = old_tree.nodes[0]
        impostor = replace(original)
        if id(impostor) not in old_at:
            control_a_red += 1
        if old_by_value.get(impostor) is not None:
            control_a_value_silent += 1

        pairs_checked += 1

    print("===== IDENTITY SURVIVAL THROUGH match_nodes =====")
    print(f"corpus pairs checked: {pairs_checked}")
    print(f"returned nodes NOT an object of their source tree (copies/reconstructions): {foreign_objects}")
    print(f"observations claimed by more than one pairing: {claimed_twice}")
    print(f"observations reaching no pairing at all: {omitted}")

    print("\n===== CONTROL A: A COPY IS SUBSTITUTED FOR THE REAL NODE =====")
    print(f"pairs where the IDENTITY lookup went red (correct): {control_a_red}/{pairs_checked}")
    print(f"pairs where the VALUE-EQUALITY lookup answered anyway (wrong address, no error): {control_a_value_silent}")

    print("\n===== CONTROL B: VALUE-EQUAL NODES WITHIN ONE TREE =====")
    print(f"tree sides holding at least one value-collision: {value_collision_sides}")
    print(f"observations a value-keyed map would silently lose: {value_collision_nodes}")

    print("\n===== CONTROL C: OUTPUT POSITION USED AS THE ORDINAL =====")
    print(f"addresses derived from output position: {position_total}")
    print(f"of those, WRONG (position != parser ordinal): {position_wrong}")
    if position_total:
        print(f"share wrong: {100.0 * position_wrong / position_total:.1f}%")


if __name__ == "__main__":
    main()
