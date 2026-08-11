"""Investigation C: where a complete-sequence ordinal exists, and where it is lost.

Measures whether element_id could reconstruct an ObservationRef.ordinal, which is the
cheapest-looking option and the one most likely to be wrong.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs  # noqa: E402

empty = 0
total = 0
dup_sides = 0
sides = 0
dup_examples = []
seen_files = set()

for key, old_path, new_path in baseline_pairs():
    for path in (old_path, new_path):
        if path in seen_files:
            continue
        seen_files.add(path)
        tree = normalize_bill(path)
        ids = [n.element_id for n in tree.nodes]
        sides += 1
        total += len(ids)
        empty += sum(1 for i in ids if not i)
        counts = Counter(i for i in ids if i)
        dups = {i: n for i, n in counts.items() if n > 1}
        if dups:
            dup_sides += 1
            if len(dup_examples) < 5:
                dup_examples.append((path.name, len(dups), list(dups.items())[:3]))

print(f"tree sides inspected: {sides}")
print(f"total nodes: {total}")
print(f"nodes with EMPTY element_id: {empty}  ({100.0 * empty / total:.2f}%)")
print(f"sides containing a DUPLICATE element_id: {dup_sides}")
for ex in dup_examples:
    print(f"  {ex[0]}: {ex[1]} duplicated ids, e.g. {ex[2]}")
