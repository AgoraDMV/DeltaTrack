"""Turn two PDF byte blobs into canonical diff JSON or standalone HTML.

This is the in-process wrap of the existing PDF pipeline, with the inputs coming
from uploaded bytes instead of files on disk:

    extract_clean_pages()  (parsers.pdf_text)
    diff_pdfs()            (diff_pdf)
    pdf_full_text()        (parsers.pdf_text)   — both paths (full text + offsets)
    pdf_diff_to_canonical()(formatters.canonical) — both paths (JSON out / embedded)
    view_from_canonical()  (formatters.canonical) — canonical → DiffView (HTML path)
    format_diff_html()     (formatters.diff_html) — HTML path (view + canonical)

No subprocess; no persistence. The temp files exist only long enough for
pypdfium2 to open them and are deleted before this function returns.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from diff_pdf import PdfDiff, diff_pdfs
from formatters.canonical import pdf_diff_to_canonical, view_from_canonical
from formatters.diff_html import format_diff_html
from parsers.pdf_anchors import Anchor
from parsers.pdf_text import Page, extract_clean_pages, pdf_full_text, pdf_full_text_print


def _extract_and_diff(
    start_bytes: bytes,
    end_bytes: bytes,
) -> tuple[PdfDiff, list[Page], list[Page]]:
    """Parse both PDFs, diff them, return pages for downstream serializers.

    Temp files are deleted before return; callers work on in-memory Page lists.
    """
    with tempfile.TemporaryDirectory(prefix="deltatrack-") as tmp:
        start_path = Path(tmp) / "start.pdf"
        end_path = Path(tmp) / "end.pdf"
        start_path.write_bytes(start_bytes)
        end_path.write_bytes(end_bytes)

        old_pages = extract_clean_pages(start_path)
        new_pages = extract_clean_pages(end_path)
    return diff_pdfs(old_pages, new_pages), old_pages, new_pages


_CONGRESS_RE = re.compile(r"(\d{1,3})(?:ST|ND|RD|TH)\s+CONGRESS", re.IGNORECASE)


def _derive_congress(pages: list[Page]) -> str:
    """Pull the Congress number from the cover (e.g. "118TH CONGRESS" → "118").

    GPO PDFs carry no metadata, so the number is read from the front matter;
    returns "" when not found (the renderer then omits the "th Congress" suffix).
    """
    if not pages:
        return ""
    head = "\n".join(line.text for line in pages[0].lines[:10])
    m = _CONGRESS_RE.search(head)
    return m.group(1) if m else ""


def _build_canonical(
    pdf_diff: PdfDiff,
    old_pages: list[Page],
    new_pages: list[Page],
    start_label: str,
    end_label: str,
    *,
    congress: str = "",
    printed: bool = False,
) -> dict:
    """Canonical diff JSON (schema v1.2) with full text + per-change spans.

    Shared by both entry points: it is the JSON response on the JSON path and
    the embedded ``diff.json`` (driving export) on the HTML path. With
    ``printed=True`` the full text and spans use the print-faithful rendering
    (`pdf_full_text_print`) instead of the merged whole-word text — that variant
    drives only the on-screen full-bill view, not the embed/export.
    """
    render = pdf_full_text_print if printed else pdf_full_text
    v1_text, v1_offsets = render(old_pages)
    v2_text, v2_offsets = render(new_pages)
    return pdf_diff_to_canonical(
        pdf_diff,
        bill_type="",
        bill_number="",
        congress=congress,
        v1_label=start_label,
        v2_label=end_label,
        full_text={"v1": v1_text, "v2": v2_text},
        line_offsets={"v1": v1_offsets, "v2": v2_offsets},
    )


_BILL_DESIGNATOR = re.compile(
    r"\b(H\.\s?R\.|S\.\s?J\.\s?RES\.|H\.\s?J\.\s?RES\.|S\.\s?CON\.\s?RES\.|H\.\s?CON\.\s?RES\."
    r"|S\.\s?RES\.|H\.\s?RES\.|S\.)\s?(\d{1,5})\b"
)


def _derive_bill_title(canonical: dict) -> str:
    """Best-effort report heading from the document's opening text.

    Pulls the chamber designator (e.g. "H.R. 4366") and the long title that
    follows "AN ACT" / "A BILL". Returns "" when neither is found (the renderer
    then falls back to a generic heading). This parses GPO front matter
    heuristically and is not yet validated across bill types — see the
    deep-data-testing follow-up.
    """
    full_text = canonical.get("full_text") or {}
    text = full_text.get("v2") or full_text.get("v1") or ""
    head = " ".join(line.strip() for line in text[:1500].splitlines() if line.strip())

    designator = ""
    m = _BILL_DESIGNATOR.search(head)
    if m:
        designator = f"{m.group(1).replace(' ', '')} {m.group(2)}"

    title = ""
    m2 = re.search(r"\bAN ACT\b\s+(.+?\bpurposes\.)", head, re.IGNORECASE) or re.search(
        r"\bA BILL\b\s+(.+?\bpurposes\.)", head, re.IGNORECASE
    )
    if m2:
        title = re.sub(r"\s+", " ", m2.group(1)).strip()
        if len(title) > 140:
            title = title[:137].rstrip() + "…"

    if designator and title:
        return f"{designator} — {title}"
    return designator or title


def compare_pdfs(
    start_bytes: bytes,
    end_bytes: bytes,
    *,
    start_label: str = "Start version",
    end_label: str = "End version",
) -> dict:
    """Diff two PDF documents and return canonical diff JSON (schema v1.2)."""
    pdf_diff, old_pages, new_pages = _extract_and_diff(start_bytes, end_bytes)
    congress = _derive_congress(new_pages)
    return _build_canonical(pdf_diff, old_pages, new_pages, start_label, end_label, congress=congress)


def compare_pdfs_html(
    start_bytes: bytes,
    end_bytes: bytes,
    *,
    start_label: str = "Start version",
    end_label: str = "End version",
) -> str:
    """Diff two PDF documents and return a standalone HTML report.

    The canonical dict is computed and handed to the renderer so the report can
    carry the full-bill view and an embedded ``diff.json`` for export.
    """
    pdf_diff, old_pages, new_pages = _extract_and_diff(start_bytes, end_bytes)
    congress = _derive_congress(new_pages)
    canonical = _build_canonical(pdf_diff, old_pages, new_pages, start_label, end_label, congress=congress)
    # Per-change card text comes from the hunks, so it is identical regardless of the
    # printed flag; derive the view from the (non-printed) canonical for consistency
    # with the embedded diff.json.
    view = view_from_canonical(canonical)
    display_canonical = _build_canonical(
        pdf_diff, old_pages, new_pages, start_label, end_label, congress=congress, printed=True
    )
    title = _derive_bill_title(canonical)
    sections = _section_nav(pdf_diff, new_pages)
    return format_diff_html(
        view, canonical=canonical, display_canonical=display_canonical, title=title, sections=sections
    )


def _title_descriptor(new_pages: list[Page], anchor: Anchor) -> str:
    """The heading printed right below a TITLE line (e.g. "DEPARTMENT OF DEFENSE"),
    which names the otherwise bare "TITLE I". "" when the next line isn't an
    uppercase heading (so we never pull body prose into the label)."""
    page = next((p for p in new_pages if p.page_number == anchor.page_number), None)
    if page is None:
        return ""
    idx = next((i for i, ln in enumerate(page.lines) if ln.line_number == anchor.line_number), None)
    if idx is None or idx + 1 >= len(page.lines):
        return ""
    nxt = page.lines[idx + 1].text.strip()
    return nxt if nxt and nxt == nxt.upper() and not nxt.startswith("SEC.") else ""


def _section_nav(pdf_diff: PdfDiff, new_pages: list[Page]) -> list[dict]:
    """Section-jump list for the full-bill view's TOC.

    Maps each v2 anchor (TITLE / SEC. / account heading) to its char offset in
    the print-faithful display text, so the renderer can id the matching row and
    the sidebar can link to it. `pdf_full_text_print`'s offsets are keyed by the
    same (page, merged-line) coordinates the anchors use; unresolved anchors are
    skipped. TITLE anchors carry a `descriptor` (the heading below them) so the
    bare "TITLE I" can be labelled.
    """
    _, offsets = pdf_full_text_print(new_pages)
    sections: list[dict] = []
    for a in pdf_diff.v2_anchors:
        rng = offsets.get((a.page_number, a.line_number))
        if rng is None:
            continue
        entry = {"label": a.text, "kind": a.kind, "start": rng[0]}
        if a.kind == "title":
            entry["descriptor"] = _title_descriptor(new_pages, a)
        sections.append(entry)
    return sections
