"""Experiment 3: what actually breaks when DeltaTrack is opened from file:// ?

Loads spike/static-app/index.html twice -- once as a file:// document and once from
a local HTTP server -- in a real browser engine, and reports the capability probes
plus whether the Python engine loaded. Then runs a real two-file comparison on the
committed corpus over HTTP to confirm the whole path works end to end in-page.

Run:  uv run python spike/probe_static_app.py [http://127.0.0.1:8971]
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

APP = Path(__file__).resolve().parent / "static-app" / "index.html"
# probes/ -> staffer-delivery/ -> research/ -> docs/ -> repo root
CORPUS = Path(__file__).resolve().parents[4] / "tests/corpus/118-hr-4366"
HTTP_BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8971"


def drive(page, url: str, *, compare: bool) -> None:
    print(f"\n{'=' * 92}\n{url}\n{'=' * 92}")
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

    page.goto(url, wait_until="load")
    # The probes are async; wait for the log to settle on a terminal line.
    page.wait_for_function("() => /READY|FAILED/.test(document.getElementById('log').textContent)", timeout=120_000)
    print(page.eval_on_selector("#log", "el => el.innerText").strip())

    if compare:
        page.set_input_files("#f1", str(CORPUS / "3_placed-on-calendar-senate.xml"))
        page.set_input_files("#f2", str(CORPUS / "4_engrossed-amendment-senate.xml"))
        page.click("#go")
        page.wait_for_function(
            "() => /diff \\+ render|Error/.test(document.getElementById('log').textContent)", timeout=300_000
        )
        tail = page.eval_on_selector("#log", "el => el.innerText").strip().splitlines()[-2:]
        print("\n-- real comparison, in-page --")
        print("\n".join(tail))

    if errors:
        print("\n-- page errors --")
        for e in errors[:8]:
            print("  " + e[:220])


with sync_playwright() as p:
    for channel in ("chromium", "chrome"):
        try:
            browser = p.chromium.launch(channel=None if channel == "chromium" else channel)
        except Exception as e:  # noqa: BLE001
            print(f"\n### {channel}: unavailable ({type(e).__name__})")
            continue
        print(f"\n\n############ ENGINE: {channel} — {browser.version} ############")
        ctx = browser.new_context()
        drive(ctx.new_page(), APP.as_uri(), compare=False)
        drive(ctx.new_page(), f"{HTTP_BASE}/index.html", compare=True)
        browser.close()
