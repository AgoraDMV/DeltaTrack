"""Shared discovery + caching for corpus-wide PDF tests.

Both the amount-recall cross-check (test_pdf_xml_amount_recall.py) and the diff
smoke suite (test_pdf_corpus_smoke.py) iterate over the bill PDFs. `cached_pages`
extracts each PDF at most once per session so the two suites don't re-parse the
same (often 1000+ page) PDFs twice.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pdfplumber

from parsers.pdf_text import Page, extract_clean_pages

BILLS_DIR = Path(__file__).parent.parent / "bills"


@lru_cache(maxsize=None)
def cached_pages(pdf_path: Path) -> list[Page]:
    """Extract and cache cleaned pages for a PDF (shared across PDF test modules)."""
    return extract_clean_pages(pdf_path)


@lru_cache(maxsize=None)
def page_count(pdf_path: Path) -> int:
    """Page count without text extraction (parses the page tree only)."""
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def full_text(pages: list[Page]) -> str:
    """Join every cleaned line across all pages into one string."""
    return "\n".join(page.text for page in pages)


def dual_format_versions() -> list[tuple[str, Path, Path]]:
    """(bill_name, xml_path, pdf_path) for every version present in both formats."""
    out: list[tuple[str, Path, Path]] = []
    for bill_dir in sorted(BILLS_DIR.iterdir()):
        if not bill_dir.is_dir():
            continue
        for xml in sorted(bill_dir.glob("*.xml")):
            pdf = xml.with_suffix(".pdf")
            if pdf.exists():
                out.append((bill_dir.name, xml, pdf))
    return out


def adjacent_pdf_pairs() -> list[tuple[str, Path, Path]]:
    """(bill_name, old_pdf, new_pdf) for each adjacent version pair within a bill."""
    out: list[tuple[str, Path, Path]] = []
    for bill_dir in sorted(BILLS_DIR.iterdir()):
        if not bill_dir.is_dir():
            continue
        pdfs = sorted(bill_dir.glob("*.pdf"))
        for i in range(len(pdfs) - 1):
            out.append((bill_dir.name, pdfs[i], pdfs[i + 1]))
    return out
