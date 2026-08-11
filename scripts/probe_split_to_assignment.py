"""Simulate moving the similarity split out of classification, and check it changes nothing.

Evidence for the ADR 0020 slice that makes one property true:

    Classification no longer thresholds or revokes correspondence.

``diff_bills`` currently decides, inside its classification loop, that a path-matched pair
is not one provision but a removal plus an addition (``diff_bill.py:586-606``). That is an
assignment decision executed inside classification. This probe runs the proposed two-pass
shape against production and reports whether anything moved.

THE EXACT CONDITION BEING MOVED, and why it is transcribed rather than tidied:

    old_normalized = _normalize_text(old_node.body_text)
    new_normalized = _normalize_text(new_node.body_text)
    text_changes = diff_text(old_normalized, new_normalized)
    if not text_changes:                                            -> kept (unchanged)
    elif text_similarity(...) < SIMILARITY_THRESHOLD:               -> REVOKED
    else:                                                           -> kept (modified)

So the pairing is revoked exactly when ``diff_text`` is non-empty AND the similarity falls
below the cutoff. The gate is the emptiness of a *word-level diff*, not a string equality,
and this probe preserves it verbatim -- including the ``diff_text`` call that a tidier
predicate would replace with ``old_normalized == new_normalized``. Section F measures
whether the two agree, and the answer is not a licence to substitute one for the other: an
agreement measured on 27 documents is not a proof about every input a bill can contain.

WHAT A GENERAL PROOF WOULD NEED, since section F cannot supply it:

    not diff_text(a, b)  iff  a == b,  for every NORMALIZED a, b

The forward direction is ``diff_text``'s own first line. The reverse needs two facts, and
section G checks the load-bearing one on inputs rather than on the corpus. (1) Every
character ``str.splitlines`` treats as a line boundary satisfies ``str.isspace()``, and
``_normalize_text`` is ``" ".join(text.split())``, whose no-argument ``split`` consumes
every such character -- so a normalized string contains NO line boundary and
``splitlines(keepends=True)`` returns ``[]`` or a single element. (2) With at most one
element per side, two unequal normalized strings give unequal line lists, and
``difflib.unified_diff`` yields nothing only when its two sequences are equal, so it emits
at least its ``---``/``+++`` header; the trailing ``rstrip`` comprehension preserves list
length. Section G runs (1) against the boundary set directly, which is a statement about
the function rather than about these 27 bills.

THE PROPOSED SHAPE, simulated here exactly:

    match_nodes provisional pairings
        -> PASS 1 (assignment): a revoked (old, new) becomes (old, None) then (None, new),
           adjacent, in place. Every other pairing passes through untouched.
        -> PASS 2 (classification): three branches only. The split branch is GONE, not
           moved -- a revoked pairing's two entries are built by the same code that already
           builds a structural removal and a structural addition.

NEGATIVE CONTROLS, because "the simulation agrees with production" is exactly the shape
that can pass while measuring nothing:

control A (policy)
    Revoke nothing at all. The simulated list must then DIFFER from production.

control B (emission order)
    Emit a revoked pairing as addition-then-removal. The simulated list must DIFFER while
    holding identical change counts -- the case a count-based check passes through.

control C (canonical)
    Mutate ONLY the predicate, leaving classification untouched, and require the committed
    canonical baseline to redden.

Read-only, writes nothing, changes no production code. Run from the project root:

    uv run python scripts/probe_split_to_assignment.py
"""

from __future__ import annotations

import difflib
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deltatrack.compare.xml as compare_xml_module  # noqa: E402
import deltatrack.diff_bill as db  # noqa: E402
from deltatrack.bill_tree import amount_text, normalize_bill  # noqa: E402
from deltatrack.diff_bill import BillDiff, NodeDiff, diff_bills, match_nodes  # noqa: E402
from deltatrack.similarity import MOVE_THRESHOLD, SIMILARITY_THRESHOLD, text_similarity  # noqa: E402
from tests.corpus_paths import DATA_DIR  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs, baseline_record  # noqa: E402

REAL_RECONCILE = db.reconcile_moves
REAL_DIFF_BILLS = compare_xml_module.diff_bills
REAL_DIFF_TEXT = db.diff_text

#: Every character ``str.splitlines`` treats as a line boundary (CPython's documented set).
LINE_BOUNDARIES = ("\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")

CALLS: Counter[str] = Counter()


def counting_diff_text(old_text: str, new_text: str) -> list[str]:
    """``diff_text`` with a call counter, installed over ``db.diff_text`` for a whole pass."""
    CALLS["diff_text"] += 1
    return REAL_DIFF_TEXT(old_text, new_text)


def pairing_is_kept(old_node, new_node) -> bool:
    """The legacy assignment decision, transcribed from ``diff_bill.py:586-606``.

    Deliberately NOT simplified to ``old_normalized == new_normalized``. The gate the
    current engine applies is the emptiness of ``diff_text``'s output, and a Phase-1
    extraction that swapped in a different-looking condition would be changing the rule
    while claiming to move it. The redundant computation is the visible residue of the
    fusion this slice does not yet remove; deleting it is a later change with its own
    evidence.
    """
    old_normalized = db._normalize_text(old_node.body_text)
    new_normalized = db._normalize_text(new_node.body_text)
    if not db.diff_text(old_normalized, new_normalized):
        return True
    return text_similarity(old_normalized, new_normalized) >= SIMILARITY_THRESHOLD


def pairing_is_kept_simplified(old_node, new_node) -> bool:
    """The tidier predicate, kept ONLY so section F can measure whether it agrees."""
    old_normalized = db._normalize_text(old_node.body_text)
    new_normalized = db._normalize_text(new_node.body_text)
    if old_normalized == new_normalized:
        return True
    return text_similarity(old_normalized, new_normalized) >= SIMILARITY_THRESHOLD


def decide(pairs: list, *, keep_everything: bool = False, reversed_emission: bool = False) -> list:
    """PASS 1 -- assignment. Provisional pairings in, decided pairings out.

    A revoked pairing becomes two, adjacent and in place, so classification emits its
    removal and its addition at the position the pairing occupied.
    """
    decided: list = []
    for old_node, new_node in pairs:
        revoked = (
            old_node is not None
            and new_node is not None
            and not keep_everything
            and not pairing_is_kept(old_node, new_node)
        )
        if not revoked:
            decided.append((old_node, new_node))
        elif reversed_emission:
            decided.append((None, new_node))
            decided.append((old_node, None))
        else:
            decided.append((old_node, None))
            decided.append((None, new_node))
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
    text_changes = db.diff_text(old_normalized, new_normalized)
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


def simulated_diff_bills(old_tree, new_tree, *, keep_everything: bool = False, reversed_emission: bool = False):
    """``diff_bills`` in the proposed two-pass shape, assembled from the passes above.

    Everything after classification is production's own: the real ``reconcile_moves``, the
    real ``_count_changes``. Only the ordering of the correspondence decision changes.
    """
    decided = decide(
        match_nodes(old_tree, new_tree),
        keep_everything=keep_everything,
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


def canonical_digests() -> dict[str, dict]:
    return {key: baseline_record(old, new) for key, old, new in baseline_pairs()}


def canonical_compare(label: str, committed: dict, produced: dict) -> list[str]:
    moved = [key for key in committed if committed[key]["sha256"] != produced[key]["sha256"]]
    verdict = "MATCHES the committed baseline" if not moved else f"DIFFERS on {len(moved)} pair(s)"
    print(f"{label}: {verdict}")
    for key in moved[:4]:
        before, after = committed[key], produced[key]
        print(f"    {key}: changes {before['changes']} -> {after['changes']}")
    return moved


def shape_violations(decided: list, changes: list) -> list[str]:
    """Classification must preserve the correspondence shape it is handed.

    The durable ADR 0020 property, stated so it outlives the comparison against production:
    classification is a length-preserving, order-preserving, side-preserving map from
    decided pairings to change records. That single statement refuses all five failures --
    splitting one pairing into two and joining two into one both move the length, while
    dropping a side, inventing one, or substituting a different observation all show up as
    a side mismatch at the pairing's own index.

    Returns the violations rather than asserting, so a caller can prove the check fires by
    handing it a doctored list.
    """
    if len(changes) != len(decided):
        return [f"classification emitted {len(changes)} records for {len(decided)} decided pairings"]
    problems = []
    for index, ((old_node, new_node), change) in enumerate(zip(decided, changes)):
        expected_old = "" if old_node is None else old_node.element_id
        expected_new = "" if new_node is None else new_node.element_id
        if change.element_id_old != expected_old or change.element_id_new != expected_new:
            problems.append(
                f"index {index}: sides {change.element_id_old!r}/{change.element_id_new!r} "
                f"!= {expected_old!r}/{expected_new!r}"
            )
    return problems


def move_pass_similarity(old_normalized: str, new_normalized: str) -> float:
    """The ratio ``similarity.move_candidates`` would compute for this pair.

    Built the way ``move_candidates`` builds it -- a bare ``SequenceMatcher`` with
    ``set_seq2`` then ``set_seq1`` -- rather than the way ``text_similarity`` does, so an
    autojunk or construction difference between the two sites would show up here instead of
    being assumed away.
    """
    matcher = difflib.SequenceMatcher()
    matcher.set_seq2(new_normalized.split())
    matcher.set_seq1(old_normalized.split())
    return matcher.ratio()


def _label(change: NodeDiff) -> str:
    return f"{change.change_type}/{change.element_id_old or change.element_id_new}"


def first_divergence(left: list, right: list) -> str:
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return f"index {index}: {_label(a)} vs {_label(b)}"
    return f"identical for {min(len(left), len(right))} entries, then lengths differ ({len(left)} vs {len(right)})"


def check_normalization_removes_line_boundaries() -> list[str]:
    """Section G: the general leg of the proof, checked on inputs rather than on the corpus."""
    survivors = []
    for boundary in LINE_BOUNDARIES:
        normalized = db._normalize_text(f"alpha{boundary}beta")
        if normalized != "alpha beta" or len(normalized.splitlines(keepends=True)) != 1:
            survivors.append(repr(boundary))
    normalized_crlf = db._normalize_text("alpha\r\nbeta")
    if normalized_crlf != "alpha beta":
        survivors.append(repr("\r\n"))
    return survivors


def main() -> None:
    pairs_checked = 0
    revoked_total = 0
    paired_total = 0
    predicate_disagreements = 0
    mismatches: list[str] = []
    order_key_mismatches: list[str] = []
    control_a_reached = control_a_differed = 0
    control_b_reached = control_b_differed = control_b_same_counts = 0
    shape_problems: list[str] = []
    control_d_reached = control_d_caught = 0
    repairable_revocations = 0
    # Plain integers, NOT entries in CALLS: the per-pair `CALLS.clear()` below would wipe a
    # running total stored there, and the corpus figure would silently become the last
    # pair's figure -- which is exactly what an earlier revision of this probe reported.
    simulated_calls_total = 0
    production_calls_total = 0

    db.diff_text = counting_diff_text
    try:
        for key, old_path, new_path in baseline_pairs():
            old_tree = normalize_bill(old_path)
            new_tree = normalize_bill(new_path)
            provisional = match_nodes(old_tree, new_tree)

            paired = [(o, n) for o, n in provisional if o is not None and n is not None]
            paired_total += len(paired)
            revoked = [(o, n) for o, n in paired if not pairing_is_kept(o, n)]
            revoked_total += len(revoked)
            predicate_disagreements += sum(
                1 for o, n in paired if pairing_is_kept(o, n) != pairing_is_kept_simplified(o, n)
            )

            # Both counts must cover the WHOLE pipeline or they are not comparable: the
            # production figure below includes reconcile_moves' own diff_text calls, so the
            # simulated one runs the same reconciliation rather than stopping at
            # classification.
            CALLS.clear()
            simulated = [classify(o, n) for o, n in decide(provisional)]
            REAL_RECONCILE(list(simulated))
            simulated_calls = CALLS["diff_text"]

            CALLS.clear()
            produced = production_changes(old_tree, new_tree)
            simulated_calls_total += simulated_calls
            production_calls_total += CALLS["diff_text"]

            if simulated != produced:
                mismatches.append(f"{key}: {first_divergence(simulated, produced)}")
                continue

            decided = decide(provisional)
            decided_removals = [o for o, n in decided if o is not None and n is None]
            decided_additions = [n for o, n in decided if o is None and n is not None]
            removal_key_holds = [node.element_id for node in decided_removals] == [
                c.element_id_old for c in produced if c.change_type == "removed"
            ]
            addition_key_holds = [node.element_id for node in decided_additions] == [
                c.element_id_new for c in produced if c.change_type == "added"
            ]
            if not (removal_key_holds and addition_key_holds):
                order_key_mismatches.append(f"{key}: removals={removal_key_holds} additions={addition_key_holds}")

            # --- structural: classification preserves the shape it is given ------------
            shape_problems += [f"{key}: {problem}" for problem in shape_violations(decided, produced)]

            # Control D, self-proving: doctor one record so a side goes missing, and require
            # the shape check to notice. A check that has never rejected anything cannot be
            # told apart from one that accepts everything.
            paired_index = next(
                (i for i, (o, n) in enumerate(decided) if o is not None and n is not None),
                None,
            )
            if paired_index is not None:
                control_d_reached += 1
                doctored = list(produced)
                doctored[paired_index] = replace(doctored[paired_index], element_id_new="")
                if shape_violations(decided, doctored):
                    control_d_caught += 1

            # A revoked pairing scores below SIMILARITY_THRESHOLD; the move pass needs
            # MOVE_THRESHOLD over the same measure and normalisation. Checked rather than
            # read off the constants, because move_candidates builds its SequenceMatcher
            # differently and an autojunk difference would not announce itself.
            repairable_revocations += sum(
                1
                for old_node, new_node in revoked
                if move_pass_similarity(db._normalize_text(old_node.body_text), db._normalize_text(new_node.body_text))
                >= MOVE_THRESHOLD
            )

            if revoked:
                control_a_reached += 1
                if [classify(o, n) for o, n in decide(provisional, keep_everything=True)] != produced:
                    control_a_differed += 1
                control_b_reached += 1
                control_b = [classify(o, n) for o, n in decide(provisional, reversed_emission=True)]
                if control_b != produced:
                    control_b_differed += 1
                    control_b_same_counts += sorted(c.change_type for c in control_b) == sorted(
                        c.change_type for c in produced
                    )

            pairs_checked += 1
    finally:
        db.diff_text = REAL_DIFF_TEXT

    print("===== A: DOES THE TWO-PASS SHAPE REPRODUCE PRODUCTION? =====")
    print(f"corpus pairs compared element-wise and length-checked: {pairs_checked}")
    print(f"pairs whose simulated change list DIFFERS from production: {len(mismatches)}")
    for line in mismatches[:5]:
        print(f"  {line}")

    print("\n===== B: THE DECISION MOVED =====")
    print(f"path-matched pairings: {paired_total}")
    print(f"pairings revoked by the transcribed predicate: {revoked_total}")

    print("\n===== C: IS (ri, ai) DERIVABLE BEFORE CLASSIFICATION? =====")
    print(f"pairs where decided-pairing order does NOT reproduce the filtered order: {len(order_key_mismatches)}")
    for line in order_key_mismatches[:5]:
        print(f"  {line}")

    print("\n===== D: NEGATIVE CONTROLS =====")
    print(f"control A (revoke nothing)  reached {control_a_reached} pairs, differed on {control_a_differed}")
    print(f"control B (reversed order)  reached {control_b_reached} pairs, differed on {control_b_differed}")
    print(f"  of those, with IDENTICAL change-type counts: {control_b_same_counts}")

    print("\n===== D2: CLASSIFICATION PRESERVES THE SHAPE IT IS GIVEN =====")
    print(f"shape violations across the corpus: {len(shape_problems)}")
    for line in shape_problems[:5]:
        print(f"  {line}")
    print(f"control D (a side deliberately dropped) reached {control_d_reached} pairs, caught {control_d_caught}")
    print(f"revoked pairings the move pass could re-pair WITH EACH OTHER: {repairable_revocations}")

    print("\n===== E: diff_text CALL COST =====")
    print(f"production calls (whole pipeline): {production_calls_total}")
    print(f"two-pass calls (predicate + classification): {simulated_calls_total}")
    print(f"additional calls from preserving the exact condition: {simulated_calls_total - production_calls_total}")

    print("\n===== F: DOES THE TIDIER PREDICATE AGREE? (corpus only, NOT a proof) =====")
    print(f"path-matched pairings where the two predicates disagree: {predicate_disagreements}")
    print("Agreement here licenses nothing on its own -- see section G for the general leg.")

    print("\n===== G: NORMALIZATION REMOVES EVERY LINE BOUNDARY (input-level, not corpus) =====")
    survivors = check_normalization_removes_line_boundaries()
    print(f"line-boundary characters surviving _normalize_text: {len(survivors)} {survivors}")

    if mismatches:
        raise SystemExit("the two-pass shape does not reproduce production; it is not behaviour-preserving")
    if control_a_reached and control_a_differed != control_a_reached:
        raise SystemExit("VACUOUS: removing the revocation did not move the output on every pair carrying one")
    if control_b_reached and control_b_differed != control_b_reached:
        raise SystemExit("VACUOUS: reversing removed/added emission did not move the output")
    if shape_problems:
        raise SystemExit("classification did not preserve the correspondence shape it was given")
    if control_d_reached != control_d_caught:
        raise SystemExit("VACUOUS: the shape check missed a deliberately dropped side, so it proves nothing")
    if repairable_revocations:
        raise SystemExit("a revoked pairing is reachable by the move pass; the two cutoffs are not ordered as assumed")

    committed = json.loads((DATA_DIR / "canonical_baseline.json").read_text())
    print("\n===== H: CANONICAL OUTPUT UNDER THE TWO-PASS SHAPE =====")
    compare_xml_module.diff_bills = simulated_diff_bills
    try:
        canonical_clean = canonical_compare("two-pass, transcribed predicate ", committed, canonical_digests())
        compare_xml_module.diff_bills = lambda old, new: simulated_diff_bills(old, new, keep_everything=True)
        canonical_faulted = canonical_compare("two-pass, predicate MUTATED     ", committed, canonical_digests())
    finally:
        compare_xml_module.diff_bills = REAL_DIFF_BILLS
    canonical_restored = canonical_compare("production restored             ", committed, canonical_digests())

    if canonical_clean or canonical_restored:
        raise SystemExit("the two-pass shape moved canonical bytes; it is not byte-identical")
    if not canonical_faulted:
        raise SystemExit("VACUOUS: mutating the predicate moved no canonical byte, so the baseline cannot police it")
    print(
        f"\nRESULT: element-wise identical, canonical byte-identical, and mutating ONLY the "
        f"predicate reddens {len(canonical_faulted)} pair(s) with classification untouched."
    )


if __name__ == "__main__":
    main()
