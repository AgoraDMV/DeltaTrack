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

    from web.app import app

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
    `_build_toc_from_tree` markup for one single-line title — making
    `.toc-group > summary` exactly one text line when laid out correctly. Built
    directly rather than through the full report so the full-bill gating
    (`full_text.v2`) isn't needed.
    """
    import re

    from deltatrack.diff_pdf import PdfDiff
    from deltatrack.formatters.canonical import pdf_diff_to_canonical, view_from_canonical
    from deltatrack.formatters.diff_html import _build_toc_from_tree, format_diff_html

    canonical = pdf_diff_to_canonical(PdfDiff(hunks=()), bill_type="hr", bill_number=8752, congress=118)
    full_report = format_diff_html(view_from_canonical(canonical))
    style = re.search(r"<style>.*?</style>", full_report, re.DOTALL).group(0)
    # A labeled parent with one labeled child is the shape that renders a
    # <details class="toc-group"> toggle; a childless node renders a plain leaf.
    full_text = "Title I\nSEC. 101."
    tree = [
        {
            "label": "Title I",
            "full_text_span": {"start": 0, "end": 7},
            "children": [{"label": "SEC. 101.", "full_text_span": {"start": 8, "end": 17}, "children": []}],
        }
    ]
    toc = _build_toc_from_tree(tree, full_text)
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
    from deltatrack.formatters.canonical import view_from_canonical
    from deltatrack.formatters.diff_html import format_diff_html

    def node(label, level, span, children=()):
        return {
            "label": label,
            "level": level,
            "own_amounts": [],
            "full_text_span": span,
            "children": list(children),
        }

    def change(i, start, end, amount_entries):
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
            "amount_entries": amount_entries,
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
        "schema_version": "2.0",
        "bill": {"type": "hr", "number": 1, "congress": 119},
        "versions": {
            "v1": {"label": "v1", "version_number": 1, "source": "xml"},
            "v2": {"label": "v2", "version_number": 2, "source": "xml"},
        },
        "summary": {"added": 0, "removed": 0, "modified": 3, "moved": 0},
        "changes": [
            change(0, 2, 5, [{"old": 100, "new": 200, "kind": "changed"}]),  # TITLE I direct, financial
            change(1, 20, 30, []),  # SALARIES
            change(2, 70, 80, []),  # OPERATIONS
        ],
        "full_text": {"v1": "x" * 120, "v2": "TITLE I\n" + "y" * 112},
        "tree": {"v1": [], "v2": tree_v2},
    }
    return format_diff_html(view_from_canonical(canonical), canonical=canonical)


def _render_full_bill_report() -> str:
    """A standalone report whose full-bill view interleaves headings and changes.

    ``_render_grouped_report``'s full text is two lines, so every tree node
    anchors to the same row — too coarse to say which change follows which
    heading. Here each TITLE is its own row with one change in the body row
    below it, and TITLE IV deliberately has no change after it, which is the
    case where "first change at or after this heading" has no answer.
    """
    from deltatrack.formatters.canonical import view_from_canonical
    from deltatrack.formatters.diff_html import format_diff_html

    lines = [
        "TITLE I",
        "alpha aaa",
        "TITLE II",
        "beta bbb",
        "TITLE III",
        "gamma ccc",
        "TITLE IV",
        "delta ddd",
    ]
    v2_text = "\n".join(lines)
    offsets = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    def title_node(label, i):
        # Span starts on the heading row itself, so _node_anchor_offset resolves
        # the TOC link to that row. No children: renders as a clickable leaf.
        return {
            "label": label,
            "level": "title",
            "own_amounts": [],
            "full_text_span": {"start": offsets[i], "end": offsets[i] + len(lines[i])},
            "children": [],
        }

    def change(i, line_index):
        start = offsets[line_index]
        return {
            "id": f"c{i}",
            "change_type": "modified",
            "section_number": "",
            "path": {"v1": ["TITLE I"], "v2": ["TITLE I"]},
            "location": None,
            "anchor_resolution": "resolved",
            "text": {"old": f"shared {i}", "new": f"shared {i} added{i}"},
            "amount_entries": [],
            "move": None,
            "full_text_span": {
                "v1": None,
                "v2": {"start": start, "end": start + len(lines[line_index])},
            },
        }

    canonical = {
        "schema_version": "2.0",
        "bill": {"type": "hr", "number": 1, "congress": 119},
        "versions": {
            "v1": {"label": "v1", "version_number": 1, "source": "xml"},
            "v2": {"label": "v2", "version_number": 2, "source": "xml"},
        },
        "summary": {"added": 0, "removed": 0, "modified": 3, "moved": 0},
        # One change in each of the first three titles' body rows; none under
        # TITLE IV.
        "changes": [change(0, 1), change(1, 3), change(2, 5)],
        "full_text": {"v1": "x" * len(v2_text), "v2": v2_text},
        "tree": {
            "v1": [],
            "v2": [title_node(label, i) for i, label in enumerate(lines) if i % 2 == 0],
        },
    }
    return format_diff_html(view_from_canonical(canonical), canonical=canonical)


def test_counter_follows_full_bill_navigation(chromium, tmp_path):
    """In the full-bill view, an explicit jump sets the prev/next position the
    same way it does in the changes view (#185).

    The two entry points differ from the changes view and need different
    resolution. An inline highlight IS a nav target, so it resolves exactly, as
    a card does. A TOC link points at a heading row, which is never a target, so
    it resolves to the first change at or after that row ("the next change from
    here down"); a heading with nothing below it leaves the position alone
    rather than guessing.
    """
    report = tmp_path / "full_bill_nav.html"
    report.write_text(_render_full_bill_report(), encoding="utf-8")
    page = chromium.new_page(viewport={"width": 1280, "height": 900})
    page.goto(report.as_uri(), wait_until="domcontentloaded")

    page.locator('.view-toggle__btn[data-view="full"]').click()
    counter = page.locator("#nav-counter")
    assert counter.inner_text() == "0 / 3"

    # 1. TOC jump to a heading resolves to the first change below it, and the
    # arrow steps on from there (pre-fix this read "0 / 3" then "1 / 3").
    # TITLE II is row 18; the next change is c1 at 27, the 2nd of 3.
    page.locator('.sidebar-toc a[href="#fb-off-18"]').click()
    assert counter.inner_text() == "2 / 3"
    page.locator("#btn-next").click()
    assert counter.inner_text() == "3 / 3"

    # Resolution is "at or after", not "the nearest": TITLE I is row 0 and the
    # first change is c0 at row 8, so it lands on 1 rather than staying put.
    page.locator('.sidebar-toc a[href="#fb-off-0"]').click()
    assert counter.inner_text() == "1 / 3"

    # 2. A click on an inline highlight is itself a target, so it resolves
    # exactly, the way a change card does.
    page.locator("#attr-c2").click()
    assert counter.inner_text() == "3 / 3"
    page.keyboard.press("ArrowLeft")
    assert counter.inner_text() == "2 / 3"

    # 3. A heading with no change below it has no answer: the position is left
    # where it was rather than being reset or clamped. TITLE IV is the last row
    # and every change sits above it.
    page.locator('.sidebar-toc a[href="#fb-off-56"]').click()
    assert counter.inner_text() == "2 / 3"

    # The changes view keeps its own exact-match resolution: switching views
    # resets, and a card jump still lands on that card and not a neighbour.
    page.locator('.view-toggle__btn[data-view="changes"]').click()
    assert counter.inner_text() == "0 / 3"
    page.locator("#change-2").click(position={"x": 5, "y": 5})
    assert counter.inner_text() == "3 / 3"
    page.close()


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


def test_counter_follows_explicit_card_navigation(chromium, tmp_path):
    """Jumping to a card by any explicit gesture sets the prev/next position to
    that card, so the next arrow step continues from what the reader is looking
    at rather than from wherever the arrows last were (#185).

    Three entry points: sidebar nav links, Financial Summary row links, and a
    click on the card itself (which is what makes the scroll-and-read flow
    work). The index is taken against the currently visible targets, so it has
    to stay correct with the type filter active. Browser-level because the
    contract is the runtime index lookup, which string assertions can't prove.
    """
    report = tmp_path / "grouped_sync.html"
    report.write_text(_render_grouped_report(), encoding="utf-8")
    page = chromium.new_page(viewport={"width": 1280, "height": 900})
    page.goto(report.as_uri(), wait_until="domcontentloaded")

    counter = page.locator("#nav-counter")
    assert counter.inner_text() == "0 / 3"

    # Sidebar nav groups are collapsed by default; expand down to the link.
    page.locator(".sidebar .nav-group > summary").first.click()
    page.locator(".sidebar .nav-group .nav-group > summary").first.click()

    # 1. Sidebar link into a nested group: counter lands on that card, and the
    # next arrow step continues from it (pre-#185 this read "0 / 3" then "1 / 3").
    page.locator('.sidebar a[href="#change-1"]').click()
    assert counter.inner_text() == "2 / 3"
    page.locator("#btn-next").click()
    assert counter.inner_text() == "3 / 3"

    # 2. Financial Summary row link (only change-0 carries amounts). The table
    # ships collapsed, so open it before reaching a row.
    fin = page.locator("details.financial-summary")
    assert fin.evaluate("el => el.open") is False
    fin.locator("summary").click()
    page.locator('.financial-table a[href="#change-0"]').first.click()
    assert counter.inner_text() == "1 / 3"

    # 3. A click on the card body itself, then keyboard stepping from there.
    page.locator("#change-1").click(position={"x": 5, "y": 5})
    assert counter.inner_text() == "2 / 3"
    page.keyboard.press("ArrowRight")
    assert counter.inner_text() == "3 / 3"

    # The index is against the *visible* targets: with the financial filter on,
    # change-0 is the only target, so jumping to it is 1 / 1, not 1 / 3.
    page.locator('input[name="change-filter"][value="financial"]').check()
    assert counter.inner_text() == "0 / 1"
    page.locator('.financial-table a[href="#change-0"]').first.click()
    assert counter.inner_text() == "1 / 1"

    # A jump into a collapsed group still resolves to the right index: the card
    # is revealed first, so it is a visible target when indexOf runs.
    page.locator('input[name="change-filter"][value="all"]').check()
    salaries = page.locator(".card-group .card-group").first
    salaries.evaluate("el => el.open = false")
    page.locator('.sidebar a[href="#change-1"]').click()
    assert salaries.evaluate("el => el.open") is True
    assert counter.inner_text() == "2 / 3"

    # A jump whose target is not in the visible set leaves the position alone
    # rather than resetting it. applyFilters hides cards and their sidebar nav
    # items, but not Financial Summary rows, so a row can outlive its card and
    # stay clickable: on a real report (HR 4366 reported-vs-enrolled) the
    # Structural filter leaves 28 such links. Hiding the card directly puts the
    # DOM in that state without needing a change type this fixture lacks.
    page.locator("#change-0").evaluate("el => el.style.display = 'none'")
    page.locator('.financial-table a[href="#change-0"]').first.click()
    assert counter.inner_text() == "2 / 3"
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


def test_report_tab_shows_progress_while_the_diff_renders(live_url, chromium, tmp_path):
    """The report tab is opened on the click but can't be filled until the server
    finishes, which on a large bill takes tens of seconds. It must say so rather
    than sit on about:blank, where a slow render is indistinguishable from a
    stalled one.

    The compare request is intercepted and left unanswered, which is exactly the
    state under test: the tab is open, the report has not arrived.
    """
    start = tmp_path / "start.pdf"
    end = tmp_path / "end.pdf"
    start.write_bytes(b"%PDF-1.4 start")
    end.write_bytes(b"%PDF-1.4 end")

    page = chromium.new_page()
    # Hold the request open for the life of the test; nothing ever fulfills it.
    page.route("**/api/compare*", lambda route: None)
    page.goto(live_url.rstrip("/") + "/compare.html", wait_until="domcontentloaded")

    page.locator("#start-input").set_input_files(str(start))
    page.locator("#end-input").set_input_files(str(end))

    with page.context.expect_page() as new_page_info:
        page.locator("#compare-btn").click()
    report = new_page_info.value

    report.wait_for_selector(".spinner")
    assert "Diff in progress" in report.locator("h1").inner_text()
    # The spinner is a real animation, not a static glyph, so the tab reads as
    # working rather than frozen.
    assert report.locator(".spinner").evaluate("el => getComputedStyle(el).animationName") != "none"

    report.close()
    page.close()


# --- Find across printed line breaks (#162) ---------------------------------
#
# The PDF full-bill view is print-faithful: GPO's line breaks and its soft-
# hyphenated word splits are real DOM boundaries, one `.fb-row` per printed
# line. Matching per text node therefore made every printed line an island, so
# a phrase the reader can see on screen returned `0 / 0`.

# Printed page text in GPO's `<line number> <content>` layout. Deliberately
# contains all four boundary cases the find bar has to cross (or refuse to):
#   line 1/2   soft hyphen, lowercase continuation  -> join ("Services")
#   line 2/3   plain wrap, no hyphen                -> join with a space
#   line 4/5   real compound, uppercase continuation -> must NOT join
#   line 6     column padding (a run of spaces)      -> collapses to one space
_FIND_PAGE_SRC = (
    "1 for expenses of the Administrator of General Serv-\n"
    "2 ices for vehicles the Administrator of General\n"
    "3 Services does not provide for lease under this\n"
    "4 heading, and for grants under the Child-\n"
    "5 Rescue Act of 2019, to remain available until\n"
    "6 expended                                    $5,000,000\n"
)


def _find_fixture_texts() -> tuple[str, str]:
    """(printed display text, merged whole-word text) from the real parser.

    Both come from the producer the browser has to agree with — `pdf_full_text`
    is the de-hyphenated ground truth the flattened search string must
    reproduce, so the fixture can't encode a belief about GPO's line-joining
    that the parser doesn't share.
    """
    from deltatrack.parsers.pdf_text import (
        Page,
        _merge_print_lines,
        _parse_print_lines,
        pdf_full_text,
        pdf_full_text_print,
    )

    print_lines = _parse_print_lines(_FIND_PAGE_SRC.rstrip("\n"))
    merged, ranges = _merge_print_lines(print_lines)
    page = Page(1, tuple(merged), tuple(print_lines), tuple(ranges))
    printed_text, _ = pdf_full_text_print([page])
    merged_text, _ = pdf_full_text([page])
    return printed_text, merged_text


def _render_find_report() -> str:
    """A real report whose full-bill view is the print-faithful page above.

    One change span sits mid-line on the word "vehicles", so that row's text is
    split across sibling text nodes by the tracked-change mark — the in-line
    counterpart of the cross-row case.
    """
    from deltatrack.formatters.canonical import view_from_canonical
    from deltatrack.formatters.diff_html import format_diff_html

    printed_text, _ = _find_fixture_texts()
    start = printed_text.index("vehicles")
    canonical = {
        "schema_version": "2.0",
        "bill": {"type": "hr", "number": 8752, "congress": 118},
        "versions": {
            "v1": {"label": "Reported", "version_number": 1, "source": "pdf"},
            "v2": {"label": "Enrolled", "version_number": 2, "source": "pdf"},
        },
        "summary": {"added": 0, "removed": 0, "modified": 1},
        "full_text": {"v1": "", "v2": printed_text},
        "changes": [
            {
                "id": "c0",
                "change_type": "modified",
                "section_number": "",
                "path": {"v1": [], "v2": []},
                "location": None,
                "anchor_resolution": "resolved",
                "text": {"old": "cars", "new": "vehicles"},
                "amount_entries": [],
                "move": None,
                "full_text_span": {"v1": None, "v2": {"start": start, "end": start + len("vehicles")}},
            }
        ],
    }
    return format_diff_html(view_from_canonical(canonical), canonical=canonical)


def _open_full_bill(chromium, tmp_path, name="find_report.html"):
    report = tmp_path / name
    report.write_text(_render_find_report(), encoding="utf-8")
    page = chromium.new_page(viewport={"width": 1280, "height": 900})
    page.goto(report.as_uri(), wait_until="domcontentloaded")
    page.locator('.view-toggle__btn[data-view="full"]').click()
    return page


def _find(page, query):
    """Type a query and settle the 150ms debounce; returns the counter text."""
    page.locator("#find-input").fill(query)
    page.wait_for_timeout(300)
    return page.locator("#find-counter").inner_text()


def test_find_matches_across_printed_line_breaks(chromium, tmp_path):
    """Phrases that wrap across printed lines are findable (#162).

    Pre-fix each of these returned `0 / 0` — the silent failure mode, since the
    reader can see the phrase on screen.
    """
    page = _open_full_bill(chromium, tmp_path)

    # Soft hyphen: the page reads "Serv-" / "ices" across two rows.
    assert _find(page, "General Services") == "1 / 2"
    # Plain wrap, no hyphen involved: "…of General" / "Services does not…".
    assert _find(page, "Administrator of General Services does not") == "1 / 1"
    # A match crossing a tracked-change mark inside ONE printed line: the <ins>
    # around "vehicles" splits that row into sibling text nodes.
    assert _find(page, "for vehicles the") == "1 / 1"
    page.close()


def test_find_does_not_join_real_compounds(chromium, tmp_path):
    """The soft-hyphen rejoin must not weld a real compound together.

    GPO breaks syllables with a lowercase continuation; "Child-" / "Rescue"
    keeps its uppercase continuation and is a real hyphenated name. Without this
    the rejoin looks correct on every positive case while silently corrupting
    compounds — the join would fire, but wrongly.
    """
    page = _open_full_bill(chromium, tmp_path)
    assert _find(page, "childrescue") == "0 / 0"
    assert _find(page, "Child-Rescue Act") == "1 / 1"
    page.close()


def test_find_ignores_line_number_gutter(chromium, tmp_path):
    """Line numbers are print furniture, not bill text, so they aren't searched.

    Flattening the view would otherwise splice the gutter into the middle of the
    text ("…Serv- 2 ices…"), both creating false hits and breaking real ones.
    """
    page = _open_full_bill(chromium, tmp_path)
    # A phrase crossing rows 5 -> 6: with the gutter in the searchable text this
    # would read "…available until 6 expended" and never match. This is the
    # assertion that makes the test discriminating — the two negatives below
    # both hold on the pre-fix per-node search as well.
    assert _find(page, "available until expended") == "1 / 1"
    # Runs of column padding collapse to a single space, as they do in the
    # parser's merged text.
    assert _find(page, "expended $5,000,000") == "1 / 1"
    # The rejoined hyphen is gone from the searchable text, and no gutter digit
    # is ever itself a hit.
    assert _find(page, "Serv- ices") == "0 / 0"
    hits_in_gutter = page.evaluate("() => document.querySelectorAll('.fb-gutter mark.find-hit').length")
    assert hits_in_gutter == 0
    page.close()


def test_find_counts_matches_not_marks_and_steps_across_rows(chromium, tmp_path):
    """A match spanning two rows is one hit, and stepping lands on its first row.

    The match is highlighted with one <mark> per row it covers; counting marks
    would report a two-row phrase as two separate hits and make prev/next step
    through half-matches.
    """
    page = _open_full_bill(chromium, tmp_path)
    assert _find(page, "General Services") == "1 / 2"

    marks = page.evaluate("() => document.querySelectorAll('mark.find-hit--current').length")
    assert marks == 2, "the two-row match should carry current styling on both of its marks"

    # Both marks belong to the current hit, and the first sits on the earlier row.
    rows = page.evaluate(
        """() => Array.from(document.querySelectorAll('mark.find-hit--current'))
                     .map(m => m.closest('.fb-row').querySelector('.fb-gutter').textContent.trim())"""
    )
    assert rows == ["1", "2"]

    page.locator("#find-next").click()
    assert page.locator("#find-counter").inner_text() == "2 / 2"
    page.close()


def test_find_agrees_with_the_parser_merged_text(chromium, tmp_path):
    """Every phrase in the parser's merged text is findable in the browser.

    The JS rejoin re-implements one parser rule (`_merge_print_lines`), so the
    two can drift. Rather than assert the flattened string against a
    hand-written expectation — which would only encode a belief about what the
    parser does — this walks every 5-word window of `pdf_full_text`'s output,
    the de-hyphenated ground truth, and requires the browser to find each one.
    A missing join, a wrong join, or a gutter spliced into the text all break
    some window.
    """
    import re as _re

    _, merged_text = _find_fixture_texts()
    # Windows stay inside one merged line. Each merged line is already whole-word
    # (the parser rejoined its soft hyphens), so this pins the de-hyphenation
    # contract without asserting how the JS joins one display line to the next.
    windows = []
    for line in merged_text.splitlines():
        words = _re.sub(r"\s+", " ", line[7:]).strip().split(" ")
        windows += [" ".join(words[i : i + 5]) for i in range(0, len(words) - 4)]
    assert len(windows) > 10, "fixture too small to be evidence of anything"

    page = _open_full_bill(chromium, tmp_path)
    missing = [w for w in windows if _find(page, w) == "0 / 0"]

    # The check must be able to fail: a phrase the merged text does NOT contain
    # has to come back empty, otherwise a green run above proves nothing.
    control = _find(page, "vehicles for grants under expended")
    page.close()

    assert not missing, f"phrases in the merged text that Find cannot locate: {missing}"
    assert control == "0 / 0", "control phrase matched — the search is not discriminating"


def test_find_does_not_match_across_a_deletion_and_its_replacement(chromium, tmp_path):
    """In the changes view, old and new wording are alternatives, not a sequence.

    A card shows the removed text next to the text that replaces it. Flattening
    the view for search puts them side by side, so joining them with a space
    would let a query match wording that appears in no version of the bill —
    a false positive, which is worse than the missed match this all started
    with. A separator no query can contain keeps them apart.
    """
    report = tmp_path / "changes_view.html"
    report.write_text(_render_find_report(), encoding="utf-8")
    page = chromium.new_page(viewport={"width": 1280, "height": 900})
    page.goto(report.as_uri(), wait_until="domcontentloaded")  # changes view is the default

    # The card reads "cars" (removed) immediately followed by "vehicles" (added).
    card = page.locator(".change-card").first.inner_text()
    assert "cars" in card and "vehicles" in card, "fixture no longer shows both sides"

    assert _find(page, "cars vehicles") == "0 / 0"
    # Each side is still findable on its own.
    assert _find(page, "vehicles") != "0 / 0"
    assert _find(page, "cars") != "0 / 0"
    page.close()


def test_find_accepts_a_query_pasted_off_the_screen(chromium, tmp_path):
    """A phrase copied from the page can end at a line-break hyphen.

    The reader sees "…Administrator of General Serv-" at the end of a printed
    line and pastes exactly that. The hyphen is not in the searchable text
    (it was rejoined away), so without handling this the query returns 0 / 0 —
    the same silent miss, in the opposite direction.
    """
    page = _open_full_bill(chromium, tmp_path)
    # Dropping the trailing hyphen leaves "…General Serv", which is a prefix of
    # both the split occurrence on rows 1-2 and the whole "Services" on row 3,
    # so two matches is correct here — the point is that it is no longer zero.
    assert _find(page, "Administrator of General Serv-") == "1 / 2"
    # The first hit is the line the reader copied from.
    row = page.evaluate(
        """() => document.querySelector('mark.find-hit--current')
                        .closest('.fb-row').querySelector('.fb-gutter').textContent.trim()"""
    )
    assert row == "1"
    page.close()
