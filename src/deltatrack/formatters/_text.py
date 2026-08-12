"""Shared text helpers used by every diff renderer."""

import difflib
from html import escape

#: Below this word-level ratio an inline word-diff stops being legible, so the reader is
#: shown two stacked paragraphs instead. A RENDERING decision about what a reader can
#: follow, and this module owns it.
#:
#: It is deliberately NOT ``deltatrack.similarity.SIMILARITY_THRESHOLD``, which decides
#: whether two observations are the same provision. Those are different questions with
#: different correctness criteria, and [ADR 0020](../../../docs/decisions/0020-matching-stages.md)
#: separates them: a correspondence cutoff belongs to assignment, while this one decides
#: only how a settled change reaches the page. They carry the same value today, and that
#: is a coincidence of history rather than a constraint either may rely on -- #368 and
#: #170 are both open and both would move or reinterpret the differ's cutoff, which must
#: no longer silently restyle the report in the same edit.
#:
#: Equality with the differ's cutoff is NOT asserted anywhere, and must not be: a test
#: pinning the two together would re-create in the suite the coupling this constant was
#: introduced to remove, and would redden the moment the differ is legitimately retuned.
LEGIBILITY_THRESHOLD = 0.4


def word_diff(old_text: str, new_text: str, threshold: float = LEGIBILITY_THRESHOLD) -> str | None:
    """Produce an inline HTML diff at the word level.

    Returns an HTML string with <del> and <ins> tags wrapping changed words,
    or None if the texts are too dissimilar (below *threshold*).

    The default was a bare ``0.4`` (#492), then ``similarity.SIMILARITY_THRESHOLD``. Its
    only production caller (``diff_html._prose_body_html``) renders without passing it, so
    whichever number sits here is the one that decides whether a reader sees an inline
    word-diff or two stacked paragraphs. Naming it fixed the invisibility; pointing it at
    the differ's cutoff left the rendering layer reading the differ's correspondence
    policy. It now reads :data:`LEGIBILITY_THRESHOLD`, which this module owns.

    **The default is bound at import, and that is deliberate.** Rebinding
    ``LEGIBILITY_THRESHOLD`` at runtime does not change what this function does, so no
    test may establish the separation by monkeypatching a module attribute. The
    separation is established on the import graph and on this default's *expression*
    (``tests/test_formatter_boundary.py``), and the cutoff's live effect is established
    through the real ``_prose_body_html`` caller on cases either side of it. Reshaping
    this signature to make the constant perturbable would be changing production to suit
    a test technique that source mutation already covers.
    """
    old_words = old_text.split()
    new_words = new_text.split()

    matcher = difflib.SequenceMatcher(None, old_words, new_words)
    if matcher.ratio() < threshold:
        return None

    parts: list[str] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            parts.append(escape(" ".join(old_words[i1:i2])))
        elif op == "replace":
            parts.append("<del>" + escape(" ".join(old_words[i1:i2])) + "</del>")
            parts.append("<ins>" + escape(" ".join(new_words[j1:j2])) + "</ins>")
        elif op == "delete":
            parts.append("<del>" + escape(" ".join(old_words[i1:i2])) + "</del>")
        elif op == "insert":
            parts.append("<ins>" + escape(" ".join(new_words[j1:j2])) + "</ins>")

    return " ".join(parts)


def fmt_dollar(amount: int) -> str:
    """Format an integer as a dollar string with commas."""
    return f"${amount:,}"
