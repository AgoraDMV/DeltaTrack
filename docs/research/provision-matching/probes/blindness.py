"""Shared §5 blindness enforcement for both labeling paths.

Protocol §5 says a labeler must never see the stratum name (the mining rule that selected the
pair, which telegraphs the expected answer) or the similarity scores under test. Validating a
measure against labels that measure influenced is circular, so this is the guarantee the whole
Pass 2 dataset rests on.

Two paths present a card to a labeler: `make_form.py` renders HTML for a human, `label_llm.py`
assembles a prompt for the model. They enforced §5 differently, and the human path's check
could not fail (#332): it compared key names against a card built from a hardcoded literal, and
never looked at the rubric or worked examples the reviewer reads before labeling. The scan that
worked lives here now, so the path producing the ground truth and the path producing the second
opinion cannot drift apart again.

Both callers assemble the text a labeler will actually see, mask the corpus-derived spans, and
scan what is left. Masking matters: the bill texts and breadcrumbs are shown on purpose and
legitimately contain domain words ("measures", "consolidation") and dollar figures, so an
unmasked scan false-positives on real bills. Everything that survives masking is text we
authored, where a forbidden word or a bare decimal can only have arrived by interpolation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# The scores under test plus the mining artifacts that hint at the expected answer. "extra" is
# scanned structurally (as a card key) but never as a word: it is ordinary English and would
# false-positive on any authored sentence containing it.
FORBIDDEN = {"measures", "containment", "cosine", "word_overlap", "stratum", "change_type", "extra"}

# A score-shaped float. containment / cosine / word_overlap all live in [0,1], and nothing we
# author contains a decimal, so one surviving the mask means a measure leaked in.
SCORE_RE = re.compile(r"\d\.\d+")


class BlindnessError(Exception):
    """A forbidden field, stratum name, or score-shaped float reached what a labeler would see.

    Raised rather than exiting so the caller decides: the LLM dry-run pre-flight hard-fails on it,
    a real run skips the one card instead of nuking a multi-hour batch, and form generation
    refuses to write the file.
    """


def breadcrumb(path: list[str]) -> str:
    """The structural location as a labeler reads it. Shown on purpose (§5): it is the
    ground-truth signal a human legitimately uses."""
    return " > ".join(path) if path else "(no breadcrumb)"


def mask_corpus(text: str, card: dict) -> str:
    """Blank every corpus-derived span the labeler is shown verbatim: the two texts, the two
    breadcrumbs, and the bill/version metadata.

    Ranges are computed on the PRISTINE text and blanked in one pass. A sequential str.replace
    corrupts overlapping spans: on the high-containment stratum text_old is a substring of
    text_new, so replacing text_old first breaks the text_new match and leaks its residue, which
    is how a legitimate "measures" in a bill once tripped the guard and aborted a run.
    """
    spans = [
        card["text_old"],
        card["text_new"],
        breadcrumb(card["bc_old"]),
        breadcrumb(card["bc_new"]),
        str(card["bill_old"]),
        str(card["bill_new"]),
        str(card["version_old"]),
        str(card["version_new"]),
    ]
    chars = list(text)
    for span in spans:
        # Skip empty AND pathologically short spans: a 1-2 char corpus value (a degenerate version
        # code, say) would blank that letter everywhere and could over-mask authored text, hiding a
        # real leak. A <3-char span cannot itself be a forbidden word / stratum name / score float,
        # so never masking it cannot cause a false positive.
        if len(span) < 3:
            continue
        start = 0
        while (i := text.find(span, start)) >= 0:
            for j in range(i, i + len(span)):
                chars[j] = " "
            start = i + 1  # +1 (not +len) so overlapping occurrences are all found
    return "".join(chars)


def leaks_in(text: str, stratum_names: Iterable[str]) -> list[str]:
    """Everything §5 forbids that survives in `text`. Empty means blind. Call on MASKED text."""
    low = text.lower()
    found = [k for k in FORBIDDEN if k != "extra" and k.lower() in low]
    found += [s for s in stratum_names if s.lower() in low]
    if SCORE_RE.search(text):
        found.append("score-shaped-float")
    return sorted(set(found))
