"""Tests for the diff_pdf CLI entry point (issue #25)."""

from __future__ import annotations

from pathlib import Path

import pytest

from diff_pdf import _label_from_stem, build_parser, main

BILL_DIR = Path(__file__).parent.parent / "bills" / "118-hr-8752"
V1 = BILL_DIR / "1_reported-in-house.pdf"
V2 = BILL_DIR / "2_engrossed-in-house.pdf"

requires_corpus = pytest.mark.skipif(
    not (V1.exists() and V2.exists()),
    reason="corpus PDFs not present (run scripts/fetch_test_assets.py)",
)


class TestLabelFromStem:
    def test_strips_numeric_version_prefix(self):
        assert _label_from_stem("1_reported-in-house") == "reported-in-house"

    def test_keeps_stem_without_numeric_prefix(self):
        assert _label_from_stem("draft-v2") == "draft-v2"

    def test_keeps_underscore_when_prefix_not_numeric(self):
        assert _label_from_stem("foo_bar") == "foo_bar"


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


@requires_corpus
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
