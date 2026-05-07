"""Unit tests for pdf_text primitives. One test per primitive that earned its keep."""

from __future__ import annotations

from parsers.pdf_text import strip_line_numbers


class TestStripLineNumbers:
    def test_strips_leading_line_number_per_line(self):
        raw = "1 Be it enacted by the Senate\n2 of the United States"
        assert strip_line_numbers(raw) == "Be it enacted by the Senate\nof the United States"

    def test_handles_two_digit_line_numbers(self):
        raw = "14 For necessary expenses\n15 of the Office\n25 representation expenses."
        assert strip_line_numbers(raw) == ("For necessary expenses\nof the Office\nrepresentation expenses.")

    def test_does_not_strip_numbers_mid_line(self):
        raw = "5 of which $22,151,000 shall remain"
        assert strip_line_numbers(raw) == "of which $22,151,000 shall remain"

    def test_preserves_lines_without_leading_number(self):
        raw = "TITLE I\n1 Be it enacted"
        assert strip_line_numbers(raw) == "TITLE I\nBe it enacted"

    def test_does_not_strip_year_like_tokens_mid_paragraph(self):
        # 2026 should never appear at line-start in body text, but if it did we
        # would not strip it — we only strip 1-2 digit tokens.
        raw = "2026 budget submission for the Department"
        assert strip_line_numbers(raw) == "2026 budget submission for the Department"

    def test_handles_empty_lines(self):
        raw = "1 first line\n\n2 second line"
        assert strip_line_numbers(raw) == "first line\n\nsecond line"
