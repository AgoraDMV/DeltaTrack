"""Regression tests for scripts/generate_validation_report.py.

The script reads gitignored, fetch-scripted fixtures, so it must degrade
gracefully on a clean clone instead of raising FileNotFoundError (#18).
"""

from pathlib import Path

import scripts.generate_validation_report as report


def test_leg_branch_summary_degrades_when_fixture_absent(monkeypatch):
    monkeypatch.setattr(report, "LEG_BRANCH_FIXTURE", Path("test_data/_does_not_exist.json"))
    summary = report._leg_branch_summary()
    assert "not fetched" in summary
    assert "Legislative Branch" in summary
