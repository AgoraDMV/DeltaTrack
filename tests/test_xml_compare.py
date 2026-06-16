"""Tests for the web service's XML compare wrap (server/xml_compare.py).

Mirrors test_pdf_compare's slow end-to-end layer: runs the real engine on the
committed HR4366 sample XMLs and validates the result. Skipped if the sample
XMLs aren't present (they're gitignored / not in CI).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BILL_DIR = ROOT / "bills" / "118-hr-4366"
SCHEMA = ROOT / "prototype" / "sample-diffs" / "schema.json"


@pytest.mark.slow
def test_compare_xml_returns_valid_canonical():
    start = BILL_DIR / "1_reported-in-house.xml"
    end = BILL_DIR / "2_engrossed-in-house.xml"
    if not start.exists() or not end.exists():
        pytest.skip("sample bill XMLs not present (bills/118-hr-4366/)")

    from server.xml_compare import compare_xml

    canonical = compare_xml(
        start.read_bytes(),
        end.read_bytes(),
        start_label="Reported in House",
        end_label="Engrossed in House",
    )

    assert canonical["schema_version"]
    assert canonical["versions"]["v1"]["label"] == "Reported in House"
    assert canonical["versions"]["v2"]["label"] == "Engrossed in House"
    assert canonical["versions"]["v1"]["source"] == "xml"
    assert isinstance(canonical["changes"], list) and canonical["changes"]
    assert canonical["full_text"]["v1"] and canonical["full_text"]["v2"]

    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text())
    jsonschema.validate(canonical, schema)


@pytest.mark.slow
def test_compare_xml_html_gutterless_fullbill():
    start = BILL_DIR / "1_reported-in-house.xml"
    end = BILL_DIR / "2_engrossed-in-house.xml"
    if not start.exists() or not end.exists():
        pytest.skip("sample bill XMLs not present (bills/118-hr-4366/)")

    from server.xml_compare import compare_xml_html

    html = compare_xml_html(
        start.read_bytes(),
        end.read_bytes(),
        start_label="Reported in House",
        end_label="Engrossed in House",
    )

    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "change-card" in html
    # XML full-bill view is gutterless: no PDF line-number column, no page markers.
    assert "full-bill--no-gutter" in html
    assert '<span class="fb-gutter">' not in html
    # Full bill text survives intact (the 7-char-gutter truncation bug is gone).
    assert "DEPARTMENT OF DEFENSE" in html
    assert '">ENT OF DEFENSE' not in html
