"""Turn two PDF byte blobs into canonical diff JSON or standalone HTML.

This is the in-process wrap of the existing PDF pipeline — the exact sequence
``prototype/generate_samples.py`` uses for its PDF sample, with the inputs coming
from uploaded bytes instead of files on disk:

    extract_clean_pages()  (parsers.pdf_text)
    diff_pdfs()            (diff_pdf)
    pdf_full_text()        (parsers.pdf_text)   — JSON path only
    pdf_diff_to_canonical()(formatters.canonical) — JSON path
    pdf_diff_to_view()     (formatters.adapters) — HTML path
    format_diff_html()     (formatters.diff_html) — HTML path

No subprocess; no persistence. The temp files exist only long enough for
pypdfium2 to open them and are deleted before this function returns.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from diff_pdf import PdfDiff, diff_pdfs
from formatters.adapters import pdf_diff_to_view
from formatters.canonical import pdf_diff_to_canonical
from formatters.diff_html import format_diff_html
from parsers.pdf_text import Page, extract_clean_pages, pdf_full_text


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


def compare_pdfs(
    start_bytes: bytes,
    end_bytes: bytes,
    *,
    start_label: str = "Start version",
    end_label: str = "End version",
) -> dict:
    """Diff two PDF documents and return canonical diff JSON (schema v1.2)."""
    pdf_diff, old_pages, new_pages = _extract_and_diff(start_bytes, end_bytes)
    v1_text, v1_offsets = pdf_full_text(old_pages)
    v2_text, v2_offsets = pdf_full_text(new_pages)

    return pdf_diff_to_canonical(
        pdf_diff,
        bill_type="",
        bill_number="",
        congress="",
        v1_label=start_label,
        v2_label=end_label,
        full_text={"v1": v1_text, "v2": v2_text},
        line_offsets={"v1": v1_offsets, "v2": v2_offsets},
    )


def compare_pdfs_html(
    start_bytes: bytes,
    end_bytes: bytes,
    *,
    start_label: str = "Start version",
    end_label: str = "End version",
) -> str:
    """Diff two PDF documents and return a standalone HTML report."""
    pdf_diff, _, _ = _extract_and_diff(start_bytes, end_bytes)
    view = pdf_diff_to_view(
        pdf_diff,
        bill_type="",
        bill_number="",
        congress="",
        v1_label=start_label,
        v2_label=end_label,
    )
    return format_diff_html(view)
