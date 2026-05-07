"""PDF text extraction with the smallest set of primitives that fixture cases require."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

_LINE_NUMBER_PREFIX = re.compile(r"^\d{1,2} ", re.MULTILINE)


@dataclass(frozen=True)
class Page:
    page_number: int  # 1-based
    text: str


def strip_line_numbers(text: str) -> str:
    """Remove leading 1- or 2-digit line numbers (followed by a space) from each line."""
    return _LINE_NUMBER_PREFIX.sub("", text)


def extract_clean_pages(pdf_path: Path) -> list[Page]:
    with pdfplumber.open(pdf_path) as pdf:
        return [Page(i + 1, strip_line_numbers(page.extract_text() or "")) for i, page in enumerate(pdf.pages)]
