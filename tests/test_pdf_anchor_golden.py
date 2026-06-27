"""Golden anchor-snapshot guard + precision-harness self-test (DeltaTrack#89).

The golden snapshots pin the full ordered anchor list per fixture bill. They are
the deterministic regression guard the tolerant diff-recall suite can't provide:
they catch BOTH over-emission (spurious accounts) and under-emission (dropped
accounts) when the size-detection swap lands. Regenerate ONLY when a change is
intended, and prove the delta with the set-diff assertion in the swap commit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parsers.pdf_anchors import extract_anchors
from parsers.pdf_text import extract_clean_pages

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / "test_data" / "pdf" / "anchors_golden"

# (golden name, pdf path) — approps (House), non-approps (House), approps (Senate).
FIXTURES = {
    "118-hr-8752": ROOT / "bills" / "118-hr-8752" / "1_reported-in-house.pdf",
    "118-hr-8282": ROOT / "bills" / "118-hr-8282" / "1_introduced-in-house.pdf",
    "118-s-4795": ROOT / "test_data" / "BILLS-118s4795rs.pdf",
}


def _current_anchors(pdf_path: Path) -> list[list]:
    anchors = extract_anchors(extract_clean_pages(pdf_path))
    return [[a.kind, a.text, a.page_number, a.line_number] for a in anchors]


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_anchors_match_golden(name: str):
    pdf_path = FIXTURES[name]
    if not pdf_path.exists():
        pytest.skip(f"{name} PDF not present")
    golden = json.loads((GOLDEN_DIR / f"{name}.json").read_text())
    # JSON has no tuples; compare as lists.
    assert _current_anchors(pdf_path) == golden


class TestPrecisionHarnessOracle:
    """Validate the harness computation (it is the oracle the swap is judged by)."""

    def test_measure_arithmetic_and_stable_xml_counts(self):
        pdf = FIXTURES["118-hr-8752"]
        xml = ROOT / "bills" / "118-hr-8752" / "1_reported-in-house.xml"
        if not pdf.exists():
            pytest.skip("HR 8752 PDF not present")
        from scripts.heading_precision import measure

        m = measure(pdf, xml)
        # XML-side counts are stable (independent of PDF detection method).
        assert m["xml_small"] == 35
        # count_ratio is accounts / (small + intermediate); verify the arithmetic.
        denom = m["xml_small"] + m["xml_intermediate"]
        assert m["count_ratio"] == pytest.approx(m["pdf_accounts"] / denom)
        # full margin-number attachment on this clean working-stage bill.
        assert m["coverage"] == 1.0
        # vocabulary precision/recall are bounded ratios.
        assert 0.0 <= m["vocab_precision"] <= 1.0
        assert 0.0 <= m["vocab_recall"] <= 1.0
