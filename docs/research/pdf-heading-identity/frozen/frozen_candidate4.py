"""FROZEN #524 candidate 4 (CONSERVATIVE). Do not edit to fit a result.

Candidate 3 plus one clause: where line fullness has no margin to observe *because the
line was condensed to manufacture the fit*, decline to join. That is the fail-closed
answer to the #501 near-full container, and it is the discriminator measured in
`nearfull/` -- no new search, no new threshold hunt.

Frozen before any new holdout is selected. `freeze_check4.py` pins these bytes.

================================================================================
1. IN-SCOPE POPULATION
================================================================================
Unchanged from candidate 1: the ACCOUNT-TERMINATED heading run only. Grouping-header
runs, the body-size major band (#501's original site), documents with no size bands
(#508) and unnumbered layouts (#261) are all out of scope and untouched.

A boundary is the gap between line i and i+1 of such a run.

================================================================================
2. EVIDENCE
================================================================================
caps_per_word(line)
    large capitals / words. A "large capital" is a content glyph whose rounded size
    equals the maximum rounded size on that same printed line; sizes round to 0.1 pt.
    Words are maximal alphanumeric runs (`[^A-Za-z0-9]+` as separator). A line with a
    single distinct size returns 0.0 -- a measured value, not a missing one.

slack = column_width - (upper_width + 6.0 + first_word_width_of_lower)
    #130's line-fullness signal. column_width is `_body_column_width` (median over body
    prose). >= 0 means the next word would have fitted, so the break was deliberate.

fill = upper_width / column_width
    how much of the measure the upper line occupies.

tracking(line) = mean over adjacent intra-word glyph pairs of (next.left - prev.right)/size
    negative means CONDENSED. Not currently retained by `pdf_text`; `LineGeom` keeps three
    x-coordinates and discards the inter-glyph geometry entirely.

track_ratio = tracking(upper) / median(tracking over that DOCUMENT's lines with >= 8 gaps)
    normalised because tracking varies by print class, so an absolute bound compares
    across incompatible documents.

================================================================================
3. DECISION ORDERING (first match wins; order is load-bearing)
================================================================================
    C1  upper line ends in a wrap hyphen                        -> JOIN
    C2  caps_per_word(upper) >= T and caps_per_word(lower) < T  -> SPLIT
    C3  slack is None (geometry absent)                         -> SPLIT   fail closed
    C4  slack >= 0                                              -> SPLIT
    C5  fill >= FILL_MIN and track_ratio <= TRACK_RATIO_MAX     -> SPLIT   fit manufactured
    C5b tracking or the document median is unavailable          -> SPLIT   fail closed
    C6  otherwise                                               -> JOIN

C2 is skipped when either caps_per_word is None. When tracking for the upper line or the
document median is unavailable, C5 cannot be evaluated and C5b declines rather than
guessing -- the near-full guard is exactly the evidence that is missing.

Rationale for C5, stated once. GPO condenses a line to make text fit. A near-full line
that was *also* condensed relative to its own document proves only that a fit was
manufactured -- it does not prove the text ended there. Fullness has nothing left to
observe in that case, so the honest answer is to decline rather than to join.

================================================================================
4. CONSTANTS
================================================================================
T                     = 0.5     caps-per-word cut, unchanged from candidate 1/3
FILL_MIN              = 0.97    near-full
TRACK_RATIO_MAX       = 0.31    condensed relative to the document's own norm
SPACE                 = 6.0     one inter-word space at body size (`_MAJOR_SPLIT_SPACE`)
MIN_GAPS_FOR_MEDIAN   = 8       lines too short to estimate tracking are excluded

FILL_MIN and TRACK_RATIO_MAX are the operating point measured in `nearfull/`: the
tightest conjunction that catches both observed near-full containers. They are NOT tuned
here and must not be re-tuned against a holdout.

================================================================================
5. MISSING-EVIDENCE BEHAVIOUR, INCLUDING WHERE IT IS NOT CONSERVATIVE
================================================================================
    missing caps        C2 skipped; decision falls through. Conservative.
    missing geometry    C3 -> SPLIT. Conservative: declines to join on absent evidence.
    missing tracking    C5b -> SPLIT. Conservative, and CORRECTED at closure.

                        An earlier revision let this fall through to C6 (JOIN), which was
                        the specification's one fail-open branch. It fired zero times in
                        development and zero times in either holdout, so closing it
                        changes no validated result; it is monotonic toward the primary
                        invariant, because declining can only remove joins and a false
                        join is the thing the invariant forbids. `test_missing_tracking_
                        cannot_recreate_a_false_join` is the control that pins it.

================================================================================
6. SCORING DEFINITIONS
================================================================================
    TRUE WRAP / TRUE STACK   the independent XML oracle's unique segmentation.
    FALSE JOIN               truth SPLIT, decision JOIN. Fabricates hierarchy.
    MISSED JOIN              truth JOIN, decision SPLIT. Loses structure; recoverable,
                             and identical to shipped behaviour at that boundary.
    NOVEL                    an error the shipped rule does not also make.

PRIMARY GATE: no oracle-established SPLIT boundary may be joined. Missed joins are the
secondary quality metric and are NOT driven to zero -- the research established that
requiring all fourteen historical #524 examples is incompatible with the primary gate on
observed print.
"""
from __future__ import annotations

import re
import statistics

T = 0.5
FILL_MIN = 0.97
TRACK_RATIO_MAX = 0.31
SPACE = 6.0
MIN_GAPS_FOR_MEDIAN = 8
WRAP_HYPHENS = ("-", "‐", "‑")
SPLIT, JOIN = "SPLIT", "JOIN"


def words(text: str) -> list[str]:
    return [w for w in re.split(r"[^A-Za-z0-9]+", text) if w]


def join_lines(texts) -> str:
    out = texts[0]
    for seg in texts[1:]:
        out = out[:-1] + seg if out.endswith(WRAP_HYPHENS) else f"{out} {seg}"
    return out


def caps_per_word(text: str, profile) -> float | None:
    if profile is None:
        return None
    hist = {float(k): v for k, v in profile.items()}
    if not hist:
        return None
    if len(hist) < 2:
        return 0.0
    n = len(words(text))
    return hist[max(hist)] / n if n else None


def slack(upper_geom, lower_geom, column_width) -> float | None:
    if upper_geom is None or lower_geom is None or not column_width:
        return None
    return column_width - ((upper_geom["right"] - upper_geom["left"]) + SPACE
                           + (lower_geom["fwr"] - lower_geom["left"]))


def document_track_median(tracking_by_line, gaps_by_line) -> float | None:
    """Median tracking over the document's lines long enough to estimate it."""
    vals = [t for k, t in tracking_by_line.items()
            if t is not None and gaps_by_line.get(k, 0) >= MIN_GAPS_FOR_MEDIAN]
    return statistics.median(vals) if vals else None


def decide(texts, geoms, column_width, profiles, tracking_upper, track_median, i):
    """Spec section 3. Returns ``(SPLIT|JOIN, clause)``."""
    if texts[i].rstrip().endswith(WRAP_HYPHENS):
        return JOIN, "C1_hyphen"
    cu = caps_per_word(texts[i], profiles(i))
    cl = caps_per_word(texts[i + 1], profiles(i + 1))
    if cu is not None and cl is not None and cu >= T and cl < T:
        return SPLIT, "C2_caps_container"
    sl = slack(geoms[i], geoms[i + 1], column_width)
    if sl is None:
        return SPLIT, "C3_no_geometry"
    if sl >= 0.0:
        return SPLIT, "C4_fullness_split"
    gu = geoms[i]
    if gu is None or not column_width or tracking_upper is None or not track_median:
        return SPLIT, "C5b_no_tracking"
    fill = (gu["right"] - gu["left"]) / column_width
    if fill >= FILL_MIN and (tracking_upper / track_median) <= TRACK_RATIO_MAX:
        return SPLIT, "C5_condensed_nearfull"
    return JOIN, "C6_fullness_join"


def shipped_decide(texts, i):
    """Shipped: the only cut is immediately before the leaf."""
    return (SPLIT, "S_before_leaf") if i == len(texts) - 2 else (JOIN, "S_in_run")
