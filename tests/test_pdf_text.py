"""Unit tests for pdf_text primitives. One test per primitive that earned its keep."""

from __future__ import annotations

from parsers.pdf_text import (
    Line,
    Page,
    _merge_print_lines,
    _parse_print_lines,
    normalize_glyphs,
    normalize_raw,
    page_range_text,
    pdf_full_text,
    pdf_full_text_print,
    rejoin_soft_hyphens,
    strip_page_chrome,
)


def _print_page(page_number: int, chrome_stripped: str) -> Page:
    """Build a Page the way extract_clean_pages does: pre-merge print lines plus
    the soft-hyphen-merged lines and their constituent ranges."""
    print_lines = _parse_print_lines(chrome_stripped)
    merged, ranges = _merge_print_lines(print_lines)
    return Page(page_number, tuple(merged), tuple(print_lines), tuple(ranges))


class TestPdfFullTextPrint:
    # Two printed lines where a soft hyphen merges line 8 into line 9 for the
    # diff, but the printed view should keep both lines and the hyphen.
    _SRC = "8 For acquisition and equip-\n9 ment of public works\n10 Marine Corps as authorized"

    def test_keeps_every_printed_line_and_hyphen(self):
        text, _ = pdf_full_text_print([_print_page(1, self._SRC)])
        assert "    8  For acquisition and equip-" in text
        assert "    9  ment of public works" in text
        assert "   10  Marine Corps as authorized" in text

    def test_merged_line_offset_spans_its_printed_lines(self):
        text, offsets = pdf_full_text_print([_print_page(1, self._SRC)])
        # Merged line 8 absorbed printed line 9, so its span covers both 8 and 9.
        start, end = offsets[(1, 8)]
        assert text[start:end] == "    8  For acquisition and equip-\n    9  ment of public works"
        # Line 10 didn't merge, so its span is just itself.
        s10, e10 = offsets[(1, 10)]
        assert text[s10:e10] == "   10  Marine Corps as authorized"

    def test_merged_full_text_collapses_the_hyphen(self):
        # Contrast: the canonical (merged) text rejoins the word onto one line.
        text, _ = pdf_full_text([_print_page(1, self._SRC)])
        assert "    8  For acquisition and equipment of public works" in text


def _page(page_number: int, text: str) -> Page:
    """Test helper: build a Page whose text round-trips through the property.

    Each newline in `text` becomes its own Line with no source line number.
    """
    return Page(page_number, tuple(Line(None, line) for line in text.split("\n")))


class TestRejoinSoftHyphens:
    def test_joins_lowercase_continuation(self):
        raw = "Representa-\ntives of the United"
        assert rejoin_soft_hyphens(raw) == "Representatives of the United"

    def test_joins_multiple_hyphens(self):
        raw = "avail-\nable until Sep-\ntember 30, 2026"
        assert rejoin_soft_hyphens(raw) == "available until September 30, 2026"

    def test_preserves_compound_with_uppercase_continuation(self):
        # GPO soft breaks always continue on a lowercase letter; uppercase
        # signals a real compound like Child-Rescue and must be preserved.
        raw = "Operative Child-\nRescue Corps"
        assert rejoin_soft_hyphens(raw) == "Operative Child-\nRescue Corps"

    def test_preserves_inline_hyphens(self):
        raw = "police-type vehicles"
        assert rejoin_soft_hyphens(raw) == "police-type vehicles"

    def test_preserves_dollar_for_dollar_inline(self):
        raw = "reduced on a dollar-for-dollar basis"
        assert rejoin_soft_hyphens(raw) == "reduced on a dollar-for-dollar basis"


class TestNormalizeRaw:
    def test_converts_crlf_to_lf(self):
        assert normalize_raw("a\r\nb\r\n") == "a\nb\n"

    def test_reconstructs_soft_hyphen_break_with_margin_number(self):
        # `equip￾4 ment` is line 3 ending in a soft-hyphenated word whose
        # continuation is GPO line 4; reconstructed to the `-\n4 ` line boundary.
        raw = "3 and equip￾4 ment of works\r\n"
        assert normalize_raw(raw) == "3 and equip-\n4 ment of works\n"

    def test_reconstructs_two_digit_margin_number(self):
        raw = "17 study, plan￾18 ning, and design\r\n"
        assert normalize_raw(raw) == "17 study, plan-\n18 ning, and design\n"

    def test_strips_trailing_spaces_per_line(self):
        assert normalize_raw("departments, by law, \r\n") == "departments, by law,\n"

    def test_page_break_hyphen_strips_glued_watermark(self):
        # A word hyphenating onto the next page glues the footer watermark on via
        # the soft-hyphen glyph; only the hyphenated word survives.
        raw = "purposes and no￾mstockstill on DSK4VPTVN1PROD with BILLS\r\n"
        assert normalize_raw(raw) == "purposes and no-\n"

    def test_page_break_hyphen_strips_glued_verdate(self):
        raw = "training and ad￾VerDate Sep 11 2014 Jkt E:\\BILLS\\H4366.PCS\r\n"
        assert normalize_raw(raw) == "training and ad-\n"

    def test_soft_hyphen_mid_line_joins_word(self):
        # On pages with no margin numbers (title pages, enrolled bills) a wrapped
        # word's soft hyphen has no `-\n` boundary, so it is joined into one word
        # rather than left as `equip-ment` (which would also miss a recall match).
        assert normalize_raw("equip￾ment of works\r\n") == "equipment of works\n"


class TestStripPageChrome:
    def test_strips_leading_page_number_with_trailing_space(self):
        assert strip_page_chrome("5 \n1 BODY") == "1 BODY"

    def test_strips_running_hr_header_line(self):
        # PDFium floats the running header to the top, after the page number.
        assert strip_page_chrome("•HR 4366 RH\n1 BODY") == "1 BODY"

    def test_strips_verdate_footer_and_watermark_below(self):
        raw = "23 reasons therefor.\nVerDate Sep 11 2014 00:17 Jkt\nSSpencer on DSK PROD with BILLS"
        assert strip_page_chrome(raw) == "23 reasons therefor."

    def test_strips_standalone_watermark_line(self):
        # When a page-boundary soft hyphen consumes the VerDate line, the print
        # watermark is left on its own line and must still be removed.
        raw = "24 training and ad-\npbinns on DSKJLVW7X2PROD with $$_JOB"
        assert strip_page_chrome(raw) == "24 training and ad-"

    def test_keeps_body_without_chrome_unchanged(self):
        assert strip_page_chrome("1 BODY\n2 MORE") == "1 BODY\n2 MORE"


class TestPageRangeText:
    def test_concatenates_pages_in_range(self):
        pages = [_page(1, "first"), _page(2, "second"), _page(3, "third")]
        assert page_range_text(pages, 1, 2) == "first\nsecond"

    def test_inclusive_end(self):
        pages = [_page(1, "a"), _page(2, "b"), _page(3, "c")]
        assert page_range_text(pages, 1, 3) == "a\nb\nc"

    def test_rejoins_cross_page_soft_hyphen(self):
        # Per-page cleanup leaves a trailing `-` on the prior page when the
        # break crosses a page boundary; concatenation re-creates `-\n` and
        # the helper must rejoin it.
        pages = [_page(15, "not to ex-"), _page(16, "ceed $7,650")]
        assert page_range_text(pages, 15, 16) == "not to exceed $7,650"

    def test_skips_pages_outside_range(self):
        pages = [_page(1, "a"), _page(2, "b"), _page(3, "c")]
        assert page_range_text(pages, 2, 2) == "b"


class TestNormalizeGlyphs:
    def test_em_dash_to_padded_hyphen(self):
        # GPO uses em-dash to introduce enumerated subparagraphs; readers see it
        # as " - ". Pad with spaces so whitespace-normalization handles either form.
        assert normalize_glyphs("used—(1)") == "used - (1)"

    def test_en_dash_to_padded_hyphen(self):
        # Same treatment for en-dash (U+2013), used in `H–2B`.
        assert normalize_glyphs("H–2B") == "H - 2B"

    def test_smart_singles_to_ascii_apostrophe(self):
        assert normalize_glyphs("‘foo’") == "'foo'"

    def test_smart_doubles_to_ascii_double_quote(self):
        assert normalize_glyphs("“foo”") == '"foo"'

    def test_paired_smart_singles_collapse_to_double_quote(self):
        # GPO encodes double quotes as two adjacent single-glyph smart quotes:
        # ``Asylum Program Fee'' → "Asylum Program Fee"
        assert normalize_glyphs("‘‘Asylum’’") == '"Asylum"'

    def test_preserves_ascii_hyphen(self):
        assert normalize_glyphs("police-type") == "police-type"

    def test_preserves_apostrophe_in_possessive(self):
        assert normalize_glyphs("Will's") == "Will's"
