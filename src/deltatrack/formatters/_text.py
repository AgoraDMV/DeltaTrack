"""Shared text helpers used by every diff renderer."""

import difflib
from html import escape

from deltatrack.similarity import SIMILARITY_THRESHOLD


def word_diff(old_text: str, new_text: str, threshold: float = SIMILARITY_THRESHOLD) -> str | None:
    """Produce an inline HTML diff at the word level.

    Returns an HTML string with <del> and <ins> tags wrapping changed words,
    or None if the texts are too dissimilar (below *threshold*).

    The default was a bare ``0.4`` (#492). Its only production caller
    (``diff_html._prose_body_html``) renders without passing it, so the number that
    decides whether a reader sees an inline word-diff or two stacked paragraphs was
    named by nothing and invisible to a search for the constant. It is the same cutoff
    the differ uses to decide a pair is not the same provision, so it comes from
    ``deltatrack.similarity`` — not from ``diff_bill``, which would point the rendering
    layer at the differ.
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
