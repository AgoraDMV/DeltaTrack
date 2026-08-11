"""Tests for the diff_pdf CLI entry point (issue #25)."""

from __future__ import annotations

from pathlib import Path

from deltatrack.diff_pdf import build_parser, main
from tests.corpus_paths import fixture_path

V1 = fixture_path("118-hr-8752", "1_reported-in-house.pdf")
V2 = fixture_path("118-hr-8752", "2_engrossed-in-house.pdf")


def test_fixtures_committed():
    """Fail-closed floor (#326): both PDFs are committed and manifested, so an absent
    one is a broken checkout, not an optional case. This used to be a class-level
    ``skipif`` written when the corpus was fetched rather than committed; a skip is
    green, so deleting either file would have silently turned the two CLI tests below
    off (the fail-open shape epic #288 collects, same as #287)."""
    absent = sorted(str(p) for p in (V1, V2) if not p.exists())
    assert not absent, f"committed diff_pdf CLI fixtures absent from checkout: {absent}"


class TestParser:
    def test_positional_and_output(self):
        args = build_parser().parse_args(["a.pdf", "b.pdf", "-o", "out.html"])
        assert args.v1_pdf == Path("a.pdf")
        assert args.v2_pdf == Path("b.pdf")
        assert args.output == Path("out.html")

    def test_label_defaults(self):
        args = build_parser().parse_args(["a.pdf", "b.pdf"])
        assert args.v1_label is None
        assert args.v2_label is None


class TestCli:
    def test_writes_html_file(self, tmp_path):
        out = tmp_path / "diff.html"
        main([str(V1), str(V2), "-o", str(out)])
        html = out.read_text()
        assert html.lstrip().lower().startswith("<!doctype html") or "<html" in html.lower()
        assert "reported-in-house" in html
        assert "engrossed-in-house" in html
        # Delegating to compare_pdfs_html means the report carries the
        # full-bill view + embedded export, not just the changed-section cards.
        assert "full-bill" in html
        assert "diff.json" in html

    def test_stdout_when_no_output(self, capsys):
        main([str(V1), str(V2)])
        captured = capsys.readouterr()
        assert "<html" in captured.out.lower()
