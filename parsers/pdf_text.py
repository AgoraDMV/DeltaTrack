"""PDF text extraction with the smallest set of primitives that fixture cases require.

Text is extracted with pypdfium2 (PDFium, Chrome's PDF engine). `Page` is
line-aware: every cleaned `Line` carries the source PDF's printed line number
(1-based, the small digit GPO renders in the left margin). Phase 2 uses those
numbers to produce hunk citations like `p.61 L5` and to attach anchor breadcrumbs
by binary-searching the anchor list. The page-level `text` property is a derived
join, so existing consumers (recall test, `page_range_text`) keep working without
change.

PDFium's raw page text needs three normalizations before the line-numbered cleaner
can read it (`normalize_raw`): CRLF endings, soft-hyphenated breaks rendered as a
U+FFFE glyph with the next margin number glued inline, and footer chrome glued onto
a line whose word hyphenates onto the next page. The running `•HR` header also
floats to the top of the reading order, so chrome stripping (`strip_page_chrome`)
removes it in place rather than from the bottom.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

_NUMBERED_LINE = re.compile(r"^(\d{1,2}) (.*)$")
_SOFT_HYPHEN_BREAK = re.compile(r"(\w)-\n([a-z])")
_SMART_GLYPHS = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
    }
)

# PDFium soft-hyphen glyph (U+FFFE), emitted at a syllable break and immediately
# followed by the *next* GPO margin line number glued inline (e.g. `equip￾4 ment`).
_HYPHEN_BREAK = re.compile(r"￾(\d{1,2}) ")
# A soft hyphen NOT followed by a margin number is a page-boundary break: PDFium has
# no same-page continuation to emit after the U+FFFE, so it pulls whatever footer
# chrome it reads next (VerDate or the `name on DSK…PROD` watermark) onto that line.
# Drop only that recognized chrome, keeping the hyphen for the cross-page rejoin.
# The match is chrome-specific on purpose: enrolled bills carry no GPO margin
# numbers, so their soft hyphens are followed by ordinary word text (`equip￾ment`)
# that must NOT be stripped.
_GLUED_CHROME = re.compile(r"￾(?:VerDate\b|\S* on DSK)[^\n]*")
# Page chrome. The page-number header is `5 \n` (digit + optional trailing space).
# The running `•HR … RH` (House) / `•S … RS` (Senate) header floats to the top of
# PDFium's reading order. The
# `VerDate …` print line and the `name on DSK…PROD with …` watermark sit at the
# bottom; either may be the anchor depending on the page, so both are stripped.
_PAGE_HEADER_NUMBER = re.compile(r"\A\d+ *\n")
_RUNNING_HEADER = re.compile(r"^•(?:HR|S)\b.*\n", re.MULTILINE)
_VERDATE_AND_BELOW = re.compile(r"\n?VerDate\b.*\Z", re.DOTALL)
_WATERMARK_AND_BELOW = re.compile(r"\n?\S+ on DSK\S*PROD with .*\Z", re.DOTALL)


@dataclass(frozen=True)
class Line:
    line_number: int | None  # 1-based source PDF line number; None if unnumbered
    text: str  # cleaned line content (line-number prefix stripped)
    # Representative recovered glyph size (points) for this line, or None when no
    # size could be attached (unnumbered line, or the geometry sidecar found no
    # match for this line number). Filled post-merge by extract_clean_pages; the
    # string pipeline leaves it None. Used for size-based heading segmentation (#89).
    glyph_size: float | None = None


@dataclass(frozen=True)
class Page:
    page_number: int  # 1-based
    lines: tuple[Line, ...]  # soft-hyphens rejoined into whole words; what the diff compares
    # The original printed lines (pre-merge): one entry per line the GPO actually
    # printed, with its own margin number and hyphenated word breaks intact. Used
    # only by the full-bill display so it can match the printed page; empty for
    # Pages built directly in tests / by the anchor parser, which don't display.
    print_lines: tuple[Line, ...] = ()
    # Parallel to `lines`: for each merged line, the [start, end) slice of
    # `print_lines` it was built from, so a merged-line coordinate can be mapped
    # back onto the printed lines it covers.
    merge_ranges: tuple[tuple[int, int], ...] = ()

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


def normalize_raw(text: str) -> str:
    """Rewrite PDFium's raw page text into the layout the line-numbered cleaner expects.

    Converts CRLF to LF; reconstructs soft-hyphenated breaks (`WORD￾N word` →
    `WORD-\\nN word`) so the continuation line keeps its margin number; drops footer
    chrome glued onto a page's last body line by a page-boundary hyphen, keeping the
    hyphen for the cross-page rejoin; and strips trailing spaces (which PDFium keeps
    on nearly every line) so line text is stable. A soft hyphen mid-line followed by a
    lowercase letter (a word that wrapped on a page with no margin numbers, e.g. a
    title page or enrolled bill) is joined into one word, since there is no `-\n`
    boundary for the later rejoin pass to act on.
    """
    text = text.replace("\r\n", "\n")
    text = _HYPHEN_BREAK.sub(r"-\n\1 ", text)
    text = _GLUED_CHROME.sub("-", text)
    text = re.sub(r"￾([a-z])", r"\1", text)
    text = text.replace("￾", "-")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text


def strip_page_chrome(text: str) -> str:
    """Remove page furniture: the page-number header, the running `•HR` header, the
    VerDate print line, and the reversed-glyph watermark below it.

    PDFium floats the `•HR … RH` running header to the top of the page (after the
    page number), so it is removed in place rather than from the bottom. VerDate and
    the watermark are each dropped from their first occurrence to end-of-text.
    """
    text = _PAGE_HEADER_NUMBER.sub("", text)
    text = _RUNNING_HEADER.sub("", text)
    text = _VERDATE_AND_BELOW.sub("", text)
    text = _WATERMARK_AND_BELOW.sub("", text)
    return text


def rejoin_soft_hyphens(text: str) -> str:
    """Join `WORD-\\nword` (lowercase continuation) into `WORDword`.

    GPO bills break long words at syllable boundaries with `-\\n` followed by a
    lowercase letter. Real compounds like `Child-Rescue` keep an uppercase
    continuation, so the lowercase guard preserves them.
    """
    return _SOFT_HYPHEN_BREAK.sub(r"\1\2", text)


def normalize_glyphs(text: str) -> str:
    """Map typographic glyphs to ASCII equivalents for comparison-time use.

    Em/en-dashes become ` - ` (space-padded so whitespace normalization handles
    spaced and unspaced source forms). Smart single/double quotes become their
    ASCII counterparts. GPO encodes double quotes as two adjacent single-glyph
    smart quotes (`‘‘…’’`), so paired ASCII apostrophes collapse to `"`.

    The extractor itself preserves original glyphs; this helper exists so
    comparison and diff layers can canonicalize without losing source bytes.
    """
    text = text.replace("—", " - ").replace("–", " - ")
    text = text.translate(_SMART_GLYPHS)
    text = text.replace("''", '"')
    return text


def _parse_print_lines(chrome_stripped: str) -> list[Line]:
    """Parse chrome-stripped page text into one Line per printed line.

    Each body line in a GPO bill begins with `<line_number> <content>`. Lines
    that don't fit (anomalies, empty lines, cover-page text) get
    `line_number=None`. No rejoining — this is the printed layout verbatim.
    """
    parsed: list[Line] = []
    for raw_line in chrome_stripped.split("\n"):
        m = _NUMBERED_LINE.match(raw_line)
        if m:
            parsed.append(Line(int(m.group(1)), m.group(2)))
        else:
            parsed.append(Line(None, raw_line))
    return parsed


def _merge_print_lines(parsed: list[Line]) -> tuple[list[Line], list[tuple[int, int]]]:
    """Rejoin per-page soft hyphens at line boundaries.

    When line[i] ends with `WORD-` and line[i+1] starts lowercase, merge them
    into the earlier line and drop the later record. Chain: a single hunk can
    span 3+ lines (e.g. `wel-\\nfare; ... (in-\\ncreased by …)`), so the merged
    line may itself end in another soft hyphen to join with the line after.

    Returns the merged lines and, parallel to them, the `[start, end)` slice of
    `parsed` each merged line was built from (so callers can map a merged line
    back to the printed lines it covers).
    """
    merged: list[Line] = []
    ranges: list[tuple[int, int]] = []
    i = 0
    while i < len(parsed):
        current = parsed[i]
        next_i = i + 1
        while (
            next_i < len(parsed)
            and current.text.endswith("-")
            and len(current.text) >= 2
            and current.text[-2].isalnum()
            and parsed[next_i].text[:1].islower()
        ):
            current = Line(current.line_number, current.text[:-1] + parsed[next_i].text)
            next_i += 1
        merged.append(current)
        ranges.append((i, next_i))
        i = next_i
    return merged, ranges


def parse_lines(chrome_stripped: str) -> tuple[Line, ...]:
    """Parse chrome-stripped page text into merged (whole-word) Line records.

    Convenience wrapper over `_parse_print_lines` + `_merge_print_lines` for
    callers that only need the rejoined lines the diff compares.
    """
    merged, _ = _merge_print_lines(_parse_print_lines(chrome_stripped))
    return tuple(merged)


def page_range_text(pages: list[Page], start_page: int, end_page: int) -> str:
    """Concatenate page texts in [start_page, end_page] and rejoin cross-page soft hyphens.

    Per-page cleanup handles intra-page hyphens. Cross-page hyphens (where one
    page ends with `word-` and the next begins with the continuation) only
    surface after concatenation, so the rejoin pass runs again on the seam.
    """
    joined = "\n".join(p.text for p in pages if start_page <= p.page_number <= end_page)
    return rejoin_soft_hyphens(joined)


def extract_clean_pages(pdf_path: Path) -> list[Page]:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        pages: list[Page] = []
        for i in range(len(pdf)):
            raw = pdf[i].get_textpage().get_text_range()
            chrome_stripped = strip_page_chrome(normalize_raw(raw))
            print_lines = _parse_print_lines(chrome_stripped)
            merged, ranges = _merge_print_lines(print_lines)
            pages.append(Page(i + 1, tuple(merged), tuple(print_lines), tuple(ranges)))
        return pages
    finally:
        pdf.close()


def _render_lines(lines: tuple[Line, ...]) -> tuple[list[str], list[tuple[int, int]]]:
    """Render a page's lines as `{number:>5}  {content}` rows (five-space pad
    when unnumbered). Returns the rendered rows and, parallel to them, each
    row's (start, end) char span relative to a 0-based page start."""
    rows: list[str] = []
    spans: list[tuple[int, int]] = []
    pos = 0
    for line in lines:
        prefix = f"{line.line_number:>5}" if line.line_number is not None else " " * 5
        rendered = f"{prefix}  {line.text}"
        spans.append((pos, pos + len(rendered)))
        rows.append(rendered)
        pos += len(rendered) + 1  # +1 for the joining newline
    return rows, spans


def pdf_full_text(pages: list[Page]) -> tuple[str, dict[tuple[int, int], tuple[int, int]]]:
    """Render the merged (whole-word) page lines with their line numbers.

    This is the canonical full text: it backs the embedded ``diff.json`` and the
    export, and its offsets anchor change spans. Each line gets a 5-char
    right-aligned line-number prefix (blank padding when unnumbered); pages are
    separated by a blank line. For the print-faithful reading view, see
    ``pdf_full_text_print``.

    Returns (text, line_offsets) where line_offsets maps (page_number,
    line_number) -> (start_char, end_char) in `text`. Only lines with a
    non-None line_number are indexed; unnumbered lines aren't reachable
    via change.location anyway. This is the producer counterpart consumed
    by pdf_diff_to_canonical(..., line_offsets=...) to fill full_text_span.
    """
    chunks: list[str] = []
    line_offsets: dict[tuple[int, int], tuple[int, int]] = {}
    base = 0
    for i, page in enumerate(pages):
        if i > 0:
            chunks.append("")  # blank line between pages
            base += 1  # for the trailing newline
        rows, spans = _render_lines(page.lines)
        for line, (s, e) in zip(page.lines, spans):
            if line.line_number is not None:
                line_offsets[(page.page_number, line.line_number)] = (base + s, base + e)
        chunks.extend(rows)
        base += spans[-1][1] + 1 if spans else 0
    return "\n".join(chunks), line_offsets


def pdf_full_text_print(pages: list[Page]) -> tuple[str, dict[tuple[int, int], tuple[int, int]]]:
    """Render the *original printed* lines (pre-merge) for the full-bill view.

    Unlike `pdf_full_text`, this keeps every printed line number and the GPO
    line breaks (soft-hyphenated words stay split, as on the page), so the
    on-screen text matches a printed copy line for line.

    Returns (text, line_offsets) where line_offsets maps (page_number,
    **merged** line_number) -> (start_char, end_char) in this print-faithful
    text, spanning all the printed lines the merged line was built from. Keying
    by the merged line number (via `Page.merge_ranges`) lets change spans —
    which are expressed in merged-line coordinates — land on the right printed
    lines when fed to pdf_diff_to_canonical(..., line_offsets=...).
    """
    chunks: list[str] = []
    line_offsets: dict[tuple[int, int], tuple[int, int]] = {}
    base = 0
    for i, page in enumerate(pages):
        if i > 0:
            chunks.append("")  # blank line between pages
            base += 1
        rows, spans = _render_lines(page.print_lines)
        for line, (start_idx, end_idx) in zip(page.lines, page.merge_ranges):
            if line.line_number is None:
                continue
            start = base + spans[start_idx][0]
            end = base + spans[end_idx - 1][1]
            line_offsets[(page.page_number, line.line_number)] = (start, end)
        chunks.extend(rows)
        base += spans[-1][1] + 1 if spans else 0
    return "\n".join(chunks), line_offsets
