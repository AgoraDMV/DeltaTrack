"""Measure the move-reconciliation assignment step: population, ties, and what decides them.

Read-only. Evidence for the ADR 0020 slice-2 extraction question: whether the second
retrieval/assignment pass in ``diff_bill.reconcile_moves`` can be extracted behaviour-
preservingly, and what its selection actually depends on.

Run from the project root:

    uv run python scripts/probe_move_assignment.py                  # measure and print
    uv run python scripts/probe_move_assignment.py --dump out.json  # also record selections

``--dump`` writes the selected correspondences per corpus pair, keyed by element id, so
two runs (for example production versus a temporarily mutated tie-break) can be compared
without re-deriving anything.

DEFINITIONS, stated because every number below depends on them:

candidate
    One ``(similarity, ri, ai)`` tuple returned by ``similarity.move_candidates`` for one
    corpus pair: a removed x added text pair scoring at or above ``MOVE_THRESHOLD`` where
    neither side's normalised text is empty. ``ri``/``ai`` are positions in the FILTERED
    removed/added lists, not positions in the change list and not parser ordinals.

population
    Every adjacent manifested XML version pair, taken from
    ``tests.test_canonical_baseline.baseline_pairs`` so this probe and the byte-identity
    gate always describe the same corpus.

similarity tie
    Two or more candidates within one corpus pair sharing an identical ``similarity``.

tie-decided selection
    A selection made while another *still-unclaimed* candidate had the same similarity and
    competed for one of the same two slots. Only the ``(ri, ai)`` component of the sort key
    separated them, so the outcome is a function of local list position rather than of any
    property of the two sections.

HOW IT INSTRUMENTS
    ``reconcile_moves`` is *wrapped*, not reimplemented, so the changes list measured is the
    one production's own classification loop produces. Where the greedy loop has to be
    duplicated in order to see inside it (a copy cannot be avoided: production keeps no
    record of which candidate lost), the duplicate resolves each selection it makes back
    to the same ``(element_id_old, element_id_new)`` identity production records, and
    asserts **exact agreement with production on both the selected set and the selected
    order**, per corpus pair, before any tie number is reported.

    Comparing counts alone would not be enough, and the gap is precisely the phenomenon
    this probe exists to measure: a tie-policy difference can change *which* pair wins
    while leaving the number of selections identical. A count-only check would pass
    through exactly that error. Identities come from the filtered ``removed``/``added``
    lists rather than from positions in the emitted output, because a key read off the
    post-selection order could not detect a change in that order.

    If any pair disagrees, the run stops and reports the differing pair. No tie figure is
    printed, because a drifted duplicate measures a different population than the one it
    would be reporting about.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deltatrack.diff_bill as db
from deltatrack.compare.xml import compare_xml
from deltatrack.similarity import MOVE_THRESHOLD, move_candidates
from deltatrack.version_stems import label_from_stem
from tests.test_canonical_baseline import baseline_pairs

REAL_RECONCILE = db.reconcile_moves


def capture_reconcile_inputs() -> dict[str, list]:
    """The exact ``changes`` list production hands to ``reconcile_moves``, per corpus pair.

    Wrapping rather than rebuilding: reconstructing this list here would measure the
    reconstruction, and the classification loop that produces it is precisely the thing the
    slice-2 question is about.
    """
    captured: dict[str, list] = {}
    holder: dict[str, str] = {}

    def spy(changes, threshold=MOVE_THRESHOLD):
        captured[holder["key"]] = list(changes)
        return REAL_RECONCILE(changes, threshold)

    db.reconcile_moves = spy
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
        db.reconcile_moves = REAL_RECONCILE
    return captured


def candidates_for(changes) -> tuple[list, list, list]:
    """Reproduce the candidate call ``reconcile_moves`` makes, with its own normalisation."""
    removed = [(i, c) for i, c in enumerate(changes) if c.change_type == "removed"]
    added = [(i, c) for i, c in enumerate(changes) if c.change_type == "added"]
    if not removed or not added:
        return [], removed, added
    cands = move_candidates(
        [db._normalize_text(rc.old_text or "") for _, rc in removed],
        [db._normalize_text(ac.new_text or "") for _, ac in added],
        MOVE_THRESHOLD,
    )
    return cands, removed, added


def selected_signature(changes) -> list[tuple]:
    """Ordered selected correspondences from the REAL function, keyed by element id.

    Element ids rather than list positions: the property under test is ordering, so a key
    read off the post-sort order could not detect a change in it.
    """
    out = REAL_RECONCILE(list(changes))
    return [(c.element_id_old, c.element_id_new) for c in out if c.change_type == "moved"]


def replay_assignment(cands, removed, added) -> tuple[list[tuple[str, str]], int, list[tuple]]:
    """Production's greedy loop, duplicated so the losing candidate is observable.

    Returns the selected correspondences in selection order, keyed by the same
    ``(element_id_old, element_id_new)`` identity production records, plus how many of
    those selections a same-similarity rival contested and a sample of them.
    """
    ordered = sorted(cands, reverse=True)
    claimed_r: set[int] = set()
    claimed_a: set[int] = set()
    selected: list[tuple[str, str]] = []
    tie_decided = 0
    examples: list[tuple] = []

    for sim, ri, ai in ordered:
        if ri in claimed_r or ai in claimed_a:
            continue
        # A competing candidate at the SAME similarity, still unclaimed at this moment,
        # wanting one of the same two slots. If one exists, only (ri, ai) separated them.
        rival = next(
            (
                (s2, r2, a2)
                for s2, r2, a2 in ordered
                if s2 == sim
                and (s2, r2, a2) != (sim, ri, ai)
                and r2 not in claimed_r
                and a2 not in claimed_a
                and (r2 == ri or a2 == ai)
            ),
            None,
        )
        claimed_r.add(ri)
        claimed_a.add(ai)

        # Resolve to the identity production records for this pair, so the comparison
        # below is against what production actually emits rather than against a count.
        _, rc = removed[ri]
        _, ac = added[ai]
        selected.append((rc.element_id_old, ac.element_id_new))

        if rival is not None:
            tie_decided += 1
            examples.append((round(sim, 6), (ri, ai), rival[1:]))

    return selected, tie_decided, examples


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", type=Path, default=None, help="write selected correspondences to JSON")
    args = ap.parse_args()

    captured = capture_reconcile_inputs()

    per_pair: dict[str, int] = {}
    dup_full_keys = 0
    dup_coords = 0
    tied_candidates = 0
    pairs_with_ties = 0
    total_selected = 0
    tie_decided = 0
    tie_examples: list[tuple] = []
    disagreements: list[str] = []
    dump: dict[str, list] = {}

    for key, changes in sorted(captured.items()):
        cands, removed, added = candidates_for(changes)
        per_pair[key] = len(cands)
        if not cands:
            continue

        keys = [tuple(c) for c in cands]
        dup_full_keys += len(keys) - len(set(keys))
        coords = [(ri, ai) for _, ri, ai in cands]
        dup_coords += len(coords) - len(set(coords))

        sims = Counter(sim for sim, _, _ in cands)
        tied_here = sum(n for n in sims.values() if n > 1)
        tied_candidates += tied_here
        if tied_here:
            pairs_with_ties += 1

        mine, mine_tie_decided, mine_examples = replay_assignment(cands, removed, added)
        sig = selected_signature(changes)

        # Exact agreement, on the set AND on the order. Reported separately so a failure
        # says which property broke; either one voids the tie figures for this corpus.
        if mine != sig:
            only_mine = [p for p in mine if p not in set(sig)]
            only_prod = [p for p in sig if p not in set(mine)]
            if set(mine) == set(sig):
                disagreements.append(
                    f"{key}: same {len(sig)} correspondences, DIFFERENT ORDER "
                    f"(first divergence at index {next(i for i, (a, b) in enumerate(zip(mine, sig)) if a != b)})"
                )
            else:
                disagreements.append(
                    f"{key}: SET differs -- {len(sig)} in production, {len(mine)} in the duplicate; "
                    f"only in duplicate={only_mine[:3]}; only in production={only_prod[:3]}"
                )
            continue

        # Only fold this pair's figures in once its duplicate is proven equivalent.
        total_selected += len(mine)
        tie_decided += mine_tie_decided
        for sim, winner, rival in mine_examples:
            if len(tie_examples) < 10:
                tie_examples.append((key, sim, winner, rival))
        dump[key] = [list(pair) for pair in sig]

    if disagreements:
        print("DUPLICATE-LOOP AGREEMENT FAILURES -- no tie figure is valid:")
        for line in disagreements:
            print(f"  {line}")
        raise SystemExit("duplicated greedy loop disagrees with production; numbers are void")

    counts = list(per_pair.values())
    nonzero = [n for n in counts if n]
    total = sum(counts)

    print("===== A: CANDIDATE POPULATION =====")
    print(f"corpus pairs: {len(counts)}")
    print(f"total candidates: {total}")
    print(f"pairs with >=1 candidate: {len(nonzero)}")
    if nonzero:
        print(f"min/median/max per pair (nonzero): {min(nonzero)} / {statistics.median(nonzero)} / {max(nonzero)}")
    for k, n in sorted(per_pair.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {n:6d}  ({100.0 * n / total:5.1f}%)  {k}")

    print("\n===== B: SELECTION KEY =====")
    print(f"duplicate full sort keys (sim, ri, ai): {dup_full_keys}")
    print(f"duplicate (ri, ai) coordinates: {dup_coords}")
    print(f"candidates sharing a similarity: {tied_candidates}")
    print(f"pairs containing a tie: {pairs_with_ties}")

    print("\n===== C: WHAT DECIDES A SELECTION =====")
    print(f"selected moves: {total_selected}")
    print(f"tie-decided selections: {tie_decided}")
    if total_selected:
        print(f"share decided by the (ri, ai) tiebreak: {100.0 * tie_decided / total_selected:.1f}%")
    for ex in tie_examples:
        print(f"  {ex[0]}  sim={ex[1]}  winner={ex[2]}  rival={ex[3]}")

    print(f"\nduplicate-loop agreement: exact set AND order match on all {len(dump)} pairs carrying a selection")

    if args.dump:
        args.dump.write_text(json.dumps(dump, indent=2, sort_keys=True))
        print(f"wrote selected correspondences for {len(dump)} pairs to {args.dump}")


if __name__ == "__main__":
    main()
