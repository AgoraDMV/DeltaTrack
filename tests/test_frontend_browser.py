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
