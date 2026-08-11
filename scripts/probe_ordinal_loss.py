"""Where does the complete parser-sequence ordinal stop being representable?

:class:`deltatrack.matching.ObservationRef` addresses an observation by ``(side, ordinal)``
where the ordinal indexes the parser's **complete emitted sequence**. ADR 0019 names
indexing a filtered or re-sorted view as a genuine hazard, because the resulting address
looks valid and points at the wrong node. This measures whether the engine still carries
that ordinal by the time assignment runs, and what the alternatives would actually address.

Read-only, writes nothing. Run from the project root:

    uv run python scripts/probe_ordinal_loss.py

Reports, per adjacent manifested XML pair:

addressable
    Whether ``element_id`` is a unique key over ``BillTree.nodes`` on both sides. It is the
    only node-identifying value that survives into ``NodeDiff``, so if it were not unique
    the ordinal could not be recovered downstream even in principle.

old_ord / new_ord
    Whether ``match_nodes`` emits nodes in parser order. It groups by ``match_path`` first,
    so its output order is path-first-appearance order, not document order. Where this is
    False, positions in the changes list are NOT a proxy for document sequence -- which is
    what the ``(ri, ai)`` tiebreak in ``reconcile_moves`` sorts on.

old_inv / new_inv
    Adjacent inversions, sizing how far out of parser order the output actually is.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import match_nodes  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs  # noqa: E402


def main() -> None:
    rows = []
    for key, old_path, new_path in baseline_pairs():
        old_tree = normalize_bill(old_path)
        new_tree = normalize_bill(new_path)

        old_ord = {n.element_id: i for i, n in enumerate(old_tree.nodes)}
        new_ord = {n.element_id: i for i, n in enumerate(new_tree.nodes)}
        addressable = len(old_ord) == len(old_tree.nodes) and len(new_ord) == len(new_tree.nodes)

        pairs = match_nodes(old_tree, new_tree)
        old_seq = [old_ord[o.element_id] for o, _ in pairs if o is not None]
        new_seq = [new_ord[n.element_id] for _, n in pairs if n is not None]

        rows.append(
            (
                key,
                addressable,
                old_seq == sorted(old_seq),
                new_seq == sorted(new_seq),
                sum(1 for a, b in zip(old_seq, old_seq[1:]) if a > b),
                sum(1 for a, b in zip(new_seq, new_seq[1:]) if a > b),
            )
        )

    print(f"{'pair':<62}{'addr':<6}{'old_ord':<9}{'new_ord':<9}{'old_inv':<9}{'new_inv':<9}")
    for key, addressable, old_sorted, new_sorted, old_inv, new_inv in rows:
        print(f"{key:<62}{str(addressable):<6}{str(old_sorted):<9}{str(new_sorted):<9}{old_inv:<9}{new_inv:<9}")

    total = len(rows)
    print()
    print(f"pairs where element_id uniquely addresses every node: {sum(1 for r in rows if r[1])}/{total}")
    print(f"pairs where match_nodes emits OLD nodes in parser order: {sum(1 for r in rows if r[2])}/{total}")
    print(f"pairs where match_nodes emits NEW nodes in parser order: {sum(1 for r in rows if r[3])}/{total}")


if __name__ == "__main__":
    main()
