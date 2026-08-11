"""Can a populated ``CorrespondenceSet`` be revised in place from 1:0 + 0:1 to a 1:1?

The proposition this demonstrates, stated exactly:

    Once observations have been added to a ``CorrespondenceSet`` as settled 1:0 and 0:1
    correspondence, that set cannot be revised in place to a later 1:1 under the current
    API. A migration must therefore either delay settlement until later retrieval rounds
    are complete, or construct a new final set from the ultimate correspondence.

Note what this does **not** say. The final 1:1 state is perfectly representable: step 4
below builds a ``CorrespondenceSet`` containing it. The constraint is on *in-place
revision of an already populated set*, not on representational capability, and the
finding is therefore about migration order rather than a gap in the contract.

Why it is worth demonstrating. The current engine can first treat two observations as a
removal and an addition, and later relink them as a move. That is a property of the
legacy code path, described here in its own terms: the legacy engine does not materialise
ADR 0020 ``Correspondence`` values at all, and ``match_nodes`` output is not necessarily
settled, because classification can still revoke a pairing. If a migration settled those
earlier states into a ``CorrespondenceSet`` as it went, the later relink would have
nowhere to go.

This probe chooses between neither migration design. It runs the sequence against the
real types instead of arguing it. Read-only, writes nothing, changes no contract.

    uv run python scripts/probe_correspondence_revision.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deltatrack.matching import (  # noqa: E402
    Correspondence,
    CorrespondenceEvidence,
    CorrespondenceSet,
    ObservationRef,
)


def main() -> None:
    old_ref = ObservationRef(side="old", ordinal=17)
    new_ref = ObservationRef(side="new", ordinal=204)

    # 1. The two shapes a migration would settle from a removal and an addition. Both are
    #    constructible, so the refusal below is not about either shape being invalid.
    removal = Correspondence(old=(old_ref,))
    addition = Correspondence(new=(new_ref,))
    print(f"1:0 constructible: {removal.shape}")
    print(f"0:1 constructible: {addition.shape}")

    # 2. Settling them succeeds. This step is NOT where the constraint bites.
    settled = CorrespondenceSet([removal, addition])
    print(f"settled separately, without complaint: {len(settled)} correspondences")

    # 3. The constraint bites here: relinking the SAME two observations as one move,
    #    inside the set that already holds them.
    moved = Correspondence(
        old=(old_ref,),
        new=(new_ref,),
        evidence=(CorrespondenceEvidence.of(old_ref, new_ref, similarity=1.0),),
    )
    try:
        settled.add(moved)
        print("RESULT: the later 1:1 was accepted into the populated set")
    except ValueError as exc:
        print(f"RESULT: the later 1:1 is refused by the populated set -- {exc}")

    api = [name for name in dir(settled) if not name.startswith("_")]
    print(f"CorrespondenceSet public API: {api}")
    print("this populated set has no in-place remove/replace operation, so it cannot be revised in place")

    # 4. The final state itself is representable: a NEW set holding the 1:1 instead of
    #    the two provisional records. Stated as a demonstration so the constraint above
    #    is not over-read as "the 1:1 cannot be represented".
    rebuilt = CorrespondenceSet([moved])
    print(
        f"a NEW set built from the ultimate correspondence holds it fine: "
        f"{len(rebuilt)} correspondence, shape {rebuilt.correspondences()[0].shape}"
    )
    print("so the constraint is on in-place revision, not on representing the final state")


if __name__ == "__main__":
    main()
