"""Pin the version-prefixed filename-stem parsers in shared.version_stems."""

from __future__ import annotations

from shared.version_stems import label_from_stem, version_number_from_stem


class TestVersionNumberFromStem:
    def test_numeric_prefix(self):
        assert version_number_from_stem("1_reported-in-house") == 1

    def test_multi_digit_prefix(self):
        assert version_number_from_stem("10_engrossed") == 10

    def test_no_numeric_prefix(self):
        assert version_number_from_stem("draft-v2") is None

    def test_empty_stem(self):
        assert version_number_from_stem("") is None


class TestLabelFromStem:
    def test_strips_numeric_prefix(self):
        assert label_from_stem("1_reported-in-house") == "reported-in-house"

    def test_no_prefix_returned_unchanged(self):
        assert label_from_stem("draft-v2") == "draft-v2"

    def test_non_numeric_prefix_not_stripped(self):
        # Numeric-only strip: "foo_" is not a version prefix, so the stem stands.
        assert label_from_stem("foo_bar") == "foo_bar"

    def test_empty_stem(self):
        assert label_from_stem("") == ""
