"""m3_selftest -- prove the M3 implementation behaves as PRE-REGISTRATION.md 6.3 says.

Synthetic and DEVELOPMENT material only. Touches no confirmatory holdout document.

Run: .venv/bin/python .../probes/m3_selftest.py     (exit 0 = all cases hold)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from m3_boundaries import (  # noqa: E402
    NO_REFERENCE,
    OK,
    SPLIT,
    TEXT_ERROR,
    WELD,
    HeadingOutcome,
    decompose,
    heading_outcome,
    score_heading,
)

FAILURES: list[str] = []


def check(name: str, got, want) -> None:
    ok = got == want
    print(
        f"[{'PASS' if ok else 'FAIL'}] {name}\n         got={got!r}\n        want={want!r}"
        if not ok
        else f"[PASS] {name}"
    )
    if not ok:
        FAILURES.append(name)


def counts(s) -> tuple[int, int, int, bool]:
    return (s.weld, s.split, s.text_error, s.no_reference)


# -- decomposition ------------------------------------------------------------
check(
    "decompose splits chars from boundaries",
    decompose("FAMILY HOUSING"),
    ("FAMILYHOUSING", [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0]),
)
check("a run of spaces is ONE boundary", decompose("FAMILY   HOUSING")[1], decompose("FAMILY HOUSING")[1])
check("leading/trailing space is not a boundary", decompose("  ABC  "), ("ABC", [0, 0]))

# -- the cases the review named ----------------------------------------------
check("WELD: printed boundary missing", counts(score_heading("FAMILY HOUSING", "FAMILYHOUSING")), (1, 0, 0, False))
check("SPLIT: boundary not printed", counts(score_heading("FAMILYHOUSING", "FAMILY HOUSING")), (0, 1, 0, False))
check("TEXT_ERROR is not a spacing defect", counts(score_heading("FAMILY HOUSING", "FAM1LY HOUSING")), (0, 0, 1, False))

# Repeated-character ambiguity: "AB AB" -> "ABAB" must be a single WELD, deterministically.
ab = score_heading("AB AB", "ABAB")
check("repeated-character alignment stays one WELD", counts(ab), (1, 0, 0, False))
check("repeated-character outcomes are positional", ab.outcomes, [OK, WELD, OK])

# Multiple boundary defects inside ONE heading.
multi = score_heading("A B C D", "AB CD")
check("two welds in one heading", counts(multi), (2, 0, 0, False))

# UNALIGNABLE is WITHDRAWN. Severe corruption is a severe TEXT_ERROR and the heading stays
# in the denominator; making it unscorable removed precisely the worst failures from the
# comparison. Only a MISSING ORACLE REFERENCE is unscorable.
check(
    "total corruption is a maximal TEXT_ERROR, still scored",
    counts(score_heading("ABCDEF", "123456")),
    (0, 0, 6, False),
)
check("total corruption is NOT clean", score_heading("ABCDEF", "123456").clean, False)
check("sharing no subsequence is a DIAGNOSTIC flag only", score_heading("ABCDEF", "123456").no_common_subsequence, True)
check("empty extraction loses every printed character", counts(score_heading("ABC", "")), (0, 0, 3, False))
check("missing ORACLE text is the only unscorable state", counts(score_heading("", "ABC")), (0, 0, 0, True))
check("missing reference reported as its own outcome", score_heading("", "ABC").outcomes, [NO_REFERENCE])

# The adversarial cases: strings that SHARE subsequences but whose minimum-cost alignment
# may contain no exact match. The withdrawn rule called these unalignable.
for _o, _e in [("AB", "BA"), ("ABA", "BAA"), ("ABC", "BAC"), ("AAB", "ABA"), ("ABAB", "BABA"), ("AAAAAB", "BAAAAA")]:
    _sc = score_heading(_o, _e)
    check(f"{_o} vs {_e}: shares a subsequence, not flagged as sharing nothing", _sc.no_common_subsequence, False)
    check(f"{_o} vs {_e}: remains scorable", _sc.no_reference, False)

# A long shared run with one substitution is NOT unalignable -- no edit budget to trip.
check(
    "no edit budget: long string, many errors, still aligned",
    score_heading("A" * 40 + "Z", "A" * 40 + "Q").no_reference,
    False,
)

# -- heading-level decision unit ---------------------------------------------
check(
    "X repairs the whole label -> X_CORRECTS",
    heading_outcome("FAMILY HOUSING", "FAMILYHOUSING", "FAMILY HOUSING")[0],
    HeadingOutcome.X_CORRECTS,
)
check(
    "X breaks a label H got right -> X_REGRESSES",
    heading_outcome("FAMILY HOUSING", "FAMILY HOUSING", "FAMILYHOUSING")[0],
    HeadingOutcome.X_REGRESSES,
)
check(
    "both correct -> BOTH_CLEAN",
    heading_outcome("FAMILY HOUSING", "FAMILY HOUSING", "FAMILY HOUSING")[0],
    HeadingOutcome.BOTH_CLEAN,
)
# THE CASE THE REVIEW ASKED ABOUT: H has two welds, X fixes one and keeps one.
mixed = heading_outcome("A B C D", "AB CD", "A B CD")
check("H 2 welds, X fixes ONE -> BOTH_DIRTY, not a correction", mixed[0], HeadingOutcome.BOTH_DIRTY)
check("  ... and the boundary counts still show the improvement", (counts(mixed[1])[0], counts(mixed[2])[0]), (2, 1))
check(
    "a TEXT_ERROR alone makes a heading not clean",
    heading_outcome("FAMILY HOUSING", "FAMILY HOUSING", "FAM1LY HOUSING")[0],
    HeadingOutcome.X_REGRESSES,
)
check(
    "X emitting garbage is X_REGRESSES, NOT an exclusion",
    heading_outcome("FAMILY HOUSING", "FAMILY HOUSING", "999999")[0],
    HeadingOutcome.X_REGRESSES,
)
check(
    "H emitting garbage is X_CORRECTS, symmetrically",
    heading_outcome("FAMILY HOUSING", "999999", "FAMILY HOUSING")[0],
    HeadingOutcome.X_CORRECTS,
)
check(
    "ONLY a missing oracle reference is UNSCORABLE",
    heading_outcome("", "FAMILY HOUSING", "FAMILY HOUSING")[0],
    HeadingOutcome.UNSCORABLE,
)

# -- development material: the two real seam differences the pilot found ------
# Both are letter-spaced display type, and on the second BOTH architectures are wrong,
# which must read as BOTH_DIRTY rather than as a correction for either side.
check(
    "development case 'H. R. 2029' vs 'H.R. 2029' against the printed form",
    heading_outcome("H.R. 2029", "H. R. 2029", "H.R. 2029")[0],
    HeadingOutcome.X_CORRECTS,
)
check(
    "development case CONTENTS: both wrong, differently -> BOTH_DIRTY",
    heading_outcome("CONTENTS", "C O N T E N T S", "C O N T E N TS")[0],
    HeadingOutcome.BOTH_DIRTY,
)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: " + "; ".join(FAILURES))
    sys.exit(1)
print("M3 SELF-TEST PASS -- every case in PRE-REGISTRATION.md 6.3 holds")
sys.exit(0)
