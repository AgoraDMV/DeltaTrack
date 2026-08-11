"""Prove the canonical byte-identity gate reddens when move correspondence changes.

The acceptance criterion for every ADR 0020 Phase 1 slice is that
``tests/test_canonical_baseline.py`` stays green. A gate nobody has ever seen fail cannot
distinguish "the extraction preserved behaviour" from "the gate cannot see this class of
change" -- and correspondence is precisely the class it is being trusted for. So this
injects a real correspondence change and watches the digests move.

The fault is chosen to be the one #581 is most likely to introduce by accident:
**substituting ADR 0019 ordinals for the legacy ``(ri, ai)`` component of the sort key.**
``scripts/probe_round2_migration.py`` measures that this changes the selected move set on
exactly 3 of the 16 selecting corpus pairs, so the prediction is sharp -- and it is
enforced as a prediction rather than a remark: those exact three digests must move and no
others. The pair keys are imported from that probe rather than respelled here, so the two
cannot drift into disagreeing about which pairs matter.

FOUR PASSES, because a two-pass green/red would leave two other explanations open:

1. **production** -- the harness reproduces the committed baseline. Without this a later
   mismatch could be the harness rather than the fault. Must be EMPTY.
2. **duplicate, production key** -- the copied ``reconcile_moves`` below must reproduce the
   committed baseline too. A copy made in order to instrument something is a second
   implementation that can drift; unless it is shown equivalent first, pass 3 would be
   comparing the ordinal key against a drifted copy rather than against production. Must
   be EMPTY.
3. **duplicate, ordinal key** -- the injected fault. Must be EXACTLY the expected three.
4. **production, restored** -- the baseline matches again, so the difference was the fault
   and not something sticky the run left behind. Must be EMPTY.

An extra reddened pair, a missing one, or a different one fails the run. "Non-empty" would
have been satisfied by a fault that reddened everything, which is the shape a genuinely
broken harness produces.

The ``element_id -> ordinal`` bridge is built through ``probe_round2_migration``'s
fail-closed :func:`~scripts.probe_round2_migration.ordinal_bridge`, which refuses an empty
or repeated id rather than silently constructing a dictionary that collapses two
observations onto one address. The bridge is a MEASUREMENT convenience only -- ``NodeDiff``
carries no node reference -- and ADR 0019 refuses ``element_id`` as identity.

Read-only with respect to the repository: it patches module attributes at runtime and
restores them, and writes no file. Exits non-zero on any failure. Run from the project
root:

    uv run python scripts/probe_canonical_sensitivity.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deltatrack.diff_bill as db  # noqa: E402
from deltatrack.diff_bill import NodeDiff, diff_text  # noqa: E402
from deltatrack.similarity import MOVE_THRESHOLD, move_candidates  # noqa: E402
from scripts.probe_round2_migration import ORDINAL_SENSITIVE_PAIRS, ordinal_bridge  # noqa: E402
from tests.corpus_paths import DATA_DIR  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs, baseline_record  # noqa: E402

REAL_MATCH_NODES = db.match_nodes
REAL_RECONCILE = db.reconcile_moves

#: Element-id -> ordinal maps for the version pair currently being compared, populated by
#: the ``match_nodes`` spy. A measurement bridge only: ``NodeDiff`` carries no node
#: reference, and ADR 0019 refuses ``element_id`` as identity.
CURRENT: dict[str, dict[str, int]] = {}

#: The corpus key currently being compared, so a bridge failure names the pair.
HOLDER: dict[str, str] = {"key": "<none>"}


def match_spy(old, new):
    CURRENT["old"] = ordinal_bridge(old.nodes, f"{HOLDER['key']} [old]")
    CURRENT["new"] = ordinal_bridge(new.nodes, f"{HOLDER['key']} [new]")
    return REAL_MATCH_NODES(old, new)


def reconcile_copy(changes: list, threshold: float = MOVE_THRESHOLD, *, key: str = "legacy") -> list:
    """``diff_bill.reconcile_moves``, copied verbatim except for the sort key.

    ``key="legacy"`` sorts on the full ``(similarity, ri, ai)`` tuple exactly as production
    does. ``key="ordinal"`` replaces ``(ri, ai)`` with the two observations' complete-
    sequence ordinals, leaving similarity and every other step untouched.
    """
    removed = [(i, c) for i, c in enumerate(changes) if c.change_type == "removed"]
    added = [(i, c) for i, c in enumerate(changes) if c.change_type == "added"]

    if not removed or not added:
        return changes

    candidates = move_candidates(
        [db._normalize_text(rc.old_text or "") for _, rc in removed],
        [db._normalize_text(ac.new_text or "") for _, ac in added],
        threshold,
    )

    if not candidates:
        return changes

    if key == "ordinal":
        removed_ordinals = [CURRENT["old"][c.element_id_old] for _, c in removed]
        added_ordinals = [CURRENT["new"][c.element_id_new] for _, c in added]
        candidates.sort(key=lambda t: (t[0], removed_ordinals[t[1]], added_ordinals[t[2]]), reverse=True)
    else:
        candidates.sort(reverse=True)

    claimed_removed: set[int] = set()
    claimed_added: set[int] = set()
    moved_indices: set[int] = set()
    moved_entries: list[NodeDiff] = []

    for _sim, ri, ai in candidates:
        if ri in claimed_removed or ai in claimed_added:
            continue
        claimed_removed.add(ri)
        claimed_added.add(ai)

        orig_ri, rc = removed[ri]
        orig_ai, ac = added[ai]
        moved_indices.add(orig_ri)
        moved_indices.add(orig_ai)

        old_norm = db._normalize_text(rc.old_text or "")
        new_norm = db._normalize_text(ac.new_text or "")
        text_changes = diff_text(old_norm, new_norm) if old_norm != new_norm else None

        moved_entries.append(
            NodeDiff(
                display_path_old=rc.display_path_old,
                display_path_new=ac.display_path_new,
                match_path=rc.match_path,
                change_type="moved",
                old_text=rc.old_text,
                new_text=ac.new_text,
                text_diff=text_changes,
                section_number=ac.section_number or rc.section_number,
                element_id_old=rc.element_id_old,
                element_id_new=ac.element_id_new,
                old_amount_text=rc.old_amount_text,
                new_amount_text=ac.new_amount_text,
            )
        )

    result = [c for i, c in enumerate(changes) if i not in moved_indices]
    result.extend(moved_entries)
    return result


def digests() -> dict[str, dict]:
    """One ``baseline_record`` per corpus pair, through the public canonical producer."""
    produced = {}
    for key, old, new in baseline_pairs():
        HOLDER["key"] = key
        produced[key] = baseline_record(old, new)
    return produced


def compare(label: str, committed: dict, produced: dict) -> set[str]:
    moved = [key for key in committed if committed[key]["sha256"] != produced[key]["sha256"]]
    verdict = "MATCHES the committed baseline" if not moved else f"DIFFERS on {len(moved)} pair(s)"
    print(f"{label}: {verdict}")
    for key in moved:
        before, after = committed[key], produced[key]
        print(f"    {key}")
        print(f"      changes {before['changes']} -> {after['changes']}, bytes {before['bytes']} -> {after['bytes']}")
        print(f"      summary {before['summary']} -> {after['summary']}")
    return set(moved)


def main() -> None:
    committed = json.loads((DATA_DIR / "canonical_baseline.json").read_text())
    expected = set(ORDINAL_SENSITIVE_PAIRS)

    db.match_nodes = match_spy
    try:
        pass1 = compare("PASS 1  production reconcile_moves          ", committed, digests())

        db.reconcile_moves = lambda changes, threshold=MOVE_THRESHOLD: reconcile_copy(changes, threshold, key="legacy")
        pass2 = compare("PASS 2  duplicated loop, PRODUCTION key     ", committed, digests())

        db.reconcile_moves = lambda changes, threshold=MOVE_THRESHOLD: reconcile_copy(changes, threshold, key="ordinal")
        pass3 = compare("PASS 3  duplicated loop, ORDINAL key (fault)", committed, digests())

        db.reconcile_moves = REAL_RECONCILE
        pass4 = compare("PASS 4  production restored                 ", committed, digests())
    finally:
        db.match_nodes = REAL_MATCH_NODES
        db.reconcile_moves = REAL_RECONCILE

    print()
    if pass1 or pass2 or pass4:
        raise SystemExit(
            "the harness or the duplicated loop is not equivalent to production; pass 3 proves nothing. "
            f"pass1={sorted(pass1)} pass2={sorted(pass2)} pass4={sorted(pass4)}"
        )
    if pass3 != expected:
        print("PASS 3 DID NOT REDDEN THE PREDICTED PAIRS:")
        for key in sorted(expected - pass3):
            print(f"  MISSING (predicted, did not redden): {key}")
        for key in sorted(pass3 - expected):
            print(f"  UNEXPECTED (reddened, not predicted): {key}")
        raise SystemExit(
            "the gate's response does not match the measured prediction. Either the injected change no "
            "longer reaches selection where probe_round2_migration says it does, or the baseline sees a "
            "different set of pairs than it did -- both need a human before this is used as the ADR 0020 "
            "acceptance gate."
        )
    print(f"RESULT: the gate is SENSITIVE to a move-correspondence change -- EXACTLY the predicted {len(expected)}")
    print("pair(s) reddened, no more and no fewer:")
    for key in sorted(expected):
        print(f"  {key}")
    print("Passes 1, 2 and 4 all reproduce the committed baseline, so the difference is the injected key.")


if __name__ == "__main__":
    main()
