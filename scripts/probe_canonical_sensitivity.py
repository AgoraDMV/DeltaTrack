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

RE-AIMED FOR SLICE 2. The fault used to be injected by replacing ``diff_bill.reconcile_moves``,
a single post-classification function. That function is gone: round-2 retrieval, evidence and
assignment now run before classification, and the ordering key lives in
``diff_bill._greedy_move_links``. Injecting there keeps the fault on the LIVE production path --
``assign_moves`` calls it, ``diff_bills`` calls that -- rather than on a parallel copy of a
pipeline nothing runs any more, which is the only way this can still speak for the real gate.

The re-aim also made the fault sharper. The old probe needed an ``element_id -> ordinal``
bridge because ``NodeDiff`` carries no address; the migrated stages carry
:class:`~deltatrack.matching.ObservationRef`, whose ``ordinal`` IS the parser's
complete-sequence position. So the ordinal key is now read directly off the evidence and the
bridge is gone, along with the chance of it silently pointing at the wrong node.

FOUR PASSES, because a two-pass green/red would leave two other explanations open:

1. **production** -- the harness reproduces the committed baseline. Without this a later
   mismatch could be the harness rather than the fault. Must be EMPTY.
2. **duplicate, production key** -- the copied greedy loop below must reproduce the committed
   baseline too. A copy made in order to instrument something is a second implementation that
   can drift; unless it is shown equivalent first, pass 3 would be comparing the ordinal key
   against a drifted copy rather than against production. Must be EMPTY.
3. **duplicate, ordinal key** -- the injected fault. Must be EXACTLY the expected three.
4. **production, restored** -- the baseline matches again, so the difference was the fault
   and not something sticky the run left behind. Must be EMPTY.

An extra reddened pair, a missing one, or a different one fails the run. "Non-empty" would
have been satisfied by a fault that reddened everything, which is the shape a genuinely
broken harness produces.

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
from deltatrack.diff_bill import WORD_OVERLAP, UnmatchedPopulation  # noqa: E402
from deltatrack.matching import CorrespondenceEvidence  # noqa: E402
from scripts.probe_round2_migration import ORDINAL_SENSITIVE_PAIRS  # noqa: E402
from tests.corpus_paths import DATA_DIR  # noqa: E402
from tests.test_canonical_baseline import baseline_pairs, baseline_record  # noqa: E402

REAL_GREEDY = db._greedy_move_links


def greedy_copy(
    population: UnmatchedPopulation,
    evidence: tuple[CorrespondenceEvidence, ...],
    threshold: float,
    *,
    key: str = "legacy",
) -> list[CorrespondenceEvidence]:
    """``diff_bill._greedy_move_links``, copied verbatim except for the sort key.

    ``key="legacy"`` sorts on ``(word_overlap, ri, ai)`` -- positions in the unmatched
    population -- exactly as production does. ``key="ordinal"`` replaces those positions with the
    two observations' ADR 0019 complete-sequence ordinals, leaving the score, the threshold and
    every other step untouched.
    """
    ri_of = {observation.ref: index for index, observation in enumerate(population.old)}
    ai_of = {observation.ref: index for index, observation in enumerate(population.new)}

    def overlap(item: CorrespondenceEvidence) -> float:
        return item.get(WORD_OVERLAP)

    if key == "ordinal":

        def sort_key(item: CorrespondenceEvidence):
            return (overlap(item), item.old.ordinal, item.new.ordinal)
    else:

        def sort_key(item: CorrespondenceEvidence):
            return (overlap(item), ri_of[item.old], ai_of[item.new])

    eligible = [item for item in evidence if overlap(item) >= threshold]
    ordered = sorted(eligible, key=sort_key, reverse=True)

    claimed_old: set[int] = set()
    claimed_new: set[int] = set()
    selected: list[CorrespondenceEvidence] = []
    for item in ordered:
        ri, ai = ri_of[item.old], ai_of[item.new]
        if ri in claimed_old or ai in claimed_new:
            continue
        claimed_old.add(ri)
        claimed_new.add(ai)
        selected.append(item)
    return selected


def digests() -> dict[str, dict]:
    """One ``baseline_record`` per corpus pair, through the public canonical producer."""
    return {key: baseline_record(old, new) for key, old, new in baseline_pairs()}


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

    try:
        pass1 = compare("PASS 1  production assignment               ", committed, digests())

        db._greedy_move_links = lambda p, e, t: greedy_copy(p, e, t, key="legacy")
        pass2 = compare("PASS 2  duplicated loop, PRODUCTION key     ", committed, digests())

        db._greedy_move_links = lambda p, e, t: greedy_copy(p, e, t, key="ordinal")
        pass3 = compare("PASS 3  duplicated loop, ORDINAL key (fault)", committed, digests())

        db._greedy_move_links = REAL_GREEDY
        pass4 = compare("PASS 4  production restored                 ", committed, digests())
    finally:
        db._greedy_move_links = REAL_GREEDY

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
