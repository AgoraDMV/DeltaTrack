"""Tests for the web service's PDF compare wrap (server/).

Two layers:
  - Fast API-guard tests (no real diffing) — validate upload rejection paths
    via FastAPI's TestClient. Skipped if fastapi isn't installed.
  - A slow end-to-end test that runs the real engine on the committed HR4366
    sample PDFs and validates the result against the canonical JSON schema.
    Skipped if the sample PDFs aren't present (they're large / not in CI).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BILL_DIR = ROOT / "bills" / "118-hr-4366"
SCHEMA = ROOT / "prototype" / "sample-diffs" / "schema.json"


# ---------- Fast API-guard tests -------------------------------------------


def _client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from server.app import app

    return TestClient(app)


def test_compare_rejects_non_pdf():
    # start_pdf lacks the %PDF magic → 415 before any diffing happens.
    resp = _client().post(
        "/api/compare",
        files={
            "start_pdf": ("a.pdf", b"not a pdf at all", "application/pdf"),
            "end_pdf": ("b.pdf", b"%PDF-1.4 whatever", "application/pdf"),
        },
    )
    assert resp.status_code == 415


def test_compare_rejects_empty_file():
    resp = _client().post(
        "/api/compare",
        files={
            "start_pdf": ("a.pdf", b"", "application/pdf"),
            "end_pdf": ("b.pdf", b"%PDF-1.4 whatever", "application/pdf"),
        },
    )
    assert resp.status_code == 400


# ---------- Slow end-to-end engine test ------------------------------------


@pytest.mark.slow
def test_compare_pdfs_returns_valid_canonical():
    start = BILL_DIR / "1_reported-in-house.pdf"
    end = BILL_DIR / "2_engrossed-in-house.pdf"
    if not start.exists() or not end.exists():
        pytest.skip("sample bill PDFs not present (bills/118-hr-4366/)")

    from server.pdf_compare import compare_pdfs

    canonical = compare_pdfs(
        start.read_bytes(),
        end.read_bytes(),
        start_label="Reported in House",
        end_label="Engrossed in House",
    )

    assert canonical["schema_version"]
    assert canonical["versions"]["v1"]["label"] == "Reported in House"
    assert canonical["versions"]["v2"]["label"] == "Engrossed in House"
    assert canonical["versions"]["v1"]["source"] == "pdf"
    assert isinstance(canonical["changes"], list) and canonical["changes"]
    assert canonical["full_text"]["v1"] and canonical["full_text"]["v2"]

    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text())
    jsonschema.validate(canonical, schema)


@pytest.mark.slow
def test_compare_pdfs_html_returns_standalone_report():
    start = BILL_DIR / "1_reported-in-house.pdf"
    end = BILL_DIR / "2_engrossed-in-house.pdf"
    if not start.exists() or not end.exists():
        pytest.skip("sample bill PDFs not present (bills/118-hr-4366/)")

    from server.pdf_compare import compare_pdfs_html

    html = compare_pdfs_html(
        start.read_bytes(),
        end.read_bytes(),
        start_label="Reported in House",
        end_label="Engrossed in House",
    )

    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "change-card" in html
    assert "financial-table" in html
    assert "Reported in House" in html
    assert "Engrossed in House" in html


@pytest.mark.slow
def test_compare_api_returns_html():
    start = BILL_DIR / "1_reported-in-house.pdf"
    end = BILL_DIR / "2_engrossed-in-house.pdf"
    if not start.exists() or not end.exists():
        pytest.skip("sample bill PDFs not present (bills/118-hr-4366/)")

    resp = _client().post(
        "/api/compare?output=html",
        files={
            "start_pdf": ("start.pdf", start.read_bytes(), "application/pdf"),
            "end_pdf": ("end.pdf", end.read_bytes(), "application/pdf"),
        },
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "change-card" in resp.text
