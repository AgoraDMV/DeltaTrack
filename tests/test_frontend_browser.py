"""Browser-level (Playwright) tests for the static front-end (#69).

These cover what TestClient can't: real browser runtime behavior. #41 was a
browser-only bug — a sample-report popup opened on page load (outside a user
gesture) was blocked, stranding the user on the upload form. Only a real
browser reproduces popup-block semantics.

Marked ``browser``; excluded from the default suite. Run with::

    uv run playwright install chromium   # one-time, downloads the browser
    uv run pytest -m browser

Skipped entirely if Playwright or its browser binary isn't available, so the
default ``-m "not browser"`` run never depends on them.
"""

from __future__ import annotations

import socket
import threading
from contextlib import closing

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

pytestmark = pytest.mark.browser


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_url():
    """Serve the real app on an ephemeral port for the duration of the module.

    A browser can't use Starlette's in-process TestClient, so we run uvicorn in
    a background thread and tear it down after. Importing here (not at module
    top) keeps collection cheap when the marker is deselected.
    """
    import uvicorn

    from server.app import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for the server to accept connections before handing the URL out.
    deadline_attempts = 100
    for _ in range(deadline_attempts):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                break
        threading.Event().wait(0.05)
    else:
        raise RuntimeError("uvicorn did not start in time")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def chromium():
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            yield b
            b.close()
    except Exception as exc:  # browser binary not installed, etc.
        pytest.skip(f"Chromium unavailable (run 'playwright install chromium'): {exc}")


def _render_report_with_toc() -> str:
    """A standalone page pairing the report's real stylesheet with a real TOC group.

    Pulls the renderer's embedded `<style>` from an actual rendered report (so the
    test tracks current CSS, not a committed artifact) and drops in the real
    `_build_toc` markup for one single-line title — making `.toc-group > summary`
    exactly one text line when laid out correctly. Built directly rather than
    through the full report so the full-bill gating (`full_text.v2`) isn't needed.
    """
    import re

    from diff_pdf import PdfDiff
    from formatters.canonical import pdf_diff_to_canonical, view_from_canonical
    from formatters.diff_html import _build_toc, format_diff_html

    canonical = pdf_diff_to_canonical(PdfDiff(hunks=()), bill_type="hr", bill_number=8752, congress=118)
    full_report = format_diff_html(view_from_canonical(canonical))
    style = re.search(r"<style>.*?</style>", full_report, re.DOTALL).group(0)
    toc = _build_toc([{"kind": "title", "label": "Title I"}])  # short, no descriptor → one line
    return (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>{style}</head>"
        f"<body><div class='sidebar'>{toc}</div></body></html>"
    )


def test_toc_group_caret_sits_on_header_line(chromium, tmp_path):
    """The full-bill TOC caret and its header share one line, not stacked (#52).

    Regression guard for the `.toc-group > summary` layout. With the pre-fix
    `display: list-item`, the `::before` caret took its own line and pushed the
    header down by ~one line-height; the flex fix keeps the header on the
    caret's row. We assert the header text begins within one line-height of the
    summary's top (i.e. on the first line), which fails on the stacked layout.
    """
    report = tmp_path / "toc_report.html"
    report.write_text(_render_report_with_toc(), encoding="utf-8")

    page = chromium.new_page(viewport={"width": 1280, "height": 900})
    page.goto(report.as_uri(), wait_until="domcontentloaded")

    metrics = page.evaluate(
        """() => {
            const sum = document.querySelector('.toc-group > summary');
            if (!sum) return null;
            const box = sum.getBoundingClientRect();
            // Range over the summary's own content (the <a>), excluding ::before,
            // gives where the header text actually starts.
            const r = document.createRange();
            r.selectNodeContents(sum);
            const textTop = r.getBoundingClientRect().top;
            const cs = getComputedStyle(sum);
            let lh = parseFloat(cs.lineHeight);
            if (Number.isNaN(lh)) lh = parseFloat(cs.fontSize) * 1.2;
            return {offset: textTop - box.top, lineHeight: lh};
        }"""
    )
    page.close()

    assert metrics is not None, "no .toc-group > summary rendered"
    # On the stacked (buggy) layout the header starts a full line below the
    # caret; on the fixed layout it starts at the summary's top padding.
    assert metrics["offset"] < metrics["lineHeight"], (
        f"TOC header starts {metrics['offset']:.1f}px below the summary top "
        f"(>= one line-height {metrics['lineHeight']:.1f}px): caret and header are stacked"
    )


def test_sample_report_opens_in_new_tab(live_url, chromium):
    """Clicking "View a sample report" opens the report in a new tab (#41).

    Pre-#41 this link routed through a page-load window.open that the browser
    blocked. The fix makes it a direct target=_blank link, so the click itself
    is the gesture that opens the tab. We assert a second page opens and shows
    the diff report — not that we're stranded on the upload form.
    """
    page = chromium.new_page()
    page.goto(live_url, wait_until="domcontentloaded")

    with page.context.expect_page() as new_page_info:
        page.get_by_role("link", name="View a sample report").click()
    report = new_page_info.value
    report.wait_for_load_state("domcontentloaded")

    # The new tab is the standalone diff report, not the upload page bouncing back.
    assert "example.html" in report.url
    assert "H.R. 8752" in report.title()

    # And the landing page shows no "pop-up blocked" / load error.
    assert page.locator("#upload-error").is_hidden()

    report.close()
    page.close()
