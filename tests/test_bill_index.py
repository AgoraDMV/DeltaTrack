"""Tests for bill_index CSV encode/decode round-trip (issue #61).

The write and read paths are asymmetric and worth testing together rather than
separately: writing goes through the hand-rolled ``_format_csv_cell``, while reading
goes through ``csv.DictReader`` (which already removes CSV quoting) and *then*
``_decode_value``. A cell therefore passes two unquoting stages, and only the
round-trip shows what the second one does to text the first one quoted.

Cases here are constructed from the declared domain rather than sampled from the
corpus. The index stores free text from bill XML (``title``, ``status``,
``policyArea``) alongside genuinely numeric counts, and the current corpus happens to
contain no title that would exercise the quote-decoding edges -- so corpus-derived
cases would bound only the observed input space, not the space the code accepts.

#256 is fixed in both halves, and the round trip is now lossless for every case here.
``_decode_value`` no longer unquotes a second time (``TestQuoteWrappedTextRoundTrips``)
and no longer coerces digits to ``int`` (``TestNumericLookingTextSurvives``). Both
fixes removed a guess: what a cell means is no longer inferred from its shape, so a
value comes back as the text that was stored.

That makes the counting columns (``actionCount`` and peers) read back as text too,
which ``TestNumericColumns`` pins deliberately rather than by omission.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bill_index.bill_index import (
    BillIdentifier,
    BillIndex,
    _decode_value,
    _format_csv_cell,
    make_bill_id,
    parse_bill_id,
)


def round_trip(tmp_path: Path, value: object, column: str = "title") -> object:
    """Persist one field value through save() and read it back through load()."""
    csv_path = tmp_path / "bills.csv"
    index = BillIndex(csv_path)
    index.add_bills([{"id": "119-hr-1", column: value}], save=True)

    reloaded = BillIndex(csv_path)
    reloaded.load()
    return reloaded.get("119-hr-1")[column]


class TestFreeTextRoundTrip:
    """Free-text columns (title, status, policyArea) must survive unchanged.

    These carry bill titles and latest-action text straight from BILLSTATUS XML, so
    CSV-significant characters are ordinary content here, not edge cases.
    """

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("Consolidated Appropriations Act", id="plain"),
            pytest.param(
                "Making appropriations for the Departments of Commerce and Justice, "
                "Science, and Related Agencies, and for other purposes.",
                id="commas",
            ),
            pytest.param("Referred to the Committee on Appropriations.", id="sentence"),
            pytest.param('An Act to amend the "Clean Air Act" provisions', id="inner-quotes"),
            pytest.param("line one\nline two", id="embedded-newline"),
            pytest.param("line one\r\nline two", id="embedded-crlf"),
            # A lone CR needs its own case: the CRLF above is already quoted by the
            # "\n" clause, so it cannot tell whether the "\r" clause works. Without
            # that clause an unquoted CR makes csv.DictReader split one record into
            # two -- silent record inflation plus a truncated title.
            pytest.param("line one\rline two", id="embedded-lone-cr"),
            pytest.param("café — em dash, naïve", id="unicode"),
            pytest.param("“Scholarships for Opportunity Act”", id="curly-quoted-short-title"),
            pytest.param(r"path\to\thing", id="backslashes"),
            pytest.param('a","b', id="quote-comma-combo"),
            pytest.param("2025-01-01", id="iso-date"),
            pytest.param("1.5", id="float-like-stays-text"),
            pytest.param("True", id="bool-like-stays-text"),
            pytest.param("119-hr-1234", id="bill-id-shape"),
            pytest.param("", id="empty"),
        ],
    )
    def test_value_survives_the_round_trip_unchanged(self, tmp_path, value):
        assert round_trip(tmp_path, value) == value

    def test_curly_quoted_title_is_not_decoded(self, tmp_path):
        # Legislative short titles are typeset with curly quotes, so they do not hit
        # the straight-quote decode branch. Pinning this keeps a future "normalize
        # smart quotes" change from silently routing real titles into that branch.
        value = "“Scholarships for Opportunity and Results Reauthorization Act”"
        assert round_trip(tmp_path, value) == value


class TestNumericColumns:
    """Count columns come back as their exact text, not as ints (#256).

    ``historySize``, ``actionCount``, ``versionCount`` and friends are produced by
    ``len()`` / ``stat()``, so they are written as digits. They are read back as
    text, because a CSV cell *is* text and the reader cannot tell a counting column
    from a free-text one that happens to hold digits.

    The rejected alternative was to keep coercing so a reloaded index stays sortable
    without callers re-parsing. Nothing in the project reads these columns back out,
    so that convenience was unused, while the same coercion turned a digits-only
    ``id`` into an int and crashed the ``--file <csv>`` download path
    (``TestDigitsOnlyIdIsUsable``). A caller that wants a number converts at the
    point of use.
    """

    @pytest.mark.parametrize("value", [0, 1, 42, 1000, 12345678901234567890])
    def test_int_round_trips_as_its_exact_text(self, tmp_path, value):
        result = round_trip(tmp_path, value, column="actionCount")
        assert result == str(value)
        assert isinstance(result, str)

    def test_negative_int_round_trips(self, tmp_path):
        # daysActive is a date subtraction and can legitimately be negative.
        result = round_trip(tmp_path, -3, column="daysActive")
        assert result == "-3"

    def test_zero_is_not_confused_with_empty(self, tmp_path):
        # 0 and "" are still different facts: no actions recorded vs field absent.
        # The empty-string short-circuit must not swallow a stored zero.
        assert round_trip(tmp_path, 0, column="actionCount") == "0"
        assert round_trip(tmp_path, "", column="actionCount") == ""


class TestDecodeValueUnit:
    """Direct unit coverage of _decode_value, below the CSV layer."""

    @pytest.mark.parametrize("value", [None, ""])
    def test_missing_values_decode_to_empty_string(self, value):
        assert _decode_value("title", value) == ""

    def test_digits_decode_to_text(self):
        result = _decode_value("actionCount", "42")
        assert result == "42"
        assert isinstance(result, str)

    def test_non_numeric_text_is_returned_as_is(self):
        assert _decode_value("title", "An Act") == "An Act"

    def test_iso_date_is_not_coerced(self):
        assert _decode_value("introducedDate", "2025-01-01") == "2025-01-01"

    def test_unbalanced_quote_is_left_alone(self):
        # The decode branch requires a quote at *both* ends, so these bypass it.
        assert _decode_value("title", '"unterminated') == '"unterminated'
        assert _decode_value("title", 'trailing"') == 'trailing"'


class TestFormatCsvCell:
    def test_quotes_commas_and_newlines_are_escaped(self):
        assert _format_csv_cell("a,b") == '"a,b"'
        assert _format_csv_cell('say "hi"') == '"say ""hi"""'
        assert _format_csv_cell("a\nb") == '"a\nb"'

    def test_plain_text_is_not_quoted(self):
        assert _format_csv_cell("plain") == "plain"

    def test_none_becomes_empty(self):
        assert _format_csv_cell(None) == ""


class TestExternallyAuthoredCsv:
    """Files the module did not write itself (#258).

    ``round_trip`` above only ever loads bytes that ``save()`` produced, so it cannot
    see anything about how ``load()`` treats input from elsewhere -- which is the whole
    class of defect #258 belongs to. The README documents
    ``./tools/fetch_bills.py download-all --file your_bills.csv``, so a hand-authored index is a
    supported input, and for a non-technical audience "author a CSV" means Excel or
    Google Sheets. Both write a UTF-8 BOM by default.

    These cases therefore construct the file bytes directly rather than going through
    ``save()``.
    """

    HEADER = "id,title\n119-hr-1,Consolidated Appropriations Act\n"

    def test_bom_prefixed_csv_loads_its_records(self, tmp_path):
        # The reported bug: the BOM binds to the first header name, so 'id' reads as
        # '﻿id' and the required-column check rejects a file that has an id column.
        csv_path = tmp_path / "bills.csv"
        csv_path.write_bytes(b"\xef\xbb\xbf" + self.HEADER.encode("utf-8"))

        index = BillIndex(csv_path)

        assert index.get("119-hr-1")["title"] == "Consolidated Appropriations Act"

    def test_bom_is_not_left_inside_the_first_column_name(self, tmp_path):
        # Distinct from the load succeeding: a fix that only relaxed the *check* would
        # pass the test above while leaving every record keyed by '﻿id', which
        # would then be written back out as a corrupt header.
        csv_path = tmp_path / "bills.csv"
        csv_path.write_bytes(b"\xef\xbb\xbf" + self.HEADER.encode("utf-8"))

        index = BillIndex(csv_path)

        assert index.columns == ["id", "title"]
        assert list(index.get("119-hr-1").keys()) == ["id", "title"]

    def test_csv_without_a_bom_is_unaffected(self, tmp_path):
        # utf-8-sig strips a BOM only when one is present; this pins that the ordinary
        # tool-written file keeps loading identically.
        csv_path = tmp_path / "bills.csv"
        csv_path.write_bytes(self.HEADER.encode("utf-8"))

        index = BillIndex(csv_path)

        assert index.columns == ["id", "title"]
        assert index.get("119-hr-1")["title"] == "Consolidated Appropriations Act"

    @pytest.mark.parametrize(
        "prefix",
        [pytest.param(b"", id="no-bom"), pytest.param(b"\xef\xbb\xbf", id="bom")],
    )
    def test_csv_without_an_id_column_still_raises(self, tmp_path, prefix):
        # The guard the fix must not mask. Reading as utf-8-sig makes a BOM invisible
        # to the required-column check, so the check has to keep firing on a file that
        # genuinely has no id column -- with or without a BOM in front of it.
        csv_path = tmp_path / "bills.csv"
        csv_path.write_bytes(prefix + b"slug,title\n119-hr-1,An Act\n")

        with pytest.raises(ValueError, match="missing required column"):
            BillIndex(csv_path)

    def test_saved_csv_does_not_start_with_a_bom(self, tmp_path):
        # The write path stays utf-8 deliberately: reading utf-8-sig would happily
        # consume a BOM we emitted ourselves, so nothing else in the suite would notice
        # if the writers drifted to utf-8-sig. Asserted on the raw bytes rather than
        # inferred from a successful reload.
        csv_path = tmp_path / "bills.csv"
        index = BillIndex(csv_path)
        index.add_bills([{"id": "119-hr-1", "title": "An Act"}], save=True)

        raw = csv_path.read_bytes()

        assert not raw.startswith(b"\xef\xbb\xbf")
        assert raw.startswith(b"id,")


class TestUndecodableCsv:
    """A CSV that is not UTF-8 at all (#258).

    Same origin as the BOM case -- a spreadsheet export -- but a different failure:
    Excel's "CSV (Comma delimited)" writes the system codepage, so one smart quote or
    accented sponsor name in a Windows-1252 file makes ``load()`` raise a bare
    ``UnicodeDecodeError`` naming a byte offset and no file. Re-raised as a ValueError
    so it matches the missing-column contract callers already see from ``load()``.
    """

    def test_non_utf8_bytes_raise_a_valueerror_naming_the_file(self, tmp_path):
        csv_path = tmp_path / "bills.csv"
        # 0x92 is a Windows-1252 right single quote -- invalid as a UTF-8 start byte.
        csv_path.write_bytes(b"id,title\n119-hr-1,Nation\x92s Defense\n")

        with pytest.raises(ValueError) as excinfo:
            BillIndex(csv_path)

        message = str(excinfo.value)
        assert str(csv_path) in message
        assert "UTF-8" in message

    def test_the_original_decode_error_is_kept_as_the_cause(self, tmp_path):
        # Re-raising for readability should not throw away the byte offset a developer
        # would need to find the offending cell.
        csv_path = tmp_path / "bills.csv"
        csv_path.write_bytes(b"id,title\n119-hr-1,Nation\x92s Defense\n")

        with pytest.raises(ValueError) as excinfo:
            BillIndex(csv_path)

        assert isinstance(excinfo.value.__cause__, UnicodeDecodeError)


class TestQuoteWrappedTextRoundTrips:
    """Stored text that itself begins and ends with a straight quote (#256).

    These reach ``_decode_value`` with a string that starts and ends with a double
    quote -- not because of CSV syntax, but because ``csv.DictReader`` has already
    removed the CSV-level quoting and handed back the content. A decode that unquotes
    again cannot tell the two apart, and used to strip them either way.

    They were xfail(strict=True) while that second unquoting branch existed. It is
    gone: it was never the inverse of anything the module wrote (``_format_csv_cell``
    has never JSON-encoded a cell in any revision), so it could only ever damage these
    values. Kept as ordinary round-trip tests so the branch cannot come back unnoticed.
    """

    def test_text_wrapped_in_straight_quotes_keeps_its_quotes(self, tmp_path):
        # '"hello"' -> written as '"""hello"""' -> DictReader -> '"hello"'. The old
        # decode ran json.loads on that and got 'hello'; the quotes are content.
        value = '"hello"'
        assert round_trip(tmp_path, value) == value

    def test_quote_wrapped_text_that_is_not_valid_json_keeps_its_quotes(self, tmp_path):
        # The old JSONDecodeError fallback: '"a"b"' -> value[1:-1].replace('""', '"')
        # -> 'a"b'. Distinct from the branch above, and it mangled a different shape.
        value = '"a"b"'
        assert round_trip(tmp_path, value) == value

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param('"a\\nb"', id="literal-backslash-n-stays-two-characters"),
            pytest.param('"\\u00e9"', id="unicode-escape-stays-literal"),
        ],
    )
    def test_escape_sequences_inside_quotes_are_not_interpreted(self, tmp_path, value):
        # The second corruption mode: where the quoted text happened to parse as JSON,
        # the old decode did not merely unwrap it, it also resolved escape sequences
        # inside -- so '"a\\nb"' came back holding a real newline instead of the two
        # literal characters stored. The fallback branch did not share that behaviour,
        # so the two paths disagreed on the same input shape.
        assert round_trip(tmp_path, value) == value


class TestNumericLookingTextSurvives:
    """Text that looks numeric keeps its exact form (#256).

    These were ``xfail(strict=True)`` while ``int()`` was used as a type sniffer: it
    ran on every column, because ``_decode_value`` took a ``column`` argument and never
    read it, and it accepted Python literal syntax rather than a plain run of digits.
    Both are gone now that the decode returns text.

    Kept as ordinary round-trip tests, since each names a distinct way the sniff got it
    wrong and they are what stops one being reintroduced.
    """

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("2024", id="year-like-title"),
            pytest.param("117", id="congress-like-title"),
            pytest.param("0", id="zero-as-text"),
        ],
    )
    def test_digits_only_text_stays_text(self, tmp_path, value):
        # The reachable member of this family: any free-text field holding a bare year
        # or number tripped the old coercion, with no exotic input required at all.
        result = round_trip(tmp_path, value)
        assert result == value
        assert isinstance(result, str)

    def test_underscore_separated_digits_stay_text(self, tmp_path):
        # int('1_000') == 1000 was Python literal syntax leaking into a data decoder.
        assert round_trip(tmp_path, "1_000") == "1_000"

    @pytest.mark.parametrize("value", ["007", "+5", " 12 "])
    def test_numeric_looking_text_keeps_its_exact_form(self, tmp_path, value):
        # int() dropped leading zeros, sign prefixes and surrounding space.
        assert round_trip(tmp_path, value) == value


class TestDigitsOnlyIdIsUsable:
    """A digits-only ``id`` must not crash the caller that reads it (#256).

    This is the case that made the coercion more than latent. ``fetch_bills
    download-all --file <csv>`` reads a user-supplied index and does
    ``record["id"].strip()``. A hand-written CSV whose ``id`` is all digits decoded to
    an ``int``, and the download aborted with ``AttributeError: 'int' object has no
    attribute 'strip'`` -- a stack trace on a user-facing command, not a wrong answer.
    """

    def test_digits_only_id_survives_as_text(self, tmp_path):
        csv_path = tmp_path / "bills.csv"
        csv_path.write_text("id,title\n12345,Some Act\n119-hr-1,2024\n", encoding="utf-8")
        records = BillIndex(csv_path).bills

        # The exact expression the --file download path uses.
        assert [r["id"].strip() for r in records] == ["12345", "119-hr-1"]
        # And the digits-only title on the second row is untouched too.
        assert records[1]["title"] == "2024"


class TestParseBillId:
    """The slug codec: identity is ``{congress}-{type}-{number}`` and nothing else (#156).

    ADR 0013 settled that a bill's identity is the bare slug and that a version is a
    per-bill ordinal addressed as a separate token, so the ``:version`` suffix this
    module once documented is not part of the identity. ``parse_bill_id`` is the place
    that decides what an identity *is*, so it rejects anything else rather than
    quietly carrying a field no caller reads.

    Rejection is the parser's contract, not the CLI's behavior: ``fetch_bills
    download-all --file`` keeps accepting a legacy colon-suffixed row by stripping the
    suffix at the boundary (see ``tests/test_fetch_bills.py``). Strictness here is what
    lets that boundary be explicit about the compatibility it is providing.
    """

    def test_valid_slug_parses_to_its_three_parts(self):
        assert parse_bill_id("118-hr-4366") == ("118", "hr", "4366")

    def test_identifier_carries_no_version_field(self):
        """A permanently-empty ``version`` field would keep the retired model in the type."""
        assert BillIdentifier._fields == ("congress", "bill_type", "number")

    def test_version_suffix_is_rejected(self):
        """The case ADR 0013 retired: ``118-sconres-12:2`` is not an identity."""
        with pytest.raises(ValueError) as excinfo:
            parse_bill_id("118-sconres-12:2")

        assert "118-sconres-12:2" in str(excinfo.value)

    def test_non_slug_id_is_rejected_with_the_slug_named(self):
        """A digits-only id reaches this parser from a hand-written CSV (#256).

        It used to reach ``"12345".split("-")`` and die on a tuple unpack, which says
        nothing about what was wrong with the input.
        """
        with pytest.raises(ValueError) as excinfo:
            parse_bill_id("12345")

        assert "12345" in str(excinfo.value)

    def test_non_ascii_digits_are_rejected(self):
        """``str.isdigit`` alone accepts these, and no govinfo URL resolves them."""
        with pytest.raises(ValueError):
            parse_bill_id("١١٨-hr-٤٣٦٦")

        with pytest.raises(ValueError):
            parse_bill_id("118-hr-4³")

    def test_unknown_bill_type_is_rejected(self):
        with pytest.raises(ValueError) as excinfo:
            parse_bill_id("118-xx-4366")

        assert "xx" in str(excinfo.value)

    def test_make_bill_id_round_trips(self):
        assert parse_bill_id(make_bill_id(118, "hr", 4366)) == ("118", "hr", "4366")
