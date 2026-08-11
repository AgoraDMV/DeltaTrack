"""Simulate moving the similarity split out of classification, and check it changes nothing.

Evidence for the ADR 0020 slice that makes one property true:

    Classification no longer thresholds or revokes correspondence.

``diff_bills`` currently decides, inside its classification loop, that a path-matched pair
whose normalised texts differ and whose similarity falls below ``SIMILARITY_THRESHOLD`` is
not one provision but a removal plus an addition (``diff_bill.py:606``). That is an
assignment decision executed inside classification. This probe runs the proposed two-pass
shape against production and reports whether the two agree.

THE PROPOSED SHAPE, simulated here exactly:

    match_nodes provisional pairings
        -> PASS 1 (assignment): a rejected (old, new) becomes (old, None) then (None, new),
           adjacent, in place. Every other pairing passes through untouched.
        -> PASS 2 (classification): three branches only. The split branch is GONE, not
           moved -- a rejected pair's two entries are built by the same code that already
           builds a structural removal and a structural addition.

WHAT IT MEASURES

1. **Element-wise agreement.** The simulated pre-reconcile change list is compared against
   production's, ``NodeDiff`` by ``NodeDiff``, in order. Not counts: a reordering or a
   swapped field leaves counts identical, and that is the failure this slice risks.

2. **Whether ``ri``/``ai`` survive the move.** The legacy assignment-order key is a pair of
   positions in the filtered removed/added lists of the *classified* change list. If the
   k-th ``(old, None)`` decided pairing is the k-th removal, and likewise for additions,
   then the key is derivable from assignment state **before** classification runs -- which
   is what a later round-2 slice needs in order to receive unmatched observations, their
   ``ObservationRef``s and the legacy order key without routing any of it through
   ``NodeDiff``.

3. **What ``diff_text`` computation disappears.** Today ``diff_text`` runs for every paired
   node before the threshold is consulted, so its result is computed and discarded for
   every rejected pair. The simulation omits that call entirely, so agreement in (1) is
   itself the evidence that dropping it is safe -- rather than an argument from purity.

NEGATIVE CONTROLS, because "the simulation agrees with production" is exactly the shape
that can pass while measuring nothing:

control A (policy)
    Reject nothing at all. The simulated list must then DIFFER from production, on the
    pairs that carry splits. If it does not, the comparison is not reading the decision.

control B (emission order)
    Emit a rejected pair as addition-then-removal instead of removal-then-addition. The
    simulated list must DIFFER while holding identical change counts -- the precise case a
    count-based check passes through.

Read-only, writes nothing, changes no production code. Run from the project root:

    uv run python scripts/probe_split_to_assignment.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deltatrack.compare.xml as compare_xml_module  # noqa: E402
import deltatrack.diff_bill as db  # noqa: E402
from deltatrack.bill_tree import amount_text, normalize_bill  # noqa: E402
from deltatrack.diff_bill import BillDiff, NodeDiff, diff_bills, diff_text, match_nodes  # noqa: E402
from deltatrack.similarity import MOVE_THRESHOLD, SIMILARITY_THRESHOLD, text_similarity  # noqa: E402
from tests.corpus_paths import DATA_DIR  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs, baseline_record  # noqa: E402

REAL_RECONCILE = db.reconcile_moves
REAL_DIFF_BILLS = compare_xml_module.diff_bills


def pairing_is_kept(old_node, new_node) -> bool:
    """The legacy assignment decision, stated as its own predicate.

    Exactly ``diff_bills``' condition at ``diff_bill.py:606``, read in the positive: a
    path-matched pairing is kept unless its normalised texts differ AND their word-level
    similarity falls below ``SIMILARITY_THRESHOLD``.

    The identical-text carve-out is written out rather than left to arithmetic. Today it is
    redundant, because ``text_similarity(x, x)`` is 1.0 and the cutoff is 0.4 -- but that is
    a fact about the current *value*, and the current *rule* is that an identical pair is
    never revoked. Encoding the rule keeps the predicate faithful if the value ever moves.
    """
    old_norm = db._normalize_text(old_node.body_text)
    new_norm = db._normalize_text(new_node.body_text)
    if old_norm == new_norm:
        return True
    return text_similarity(old_norm, new_norm) >= SIMILARITY_THRESHOLD


def decide(pairs: list, *, reject_nothing: bool = False, reversed_emission: bool = False) -> list:
    """PASS 1 -- assignment. Provisional pairings in, decided pairings out.

    A rejected pairing becomes two, adjacent and in place, so classification emits its
    removal and its addition at the position the pairing occupied.
    """
    decided: list = []
    for old_node, new_node in pairs:
        if (
            old_node is not None
            and new_node is not None
            and not reject_nothing
            and not pairing_is_kept(old_node, new_node)
        ):
            if reversed_emission:
                decided.append((None, new_node))
                decided.append((old_node, None))
            else:
                decided.append((old_node, None))
                decided.append((None, new_node))
        else:
            decided.append((old_node, new_node))
    return decided


def classify(old_node, new_node) -> NodeDiff:
    """PASS 2 -- classification. Three branches, no threshold, no correspondence change.

    Byte-for-byte the same constructions ``diff_bills`` already performs. The split branch
    is absent because it has nothing left to do: its two emissions were always identical to
    the structural removal and structural addition below.
    """
    if old_node is None:
        return NodeDiff(
            display_path_old=None,
            display_path_new=new_node.display_path,
            match_path=new_node.match_path,
            change_type="added",
            old_text=None,
            new_text=new_node.body_text,
            text_diff=None,
            section_number=new_node.section_number,
            element_id_old="",
            element_id_new=new_node.element_id,
            new_amount_text=amount_text(new_node),
        )
    if new_node is None:
        return NodeDiff(
            display_path_old=old_node.display_path,
            display_path_new=None,
            match_path=old_node.match_path,
            change_type="removed",
            old_text=old_node.body_text,
            new_text=None,
            text_diff=None,
            section_number=old_node.section_number,
            element_id_old=old_node.element_id,
            element_id_new="",
            old_amount_text=amount_text(old_node),
        )

    old_normalized = db._normalize_text(old_node.body_text)
    new_normalized = db._normalize_text(new_node.body_text)
    text_changes = diff_text(old_normalized, new_normalized)
    return NodeDiff(
        display_path_old=old_node.display_path,
        display_path_new=new_node.display_path,
        match_path=old_node.match_path,
        change_type="unchanged" if not text_changes else "modified",
        old_text=old_node.body_text,
        new_text=new_node.body_text,
        text_diff=None if not text_changes else text_changes,
        section_number=new_node.section_number or old_node.section_number,
        element_id_old=old_node.element_id,
        element_id_new=new_node.element_id,
        old_amount_text=amount_text(old_node),
        new_amount_text=amount_text(new_node),
    )


def production_changes(old_tree, new_tree) -> list:
    """The change list production hands to ``reconcile_moves``, captured by wrapping it."""
    captured: list = []

    def spy(changes, threshold=MOVE_THRESHOLD):
        captured.extend(changes)
        return REAL_RECONCILE(changes, threshold)

    db.reconcile_moves = spy
    try:
        diff_bills(old_tree, new_tree)
    finally:
        db.reconcile_moves = REAL_RECONCILE
    return captured


def simulated_diff_bills(old_tree, new_tree, *, reject_nothing: bool = False, reversed_emission: bool = False):
    """``diff_bills`` in the proposed two-pass shape, assembled from the passes above.

    Everything after classification is production's own: the real ``reconcile_moves``, the
    real ``_count_changes``. Only the ordering of the correspondence decision changes.
    """
    decided = decide(
        match_nodes(old_tree, new_tree),
        reject_nothing=reject_nothing,
        reversed_emission=reversed_emission,
    )
    changes = REAL_RECONCILE([classify(old_node, new_node) for old_node, new_node in decided])
    return BillDiff(
        old_version=old_tree.version,
        new_version=new_tree.version,
        congress=old_tree.congress,
        bill_type=old_tree.bill_type,
        bill_number=old_tree.bill_number,
        summary=db._count_changes(changes),
        changes=changes,
    )


def canonical_digests() -> dict[str, dict]:
    return {key: baseline_record(old, new) for key, old, new in baseline_pairs()}


def canonical_compare(label: str, committed: dict, produced: dict) -> list[str]:
    moved = [key for key in committed if committed[key]["sha256"] != produced[key]["sha256"]]
    print(f"{label}: {'MATCHES the committed baseline' if not moved else f'DIFFERS on {len(moved)} pair(s)'}")
    for key in moved[:4]:
        before, after = committed[key], produced[key]
        print(f"    {key}: changes {before['changes']} -> {after['changes']}")
    return moved


def _label(change: NodeDiff) -> str:
    return f"{change.change_type}/{change.element_id_old or change.element_id_new}"


def first_divergence(left: list, right: list) -> str:
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return f"index {index}: {_label(a)} vs {_label(b)}"
    return f"identical for {min(len(left), len(right))} entries, then lengths differ ({len(left)} vs {len(right)})"


def main() -> None:
    pairs_checked = 0
    rejected_total = 0
    diff_text_calls_dropped = 0
    mismatches: list[str] = []
    order_key_mismatches: list[str] = []
    control_a_differed = 0
    control_a_reached = 0
    control_b_differed = 0
    control_b_same_counts = 0
    control_b_reached = 0

    for key, old_path, new_path in baseline_pairs():
        old_tree = normalize_bill(old_path)
        new_tree = normalize_bill(new_path)

        provisional = match_nodes(old_tree, new_tree)
        rejected = [(o, n) for o, n in provisional if o is not None and n is not None and not pairing_is_kept(o, n)]
        rejected_total += len(rejected)
        diff_text_calls_dropped += len(rejected)

        decided = decide(provisional)
        simulated = [classify(o, n) for o, n in decided]
        produced = production_changes(old_tree, new_tree)

        if simulated != produced:
            mismatches.append(f"{key}: {first_divergence(simulated, produced)}")
            continue

        # --- is (ri, ai) derivable from assignment state, before classification? --------
        decided_removals = [o for o, n in decided if o is not None and n is None]
        decided_additions = [n for o, n in decided if o is None and n is not None]
        classified_removals = [c for c in produced if c.change_type == "removed"]
        classified_additions = [c for c in produced if c.change_type == "added"]
        removal_key_holds = [node.element_id for node in decided_removals] == [
            c.element_id_old for c in classified_removals
        ]
        addition_key_holds = [node.element_id for node in decided_additions] == [
            c.element_id_new for c in classified_additions
        ]
        if not (removal_key_holds and addition_key_holds):
            order_key_mismatches.append(f"{key}: removals_ok={removal_key_holds} additions_ok={addition_key_holds}")

        # --- control A: reject nothing --------------------------------------------------
        if rejected:
            control_a_reached += 1
            control_a = [classify(o, n) for o, n in decide(provisional, reject_nothing=True)]
            if control_a != produced:
                control_a_differed += 1

            # --- control B: emit addition before removal --------------------------------
            control_b_reached += 1
            control_b = [classify(o, n) for o, n in decide(provisional, reversed_emission=True)]
            if control_b != produced:
                control_b_differed += 1
                same_counts = sorted(c.change_type for c in control_b) == sorted(c.change_type for c in produced)
                control_b_same_counts += same_counts

        pairs_checked += 1

    print("===== A: DOES THE TWO-PASS SHAPE REPRODUCE PRODUCTION? =====")
    print(f"corpus pairs compared element-wise: {pairs_checked}")
    print(f"pairs whose simulated change list DIFFERS from production: {len(mismatches)}")
    for line in mismatches[:5]:
        print(f"  {line}")

    print("\n===== B: THE DECISION MOVED =====")
    print(f"pairings rejected by the extracted predicate: {rejected_total}")
    print(f"diff_text calls that disappear (computed and discarded today): {diff_text_calls_dropped}")

    print("\n===== C: IS (ri, ai) DERIVABLE BEFORE CLASSIFICATION? =====")
    print(f"pairs where the decided-pairing order does NOT reproduce the filtered order: {len(order_key_mismatches)}")
    for line in order_key_mismatches[:5]:
        print(f"  {line}")

    print("\n===== D: NEGATIVE CONTROLS =====")
    print(f"control A (reject nothing)   reached {control_a_reached} pairs, differed on {control_a_differed}")
    print(f"control B (reversed order)   reached {control_b_reached} pairs, differed on {control_b_differed}")
    print(f"  of those, with IDENTICAL change-type counts: {control_b_same_counts}")

    if mismatches:
        raise SystemExit("the two-pass shape does not reproduce production; it is not behaviour-preserving")

    # ----- E: the same question asked at the consumed output ---------------------------
    committed = json.loads((DATA_DIR / "canonical_baseline.json").read_text())
    print("\n===== E: CANONICAL OUTPUT UNDER THE TWO-PASS SHAPE =====")
    compare_xml_module.diff_bills = simulated_diff_bills
    try:
        canonical_clean = canonical_compare("two-pass, production predicate  ", committed, canonical_digests())
        compare_xml_module.diff_bills = lambda old, new: simulated_diff_bills(old, new, reject_nothing=True)
        canonical_faulted = canonical_compare("two-pass, predicate MUTATED     ", committed, canonical_digests())
    finally:
        compare_xml_module.diff_bills = REAL_DIFF_BILLS
    canonical_restored = canonical_compare("production restored             ", committed, canonical_digests())

    if canonical_clean or canonical_restored:
        raise SystemExit("the two-pass shape moved canonical bytes; it is not byte-identical")
    if not canonical_faulted:
        raise SystemExit(
            "VACUOUS: mutating the assignment predicate moved no canonical byte, so the baseline "
            "cannot police this slice"
        )
    print(
        f"\ncanonical: byte-identical under the two-pass shape; mutating ONLY the predicate "
        f"reddens {len(canonical_faulted)} pair(s), classification untouched."
    )
    if control_a_reached and control_a_differed != control_a_reached:
        raise SystemExit("VACUOUS: removing the split decision did not move the output on every pair carrying one")
    if control_b_reached and control_b_differed != control_b_reached:
        raise SystemExit("VACUOUS: reversing removed/added emission did not move the output")
    print("\nRESULT: element-wise identical, and both controls reddened on every pair they reached.")


if __name__ == "__main__":
    main()
