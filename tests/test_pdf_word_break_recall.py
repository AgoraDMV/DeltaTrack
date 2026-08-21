"""Hyphen-sensitive cross-check: a word the printer split across two lines must be
put back together as a word the bill actually contains.

GPO sets bill text justified, so a word that does not fit is broken at the right
margin and continued on the next line. Two different things produce that break and
they are printed identically:

    INTEL-   / LIGENCE    a syllable break the printer introduced  -> INTELLIGENCE
    McKinney- / Vento     the word's own hyphen, used as the break -> McKinney-Vento

Reflowing the first without dropping the hyphen invents ``INTEL-LIGENCE``; reflowing
the second while dropping it invents ``McKinneyVento``. Both are word forms that
appear nowhere in the bill, and ``full_text`` is what the report embeds for download
and what the reading view displays, so an invented form is what a reader (or the AI
assistant the report tells a staffer to hand ``diff.json`` to) sees.

**Why this is not already covered.** The prose cross-check
(test_pdf_xml_prose_recall.py) compares the same two documents but is hyphen-BLIND by
construction: ``normalize_for_cross_format`` deletes every hyphen before matching, and
says so -- "A hyphen genuinely lost by extraction is therefore invisible here."
``normalize_for_recall`` goes further and rewrites ``Child- Rescue`` back into
``Child-Rescue`` at compare time, with a comment recording that the parser could not
tell a soft wrap from a compound. Those are the right calls for a RECALL question,
which asks whether the words survived. They make this suite the only place that can
ask whether the word was reassembled correctly, which is a fidelity question.

**The oracle.** For a bill published in both formats, GPO's XML is an independent
transcription with no printed line breaks in it, so every word form the reflowed PDF
produces at a break should be a word form the XML has. Read here with lxml's
``itertext`` rather than through ``normalize_bill``, so the oracle side stays
independent of DeltaTrack code (same reason test_pdf_xml_prose_recall.py writes its
own extractor).

**What is asserted**, per dual-format version:

  1. No word the printer split reaches ``full_text`` still split. A dangling
     ``INTEL-`` reads to a consumer as a word boundary that is not in the document.
     Asked against the XML, not against the merger's rule, so it cannot pass vacuously
     by restating the implementation -- see `_unjoined_words`.
  2. Every word form produced AT a join is a word form the XML carries.

**The residual set.** Clause 2 does not reach zero. A break whose two candidate forms
are both absent from the document's own text and from the other version compared with
it is decided by case shape, and shape is wrong for a lowercase-continuation compound
with no evidence anywhere (``government-`` / ``driven``). Those sites are enumerated
in ``_RESIDUALS`` and asserted by SET EQUALITY, not as a ceiling: a ceiling is
satisfied by fixing one site and breaking another, which is precisely the swap this
file exists to catch. Shrinking the set is an explicit commit that shows which sites
moved. Growing it without a stated reason is a regression.

Marked @slow: extracts every corpus PDF and parses its XML.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from lxml import etree
from pdf_corpus import cached_pages, dual_format_versions

from deltatrack.parsers.pdf_text import Page

pytestmark = pytest.mark.slow

_RESIDUALS_PATH = Path(__file__).parent / "data" / "pdf" / "word_break_residuals.json"

#: A word token as this check counts one: starts alphanumeric, may carry internal
#: hyphens, apostrophes and periods (``E-Verify``, ``U.S.C.``, ``Nation's``).
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-\.]*")

#: A printed line broken mid-word: an alphanumeric, then the break hyphen, at line end.
_BREAK_TAIL = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-\.]*-$")


def _canon(token: str) -> str:
    """Fold a token onto the form the two producers can be compared in.

    GPO's PDF sets quotes as paired single glyphs and its XML as entities, and either
    side may carry sentence punctuation the other does not. Case is folded because an
    all-caps heading in the PDF is title case in the XML. The hyphen is deliberately
    NOT touched -- it is the whole subject of this file.
    """
    token = token.replace("‘", "'").replace("’", "'")
    return token.strip("'\".,;:()[]").lower()


def _xml_word_forms(xml_path: Path) -> set[str]:
    """Every distinct word form in a bill XML, canonicalized."""
    tree = etree.parse(str(xml_path))
    forms: set[str] = set()
    for text in tree.getroot().itertext():
        for token in _WORD.findall(text):
            forms.add(_canon(token))
    return forms


def _merge_groups(pages: list[Page]) -> list[tuple[int, str, list[str], list[int]]]:
    """(page, merged text, the printed lines it consumed, seam offsets) in document order.

    Walks the document FLAT rather than per page, because a merge can cross a page
    boundary: `_rejoin_page_seam_breaks` lets a page's last line absorb the next page's
    first, so that merged line's text runs past anything its own page's `merge_ranges`
    covers. Merges consume printed lines strictly in document order, so a single cursor
    over the flattened printed lines reconstructs every group without needing the ranges.

    Reconstructing rather than trusting a recorded disposition is the point: this reads
    what the merger actually emitted, so the check cannot agree with the pipeline by
    construction.
    """
    flat_print = [line.text for page in pages for line in page.print_lines]
    flat_merged = [(page.page_number, line.text) for page in pages for line in page.lines]
    groups: list[tuple[int, str, list[str], list[int]]] = []
    cursor = 0
    for page_no, merged in flat_merged:
        assert cursor < len(flat_print), "merged lines outran the printed lines they came from"
        fragments = [flat_print[cursor]]
        acc = fragments[0]
        seams: list[int] = []
        cursor += 1
        while acc != merged:
            assert acc.endswith("-"), f"merged {merged!r} is not a hyphen-join of {fragments!r}"
            assert cursor < len(flat_print), f"ran out of printed lines rebuilding {merged!r}"
            nxt = flat_print[cursor]
            cursor += 1
            fragments.append(nxt)
            if len(acc) - 1 < len(merged) and merged[len(acc) - 1] == "-":
                seams.append(len(acc))
                acc = acc + nxt
            else:
                seams.append(len(acc) - 1)
                acc = acc[:-1] + nxt
        groups.append((page_no, merged, fragments, seams))
    assert cursor == len(flat_print), f"{len(flat_print) - cursor} printed lines never consumed"
    return groups


def _word_at(text: str, index: int) -> str:
    """The whole word token spanning `index`, so a seam yields the word it produced."""
    for m in _WORD.finditer(text):
        if m.start() <= index < m.end():
            return m.group(0)
    return ""


def _joined_words(groups: list[tuple[int, str, list[str], list[int]]]) -> list[tuple[str, str, str]]:
    """(left fragment, right fragment, produced word) for every join the merger made."""
    out: list[tuple[str, str, str]] = []
    for _page_no, merged, fragments, seams in groups:
        for k, seam in enumerate(seams):
            left = (_WORD.findall(fragments[k]) or [""])[-1].rstrip("-")
            right = _WORD.findall(fragments[k + 1]) or [""]
            out.append((left, right[0], _word_at(merged, seam)))
    return out


def _unjoined_words(
    groups: list[tuple[int, str, list[str], list[int]]], pages: list[Page], forms: set[str]
) -> list[tuple[int, str, str]]:
    """(page, left, right) for a word the printer split that reached `full_text` split.

    Asked against the XML rather than against the merger's own rule, deliberately. The
    mechanical question -- "did a line end in a hyphen with an alphanumeric after it,
    and was it joined?" -- is one the merger now always answers yes to, so a test
    phrased that way could never fail: it would restate the implementation and pass
    vacuously. The oracle question cannot: two fragments are a split WORD when putting
    them together makes a word form the bill has and leaving them apart does not.

    That also stops three things a line-final hyphen means other than a word break from
    reading as defects, without needing to enumerate them: an em-dash introducing an
    enumeration (`is amended-` / `(1) in paragraph`), a suspended hyphen (`short-` /
    `, mid-, and long-range`), and the running-footer chrome that PDFium floats between
    a page-seam break and its continuation (`† HR 4366 EAS`, issue #535). None of the
    three joins into a word, so none is reported here.
    """
    flat = [line.text for page in pages for line in page.print_lines]
    cursor = 0
    out: list[tuple[int, str, str]] = []
    for page_no, _merged, fragments, _seams in groups:
        cursor += len(fragments)
        tail = fragments[-1].rstrip()
        m = _BREAK_TAIL.search(tail)
        if not m or cursor >= len(flat):
            continue
        left = m.group(0)[:-1]
        right = (_WORD.findall(flat[cursor]) or [""])[0]
        if not right:
            continue
        whole = {_canon(left + "-" + right), _canon(left + right)} & forms
        if whole and _canon(left) not in forms:
            out.append((page_no, left, right))
    return out


def _residuals() -> dict[str, set[tuple[str, str]]]:
    """The known-irreducible joins, per version, from the committed fixture.

    A break whose two candidate forms are BOTH absent from the document's own text
    falls to `_shape_keeps_hyphen`, and shape cannot tell a lowercase-continuation
    compound (``government-`` / ``driven``) from a syllable break. Every entry here is
    that case; each carries the reason it could not be decided.

    Regenerate with `scripts/regen_word_break_residuals.py` and review the diff. Do NOT
    add entries to clear a red run without first establishing which of the two forms
    the bill actually uses -- a wrong entry silently blesses an invented word.
    """
    if not _RESIDUALS_PATH.exists():
        return {}
    raw = json.loads(_RESIDUALS_PATH.read_text())
    out: dict[str, set[tuple[str, str]]] = {}
    for entry in raw["residuals"]:
        out.setdefault(entry["version"], set()).add((entry["left"], entry["right"]))
    return out


_CASES = dual_format_versions()
assert _CASES, "no dual-format corpus versions collected; the fixture tree is broken"


@pytest.mark.parametrize(
    ("bill", "xml_path", "pdf_path"),
    _CASES,
    ids=[f"{b}/{p.stem}" for b, _x, p in _CASES],
)
def test_printed_word_breaks_reflow_to_real_words(bill: str, xml_path: Path, pdf_path: Path) -> None:
    pages = cached_pages(pdf_path)
    version = f"{bill}/{pdf_path.stem}"

    groups = _merge_groups(pages)
    forms = _xml_word_forms(xml_path)
    unjoined = _unjoined_words(groups, pages, forms)
    expected = _residuals().get(version, set())

    invented: dict[tuple[str, str], str] = {}
    for left, right, produced in _joined_words(groups):
        if _canon(produced) not in forms:
            invented[(left, right)] = produced

    problems: list[str] = []
    if unjoined:
        shown = "; ".join(f"p{n}: {a}- / {b}" for n, a, b in unjoined[:6])
        problems.append(f"{len(unjoined)} words the printer split reached full_text still split -- {shown}")

    # Set equality, not a ceiling: a ceiling is satisfied by fixing one site and
    # breaking another, which is the swap this file exists to catch.
    unexpected = sorted(set(invented) - expected)
    if unexpected:
        shown = "; ".join(f"{a}- / {b} -> {invented[(a, b)]!r}" for a, b in unexpected[:6])
        problems.append(f"{len(unexpected)} joins produced a word form absent from the XML -- {shown}")
    repaired = sorted(expected - set(invented))
    if repaired:
        shown = "; ".join(f"{a}- / {b}" for a, b in repaired[:6])
        problems.append(
            f"{len(repaired)} residuals now resolve correctly and must be REMOVED from "
            f"{_RESIDUALS_PATH.name} -- {shown}"
        )

    assert not problems, f"{version}: " + " | ".join(problems)
