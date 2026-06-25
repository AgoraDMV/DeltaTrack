"""Tests for the static front-end served by server/app.py.

These guard the "View a sample report" path that broke in #41: the landing
page must link directly to a reachable sample document, and the static mount
must serve it. Skipped if fastapi isn't installed.

Scope / known gap: these assert routing and asset reachability, NOT browser
runtime behavior. The #41 root cause was a popup opened on page load (outside a
user gesture) being blocked by the browser — only a real browser (e.g.
Playwright) reproduces that. A Node/browser toolchain isn't worth it for one
static page today; if the web UI grows interactive JS, revisit a browser test.
"""

from __future__ import annotations

import pytest


def _client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from server.app import app

    return TestClient(app)


def test_landing_links_directly_to_sample_report():
    """The landing page links straight to the sample document (#41).

    The pre-#41 link routed through ``compare.html?example=1``, which opened the
    report via a page-load ``window.open`` that browsers blocked. The fix points
    the link at the standalone sample so a real click is the gesture that opens
    it. Guard both halves: the direct link is present, the broken one is gone.
    """
    body = _client().get("/").text
    assert 'href="sample/example.html"' in body
    assert 'target="_blank"' in body
    assert "example=1" not in body


def test_sample_report_is_served():
    """The sample document the landing page links to is reachable and real."""
    resp = _client().get("/sample/example.html")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    # A real diff report, not an empty/placeholder file.
    assert "<!DOCTYPE html>" in resp.text[:200]
    assert len(resp.content) > 10_000
