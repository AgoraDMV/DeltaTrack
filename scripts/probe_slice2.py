"""Slice 2 investigation probe: candidate population, selection-key ties, order sensitivity.

Instruments by WRAPPING production functions, never by reimplementing them, so the
population measured is the population production actually forms.

Run from the worktree root:  uv run python <this file>
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

import deltatrack.diff_bill as db  # noqa: E402
from deltatrack.similarity import MOVE_THRESHOLD, move_candidates  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs  # noqa: E402

REAL_RECONCILE = db.reconcile_moves
REAL_MOVE_CANDIDATES = db.move_candidates


def capture_inputs():
    """Run the real pipeline over every baseline pair, capturing reconcile_moves' input.

    Wrapping rather than re-deriving: the `changes` list handed to reconcile_moves is
    produced by diff_bills' own classification loop, and any reconstruction of it here
    would be measuring my copy instead of production's.
    """
    captured = {}
    key_holder = {}

    def spy(changes, threshold=MOVE_THRESHOLD):
        captured[key_holder["key"]] = list(changes)
        return REAL_RECONCILE(changes, threshold)

    db.reconcile_moves = spy
    try:
        from deltatrack.compare.xml import compare_xml
        from deltatrack.version_stems import label_from_stem

        for key, old_path, new_path in baseline_pairs():
            key_holder["key"] = key
            compare_xml(
                old_path.read_bytes(),
                new_path.read_bytes(),
                start_label=label_from_stem(old_path.stem),
                end_label=label_from_stem(new_path.stem),
            )
    finally:
        db.reconcile_moves = REAL_RECONCILE
    return captured


def candidates_for(changes):
    """Exactly what reconcile_moves computes, via the same call it makes."""
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


def moved_signature(out):
    """Ordered selected correspondences, keyed by element id, not by list position.

    Position-derived keys would be circular here: the thing under test is whether
    ordering changes, so a key read off the post-sort order cannot detect it.
    """
    return [(c.element_id_old, c.element_id_new, c.change_type) for c in out if c.change_type == "moved"]


def full_signature(out):
    return [(c.change_type, c.element_id_old, c.element_id_new) for c in out]


def main():
    captured = capture_inputs()
    print(f"pairs captured: {len(captured)}")

    # ---------- A: candidate population ----------
    per_pair = {}
    all_keys_dup = 0
    sim_counter_total = Counter()
    tie_examples = []
    structural_dup_check = 0

    for key, changes in sorted(captured.items()):
        cands, removed, added = candidates_for(changes)
        per_pair[key] = len(cands)

        # B: full sort key duplicates. The full tuple is (sim, ri, ai).
        keys = [tuple(c) for c in cands]
        if len(set(keys)) != len(keys):
            all_keys_dup += len(keys) - len(set(keys))
        # (ri, ai) coordinate duplicates -- structural uniqueness check
        coords = [(ri, ai) for _, ri, ai in cands]
        if len(set(coords)) != len(coords):
            structural_dup_check += len(coords) - len(set(coords))

        sims = Counter(sim for sim, _, _ in cands)
        sim_counter_total.update({key: sum(n for n in sims.values() if n > 1)})
        for sim, n in sims.items():
            if n > 1 and len(tie_examples) < 12:
                members = [(ri, ai) for s, ri, ai in cands if s == sim]
                tie_examples.append((key, round(sim, 6), n, members[:4]))

    counts = [n for n in per_pair.values()]
    nonzero = [n for n in counts if n > 0]
    total = sum(counts)
    print("\n===== A: CANDIDATE POPULATION =====")
    print(f"total candidates across corpus: {total}")
    print(f"pairs with >=1 candidate: {len(nonzero)} of {len(counts)}")
    if nonzero:
        print(f"min/median/max per pair (nonzero): {min(nonzero)} / {statistics.median(nonzero)} / {max(nonzero)}")
    top = sorted(per_pair.items(), key=lambda kv: -kv[1])[:6]
    print("top pairs by candidate count:")
    for k, n in top:
        share = (100.0 * n / total) if total else 0.0
        print(f"  {n:6d}  ({share:5.1f}%)  {k}")

    print("\n===== B: SELECTION KEY =====")
    print(f"duplicate FULL sort keys (sim, ri, ai): {all_keys_dup}")
    print(f"duplicate (ri, ai) coordinates:         {structural_dup_check}")
    tied_pairs = {k: v for k, v in sim_counter_total.items() if v > 0}
    print(f"pairs containing >=1 similarity tie: {len(tied_pairs)}")
    print(f"total candidates sharing a similarity with another: {sum(sim_counter_total.values())}")
    print("tie examples (bill pair, similarity, how many candidates share it, sample (ri, ai)):")
    for ex in tie_examples:
        print(f"  {ex[0]}  sim={ex[1]}  n={ex[2]}  members={ex[3]}")

    # ---------- C: order perturbation ----------
    print("\n===== C: ORDER PERTURBATION =====")
    orders = ["reversed", "seed1", "seed2", "seed3"]
    disagreements = {o: [] for o in orders}
    perturbation_reached = Counter()
    perturbation_differed = Counter()

    for key, changes in sorted(captured.items()):
        base_out = REAL_RECONCILE(list(changes))
        base_sig = moved_signature(base_out)
        base_full = full_signature(base_out)
        if not base_sig:
            continue

        for order in orders:

            def patched(removed_texts, added_texts, threshold, _order=order):
                cands = REAL_MOVE_CANDIDATES(removed_texts, added_texts, threshold)
                original = list(cands)
                if _order == "reversed":
                    cands = list(reversed(cands))
                else:
                    rng = random.Random(int(_order[-1]))
                    cands = list(cands)
                    rng.shuffle(cands)
                perturbation_reached[_order] += 1
                if cands != original and len(original) > 1:
                    perturbation_differed[_order] += 1
                return cands

            db.move_candidates = patched
            try:
                out = REAL_RECONCILE(list(changes))
            finally:
                db.move_candidates = REAL_MOVE_CANDIDATES

            if moved_signature(out) != base_sig or full_signature(out) != base_full:
                disagreements[order].append(key)

    for order in orders:
        print(
            f"  {order:9s}  perturbation reached selection on {perturbation_reached[order]} pairs, "
            f"actually reordered the list on {perturbation_differed[order]}; "
            f"outcome differed on {len(disagreements[order])} pairs"
        )
        if disagreements[order]:
            print(f"      differing pairs: {disagreements[order][:5]}")

    print("\nGUARD: if 'actually reordered' is 0, the experiment proves nothing.")
    payload = {
        "total_candidates": total,
        "pairs_with_candidates": len(nonzero),
        "dup_full_keys": all_keys_dup,
        "dup_coords": structural_dup_check,
        "tied_candidates": sum(sim_counter_total.values()),
        "disagreements": dict(disagreements),
        "perturbation_differed": dict(perturbation_differed),
    }
    # Optional first argument, so the probe writes nowhere unless asked. It previously
    # hardcoded an absolute path into one agent session's scratch directory, which made
    # the run unreproducible for anyone else and wrote outside the repository.
    if len(sys.argv) > 1:
        out_path = Path(sys.argv[1])
        out_path.write_text(json.dumps(payload, indent=2))
        print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
