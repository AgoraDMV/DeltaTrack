"""M3 -- word-boundary integrity, executable.

PRE-REGISTRATION.md section 6.3 defined M3 at the boundary level but left the alignment
to "the eventual scorer": no algorithm, no costs, no tie-breaking, no repeated-character
rule. That is scoring behaviour decided after seeing data unless it is pinned here, so it
is pinned here and tested on synthetic and DEVELOPMENT material only.

THE EDIT BUDGET IS REMOVED. An "unalignable within a frozen budget" rule is one more
arbitrary threshold, and a threshold on the exact quantity the study is measuring. This
uses a deterministic full alignment instead, and reserves UNALIGNABLE for the case where
it means something real: the two non-space sequences share no common subsequence at all.

ALIGNMENT, frozen
-----------------
* Compare the NON-SPACE character sequences. Spaces never participate in alignment, so a
  spacing difference can never cause a misalignment -- which is the whole point of
  measuring spacing separately from text.
* Normalisation is NFKC and end-stripping only. Case is preserved. Interior spaces are
  preserved for the boundary vector and then dropped from the alignment sequence.
* Needleman-Wunsch global alignment, unit costs: match 0, substitution 1, indel 1.
* Deterministic tie-break: at equal cost prefer DIAGONAL (align), then UP (oracle-only,
  a deletion), then LEFT (extractor-only, an insertion). Fixed order, so repeated
  characters like "AB AB" -> "ABAB" resolve identically on every run and platform.

BOUNDARY SEMANTICS
------------------
A boundary sits BETWEEN two adjacent non-space characters of one string. For a string s,
boundary[i] is 1 when one or more spaces separate non-space character i from i+1.
Multiple spaces are one boundary: M2 already normalises whitespace runs, and "how many
spaces" is not a legible product-level distinction.

A boundary position is comparable only when BOTH of its endpoint characters aligned to
oracle characters. Otherwise the position is not evidence about spacing at all.

    WELD        oracle 1, extractor 0   -- two printed words run together
    SPLIT       oracle 0, extractor 1   -- a boundary the print does not have
    OK          agree
    TEXT_ERROR  an aligned pair whose characters differ, OR an indel. A CHARACTER defect;
                never counted as WELD or SPLIT
    UNALIGNABLE the two sequences share no common subsequence

HEADING-LEVEL OUTCOME
---------------------
Section 6.3 classified boundaries; the decision rule counts HEADINGS. Those are different
units and one heading can carry several boundary defects, so the derived heading verdict
is defined mechanically here:

    a heading is CLEAN for an architecture when it has zero WELD, zero SPLIT and zero
    TEXT_ERROR against the oracle.

Per heading, comparing H and X against the oracle:

    X_CORRECTS   H not clean, X clean          -- X repaired the whole label
    X_REGRESSES  H clean, X not clean
    BOTH_CLEAN   both clean
    BOTH_DIRTY   neither clean (whatever the defect counts) -- explicitly NOT a correction
    UNSCORABLE   either side UNALIGNABLE

"Fixed one of two welds" is BOTH_DIRTY, not a correction. A half-repaired account label is
still a wrong account label, and the estimand is the corrupted label, not the boundary.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum

WELD = "WELD"
SPLIT = "SPLIT"
OK = "OK"
TEXT_ERROR = "TEXT_ERROR"
# Replaces the withdrawn UNALIGNABLE. It fires only when the ORACLE has no text for a
# heading, never because an extractor produced something unrecognisable.
NO_REFERENCE = "NO_REFERENCE"


class HeadingOutcome(str, Enum):
    X_CORRECTS = "X_CORRECTS"
    X_REGRESSES = "X_REGRESSES"
    BOTH_CLEAN = "BOTH_CLEAN"
    BOTH_DIRTY = "BOTH_DIRTY"
    UNSCORABLE = "UNSCORABLE"


def normalize(s: str) -> str:
    """The frozen NON-SPACING normalisation: NFKC and end-strip. Case preserved,
    interior spacing untouched."""
    return unicodedata.normalize("NFKC", s).strip()


def decompose(s: str) -> tuple[str, list[int]]:
    """(non-space characters, boundary vector).

    boundary[i] == 1 when one or more spaces separate non-space char i from i+1.
    """
    chars: list[str] = []
    boundaries: list[int] = []
    pending_space = False
    for ch in normalize(s):
        if ch.isspace():
            pending_space = bool(chars)
            continue
        if chars:
            boundaries.append(1 if pending_space else 0)
        chars.append(ch)
        pending_space = False
    return "".join(chars), boundaries


def align(a: str, b: str) -> list[tuple[int | None, int | None]]:
    """Needleman-Wunsch global alignment, unit costs, deterministic tie-break.

    Returns index pairs; None marks an indel. Tie order is DIAGONAL, then UP (a-only),
    then LEFT (b-only), so repeated characters resolve identically every time.
    """
    n, m = len(a), len(b)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i
    for j in range(1, m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i][j] = min(
                cost[i - 1][j - 1] + (0 if a[i - 1] == b[j - 1] else 1),
                cost[i - 1][j] + 1,
                cost[i][j - 1] + 1,
            )

    out: list[tuple[int | None, int | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and cost[i][j] == cost[i - 1][j - 1] + (0 if a[i - 1] == b[j - 1] else 1):
            out.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and cost[i][j] == cost[i - 1][j] + 1:
            out.append((i - 1, None))
            i -= 1
        else:
            out.append((None, j - 1))
            j -= 1
    out.reverse()
    return out


def longest_common_subsequence(a: str, b: str) -> int:
    """Length of the LCS. DIAGNOSTIC ONLY -- it no longer gates scorability.

    Kept because "these two strings share nothing" is worth reporting, and because the
    previous implementation conflated it with "the chosen minimum-cost alignment happens
    to contain no exact match", which are not the same thing: `AB` against `BA` shares the
    subsequences `A` and `B`, yet a minimum-cost alignment is two substitutions.
    """
    prev = [0] * (len(b) + 1)
    for ch in a:
        cur = [0]
        for j, ch2 in enumerate(b):
            cur.append(prev[j] + 1 if ch == ch2 else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[len(b)]


@dataclass
class BoundaryScore:
    outcomes: list[str] = field(default_factory=list)
    weld: int = 0
    split: int = 0
    ok: int = 0
    text_error: int = 0
    no_reference: bool = False
    no_common_subsequence: bool = False  # diagnostic; does NOT affect `clean`

    @property
    def clean(self) -> bool:
        return not self.no_reference and self.weld == 0 and self.split == 0 and self.text_error == 0


def score_heading(oracle: str, extracted: str) -> BoundaryScore:
    """Boundary-level M3 for one heading, one architecture, against the oracle.

    SEVERE CORRUPTION IS A SEVERE TEXT_ERROR, NOT AN EXCLUSION. An earlier version
    declared the pair UNALIGNABLE when the chosen alignment held no exact match, and the
    heading then became UNSCORABLE -- which removed from the comparison exactly the cases
    where an architecture failed worst. If X emits garbage where H reads the label
    correctly, that must count as X_REGRESSES, not vanish.

    The only thing that makes a heading unscorable is a MISSING REFERENCE: the oracle has
    no text for it (unreadable region). That is a limit of the oracle, never a result of
    an extractor.
    """
    o_chars, o_bounds = decompose(oracle)
    e_chars, e_bounds = decompose(extracted)
    res = BoundaryScore()

    if not o_chars:
        res.no_reference = True
        res.outcomes = [NO_REFERENCE]
        return res

    res.no_common_subsequence = longest_common_subsequence(o_chars, e_chars) == 0

    if not e_chars:
        # The extractor produced nothing. Every printed character is lost: a maximal text
        # error against this heading, and the heading stays in the denominator.
        res.text_error = len(o_chars)
        res.outcomes = [TEXT_ERROR] * len(o_chars)
        return res

    pairs = align(o_chars, e_chars)

    # Character defects: substitutions and indels.
    o_to_e: dict[int, int] = {}
    for oi, ei in pairs:
        if oi is None or ei is None:
            res.text_error += 1
            continue
        if o_chars[oi] != e_chars[ei]:
            res.text_error += 1
        o_to_e[oi] = ei

    # Boundary positions, comparable only where BOTH endpoints aligned.
    for i in range(len(o_chars) - 1):
        a, b = o_to_e.get(i), o_to_e.get(i + 1)
        if a is None or b is None:
            continue
        if b - a != 1:  # extractor has extra characters between the endpoints
            continue
        want, got = o_bounds[i], e_bounds[a]
        if want == got:
            res.ok += 1
            res.outcomes.append(OK)
        elif want == 1:
            res.weld += 1
            res.outcomes.append(WELD)
        else:
            res.split += 1
            res.outcomes.append(SPLIT)
    return res


def heading_outcome(oracle: str, hybrid: str, extended: str) -> tuple[HeadingOutcome, BoundaryScore, BoundaryScore]:
    """The DECISION-RULE unit: one heading occurrence, H versus X against the oracle."""
    h, x = score_heading(oracle, hybrid), score_heading(oracle, extended)
    # UNSCORABLE only when the REFERENCE is missing. An extractor's failure -- however
    # severe -- keeps the heading in the denominator and counts against that architecture.
    if h.no_reference or x.no_reference:
        return HeadingOutcome.UNSCORABLE, h, x
    if h.clean and x.clean:
        return HeadingOutcome.BOTH_CLEAN, h, x
    if not h.clean and x.clean:
        return HeadingOutcome.X_CORRECTS, h, x
    if h.clean and not x.clean:
        return HeadingOutcome.X_REGRESSES, h, x
    return HeadingOutcome.BOTH_DIRTY, h, x
