"""Guardrails that keep the docs from drifting out of sync with how the suite runs.

These are plain text checks over Markdown files, not behavior tests, so they carry
no markers and run in the default fast suite.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Docs that show how to run the tests. The fast/no-setup suite must EXCLUDE the
# browser tests (they need a one-time `playwright install chromium`), so the
# canonical marker is `not slow and not browser`. The bare `not slow` is stale:
# it now also selects the browser tests. See issue #124, fixed across #118/#120/#121.
_DOCS_WITH_RUN_COMMANDS = [
    "README.md",
    "TESTING.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    ".github/pull_request_template.md",
]

_STALE_MARKERS = ('-m "not slow"', "-m 'not slow'")


def test_docs_use_current_fast_test_marker():
    """No doc should show the stale `-m "not slow"` fast-test command.

    Whenever a new marker is added that should stay out of the fast run, update
    that marker list AND every command below, or this test fails on purpose.
    """
    offenders = []
    for rel in _DOCS_WITH_RUN_COMMANDS:
        path = ROOT / rel
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if any(marker in line for marker in _STALE_MARKERS):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")

    assert not offenders, (
        "Docs show the stale fast-test marker (now selects browser tests). "
        'Use `-m "not slow and not browser"` instead:\n' + "\n".join(offenders)
    )
