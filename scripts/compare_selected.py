"""Diff two ``probe_move_assignment.py --dump`` files: which correspondences changed.

The negative control for a selection-policy mutation. Run the assignment probe once
against production and once against a temporarily mutated build, then compare the two
dumps here. Because both dumps are keyed by element id rather than by list position,
this separates three outcomes that a bare count cannot:

  * the selected SET changed  -- a different correspondence was chosen;
  * only the ORDER changed    -- the same correspondences, emitted in another sequence;
  * nothing changed.

The distinction matters because the canonical baseline digest is sensitive to both, so a
digest failure on its own does not say which occurred.

Read-only. Usage:

    uv run python scripts/compare_selected.py PRODUCTION.json MUTATED.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)

    prod = json.loads(Path(sys.argv[1]).read_text())
    mut = json.loads(Path(sys.argv[2]).read_text())

    if set(prod) != set(mut):
        raise SystemExit(
            "the two dumps cover different corpus pairs, so no comparison is valid: "
            f"only in first={sorted(set(prod) - set(mut))} "
            f"only in second={sorted(set(mut) - set(prod))}"
        )

    changed_pairs = []
    order_only = []
    total_prod = total_mut = 0
    set_diff_total = 0

    for key in sorted(prod):
        p = [tuple(x) for x in prod[key]]
        m = [tuple(x) for x in mut[key]]
        total_prod += len(p)
        total_mut += len(m)
        if p == m:
            continue
        only_p = set(p) - set(m)
        only_m = set(m) - set(p)
        if only_p or only_m:
            set_diff_total += len(only_p)
            changed_pairs.append((key, len(p), len(m), len(only_p), len(only_m)))
        else:
            order_only.append((key, len(p)))

    print(f"pairs compared: {len(prod)}")
    print(f"total selected moves: first={total_prod} second={total_mut}")
    print(f"pairs whose SELECTED SET changed: {len(changed_pairs)}")
    print(f"pairs where only the ORDER changed: {len(order_only)}")
    print(f"correspondences present in the first but not the second: {set_diff_total}")

    print("\npair, first_n, second_n, only_in_first, only_in_second")
    for row in changed_pairs:
        print("  ", row)
    print("\norder-only pairs:", order_only)

    for key, *_ in changed_pairs[:2]:
        p = [tuple(x) for x in prod[key]]
        m = [tuple(x) for x in mut[key]]
        only_p = [x for x in p if x not in set(m)]
        only_m = [x for x in m if x not in set(p)]
        print(f"\n--- {key}")
        for a in only_p[:4]:
            print(f"   first  selected: {a}")
        for b in only_m[:4]:
            print(f"   second selected: {b}")
        # An element linked to ITSELF versus to a different element carrying identical
        # normalised text is the substantive difference, so make it countable.
        self_p = sum(1 for a, b in p if a == b)
        self_m = sum(1 for a, b in m if a == b)
        print(f"   self-correspondences (old id == new id): first={self_p} second={self_m}")


if __name__ == "__main__":
    main()
