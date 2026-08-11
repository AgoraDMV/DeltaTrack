"""Read a division's title back out of a rendered display label, for test baselines.

Production code does not do this any more (#468). A node carries its division match key
as its own value, so changing how the label is displayed cannot move a node into a
different match bucket.

The baselines below still have to, because a ``NodeDiff`` carries display paths and not
the key. That makes this module display-coupled on purpose, in one place: #66 renders
divisions as ``DIVISION A—<header>`` instead of ``Division A: <header>``, and this
pattern is what has to keep step with it.

The guard matters more than the pattern. These baselines all have the shape
``assert cross_division_mismatches(diff) <= N``, so a parser that silently matches
nothing returns 0 and every one of them passes, reporting perfect matching precisely
when the measurement has stopped working. :func:`cross_division_mismatches` raises
instead.
"""

import re

# "Division A: Military Construction" today; "DIVISION A—Military Construction" after
# #66. Both separators are accepted so this module does not become the thing that fails
# when the display form changes; the guard below is what catches a real break.
_DIVISION_LABEL_RE = re.compile(r"^division\s+\S+?\s*[:—-]\s*(.+)$", re.IGNORECASE)


def division_title(display_segment: str) -> str:
    """The normalized title from a division display label, or "" if there is none.

    A headerless division ("Division F") has no title and yields "", which is correct:
    it carries no information to compare against another division.
    """
    m = _DIVISION_LABEL_RE.match(display_segment.strip())
    if not m:
        return ""
    return " ".join(m.group(1).lower().split())


def _is_division_segment(display_segment: str) -> bool:
    return display_segment.strip().lower().startswith("division")


def cross_division_mismatches(diff) -> int:
    """Count changes whose two sides sit in divisions with different titles.

    Raises RuntimeError if division labels are present but none of them parse, which is
    what a display-format change looks like from here. Returning 0 in that case would be
    indistinguishable from a clean result.
    """
    labelled = 0
    parsed = 0
    mismatches = 0

    for change in diff.changes:
        if not (change.display_path_old and change.display_path_new):
            continue
        old_first = change.display_path_old[0]
        new_first = change.display_path_new[0]
        if not (_is_division_segment(old_first) and _is_division_segment(new_first)):
            continue

        labelled += 1
        old_title = division_title(old_first)
        new_title = division_title(new_first)
        if old_title or new_title:
            parsed += 1
        if old_title and new_title and old_title != new_title:
            mismatches += 1

    if labelled and not parsed:
        raise RuntimeError(
            f"{labelled} division-labelled changes and not one title parsed. The display "
            f"label format has moved away from _DIVISION_LABEL_RE (see #66); update the "
            f"pattern in tests/division_labels.py rather than reading this as 0 mismatches."
        )
    return mismatches
