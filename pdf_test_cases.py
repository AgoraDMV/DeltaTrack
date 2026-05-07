"""Parser for `test_data/pdf/<bill>-changes.md` test-case fixtures.

The markdown source of truth is human-edited and contains, for each
change between two PDF bill versions: a heading-style hierarchy path,
a change type, V1/V2 page+line locations, the verbatim text in each
version, an expected diff description, and extractor notes. This module
turns each `## Case N — …` block into a `PdfTestCase` for parametrized
tests to consume.

Default fixture: `test_data/pdf/118hr8752-changes.md` (HR 8752 v1→v2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FIXTURE = Path(__file__).parent / "test_data" / "pdf" / "118hr8752-changes.md"

Location = tuple[int, int, int, int]

_CASE_HEADING = re.compile(r"^## Case (\d+) — (.+)$", re.MULTILINE)
_TYPE_LINE = re.compile(r"^\*\*Type:\*\*\s+(\w+)", re.MULTILINE)
_V1_LOCATION_LINE = re.compile(r"^\*\*V1 location:\*\*\s+(.+?)\s*$", re.MULTILINE)
_V2_LOCATION_LINE = re.compile(r"^\*\*V2 location:\*\*\s+(.+?)\s*$", re.MULTILINE)
_LOCATION_RANGE = re.compile(r"p\.(\d+)\s+L(\d+)\s*[–-]\s*p\.(\d+)\s+L(\d+)")
_V1_TEXT_BLOCK = re.compile(r"\*\*V1 text:\*\*\s*\n```\n(.*?)\n```", re.DOTALL)
_V2_TEXT_BLOCK = re.compile(r"\*\*V2 text:\*\*\s*\n```\n(.*?)\n```", re.DOTALL)
_PLACEHOLDER_TEXT = re.compile(r"^\(none\s+[—-]\s+(added|removed) in v2\)$")
_EXPECTED_BLOCK = re.compile(
    r"\*\*Expected diff output:\*\*\s*\n(.*?)(?=\n\*\*Extraction notes:\*\*|\n---|\Z)",
    re.DOTALL,
)
_EXPECTED_FIELD = re.compile(
    r"^- (Anchor|What changed|Net)[^:]*:\s*(.*?)(?=\n- (?:Change type|Anchor|What changed|Net)[^:]*:|\Z)",
    re.DOTALL | re.MULTILINE,
)
_EXTRACTION_BLOCK = re.compile(
    r"\*\*Extraction notes:\*\*\s*\n(.*?)(?=\n---|\Z)",
    re.DOTALL,
)


@dataclass(frozen=True)
class PdfTestCase:
    number: int
    title: str
    change_type: str
    v1_location: Location | None
    v2_location: Location | None
    v1_text: str
    v2_text: str
    expected_anchor: str
    expected_what_changed: str
    expected_net: str | None
    extraction_notes: str


def load_cases(path: Path = DEFAULT_FIXTURE) -> list[PdfTestCase]:
    """Parse a PDF-diff fixture markdown file into PdfTestCase objects.

    Cases are returned in source order. Raises ValueError if any required
    field is missing or malformed; a fixture should never silently lose
    data.
    """
    text = path.read_text()
    headings = list(_CASE_HEADING.finditer(text))
    cases = []
    for i, m in enumerate(headings):
        body_start = m.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[body_start:body_end]
        cases.append(
            PdfTestCase(
                number=int(m.group(1)),
                title=m.group(2).strip(),
                change_type=_parse_type(body),
                v1_location=_parse_location(body, _V1_LOCATION_LINE),
                v2_location=_parse_location(body, _V2_LOCATION_LINE),
                v1_text=_parse_text(body, _V1_TEXT_BLOCK),
                v2_text=_parse_text(body, _V2_TEXT_BLOCK),
                **_parse_expected(body),
                extraction_notes=_parse_extraction_notes(body),
            )
        )
    return cases


def _parse_type(body: str) -> str:
    m = _TYPE_LINE.search(body)
    if not m:
        raise ValueError("missing **Type:** line")
    return m.group(1).lower().strip()


def _parse_location(body: str, line_regex: re.Pattern[str]) -> Location | None:
    m = line_regex.search(body)
    if not m:
        raise ValueError(f"missing location line for pattern {line_regex.pattern}")
    value = m.group(1).strip()
    if value.startswith("N/A"):
        return None
    range_match = _LOCATION_RANGE.search(value)
    if not range_match:
        raise ValueError(f"unparseable location: {value!r}")
    return tuple(int(g) for g in range_match.groups())  # type: ignore[return-value]


def _parse_text(body: str, block_regex: re.Pattern[str]) -> str:
    m = block_regex.search(body)
    if not m:
        raise ValueError(f"missing text block for pattern {block_regex.pattern}")
    raw = m.group(1).strip()
    if _PLACEHOLDER_TEXT.match(raw):
        return ""
    return raw


def _parse_extraction_notes(body: str) -> str:
    m = _EXTRACTION_BLOCK.search(body)
    return m.group(1).strip() if m else ""


def _parse_expected(body: str) -> dict:
    m = _EXPECTED_BLOCK.search(body)
    if not m:
        raise ValueError("missing **Expected diff output:** block")
    block = m.group(1)
    fields = {label: value.strip() for label, value in _EXPECTED_FIELD.findall(block)}
    return {
        "expected_anchor": fields.get("Anchor", ""),
        "expected_what_changed": fields.get("What changed", ""),
        "expected_net": fields.get("Net"),
    }
