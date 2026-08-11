"""What a pre-classification second retrieval round would have to reproduce exactly.

Investigation D for the #581 prerequisite. ADR 0020 forbids retrieval after
classification, so ``reconcile_moves`` — a second retrieval plus assignment pass running
over already-classified changes — eventually has to move ahead of classification. Two
things decide whether that is a behaviour-preserving move or a behaviour change, and
neither is measured by the probes committed with #586:

**A. The input population.** ``probe_splits.py`` measures that 327 path-matched pairs are
split into a removal plus an addition *by classification*, and says explicitly that their
overlap with the move population is NOT measured. Without that overlap, "move the round
earlier" is unscoped: an entry created by classification cannot be an input to a round
that runs before it. This measures how much of the candidate and selected-move population
depends on a classification-created entry.

**B. The ordering key.** Production sorts candidates by ``(similarity, ri, ai)``, where
``ri``/``ai`` are positions in the FILTERED removed/added lists. 37 of 496 selections are
decided by that key rather than by similarity. An extraction that replaced it with ADR
0019 ordinals would preserve behaviour only if the two orderings agree. This runs both
keys through the same greedy loop and compares the selected correspondence — set and
order — pair by pair.

FAIL-CLOSED, in two places, because both numbers are void without them:

    - ``element_id`` is used only as a MEASUREMENT BRIDGE from a ``NodeDiff`` back to the
      node it came from, since ``NodeDiff`` carries no node reference. It is not proposed
      as identity (ADR 0019 refuses that). The probe asserts uniqueness and non-emptiness
      per side and stops if either fails, rather than reporting numbers built on a lookup
      that could silently hit the wrong twin.
    - The duplicated greedy loop must reproduce production's selected set AND order under
      the production key before any comparison figure is printed. A drifted duplicate
      would be comparing the ordinal key against itself rather than against production.

Read-only, writes nothing. Run from the project root:

    uv run python scripts/probe_round2_migration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deltatrack.diff_bill as db  # noqa: E402
from deltatrack.compare.xml import compare_xml  # noqa: E402
from deltatrack.similarity import (  # noqa: E402
    MOVE_THRESHOLD,
    SIMILARITY_THRESHOLD,
    move_candidates,
    text_similarity,
)
from deltatrack.version_stems import label_from_stem  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs  # noqa: E402

REAL_MATCH_NODES = db.match_nodes
REAL_RECONCILE = db.reconcile_moves


def capture() -> dict[str, dict]:
    """Per corpus pair: the trees, the ``match_nodes`` output, and ``reconcile_moves``' input.

    Both are captured by wrapping the production functions inside a real ``compare_xml``
    run, so every value measured is the value production actually produced rather than a
    reconstruction of it.
    """
    captured: dict[str, dict] = {}
    holder: dict[str, str] = {}

    def match_spy(old, new):
        pairs = REAL_MATCH_NODES(old, new)
        captured.setdefault(holder["key"], {}).update(old_tree=old, new_tree=new, pairs=pairs)
        return pairs

    def reconcile_spy(changes, threshold=MOVE_THRESHOLD):
        captured.setdefault(holder["key"], {})["changes"] = list(changes)
        return REAL_RECONCILE(changes, threshold)

    db.match_nodes = match_spy
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


def split_element_ids(pairs: list) -> tuple[set[str], set[str]]:
    """Element ids of the nodes classification revokes into a removal plus an addition.

    Reproduces ``diff_bills``' own condition: a path-matched pair whose normalised texts
    differ and whose similarity falls below ``SIMILARITY_THRESHOLD``.
    """
    old_ids: set[str] = set()
    new_ids: set[str] = set()
    for old_node, new_node in pairs:
        if old_node is None or new_node is None:
            continue
        old_norm = db._normalize_text(old_node.body_text)
        new_norm = db._normalize_text(new_node.body_text)
        if old_norm != new_norm and text_similarity(old_norm, new_norm) < SIMILARITY_THRESHOLD:
            old_ids.add(old_node.element_id)
            new_ids.add(new_node.element_id)
    return old_ids, new_ids


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


def main() -> None:
    captured = capture()

    total_candidates = 0
    total_selected = 0
    cand_split_removal = 0
    cand_split_addition = 0
    cand_split_either = 0
    cand_split_both = 0
    sel_split_removal = 0
    sel_split_addition = 0
    sel_split_either = 0
    sel_split_both = 0
    split_removals_in_input = 0
    split_additions_in_input = 0
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
        split_old, split_new = split_element_ids(record["pairs"])

        removed, added = filtered_sides(changes)
        removals_in_input += len(removed)
        additions_in_input += len(added)
        split_removals_in_input += sum(1 for _, c in removed if c.element_id_old in split_old)
        split_additions_in_input += sum(1 for _, c in added if c.element_id_new in split_new)

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

        removed_is_split = [c.element_id_old in split_old for _, c in removed]
        added_is_split = [c.element_id_new in split_new for _, c in added]
        for _sim, ri, ai in candidates:
            r_split = removed_is_split[ri]
            a_split = added_is_split[ai]
            cand_split_removal += r_split
            cand_split_addition += a_split
            cand_split_either += r_split or a_split
            cand_split_both += r_split and a_split

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
            r_split = removed_is_split[ri]
            a_split = added_is_split[ai]
            sel_split_removal += r_split
            sel_split_addition += a_split
            sel_split_either += r_split or a_split
            sel_split_both += r_split and a_split

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
    print(f"  of those, CREATED BY CLASSIFICATION (path-matched then split): {split_removals_in_input}")
    print(f"additions reaching reconcile_moves: {additions_in_input}")
    print(f"  of those, CREATED BY CLASSIFICATION: {split_additions_in_input}")

    print("\n===== B: HOW MUCH OF THE MOVE POPULATION DEPENDS ON A SPLIT =====")
    print(f"candidates: {total_candidates}")
    print(f"  with a classification-created REMOVAL: {cand_split_removal}")
    print(f"  with a classification-created ADDITION: {cand_split_addition}")
    print(f"  with either side classification-created: {cand_split_either}")
    print(f"  with BOTH sides classification-created: {cand_split_both}")
    print(f"selected moves: {total_selected}")
    print(f"  with a classification-created REMOVAL: {sel_split_removal}")
    print(f"  with a classification-created ADDITION: {sel_split_addition}")
    print(f"  with either side classification-created: {sel_split_either}")
    print(f"  with BOTH sides classification-created: {sel_split_both}")
    if total_selected:
        print(f"  share of selected moves touching a split: {100.0 * sel_split_either / total_selected:.1f}%")

    print("\n===== C: IS THE (ri, ai) ORDER THE PARSER-ORDINAL ORDER? =====")
    print(f"pairs carrying candidates: {pairs_with_candidates}")
    print(f"  removed list already in parser-ordinal order: {monotone_removed}")
    print(f"  added list already in parser-ordinal order: {monotone_added}")

    print("\n===== D: SUBSTITUTING ORDINALS FOR (ri, ai) IN THE SORT KEY =====")
    print(f"pairs where the SELECTED SET changes: {len(ordinal_key_differs)} {ordinal_key_differs}")
    print(f"pairs where only the SELECTION ORDER changes: {len(ordinal_key_order_only)} {ordinal_key_order_only}")
    print(f"selected links added or lost by the ordinal key: {ordinal_selection_delta}")
    print("\nGUARD: the replay reproduced production's set AND order on every pair above.")


if __name__ == "__main__":
    main()
