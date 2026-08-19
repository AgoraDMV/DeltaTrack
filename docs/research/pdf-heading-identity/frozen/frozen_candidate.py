"""FROZEN #524 candidate specification. Do not edit to fit a result.

This module is the executable statement of the candidate documented at `9af49c0`:

    vocabulary  ->  caps-per-word typography  ->  line fullness

It exists so an external-validity run cannot quietly become a tuning run. The
methodology is fixed before any holdout bill is selected or inspected;
`freeze_check.py` pins these bytes by digest, and every reported number names the
digest it was produced under.

Frozen because the development corpus is in-sample for all three of: discovering the
typography signal, composing the rule, and choosing the operating point.

================================================================================
1. IN-SCOPE HEADING POPULATION
================================================================================
The ACCOUNT-TERMINATED heading run, and nothing else. A run is the maximal
contiguous block of lines that are, per `pdf_anchors._account_anchors_by_size`:

    * numbered (`line_number is not None`) and carrying a glyph size;
    * inside the document's derived heading band, +/- `_SIZE_EPS`;
    * `_is_uppercase_heading`;
    * not `_ENUM_PREFIX`; not `_is_parenthetical`;
    * not a `continues_section_catchline` continuation,

terminated by a leaf whose next meaningful line is body prose or end-of-document.

EXCLUDED, deliberately and without exception:
    * grouping-header runs (next meaningful line is a `SEC.` line) -- a different
      emission path;
    * the body-size major/department band (`_major_anchors_by_size`) -- that is #501,
      measured on a different band and NOT covered by any number here;
    * documents where `derive_size_bands` returns None (#508) or where no margin
      numbers exist (#261) -- no run is formed at all.

A boundary is the gap between line i and line i+1 of a run. All scoring is per
boundary.

================================================================================
2. VOCABULARY / BOOTSTRAP PROCEDURE
================================================================================
Per DOCUMENT (one bill version), built over EVERY run in that document, including
runs whose oracle status is unresolved -- the parser sees them all.

    ACCOUNT vocabulary:
        * the text of every run of length 1 (a complete heading by construction:
          body prose above it and body prose below it);
        * the joined LOWER side of every boundary whose fullness slack >= T_STRONG.

    CONTAINER vocabulary:
        * the UPPER line of every boundary whose fullness slack >= T_STRONG.

T_STRONG = 40.0 pt. Membership is tested on `normalize_text` (below).

Document-internal only. No appropriations English, no cross-document vocabulary, no
XML: ADR 0018 is untouched. Insufficient vocabulary is not an error -- an empty
vocabulary simply matches nothing and the decision falls through to typography.

================================================================================
3. CAPS-PER-WORD COMPUTATION
================================================================================
    caps_per_word(line) = (count of LARGE-CAPITAL glyphs) / (word count)

computed over the line's CONTENT glyphs (margin number already removed), using the
size histogram recovered by `line_typography.py`.

A line whose histogram holds a single distinct size returns 0.0 -- even small caps
carry no large capital at all. That is a measured value, not a missing one.

================================================================================
4. DEFINITION OF A "LARGE CAPITAL"
================================================================================
A content glyph whose rounded size equals the MAXIMUM rounded size present on that
same printed line. Per-line and relative, never an absolute point size: the band
differs by document and by print class, and an absolute threshold would encode one
publisher's current type sizes.

Sizes are rounded to 0.1 pt, matching `pdf_text`'s own rounding.

================================================================================
5. WORD COUNTING / TOKENIZATION
================================================================================
    words = [w for w in re.split(r"[^A-Za-z0-9]+", text) if w]

Source-neutral and vocabulary-free: any maximal alphanumeric run is a word. Hyphens,
commas, ampersands, colons and parentheses are separators, so `SELF-HELP` counts as
two words and `(TITLE XI)` as two. Frozen as-is; it is a tokenizer, not a judgement.

================================================================================
6. FULLNESS COMPUTATION
================================================================================
    slack = column_width - (upper_width + SPACE + first_word_width_of_lower)

    upper_width           = upper.content_right - upper.content_left
    first_word_width      = lower.first_word_right - lower.content_left
    SPACE                 = 6.0 pt   (transcribed from `_MAJOR_SPLIT_SPACE`)
    column_width          = `pdf_anchors._body_column_width(pages)`

slack >= 0 means the lower line's first word WOULD have fitted at the end of the
upper line, so the break was deliberate => SPLIT. This is #130's signal, applied at
the heading band rather than at the body-size major band it shipped for.

`None` when either LineGeom is missing or the document yields no column width.

================================================================================
7. DECISION ORDERING  (first matching clause wins; order is load-bearing)
================================================================================
    D1  whole run joins to an ACCOUNT-vocabulary entry            -> JOIN
    D2  lower side joins to an ACCOUNT-vocabulary entry           -> SPLIT
    D3  upper line is a CONTAINER-vocabulary entry                -> SPLIT
    D4  upper line ends in a wrap hyphen                          -> JOIN
    D5  caps_per_word(upper) >= T and caps_per_word(lower) <  T   -> SPLIT
    D6  caps_per_word(upper) <  T and caps_per_word(lower) <  T   -> JOIN
    D7  fullness slack is None                                    -> JOIN
    D8  fullness slack >= 0                                       -> SPLIT
    D9  otherwise                                                 -> JOIN

D5/D6 are skipped when either caps-per-word is None (no typography for that line).
Note there is deliberately NO clause for `cu >= T and cl >= T`: two
caps-and-small-caps lines are not separated by this signal and fall through to
fullness.

================================================================================
8. T
================================================================================
T = 0.5.

Chosen mid-plateau, not at the optimum. The development false-join count is flat at 1
across T in [0.40, 0.60] and steps to 14 at 0.62; T=0.5 keeps 0.12 of headroom below
that cliff where T=0.6 keeps 0.02, at a cost of 12 additional fail-closed misses.

================================================================================
9-12. FAIL-CLOSED CONDITIONS AND MISSING-EVIDENCE BEHAVIOUR
================================================================================
Stated exactly, including where the frozen rule is NOT conservative, because a freeze
that quietly improves the thing it freezes is not a freeze.

    Missing TYPOGRAPHY (either line has no profile)
        D5/D6 are skipped; the decision falls through to fullness (D7-D9).

    Missing GEOMETRY (slack is None: no LineGeom, or no document column width)
        D7 -> JOIN.
        *** This is the one clause that is NOT fail-closed. *** It joins on absent
        evidence, which can fabricate structure. It is frozen in this direction
        because it is the predicate that produced the reported 1-false-join /
        15-missed-join development result, and changing it now would mean validating
        a rule that was never measured. Its frequency is reported separately for
        every run, so a holdout failure arriving through D7 is identifiable rather
        than averaged in.

    Insufficient VOCABULARY
        Not an error. An empty or small vocabulary matches nothing; D1-D3 do not
        fire and the decision falls through.

    Fail-closed in the sense the research record means it
        The rule DECLINING to join leaves today's shipped behaviour in place (a
        missed join), and a missed join loses structure that is recoverable, whereas
        a false join fabricates a heading that was never printed. Every clause except
        D7 defaults toward not joining when its evidence is absent.

================================================================================
13. SCORING DEFINITIONS
================================================================================
    TRUE WRAP    the XML oracle says the two lines are one logical heading.
    TRUE STACK   the XML oracle says they are two distinct logical headings.
    UNRESOLVED   the oracle admits zero or more than one segmentation. NOT scored,
                 counted and reported separately, never silently dropped.

    FALSE JOIN   truth = STACK, decision = JOIN.   Fabricates structure (#501).
    MISSED JOIN  truth = WRAP,  decision = SPLIT.  Loses structure (#524).
    CORRECT SPLIT / CORRECT JOIN are the two agreements.

The two error types are NEVER summed into a single score in any reported ruling: they
have different consequences and a sum hides which way a rule fails.
"""

from __future__ import annotations

import re

#: Operating point. Frozen.
T = 0.5
#: Pass-1 confidence bound for the bootstrapped vocabularies (points).
T_STRONG = 40.0
#: One inter-word space at body size, transcribed from `_MAJOR_SPLIT_SPACE`.
SPACE = 6.0
#: Line-final hyphens marking a GPO soft wrap, transcribed from `_WRAP_HYPHENS`.
WRAP_HYPHENS = ("-", "‐", "‑")

SPLIT, JOIN = "SPLIT", "JOIN"


def normalize_text(text: str) -> str:
    """Vocabulary-membership key: casefolded, non-alphanumerics collapsed to spaces."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def words(text: str) -> list[str]:
    """Spec section 5."""
    return [w for w in re.split(r"[^A-Za-z0-9]+", text) if w]


def join_lines(texts) -> str:
    """Join printed lines with the parser's own de-hyphenation rule."""
    out = texts[0]
    for seg in texts[1:]:
        out = out[:-1] + seg if out.endswith(WRAP_HYPHENS) else f"{out} {seg}"
    return out


def caps_per_word(text: str, profile) -> float | None:
    """Spec sections 3 and 4. `profile` is a `{size: count}` histogram, or None."""
    if profile is None:
        return None
    hist = {float(k): v for k, v in profile.items()}
    if not hist:
        return None
    if len(hist) < 2:
        return 0.0
    n_words = len(words(text))
    if not n_words:
        return None
    return hist[max(hist)] / n_words


def slack(upper_geom, lower_geom, column_width) -> float | None:
    """Spec section 6."""
    if upper_geom is None or lower_geom is None or not column_width:
        return None
    upper_width = upper_geom["right"] - upper_geom["left"]
    first_word = lower_geom["fwr"] - lower_geom["left"]
    return column_width - (upper_width + SPACE + first_word)


def bootstrap(runs_for_document):
    """Spec section 2. Returns `(account_vocabulary, container_vocabulary)`."""
    account: set[str] = set()
    container: set[str] = set()
    for run in runs_for_document:
        texts = run["texts"]
        if len(texts) == 1:
            account.add(normalize_text(texts[0]))
            continue
        for i in range(len(texts) - 1):
            value = slack(run["geoms"][i], run["geoms"][i + 1], run["column_width"])
            if value is None or value < T_STRONG:
                continue
            account.add(normalize_text(join_lines(texts[i + 1 :])))
            container.add(normalize_text(texts[i]))
    return account, container


def decide(run, i, account, container, profiles, t=T):
    """Spec section 7. Returns `(SPLIT|JOIN, clause)`.

    `profiles` maps a boundary side to its `{size: count}` histogram:
    `profiles(i)` and `profiles(i + 1)`, either possibly None.
    """
    texts = run["texts"]
    whole = normalize_text(join_lines(texts))
    lower = normalize_text(join_lines(texts[i + 1 :]))
    upper = normalize_text(texts[i])

    if whole in account:
        return JOIN, "D1_whole_in_account_vocab"
    if lower in account:
        return SPLIT, "D2_lower_in_account_vocab"
    if upper in container:
        return SPLIT, "D3_upper_in_container_vocab"
    if texts[i].rstrip().endswith(WRAP_HYPHENS):
        return JOIN, "D4_wrap_hyphen"

    cu = caps_per_word(texts[i], profiles(i))
    cl = caps_per_word(texts[i + 1], profiles(i + 1))
    if cu is not None and cl is not None:
        if cu >= t and cl < t:
            return SPLIT, "D5_caps_container_over_account"
        if cu < t and cl < t:
            return JOIN, "D6_caps_both_account"

    value = slack(run["geoms"][i], run["geoms"][i + 1], run["column_width"])
    if value is None:
        return JOIN, "D7_no_geometry"
    return (SPLIT, "D8_fullness_split") if value >= 0.0 else (JOIN, "D9_fullness_join")


def shipped_decide(run, i):
    """Shipped behaviour: the only cut is immediately before the leaf."""
    return (SPLIT, "S_before_leaf") if i == len(run["texts"]) - 2 else (JOIN, "S_in_run")
