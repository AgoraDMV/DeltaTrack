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


def _render_grouped_report() -> str:
    """A full standalone report whose cards group under tree nodes (#172).

    Hand-built canonical (the consumed contract) with a v2 tree and change
    spans in one offset space, so the own-span join is live: one financial
    change directly under TITLE I, two non-financial changes under its
    SALARIES / OPERATIONS accounts. Exercises the real _JS.
    """
    from formatters.canonical import view_from_canonical
    from formatters.diff_html import format_diff_html

    def node(label, level, span, children=()):
        return {
            "label": label,
            "level": level,
            "own_amounts": [],
            "full_text_span": span,
            "children": list(children),
        }

    def change(i, start, end, amounts):
        return {
            "id": f"c{i}",
            "change_type": "modified",
            "section_number": "",
            "path": {"v1": ["TITLE I"], "v2": ["TITLE I"]},
            "location": None,
            "anchor_resolution": "resolved",
            # The appended token survives word_diff as ONE contiguous <ins>
            # text node, so the find bar (which scans text nodes) can hit it.
            "text": {"old": f"shared {i}", "new": f"shared {i} added{i}"},
            "amounts": amounts,
            "move": None,
            "full_text_span": {"v1": None, "v2": {"start": start, "end": end}},
        }

    tree_v2 = [
        node(
            "TITLE I",
            "title",
            {"start": 0, "end": 7},
            [
                node("SALARIES", "account", {"start": 10, "end": 50}),
                node("OPERATIONS", "account", {"start": 60, "end": 100}),
            ],
        ),
    ]
    canonical = {
        "schema_version": "1.3",
        "bill": {"type": "hr", "number": 1, "congress": 119},
        "versions": {
            "v1": {"label": "v1", "version_number": 1, "source": "xml"},
            "v2": {"label": "v2", "version_number": 2, "source": "xml"},
        },
        "summary": {"added": 0, "removed": 0, "modified": 3, "moved": 0},
        "changes": [
            change(0, 2, 5, [{"old": 100, "new": 200}]),  # TITLE I direct, financial
            change(1, 20, 30, []),  # SALARIES
            change(2, 70, 80, []),  # OPERATIONS
        ],
        "full_text": {"v1": "x" * 120, "v2": "TITLE I\n" + "y" * 112},
        "tree": {"v1": [], "v2": tree_v2},
    }
    return format_diff_html(view_from_canonical(canonical), canonical=canonical)


def test_filtering_hides_empty_card_groups_and_updates_nav_counts(chromium, tmp_path):
    """Financial filter empties the account groups: their card-group headings
    hide, and the TITLE I nav-group count recounts to the visible subtree (#172).
    Browser-level because the contract lives in applyFilters' runtime behavior,
    which string-level _JS assertions can't prove."""
    report = tmp_path / "grouped.html"
    report.write_text(_render_grouped_report(), encoding="utf-8")
    page = chromium.new_page(viewport={"width": 1280, "height": 900})
    page.goto(report.as_uri(), wait_until="domcontentloaded")

    groups = page.locator(".card-group")
    assert groups.count() == 3  # TITLE I + two nested accounts
    title_count = page.locator(".nav-group__count").first
    assert title_count.inner_text() == "(3)"

    page.locator('input[name="change-filter"][value="financial"]').check()
    # The two account groups hold only non-financial cards -> hidden; the
    # TITLE I group keeps its direct financial card and its count recounts.
    assert page.locator(".card-group:visible").count() == 1
    assert title_count.inner_text() == "(1)"
    assert page.locator("#change-0").is_visible()
    assert page.locator("#change-1").is_hidden()
    page.close()


def test_prev_next_steps_into_nested_groups_and_reveals_collapsed(chromium, tmp_path):
    """Prev/next reaches cards inside nested open groups with a true counter,
    and stepping to a card inside a user-collapsed group re-opens the group
    rather than scrolling to an invisible card; likewise a sidebar link into a
    collapsed group (#172). (Modern Chromium keeps closed-details content in
    the layout tree — content-visibility, not display:none — so collapsed
    cards stay in the target set; revealCard makes reaching them work.)"""
    report = tmp_path / "grouped_nav.html"
    report.write_text(_render_grouped_report(), encoding="utf-8")
    page = chromium.new_page(viewport={"width": 1280, "height": 900})
    page.goto(report.as_uri(), wait_until="domcontentloaded")

    counter = page.locator("#nav-counter")
    assert counter.inner_text() == "0 / 3"
    nxt = page.locator("#btn-next")
    for expected in ("1 / 3", "2 / 3", "3 / 3"):
        nxt.click()
        assert counter.inner_text() == expected

    # Collapse the SALARIES group, then step back to the card inside it:
    # revealCard must re-open the group so the card is actually shown.
    salaries = page.locator(".card-group .card-group").first
    salaries.locator("> summary").click()
    assert salaries.evaluate("el => el.open") is False
    page.locator("#btn-prev").click()
    assert salaries.evaluate("el => el.open") is True
    assert page.locator("#change-1").is_visible()

    # Same via a sidebar link into a re-collapsed group (fragment navigation
    # into a closed <details> doesn't auto-expand in every browser). Collapse
    # via JS here: after the scroll the summary can sit under the sticky
    # header, where a UI click never becomes actionable (the click-collapse
    # path is already exercised above).
    salaries.evaluate("el => el.open = false")
    assert salaries.evaluate("el => el.open") is False
    # Sidebar nav groups are collapsed by default; expand down to the link.
    page.locator(".sidebar .nav-group > summary").first.click()
    page.locator(".sidebar .nav-group .nav-group > summary").first.click()
    page.locator('.sidebar a[href="#change-1"]').click()
    assert salaries.evaluate("el => el.open") is True
    assert page.locator("#change-1").is_visible()

    # Find-bar stepping is the third navigation mechanism: a hit inside a
    # collapsed group must re-open it too ("added1" only occurs in change-1).
    # runFind is debounced 150ms on input, then lands on the first hit itself;
    # wait for the mark rather than racing the debounce.
    salaries.evaluate("el => el.open = false")
    page.locator("#find-input").fill("added1")
    page.locator("mark.find-hit--current").wait_for(state="attached")
    assert salaries.evaluate("el => el.open") is True
    assert page.locator("mark.find-hit--current").is_visible()
    page.close()


def test_explicit_navigation_syncs_the_prev_next_counter(chromium, tmp_path):
    """Jumping to a card by sidebar link, Financial Summary row, or a click on
    the card itself moves the counter to that card, so the arrows step from
    what the reader is looking at rather than from where they last were (#185).

    Browser-level because the contract is the runtime relationship between the
    click handlers and navTargets' filter-aware target list.
    """
    report = tmp_path / "nav_sync.html"
    report.write_text(_render_grouped_report(), encoding="utf-8")
    page = chromium.new_page(viewport={"width": 1280, "height": 900})
    page.goto(report.as_uri(), wait_until="domcontentloaded")

    counter = page.locator("#nav-counter")
    assert counter.inner_text() == "0 / 3"

    # Sidebar link: counter lands on the linked card, and -> steps past it.
    page.locator(".sidebar .nav-group > summary").first.click()
    page.locator(".sidebar .nav-group .nav-group > summary").first.click()
    page.locator('.sidebar a[href="#change-1"]').click()
    assert counter.inner_text() == "2 / 3"
    page.locator("#btn-next").click()
    assert counter.inner_text() == "3 / 3"
    assert page.locator("#change-2").is_visible()

    # Clicking the card body itself (the free-scroll reading flow).
    page.locator("#change-2 .change-header").click()
    assert counter.inner_text() == "3 / 3"

    # Financial Summary row link (change-0 is the only card carrying amounts).
    page.locator('.financial-table a[href="#change-0"]').click()
    assert counter.inner_text() == "1 / 3"

    # Filter-aware: with the financial filter on, change-0 is the only visible
    # target, so a jump to it reads 1 / 1 rather than its unfiltered position.
    page.locator('input[name="change-filter"][value="financial"]').check()
    assert counter.inner_text() == "0 / 1"
    page.locator('.financial-table a[href="#change-0"]').click()
    assert counter.inner_text() == "1 / 1"
    page.close()


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
