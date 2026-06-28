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

AnchorKind = Literal["title", "section", "account", "grouping", "agency", "preamble"]


@dataclass(frozen=True)
class Anchor:
    page_number: int  # 1-based
    line_number: int  # 1-based, from the source PDF's printed line numbers
    kind: AnchorKind
    # canonical form, e.g. "TITLE I", "SEC. 406", "OPERATIONS AND SUPPORT", a
    # grouping header like "ADMINISTRATIVE PROVISIONS" (a header-only intermediate
    # node owning a run of SEC. sections — DeltaTrack#103), or a carry-over agency
    # like "MANAGEMENT DIRECTORATE" (one agency spanning >=2 accounts — #104). An
    # agency whose name wraps across heading lines is joined into one text.
    text: str


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
# A carry-over agency name that, when its heading-band run is joined, ends on a
# coordinating conjunction or preposition is a *wrapped account name* mistaken for
# an agency (e.g. "CONSTRUCTION AND ENVIRONMENTAL COMPLIANCE AND" / "RESTORATION"
# on 118-s-4795), not a real agency. Telling a wrapped account from an agency in
# general needs the leveled tree (#54/#108); this dangle guard cheaply rejects the
# worst mis-joins. No real agency name ends on one of these words.
_DANGLING_TAIL = frozenset({"AND", "OR", "OF", "FOR", "TO", "THE", "A", "AN", "IN", "ON", "WITH", "AT", "BY"})


def _dangles(text: str) -> bool:
    words = text.split()
    return bool(words) and words[-1].upper() in _DANGLING_TAIL


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


def _is_parenthetical(text: str) -> bool:
    """A line wholly enclosed in parentheses, e.g. `(INCLUDING TRANSFER OF FUNDS)`.

    These GPO appropriation qualifiers render in the heading band but are riders,
    not account names. They must not be emitted as accounts, and must be treated
    as transparent in the account look-ahead so the real account heading they
    follow is still seen as immediately preceding body prose.
    """
    t = text.strip()
    return t.startswith("(") and t.endswith(")")


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
    # body = the most common prose size; on a tie take the LARGER (body is the
    # dominant, larger cluster in GPO bills — picking a smaller tied size would
    # exclude real sub-body headings and silently force the legacy fallback).
    body = max(statistics.multimode(round(s, 1) for s in body_sizes))

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
    """Size-based account / grouping-header detection over the flattened line stream.

    A heading-band, uppercase line is classified by its next meaningful line:
      - a `SEC.` section line ⇒ a **grouping header** (`ADMINISTRATIVE PROVISIONS`,
        `GENERAL PROVISIONS`) — a header-only intermediate node owning a run of
        `SEC.` sections, not an account (DeltaTrack#103). In appropriations bills
        the SEC. line carries body prose ("SEC. 101. (a) The Secretary…") and so
        renders at body size, which is why the look-ahead used to read it as
        "followed by body" and mislabel the header `account`.
      - body prose (or end-of-document) ⇒ an `account` leaf.
      - another heading ⇒ this line belongs to a carry-over agency (one agency over
        >=2 accounts, DeltaTrack#104). It is not emitted on its own; instead, when a
        leaf account is reached, the contiguous heading-band run immediately
        preceding it is joined into ONE `agency` anchor (`agency_before_leaf`). The
        join rejoins agency names that GPO wrapped across heading lines (e.g.
        "OFFICE OF THE SECRETARY AND EXECUTIVE" / "MANAGEMENT").
    The look-ahead skips blank lines and parenthetical qualifiers; an unattached
    (size-less) next line counts as body (conservative — skipping toward the next
    heading would wrongly drop a leaf). Run-in subsection headers (`(a) …`) and
    parenthetical qualifiers are never accounts. The account/grouping anchor keeps
    the heading's own page/line; the agency anchor takes the run's FIRST line.

    The agency signal is bounded: a *leaf account* name that itself wraps across
    heading lines is indistinguishable from an agency by size/position, so the join
    can absorb a wrapped account fragment. The dangle guard (`_dangles`) rejects the
    worst of these; the rest is the leveled-tree problem (#54/#108). Exact on the
    clean bill (118-hr-8752), a tolerant floor on the hard one (118-s-4795).

    Body must be confirmed positively (at body size) rather than "anything that
    isn't a heading": a wrapped run-in header continuation can sit in the heading
    band and be followed by another (enum-prefixed) run-in header — neither body
    nor a recognized heading — and must not be emitted.
    """
    flat = _flatten(pages)
    n = len(flat)

    def in_band(size: float | None) -> bool:
        return size is not None and bands.heading_lo - _SIZE_EPS <= size <= bands.heading_hi + _SIZE_EPS

    def is_account_candidate(line) -> bool:
        return (
            line.line_number is not None
            and in_band(line.glyph_size)
            and _is_uppercase_heading(line.text)
            and not _ENUM_PREFIX.match(line.text)
            and not _is_parenthetical(line.text)
        )

    def continues_section_catchline(idx: int) -> bool:
        """True when flat[idx] is the wrapped continuation of a `SEC.` catchline.

        A long section catchline ("SEC. 5. ACTIONS TO PROMOTE FREEDOM OF THE PRESS
        / AND ASSEMBLY IN HAITI.") prints in the small-caps heading band and wraps
        onto a line that, read alone, is an uppercase heading in-band followed by
        body — a false `account`. It is not a header; it belongs to the SEC. line.
        Walk back over the wrapped run (contiguous in-band uppercase headings,
        blanks/parentheticals skipped): if it originates at a SEC. catchline, this
        line is a continuation and emits no anchor. The SEC. line itself is never a
        candidate (`_is_uppercase_heading` rejects SEC. headings), so only the
        continuation reaches here. Tree-independent; the structural cases are #54.

        Load-bearing invariant: the walk only reaches a SEC. through a contiguous
        run of in-band uppercase headings — any body line stops it (returns False).
        This relies on GPO appropriations sections carrying body prose right after
        the SEC. number ("SEC. 101. (a) The Secretary…"), so a real account heading
        is always separated from a preceding SEC. by that body and never reaches the
        SEC. The pathological `SEC. / AGENCY / ACCOUNT` with NO body between would
        false-skip the account, but that needs a catchline-style SEC. directly
        abutting an agency heading, which does not occur in the corpus (catchline
        wraps appear only in authorization bills, which have no accounts). Telling
        the two apart needs the leveled tree — deferred to #54. Period-based
        disambiguation does NOT work: appropriations SEC. terminal periods track
        abbreviation wrap points ("…''U.S."), not catchline completion.
        """
        for j in range(idx - 1, -1, -1):
            prev = flat[j][1]
            if not prev.text.strip() or _is_parenthetical(prev.text):
                continue
            if _SECTION_PATTERN.match(prev.text):
                return True
            if is_account_candidate(prev):
                continue  # an earlier wrapped line of the same catchline
            return False
        return False

    def is_body(line) -> bool:
        if not line.text.strip():
            return False
        if line.glyph_size is None:  # unattached non-blank line ⇒ treat as body
            return True
        return abs(line.glyph_size - bands.body) <= _SIZE_EPS

    def agency_before_leaf(leaf_idx: int) -> Anchor | None:
        """Join the contiguous heading-band run immediately preceding a leaf account
        into one carry-over agency anchor, or None when there is no such run.

        The run is the candidate lines directly above the leaf (blanks and
        parentheticals skipped), stopping at the first body line, recognized
        heading, or document edge. Catchline continuations are excluded so a wrapped
        SEC. catchline never leaks into an agency name. Lines are joined in document
        order; the anchor takes the run's first (topmost) line. The dangle guard
        drops a run that joins into a wrapped-account fragment (ends on a
        conjunction/preposition), which is not an agency.
        """
        run: list[tuple[int, int, str]] = []  # (page, line_number, text), nearest first
        j = leaf_idx - 1
        while j >= 0:
            page_no, prev = flat[j]
            if not prev.text.strip() or _is_parenthetical(prev.text):
                j -= 1
                continue
            if is_account_candidate(prev) and not continues_section_catchline(j):
                run.append((page_no, prev.line_number, prev.text.strip()))
                j -= 1
                continue
            break
        if not run:
            return None
        run.reverse()  # document order
        text = " ".join(t for _, _, t in run)
        if _dangles(text):
            return None
        first_page, first_line, _ = run[0]
        return Anchor(first_page, first_line, "agency", text)

    anchors: list[Anchor] = []
    for idx in range(n):
        page_number, line = flat[idx]
        if not is_account_candidate(line):
            continue
        if continues_section_catchline(idx):
            continue
        # Next meaningful line, skipping blanks and parenthetical qualifiers.
        nxt = None
        for j in range(idx + 1, n):
            cand = flat[j][1]
            if not cand.text.strip() or _is_parenthetical(cand.text):
                continue
            nxt = cand
            break
        if nxt is not None and _SECTION_PATTERN.match(nxt.text.strip()):
            anchors.append(Anchor(page_number, line.line_number, "grouping", line.text.strip()))
        elif nxt is None or is_body(nxt):
            anchors.append(Anchor(page_number, line.line_number, "account", line.text.strip()))
            agency = agency_before_leaf(idx)
            if agency is not None:
                anchors.append(agency)
        # else: candidate followed by another heading ⇒ part of a carry-over agency
        # run, emitted as one joined `agency` anchor at the leaf account above.
    return anchors


def _account_anchors_legacy(pages: list[Page]) -> list[Anchor]:
    """Legacy fallback: per page, walk back ≤3 line positions from a `For necessary
    expenses of` trigger to the nearest uppercase heading (parenthetical qualifiers
    skipped). Used when size bands aren't derivable or attachment coverage is too
    low. Per-page and 3-position to match the pre-#89 behavior exactly."""
    anchors: list[Anchor] = []
    for page in pages:
        lines = page.lines
        for idx, line in enumerate(lines):
            if line.line_number is None or not _FOR_NECESSARY_EXPENSES.match(line.text):
                continue
            for back in range(idx - 1, max(idx - 4, -1), -1):
                bline = lines[back]
                if bline.line_number is None or _is_parenthetical(bline.text):
                    continue
                if _is_uppercase_heading(bline.text):
                    candidate = Anchor(page.page_number, bline.line_number, "account", bline.text.strip())
                    if candidate not in anchors:
                        anchors.append(candidate)
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
    For an ACCOUNT anchor: `("TITLE I", "OPERATIONS AND SUPPORT")`, but when a
    carry-over agency (`MANAGEMENT DIRECTORATE`) precedes it within the same title,
    the account nests under it: `("TITLE I", "MANAGEMENT DIRECTORATE", "OPERATIONS
    AND SUPPORT")` (DeltaTrack#104). One agency carries over several accounts, so
    the account need not be immediately preceded by the agency anchor — the walk
    passes through intervening sibling accounts. It does NOT pass a grouping/section
    boundary: an account after `ADMINISTRATIVE PROVISIONS` is title-level, not
    agency-scoped.
    For an AGENCY or GROUPING anchor: `("TITLE I", "MANAGEMENT DIRECTORATE")`, or
    just `("MANAGEMENT DIRECTORATE",)` with no preceding TITLE.
    For a SECTION anchor: `("TITLE IV", "SEC. 406")` normally, but when a
    grouping header (`ADMINISTRATIVE PROVISIONS`) precedes the section within the
    same title, the section nests under it: `("TITLE I", "ADMINISTRATIVE
    PROVISIONS", "SEC. 101")` (DeltaTrack#103). Sections under a general-provisions
    title with no grouping header keep the 2-level chain.

    The major / department level (DeltaTrack#105) is not yet captured; once it lands
    the chain deepens (TITLE > major > agency > account) without changing this
    function's contract.
    """
    if anchor.kind in ("title", "preamble"):
        return (anchor.text,)
    # Resolve by value-equality .index(); relies on anchors being unique per
    # (page, line) — the size path emits one per line and the legacy path dedups,
    # so no two value-equal anchors exist. Keep that invariant if emitting more.
    try:
        idx = list(all_anchors).index(anchor)
    except ValueError:
        return (anchor.text,)
    # Walk back to the nearest preceding TITLE, capturing a grouping-header parent
    # (sections) or a carry-over agency parent (accounts) that falls between that
    # TITLE and the anchor. The walk stops at the TITLE, so a parent from an earlier
    # title is never reached. For an account, a grouping/section boundary ends the
    # agency's scope: `agency_blocked` stops capture there but the walk continues to
    # the TITLE so the chain still carries it.
    grouping: str | None = None
    agency: str | None = None
    agency_blocked = False
    for j in range(idx - 1, -1, -1):
        prev = all_anchors[j]
        if prev.kind == "title":
            parents = ((agency,) if agency else ()) + ((grouping,) if grouping else ())
            return (prev.text,) + parents + (anchor.text,)
        if anchor.kind == "section" and prev.kind == "grouping" and grouping is None:
            grouping = prev.text
        if anchor.kind == "account" and not agency_blocked:
            if prev.kind == "agency":
                agency = prev.text
                agency_blocked = True  # nearest agency only
            elif prev.kind in ("grouping", "section"):
                agency_blocked = True  # agency scope ended before this account
    parents = ((agency,) if agency else ()) + ((grouping,) if grouping else ())
    if parents:
        return parents + (anchor.text,)
    return (anchor.text,)
