"""Anchor extraction for PDF bills.

An Anchor is a landmark label (TITLE / SEC. / account heading) the GPO PDF
carries reliably. The diff layer attaches the nearest preceding anchor to each
hunk as a "where am I" breadcrumb. When no anchor resolves cleanly, the diff
falls back to the page/line citation alone — anchors degrade, they don't gate.

Operates on `parsers.pdf_text.Page` objects, which carry per-line source PDF
line numbers.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from typing import Literal

from parsers.pdf_text import Page, parse_lines, strip_page_chrome

AnchorKind = Literal["title", "section", "account", "preamble"]


@dataclass(frozen=True)
class Anchor:
    page_number: int  # 1-based
    line_number: int  # 1-based, from the source PDF's printed line numbers
    kind: AnchorKind
    text: str  # canonical form, e.g. "TITLE I", "SEC. 406", "OPERATIONS AND SUPPORT"


@dataclass(frozen=True)
class SizeBands:
    """Per-document glyph-size bands derived from one bill's extracted Lines (#89).

    `body` is the prose size; the heading band [heading_lo, heading_hi] is the
    distinct cluster of (small-caps) heading sizes below it. Compared with a
    tolerance (`_SIZE_EPS`); the band is required to sit more than 2·eps below
    body so the windows are provably disjoint.
    """

    body: float
    heading_lo: float
    heading_hi: float


# Size comparison tolerance (points). Per-line medians wobble ~0.1pt; eps must
# exceed that rounding granularity. Body↔heading separation must exceed 2·eps.
_SIZE_EPS = 0.3
# A document needs at least this fraction of its numbered lines to carry an
# attached glyph size before we trust size-based detection; below it we fall back
# to the legacy text trigger (a partial join would silently drop headings).
_COVERAGE_MIN = 0.85


_TITLE_PATTERN = re.compile(r"^TITLE\s+([IVXLC]+)\b.*$")
_SECTION_PATTERN = re.compile(r"^(SEC(?:TION)?\.?\s+\d+)\b")
_FOR_NECESSARY_EXPENSES = re.compile(r"^For necessary expenses of\b", re.IGNORECASE)
# A run-in subsection header ("(B) Current visas revoked.—") renders small-caps,
# so it lands in the heading band, but it is NOT an account: it opens with a
# parenthesized enumerator, which appropriations account headings never do. Used
# to reject these false accounts on general (non-appropriations) bills.
_ENUM_PREFIX = re.compile(r"^\([0-9A-Za-z]{1,4}\)\s")


def _is_uppercase_heading(content: str) -> bool:
    """Heuristic: line is mostly uppercase letters, not a TITLE/SEC. heading.

    Allows commas, parentheses, ampersands, periods. Rejects lines with any
    lowercase ASCII letters.
    """
    if not content.strip():
        return False
    if _TITLE_PATTERN.match(content) or _SECTION_PATTERN.match(content):
        return False
    has_letter = False
    for ch in content:
        if ch.isalpha():
            has_letter = True
            if ch.islower():
                return False
    return has_letter


def _has_lowercase(text: str) -> bool:
    return any("a" <= ch <= "z" for ch in text)


def _sized_lines(pages: list[Page]):
    for page in pages:
        for line in page.lines:
            if line.line_number is not None and line.glyph_size is not None:
                yield line


def derive_size_bands(pages: list[Page]) -> SizeBands | None:
    """Derive the per-document body/heading glyph-size bands, or None.

    Returns None (→ legacy text-trigger fallback) when the signal isn't a clean
    body+single-heading-band split: no sized prose lines, no sub-body heading
    cluster, more than one strong heading cluster (trimodal, e.g. reconciliation
    bills), or a body↔heading gap within 2·eps.
    """
    body_sizes = [ln.glyph_size for ln in _sized_lines(pages) if _has_lowercase(ln.text)]
    if not body_sizes:
        return None
    # body = the most common prose size; smallest on a tie (deterministic).
    body = min(statistics.multimode(round(s, 1) for s in body_sizes))

    head_sizes = sorted(
        round(ln.glyph_size, 1)
        for ln in _sized_lines(pages)
        if _is_uppercase_heading(ln.text) and ln.glyph_size < body - _SIZE_EPS
    )
    if not head_sizes:
        return None

    # Cluster the sub-body heading sizes; split where a gap exceeds 2·eps.
    clusters: list[list[float]] = [[head_sizes[0]]]
    for s in head_sizes[1:]:
        if s - clusters[-1][-1] > 2 * _SIZE_EPS:
            clusters.append([s])
        else:
            clusters[-1].append(s)
    dominant = max(clusters, key=len)
    # More than one *strong* cluster (≥30% of the dominant) ⇒ trimodal ⇒ bail.
    if any(c is not dominant and len(c) >= 0.3 * len(dominant) for c in clusters):
        return None

    heading_lo, heading_hi = dominant[0], dominant[-1]
    if body - heading_hi <= 2 * _SIZE_EPS:
        return None
    return SizeBands(body, heading_lo, heading_hi)


def _scan_anchors_in_page(page_number: int, raw_text: str) -> list[Anchor]:
    """Scan one page's raw chrome-stripped, line-numbered text for anchors.

    Test-only entry point that takes a raw `<n> content` string per line. Runs the
    full `extract_anchors` pipeline on the single page so account detection (size
    path, or legacy fallback when the synthetic page carries no glyph sizes) is
    exercised. Production path uses `extract_anchors(pages)`.
    """
    page = Page(page_number, parse_lines(strip_page_chrome(raw_text)))
    return extract_anchors([page])


def _anchors_from_page(page: Page) -> list[Anchor]:
    """TITLE and SEC anchors for one page (per-page; no cross-line context needed).

    Account anchors are emitted separately by `extract_anchors`, which needs the
    flattened document line stream for size-band classification and page-seam
    look-ahead.
    """
    anchors: list[Anchor] = []
    for line in page.lines:
        if line.line_number is None:
            continue
        title_match = _TITLE_PATTERN.match(line.text)
        if title_match:
            anchors.append(Anchor(page.page_number, line.line_number, "title", f"TITLE {title_match.group(1)}"))
            continue
        section_match = _SECTION_PATTERN.match(line.text)
        if section_match:
            canonical = re.sub(r"\s+", " ", section_match.group(1))
            anchors.append(Anchor(page.page_number, line.line_number, "section", canonical))
    return anchors


def _coverage(pages: list[Page]) -> float:
    numbered = [ln for page in pages for ln in page.lines if ln.line_number is not None]
    if not numbered:
        return 0.0
    return sum(1 for ln in numbered if ln.glyph_size is not None) / len(numbered)


def _flatten(pages: list[Page]) -> list[tuple[int, "Line"]]:  # noqa: F821 - Line via pdf_text
    return [(page.page_number, ln) for page in pages for ln in page.lines]


def _account_anchors_by_size(pages: list[Page], bands: SizeBands) -> list[Anchor]:
    """Size-based account detection over the flattened document line stream.

    An account is a heading-band, uppercase line whose next meaningful line is
    body prose. A band heading followed by another band heading is an agency
    parent (skipped — deferred to #54). The look-ahead skips blank/None lines; an
    unattached (size-less) next line counts as body (conservative: skipping toward
    the next heading would wrongly drop a leaf). The anchor keeps the heading's own
    page/line, never the look-ahead target's.
    """
    flat = _flatten(pages)

    def in_band(size: float | None) -> bool:
        return size is not None and bands.heading_lo - _SIZE_EPS <= size <= bands.heading_hi + _SIZE_EPS

    def is_body(line) -> bool:
        # Unattached non-blank line ⇒ treat as body. Otherwise body = at body size.
        if not line.text.strip():
            return False
        if line.glyph_size is None:
            return True
        return abs(line.glyph_size - bands.body) <= _SIZE_EPS

    anchors: list[Anchor] = []
    for idx, (page_number, line) in enumerate(flat):
        if line.line_number is None or not in_band(line.glyph_size):
            continue
        if not _is_uppercase_heading(line.text):
            continue
        if _ENUM_PREFIX.match(line.text):  # run-in subsection header, not an account
            continue
        # Look ahead for the next meaningful (non-blank, numbered-or-unattached) line.
        nxt = None
        for _pg, cand in flat[idx + 1 :]:
            if cand.text.strip() == "":
                continue
            nxt = cand
            break
        # Leaf account = followed by body prose, or end-of-document. A following
        # band heading means this is an agency parent → skip.
        if nxt is None or is_body(nxt):
            anchors.append(Anchor(page_number, line.line_number, "account", line.text.strip()))
    return anchors


def _account_anchors_legacy(pages: list[Page]) -> list[Anchor]:
    """Legacy fallback: walk back ≤3 numbered lines from a `For necessary expenses
    of` trigger to the nearest uppercase heading. Used when size bands aren't
    derivable or attachment coverage is too low."""
    flat = [(pg, ln) for pg, ln in _flatten(pages)]
    anchors: list[Anchor] = []
    for idx, (page_number, line) in enumerate(flat):
        if line.line_number is None or not _FOR_NECESSARY_EXPENSES.match(line.text):
            continue
        seen = 0
        for back in range(idx - 1, -1, -1):
            bpg, bline = flat[back]
            if bline.line_number is None:
                continue
            seen += 1
            if _is_uppercase_heading(bline.text):
                candidate = Anchor(bpg, bline.line_number, "account", bline.text.strip())
                if candidate not in anchors:
                    anchors.append(candidate)
                break
            if seen >= 3:
                break
    return anchors


def extract_anchors(pages: list[Page]) -> list[Anchor]:
    """Extract all anchors (title/section/account) in document order.

    TITLE/SEC are detected per page. Accounts use size-band + position
    classification when the document yields clean bands and adequate glyph-size
    attachment coverage; otherwise they fall back to the legacy text trigger.
    """
    anchors: list[Anchor] = []
    for page in pages:
        anchors.extend(_anchors_from_page(page))

    bands = derive_size_bands(pages)
    if bands is not None and _coverage(pages) >= _COVERAGE_MIN:
        anchors.extend(_account_anchors_by_size(pages, bands))
    else:
        anchors.extend(_account_anchors_legacy(pages))

    anchors.sort(key=lambda a: (a.page_number, a.line_number))
    return anchors


def breadcrumb_for(anchor: Anchor, all_anchors: tuple[Anchor, ...] | list[Anchor]) -> tuple[str, ...]:
    """Walk back through `all_anchors` from `anchor` to assemble a parent chain.

    For a TITLE anchor: returns just `("TITLE I",)`.
    For a PREAMBLE (front-matter) anchor: returns just `("Front Matter",)` —
    it's top-level, preceding the first TITLE.
    For a SECTION anchor: returns `("TITLE IV", "SEC. 406")` if a preceding
    TITLE exists, else just `("SEC. 406",)`.
    For an ACCOUNT anchor: returns `("TITLE I", "OPERATIONS AND SUPPORT")` if
    a preceding TITLE exists, else just `("OPERATIONS AND SUPPORT",)`.

    The agency-level heading (e.g. "OFFICE OF THE SECRETARY") is not currently
    captured by anchor extraction; once that lands the chain becomes three
    levels deep without changing this function's contract.
    """
    if anchor.kind in ("title", "preamble"):
        return (anchor.text,)
    # Find anchor's index by identity
    try:
        idx = list(all_anchors).index(anchor)
    except ValueError:
        return (anchor.text,)
    # Walk back for the most recent preceding TITLE
    for j in range(idx - 1, -1, -1):
        if all_anchors[j].kind == "title":
            return (all_anchors[j].text, anchor.text)
    return (anchor.text,)
