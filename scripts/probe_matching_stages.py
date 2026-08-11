"""Evidence for ADR 0020: what the fused matching decision costs, measured.

Read-only. Runs the current engine over adjacent version pairs and reports three things
the record argues from. It changes nothing and asserts nothing; it is a measurement.

**1. The split population, and its money consequence.** A path-matched pair whose body
similarity falls under the split cutoff is broken into a removal plus an addition, and
money extraction then runs one-sided on each. Issue #368 traced that mechanism and said
plainly that the frequency was not measured, asking for it to be sized first. This counts
the pairs it happens to, and how many of those carry dollar amounts on *both* sides, which
is the population that renders a value edit as money removed plus money added.

**2. Work done by the second retriever.** ``reconcile_moves`` runs after classification,
over the surviving removals and additions, under a different cutoff. It exists because
grouping by ``match_path`` cannot find a provision that moved. This counts how many changes
it recovers, which is the volume of correspondence the first retriever structurally misses.

**3. Shapes a pair-typed result cannot relate.** Match paths whose output carries more than
one removal or more than one addition. **These are candidate non-binary shapes, not
confirmed consolidations**: nobody has ruled them, and some are collisions rather than
relations. They establish that the shape occurs, not how often it is genuine.

Usage, from the repo root:

    uv run python scripts/probe_matching_stages.py tests/corpus

The default root is the committed corpus (ADR 0015), so this reproduces on a fresh clone
with no downloads. Pass another root to sweep a wider locally-fetched set; the numbers then
describe that set, and ADR 0020 says which corpus each figure came from. Version pairs are
adjacent by the leading ordinal in each filename (ADR 0013), so a root holding a different
subset of versions yields different pairs and is not comparable term by term.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

from deltatrack.bill_tree import normalize_bill
from deltatrack.diff_bill import diff_bills, extract_amounts, match_nodes
from deltatrack.similarity import SIMILARITY_THRESHOLD, text_similarity

DEFAULT_ROOT = Path("tests/corpus")
_ORDINAL = re.compile(r"^(\d+)_")
_MAX_EXAMPLES = 8


def adjacent_pairs(bill_dir: Path) -> list[tuple[Path, Path]]:
    """Consecutive version files, ordered by the leading ordinal (ADR 0013)."""
    numbered = []
    for path in bill_dir.glob("*.xml"):
        match = _ORDINAL.match(path.name)
        if match:
            numbered.append((int(match.group(1)), path))
    numbered.sort()
    return [(numbered[i][1], numbered[i + 1][1]) for i in range(len(numbered) - 1)]


def normalize(text: str) -> str:
    return " ".join(text.split())


def main(argv: list[str]) -> int:  # noqa: C901 - one report, read top to bottom
    root = Path(argv[1]) if len(argv) > 1 else DEFAULT_ROOT
    bill_dirs = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    if not bill_dirs:
        # A silently empty sweep prints zeroes that look like a clean result, which is
        # the fail-open shape this probe exists to help argue against. Refuse instead.
        print(f"no bill directories under {root}", file=sys.stderr)
        return 1

    pairs_examined = 0
    changes_total = 0
    split_total = 0
    split_with_money = 0
    split_examples: list[str] = []
    moved_total = 0
    nonbinary_groups = 0
    nonbinary_examples: list[str] = []
    skipped: list[str] = []

    for bill_dir in bill_dirs:
        for old_path, new_path in adjacent_pairs(bill_dir):
            try:
                old_tree = normalize_bill(old_path)
                new_tree = normalize_bill(new_path)
            except Exception as exc:  # a parse failure is not what this probe measures
                skipped.append(f"{bill_dir.name} {old_path.stem}->{new_path.stem}: {type(exc).__name__}: {exc}")
                continue
            pairs_examined += 1
            label = f"{bill_dir.name} {old_path.stem}->{new_path.stem}"

            # 1. The matcher's own pairing, inspected before classification runs.
            for old_node, new_node in match_nodes(old_tree, new_tree):
                if old_node is None or new_node is None:
                    continue
                old_norm, new_norm = normalize(old_node.body_text), normalize(new_node.body_text)
                if old_norm == new_norm:
                    continue
                if text_similarity(old_norm, new_norm) >= SIMILARITY_THRESHOLD:
                    continue
                split_total += 1
                old_amounts = extract_amounts(old_node.body_text)
                new_amounts = extract_amounts(new_node.body_text)
                if old_amounts and new_amounts:
                    split_with_money += 1
                    if len(split_examples) < _MAX_EXAMPLES:
                        split_examples.append(
                            f"{label} {'/'.join(old_node.match_path)} "
                            f"old={len(old_amounts)} amounts new={len(new_amounts)} amounts"
                        )

            diff = diff_bills(old_tree, new_tree)
            changes_total += len(diff.changes)
            moved_total += sum(1 for c in diff.changes if c.change_type == "moved")

            # 3. Non-binary shapes surviving to the output.
            by_path: dict[tuple[str, ...], dict[str, int]] = defaultdict(lambda: {"removed": 0, "added": 0})
            for change in diff.changes:
                if change.change_type in ("removed", "added"):
                    by_path[change.match_path][change.change_type] += 1
            for path_key, counts in by_path.items():
                if counts["removed"] and counts["added"] and (counts["removed"] > 1 or counts["added"] > 1):
                    nonbinary_groups += 1
                    if len(nonbinary_examples) < _MAX_EXAMPLES:
                        nonbinary_examples.append(
                            f"{label} {'/'.join(path_key)} removed={counts['removed']} added={counts['added']}"
                        )

    print(f"corpus root                                   : {root}")
    print(f"adjacent version pairs diffed                 : {pairs_examined}")
    print(f"changes emitted across all pairs              : {changes_total}")
    for row in skipped:
        print(f"  SKIPPED {row}")

    print("\n--- 1. the fused split decision, and its money consequence (#368) ---")
    print(f"path-matched pairs split by the cutoff        : {split_total}")
    print(f"...of those, carrying amounts on BOTH sides   : {split_with_money}")
    for row in split_examples:
        print(f"    {row}")
    if split_with_money > len(split_examples):
        print(f"    ... and {split_with_money - len(split_examples)} more")

    print("\n--- 2. retrieval the path-blocking key cannot do ---")
    print(f"changes reconciled to 'moved' after the fact  : {moved_total}")

    print("\n--- 3. candidate shapes a pair-typed result cannot relate ---")
    print(f"match_paths with multi-node removed+added     : {nonbinary_groups}")
    for row in nonbinary_examples:
        print(f"    {row}")
    if nonbinary_groups > len(nonbinary_examples):
        print(f"    ... and {nonbinary_groups - len(nonbinary_examples)} more")
    print("    Candidates, not confirmed consolidations. None has been ruled by a human.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
