"""Dollar-amount extraction: the one primitive that reads money out of bill text.

Source-neutral by construction. It imports nothing from ``deltatrack`` and must stay that
way, because both pipelines depend on it and one of them depends on it for *observation
production* rather than for reporting.

**Why this is a module rather than a private helper in the differ.** ADR 0020 slice 1 moved
PDF block formation into ``parsers.pdf_blocks`` so that an ADR 0019 parser revision could be
derived without hashing the matcher. That left one thread uncut:
``pdf_blocks._is_strippable_heading_line`` calls :func:`extract_amounts`, and the call is
**result-bearing** — an uppercase heading with no recognised amount may be stripped from a
block body, while one carrying an amount (an all-caps ``TOTAL, …, $X`` recap line) must be
retained, so a money change is never silently dropped.

While that function lived in ``diff_bill``, a change to the regexes below could change the
emitted PDF observation sequence **without touching any file a PDF parser revision covered**.
That is exactly the failure ADR 0019 identity exists to prevent: identity must change
whenever code capable of changing the emitted observations changes. Hashing all of
``diff_bill`` would have fixed it by putting matching policy back inside observation
identity, which is the coupling slice 1 removed. Extracting the primitive is the fix that
does not trade one defect for the other.

So this module is part of the **PDF parser-revision dependency closure**:

    parsers/pdf_text.py + parsers/pdf_anchors.py + parsers/pdf_blocks.py
      + deltatrack/amounts.py + the pypdfium2 distribution version

The precedent is ``deltatrack.similarity``, extracted for the same shape of reason (#492) and
which records the rule this follows: a number or primitive lives beside its use until a
second consumer appears, and that is the moment to promote it. There are now two, and one of
them is a parser.

**Scope.** Only the extraction primitive lives here. ``match_amounts`` and its word-level
pairing stay in ``diff_bill``: they are diff machinery, only one pipeline pairs amounts
across two texts, and moving them would have widened a dependency repair into the general
#62 cleanup it is deliberately not.
"""

from __future__ import annotations

import re

#: A comma-grouped amount must use groups of exactly three digits, so a trailing
#: run of digits (e.g. a percentage abutting with no space: "$17,40022%") falls
#: outside the match instead of merging into it (#34). The no-comma alternative
#: preserves amounts written without thousands separators ("$5000000").
DOLLAR_RE = re.compile(r"\$\d{1,3}(?:,\d{3})+|\$\d+")

#: A floor amendment annotation, stripped before scanning so the delta it announces is not
#: read as an appropriation in its own right.
AMENDMENT_RE = re.compile(r"\((?:increased|reduced|decreased) by\s+\$[\d,]+\)")


def extract_amounts(text: str) -> tuple[int, ...]:
    """Find all dollar amounts in text.

    Returns tuple of integer values in document order. $0 is kept: it is real
    budget data (e.g. a rescinded or zeroed line), and an unchanged $0 produces
    no diff noise (multiset equality), so keeping it only surfaces $0 when it
    actually changes (#60). Strips floor amendment annotations like
    (increased by $X) before scanning.
    """
    text = AMENDMENT_RE.sub("", text)
    results = []
    for match in DOLLAR_RE.finditer(text):
        value = int(match.group().replace("$", "").replace(",", ""))
        results.append(value)
    return tuple(results)
