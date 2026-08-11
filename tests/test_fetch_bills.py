"""Tests for fetch_bills.py."""

import argparse
import json
import time

import httpx
import pytest
import respx

import fetch_govinfo as gi
from fetch_bills import (
    api_get,
    build_parser,
    cmd_download,
    cmd_download_all,
    congress_for_year,
    download_all_versions,
    download_version_xml,
    enumerate_bill_versions,
    fetch_all_committee_bills,
    fetch_text_versions,
    format_version_list,
    get_pdf_url,
    get_xml_url,
    sanitize_version_name,
    save_version,
    version_path,
)

TEST_API_KEY = "test-key"


def _govinfo_billstatus(congress: int, btype: str, number: int, *codes: str) -> bytes:
    """A govinfo BILLSTATUS body whose textVersions carry content/pkg URLs.

    Mirrors the real shape enumerate_versions parses: each item embeds a BILLS
    package URL so the version code is read from the URL, not the display name.
    """
    items = "".join(
        f"<item><type>{gi.resolve_code(c)[0]}</type><date>2023-06-2{i}T04:00:00Z</date>"
        f"<formats><item><url>{gi.package_content_url(f'BILLS-{congress}{btype}{number}{c}', 'xml')}</url>"
        f"</item></formats></item>"
        for i, c in enumerate(codes, 1)
    )
    return (
        f"<billStatus><bill><congress>{congress}</congress><type>{btype.upper()}</type>"
        f"<number>{number}</number><textVersions>{items}</textVersions></bill></billStatus>"
    ).encode()


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Prevent real sleeps during tests."""
    monkeypatch.setattr(time, "sleep", lambda _: None)


# --- api_get tests ---


class TestApiGet:
    @respx.mock
    def test_successful_request(self):
        respx.get("https://api.congress.gov/v3/bill/119/hr/1").respond(200, json={"bill": {"title": "Test"}})
        with httpx.Client() as client:
            result = api_get(client, "/bill/119/hr/1", api_key=TEST_API_KEY)
        assert result == {"bill": {"title": "Test"}}

    @respx.mock
    def test_retries_on_server_error(self):
        route = respx.get("https://api.congress.gov/v3/test")
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(200, json={"ok": True}),
        ]
        with httpx.Client() as client:
            result = api_get(client, "/test", api_key=TEST_API_KEY)
        assert result == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    def test_raises_after_exhausting_retries(self):
        respx.get("https://api.congress.gov/v3/test").respond(500)
        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPStatusError):
                api_get(client, "/test", api_key=TEST_API_KEY)


# --- fetch_all_committee_bills tests ---


class TestFetchAllCommitteeBills:
    @respx.mock
    def test_single_page(self):
        """When all bills fit in one page, only one API call."""
        respx.get("https://api.congress.gov/v3/committee/house/hsap00/bills").respond(
            200,
            json={
                "pagination": {"count": 3},
                "committee-bills": {
                    "bills": [
                        {"congress": 118, "type": "HR", "number": "1"},
                        {"congress": 118, "type": "HR", "number": "2"},
                        {"congress": 118, "type": "HR", "number": "3"},
                    ]
                },
            },
        )
        with httpx.Client() as client:
            bills = fetch_all_committee_bills(client, "house", "hsap00", api_key=TEST_API_KEY)
        assert len(bills) == 3

    @respx.mock
    def test_paginates_multiple_pages(self):
        """Fetches all pages when total exceeds page size."""
        route = respx.get("https://api.congress.gov/v3/committee/house/hsap00/bills")
        route.mock(
            side_effect=lambda request: httpx.Response(
                200,
                json=self._paginated_response(request),
            )
        )
        with httpx.Client() as client:
            bills = fetch_all_committee_bills(client, "house", "hsap00", api_key=TEST_API_KEY, page_size=3)
        assert len(bills) == 5
        assert route.call_count == 2

    def _paginated_response(self, request):
        offset = int(request.url.params.get("offset", 0))
        if offset == 0:
            return {
                "pagination": {"count": 5},
                "committee-bills": {"bills": [{"congress": 118, "type": "HR", "number": str(i)} for i in range(1, 4)]},
            }
        else:
            return {
                "pagination": {"count": 5},
                "committee-bills": {"bills": [{"congress": 118, "type": "HR", "number": str(i)} for i in range(4, 6)]},
            }


# --- congress_for_year tests ---


class TestCongressForYear:
    def test_known_values(self):
        assert congress_for_year(2024) == 118
        assert congress_for_year(2025) == 119
        assert congress_for_year(2026) == 119
        assert congress_for_year(1789) == 1
        assert congress_for_year(1790) == 1

    def test_year_range_produces_correct_set(self):
        congresses = sorted({congress_for_year(y) for y in range(2024, 2027)})
        assert congresses == [118, 119]

    def test_even_odd_year_same_congress(self):
        # Both years of a congress map to the same number
        assert congress_for_year(2023) == 118
        assert congress_for_year(2024) == 118


# --- sanitize_version_name tests ---


class TestSanitizeVersionName:
    def test_standard_name(self):
        assert sanitize_version_name("Reported in House") == "reported-in-house"

    def test_enrolled_bill(self):
        assert sanitize_version_name("Enrolled Bill") == "enrolled-bill"

    def test_strips_special_characters(self):
        assert sanitize_version_name("Public Law (No.)") == "public-law-no"

    def test_collapses_multiple_hyphens(self):
        assert sanitize_version_name("Some -- Name") == "some-name"

    def test_empty_string(self):
        assert sanitize_version_name("") == "unknown"


# --- format_version_list tests ---


class TestFormatVersionList:
    def test_numbered_output(self):
        versions = [
            {"date": "2023-06-27T04:00:00Z", "type": "Reported in House", "formats": []},
            {"date": "2023-07-27T04:00:00Z", "type": "Engrossed in House", "formats": []},
        ]
        result = format_version_list(versions)
        assert "1." in result
        assert "2." in result
        assert "Reported in House" in result
        assert "2023-06-27" in result

    def test_null_date(self):
        versions = [{"date": None, "type": "Enrolled Bill", "formats": []}]
        result = format_version_list(versions)
        assert "Enrolled Bill" in result
        assert "no date" in result

    def test_empty_list(self):
        result = format_version_list([])
        assert "No text versions" in result


# --- fetch_text_versions tests ---


class TestFetchTextVersions:
    @respx.mock
    def test_returns_versions_in_chronological_order(self):
        # API returns newest-first; fetch_text_versions sorts by date (oldest first)
        api_response = [
            {
                "date": "2023-07-27T04:00:00Z",
                "type": "Engrossed in House",
                "formats": [
                    {"type": "Formatted XML", "url": "https://congress.gov/eh.xml"},
                ],
            },
            {
                "date": "2023-06-27T04:00:00Z",
                "type": "Reported in House",
                "formats": [
                    {"type": "Formatted XML", "url": "https://congress.gov/rh.xml"},
                ],
            },
        ]
        respx.get("https://api.congress.gov/v3/bill/118/hr/4366/text").respond(
            200,
            json={"textVersions": api_response, "pagination": {"count": 2}},
        )
        with httpx.Client() as client:
            result = fetch_text_versions(client, 118, "hr", 4366, api_key=TEST_API_KEY)
        assert len(result) == 2
        assert result[0]["type"] == "Reported in House"
        assert result[1]["type"] == "Engrossed in House"

    @respx.mock
    def test_enrolled_bill_sorts_before_public_law(self):
        api_response = [
            {"date": "2024-03-10T04:00:00Z", "type": "Public Law", "formats": []},
            {"date": None, "type": "Enrolled Bill", "formats": []},
            {"date": "2023-06-27T04:00:00Z", "type": "Reported in House", "formats": []},
        ]
        respx.get("https://api.congress.gov/v3/bill/118/hr/1/text").respond(
            200,
            json={"textVersions": api_response, "pagination": {"count": 3}},
        )
        with httpx.Client() as client:
            result = fetch_text_versions(client, 118, "hr", 1, api_key=TEST_API_KEY)
        assert result[0]["type"] == "Reported in House"
        assert result[1]["type"] == "Enrolled Bill"
        assert result[2]["type"] == "Public Law"

    @respx.mock
    def test_returns_empty_list_when_no_versions(self):
        respx.get("https://api.congress.gov/v3/bill/118/hr/9999/text").respond(
            200,
            json={"textVersions": [], "pagination": {"count": 0}},
        )
        with httpx.Client() as client:
            result = fetch_text_versions(client, 118, "hr", 9999, api_key=TEST_API_KEY)
        assert result == []


# --- save_version tests ---


class TestSaveVersion:
    def test_creates_dir_and_file(self, tmp_path):
        content = b"<bill>test</bill>"
        path = save_version(content, tmp_path, 118, "hr", 4366, 1, "Reported in House")
        assert path.exists()
        assert path.read_bytes() == content

    def test_correct_filename(self, tmp_path):
        path = save_version(b"<xml/>", tmp_path, 119, "s", 100, 3, "Engrossed in Senate")
        assert path.name == "3_engrossed-in-senate.xml"
        assert path.parent.name == "119-s-100"

    def test_pdf_extension(self, tmp_path):
        path = save_version(b"%PDF-1.7", tmp_path, 118, "hr", 4366, 1, "Reported in House", ext="pdf")
        assert path.name == "1_reported-in-house.pdf"
        assert path.read_bytes() == b"%PDF-1.7"

    def test_existing_dir_no_error(self, tmp_path):
        save_version(b"<a/>", tmp_path, 118, "hr", 1, 1, "Introduced in House")
        path = save_version(b"<b/>", tmp_path, 118, "hr", 1, 2, "Reported in House")
        assert path.exists()


class TestVersionPath:
    def test_returns_expected_path(self, tmp_path):
        path = version_path(tmp_path, 118, "hr", 4366, 1, "Reported in House")
        assert path == tmp_path / "118-hr-4366" / "1_reported-in-house.xml"

    def test_pdf_extension(self, tmp_path):
        path = version_path(tmp_path, 118, "hr", 4366, 1, "Reported in House", ext="pdf")
        assert path == tmp_path / "118-hr-4366" / "1_reported-in-house.pdf"


class TestGetFormatUrls:
    FORMATS = [
        {"type": "Formatted Text", "url": "https://congress.gov/rh.htm"},
        {"type": "PDF", "url": "https://congress.gov/rh.pdf"},
        {"type": "Formatted XML", "url": "https://congress.gov/rh.xml"},
    ]

    def test_get_xml_url(self):
        assert get_xml_url({"formats": self.FORMATS}) == "https://congress.gov/rh.xml"

    def test_get_pdf_url(self):
        assert get_pdf_url({"formats": self.FORMATS}) == "https://congress.gov/rh.pdf"

    def test_get_pdf_url_absent(self):
        only_xml = [{"type": "Formatted XML", "url": "https://congress.gov/rh.xml"}]
        assert get_pdf_url({"formats": only_xml}) is None

    def test_get_pdf_url_no_formats(self):
        assert get_pdf_url({}) is None

    def test_already_downloaded_detected(self, tmp_path):
        path = version_path(tmp_path, 118, "hr", 4366, 1, "Reported in House")
        path.parent.mkdir(parents=True)
        path.write_bytes(b"<existing/>")
        assert path.exists()


# --- download_version_xml tests ---


class TestDownloadVersionXml:
    @respx.mock
    def test_returns_xml_bytes(self):
        xml_content = b"<bill><title>Test</title></bill>"
        respx.get("https://www.congress.gov/118/bills/hr4366/rh.xml").respond(
            200,
            content=xml_content,
            headers={"content-type": "application/xml"},
        )
        with httpx.Client() as client:
            result = download_version_xml(client, "https://www.congress.gov/118/bills/hr4366/rh.xml")
        assert result == xml_content

    @respx.mock
    def test_retries_on_server_error(self):
        route = respx.get("https://www.congress.gov/test.xml")
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(200, content=b"<ok/>"),
        ]
        with httpx.Client() as client:
            result = download_version_xml(client, "https://www.congress.gov/test.xml")
        assert result == b"<ok/>"
        assert route.call_count == 2

    @respx.mock
    def test_retries_on_429(self):
        route = respx.get("https://www.congress.gov/test.xml")
        route.side_effect = [
            httpx.Response(429),
            httpx.Response(200, content=b"<ok/>"),
        ]
        with httpx.Client() as client:
            result = download_version_xml(client, "https://www.congress.gov/test.xml")
        assert result == b"<ok/>"

    @respx.mock
    def test_raises_after_exhausting_retries(self):
        respx.get("https://www.congress.gov/fail.xml").respond(500)
        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPStatusError):
                download_version_xml(client, "https://www.congress.gov/fail.xml")

    @respx.mock
    def test_raises_on_4xx(self):
        respx.get("https://www.congress.gov/missing.xml").respond(404)
        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPStatusError):
                download_version_xml(client, "https://www.congress.gov/missing.xml")


class TestCmdDownloadFormats:
    TEXT_URL = "https://api.congress.gov/v3/bill/118/hr/4366/text"
    XML_URL = "https://www.congress.gov/118/bills/hr4366/rh.xml"
    PDF_URL = "https://www.congress.gov/118/bills/hr4366/rh.pdf"

    def _payload(self):
        return {
            "textVersions": [
                {
                    "date": "2023-06-27T04:00:00Z",
                    "type": "Reported in House",
                    "formats": [
                        {"type": "PDF", "url": self.PDF_URL},
                        {"type": "Formatted XML", "url": self.XML_URL},
                    ],
                }
            ]
        }

    def _args(self, tmp_path, fmt, source="api"):
        # source defaults to "api" here: these tests mock the Congress.gov API
        # URLs and exercise download_version's format handling, which is
        # source-independent. The shipped default source (govinfo) and its host
        # routing are pinned separately in TestSourceRouting.
        return argparse.Namespace(
            congress=118, bill_type="hr", number=4366, version=None, output_dir=tmp_path, format=fmt, source=source
        )

    @respx.mock
    def test_download_both_writes_xml_and_pdf(self, tmp_path):
        respx.get(self.TEXT_URL).respond(200, json=self._payload())
        respx.get(self.XML_URL).respond(200, content=b"<bill/>")
        respx.get(self.PDF_URL).respond(200, content=b"%PDF-1.7")
        with httpx.Client() as client:
            cmd_download(client, self._args(tmp_path, "both"), TEST_API_KEY)
        bill_dir = tmp_path / "118-hr-4366"
        assert (bill_dir / "1_reported-in-house.xml").read_bytes() == b"<bill/>"
        assert (bill_dir / "1_reported-in-house.pdf").read_bytes() == b"%PDF-1.7"

    @respx.mock
    def test_download_pdf_only(self, tmp_path):
        respx.get(self.TEXT_URL).respond(200, json=self._payload())
        respx.get(self.PDF_URL).respond(200, content=b"%PDF-1.7")
        with httpx.Client() as client:
            cmd_download(client, self._args(tmp_path, "pdf"), TEST_API_KEY)
        bill_dir = tmp_path / "118-hr-4366"
        assert (bill_dir / "1_reported-in-house.pdf").exists()
        assert not (bill_dir / "1_reported-in-house.xml").exists()

    def test_parser_format_defaults_to_xml(self):
        # XML is the authoritative published source and the default for both
        # subcommands; PDF is opt-in (the pre-publication / last-resort path).
        assert build_parser().parse_args(["download", "118", "hr", "4366"]).format == "xml"
        assert build_parser().parse_args(["download-all", "--start_year", "2024"]).format == "xml"

    @respx.mock
    def test_default_download_writes_the_xml_the_diff_consumes(self, tmp_path):
        """A default `download` must write the .xml that `diff_bill compare` reads.

        Args come from the real parser, not a hand-built Namespace: BOTH argparse
        defaults under test -- --format (xml) and --source (govinfo) -- come from
        the shipped parser, so a flip in either is caught here rather than masked by
        a test author's typing. The run therefore goes through the govinfo path (no
        key), the true default. The PDF route is mocked so a default of pdf/both
        would *succeed* and write a .pdf -- that way the no-PDF assertion fails on
        the regression instead of erroring on an unmocked request (passing for the
        wrong reason).

        Complements test_parser_format_defaults_to_xml rather than repeating it: that
        one pins the defaults' *values*, this one pins what a default run *produces*.
        A regression between flag and file -- GPO renames a format label so
        get_xml_url stops matching, or the default source flips to one that yields no
        XML -- leaves the defaults nominally correct while writing nothing and
        exiting 0. Only this test sees that.
        """
        respx.get(gi.billstatus_url(118, "hr", 4366)).respond(200, content=_govinfo_billstatus(118, "hr", 4366, "rh"))
        respx.get(gi.package_content_url("BILLS-118hr4366rh", "xml")).respond(200, content=b"<bill/>")
        respx.get(gi.package_content_url("BILLS-118hr4366rh", "pdf")).respond(200, content=b"%PDF-1.7")

        args = build_parser().parse_args(["download", "118", "hr", "4366", "--output-dir", str(tmp_path)])
        assert args.source == "govinfo"  # precondition: the shipped default under test
        with httpx.Client() as client:
            cmd_download(client, args, None)  # govinfo path takes no key

        bill_dir = tmp_path / "118-hr-4366"
        assert (bill_dir / "1_reported-in-house.xml").read_bytes() == b"<bill/>"
        # Fails if the default flips to pdf *or* both (#151, #131).
        assert not (bill_dir / "1_reported-in-house.pdf").exists()

    @respx.mock
    def test_default_download_all_writes_the_xml_the_diff_consumes(self, tmp_path):
        """The bulk path carries its own `--format` default, so it needs its own gate.

        `download` and `download-all` read the flag from separate subparsers (two
        `add_argument("--format", ...)` calls), so a flip in one is invisible to the
        other's test. Same construction as the single-bill case above: real parser
        args, real govinfo path, PDF route mocked so a default of pdf/both would
        succeed and be caught by the assertion rather than erroring on an unmocked
        request. Runs the `--file` form because it reaches `download_all_versions`
        without the API-side committee discovery a year range needs (#151).
        """
        csv_path = tmp_path / "bills.csv"
        csv_path.write_text("id\n118-hr-4366\n", encoding="utf-8")
        out = tmp_path / "out"
        respx.get(gi.billstatus_url(118, "hr", 4366)).respond(200, content=_govinfo_billstatus(118, "hr", 4366, "rh"))
        respx.get(gi.package_content_url("BILLS-118hr4366rh", "xml")).respond(200, content=b"<bill/>")
        respx.get(gi.package_content_url("BILLS-118hr4366rh", "pdf")).respond(200, content=b"%PDF-1.7")

        args = build_parser().parse_args(["download-all", "--file", str(csv_path), "--output-dir", str(out)])
        assert args.source == "govinfo"  # precondition: the shipped default under test
        with httpx.Client() as client:
            cmd_download_all(client, args, None)

        bill_dir = out / "118-hr-4366"
        assert (bill_dir / "1_reported-in-house.xml").read_bytes() == b"<bill/>"
        # Fails if download-all's default flips to pdf *or* both (#151, #131).
        assert not (bill_dir / "1_reported-in-house.pdf").exists()

    def test_parser_accepts_format_both(self):
        args = build_parser().parse_args(["download", "118", "hr", "4366", "--format", "both"])
        assert args.format == "both"


class TestSourceRouting:
    """--source picks which host serves a bill's versions (issue #10 step 6).

    One test per source pins the host actually hit, so a wiring regression that
    silently routes to the wrong source -- or ignores --source -- fails loudly.
    """

    def _args(self, tmp_path, source):
        return argparse.Namespace(
            congress=118, bill_type="hr", number=4366, version=None, output_dir=tmp_path, format="xml", source=source
        )

    @respx.mock
    def test_source_govinfo_hits_govinfo_not_congressgov(self, tmp_path):
        bs = respx.get(gi.billstatus_url(118, "hr", 4366)).respond(
            200, content=_govinfo_billstatus(118, "hr", 4366, "rh")
        )
        xml = respx.get(gi.package_content_url("BILLS-118hr4366rh", "xml")).respond(200, content=b"<bill/>")
        # Any Congress.gov API call must be a hard failure, not a silent fallback.
        api = respx.get("https://api.congress.gov/v3/bill/118/hr/4366/text").respond(500)
        with httpx.Client() as client:
            cmd_download(client, self._args(tmp_path, "govinfo"), None)
        assert bs.called and xml.called
        assert not api.called
        assert (tmp_path / "118-hr-4366" / "1_reported-in-house.xml").read_bytes() == b"<bill/>"

    @respx.mock
    def test_source_api_hits_congressgov_not_govinfo(self, tmp_path):
        payload = {
            "textVersions": [
                {
                    "date": "2023-06-27T04:00:00Z",
                    "type": "Reported in House",
                    "formats": [{"type": "Formatted XML", "url": "https://www.congress.gov/118/bills/hr4366/rh.xml"}],
                }
            ]
        }
        api = respx.get("https://api.congress.gov/v3/bill/118/hr/4366/text").respond(200, json=payload)
        xml = respx.get("https://www.congress.gov/118/bills/hr4366/rh.xml").respond(200, content=b"<bill/>")
        gov = respx.get(gi.billstatus_url(118, "hr", 4366)).respond(500)
        with httpx.Client() as client:
            cmd_download(client, self._args(tmp_path, "api"), TEST_API_KEY)
        assert api.called and xml.called
        assert not gov.called
        assert (tmp_path / "118-hr-4366" / "1_reported-in-house.xml").read_bytes() == b"<bill/>"


class TestPre113Guard:
    """govinfo bulk data starts at the 113th Congress; 111/112 and earlier 404
    per file (issue #10 trap 7, ADR 0004). Under the default --source govinfo a
    pre-113 request must fail fast with a message pointing at --source api, not
    404 per bill or silently produce nothing. --source api serves older
    Congresses and must be untouched by the guard.
    """

    def test_govinfo_pre113_enumeration_fails_fast(self):
        # No respx: the guard must fire before any network call.
        with httpx.Client() as client:
            with pytest.raises(gi.CongressNotAvailable) as exc:
                enumerate_bill_versions(client, 112, "hr", 1, source="govinfo", api_key=None)
        msg = str(exc.value)
        assert "113" in msg and "--source api" in msg

    @respx.mock
    def test_govinfo_113_is_allowed(self):
        # The floor itself (113) passes the guard and reaches BILLSTATUS.
        respx.get(gi.billstatus_url(113, "hr", 1)).respond(200, content=_govinfo_billstatus(113, "hr", 1, "rh"))
        with httpx.Client() as client:
            versions = enumerate_bill_versions(client, 113, "hr", 1, source="govinfo", api_key=None)
        assert len(versions) == 1

    @respx.mock
    def test_api_pre113_is_unaffected(self):
        # --source api still serves older Congresses; the guard is govinfo-only.
        respx.get("https://api.congress.gov/v3/bill/112/hr/1/text").respond(200, json={"textVersions": []})
        with httpx.Client() as client:
            versions = enumerate_bill_versions(client, 112, "hr", 1, source="api", api_key=TEST_API_KEY)
        assert versions == []

    def test_download_all_pre113_year_range_fails_before_discovery(self, monkeypatch):
        # A purely pre-113 year range under govinfo must fail fast, not run the
        # (API) committee discovery and then silently find zero fetchable bills.
        import fetch_bills

        def _boom(*a, **k):
            raise AssertionError("committee discovery ran before the pre-113 guard")

        monkeypatch.setattr(fetch_bills, "fetch_all_committee_bills", _boom)
        args = build_parser().parse_args(["download-all", "--start_year", "2011", "--end_year", "2012"])
        assert args.source == "govinfo"
        with httpx.Client() as client:
            with pytest.raises(gi.CongressNotAvailable):
                cmd_download_all(client, args, None)


class TestCmdDownloadAllYearRange:
    def test_start_year_without_end_year_uses_current_year(self, monkeypatch):
        """Regression: with only --start_year, end_year is resolved via
        datetime.datetime.now() (the bare datetime.now() raised AttributeError
        because the module, not the class, is imported). Committee fetch is
        stubbed empty so the year-resolution path runs offline."""
        import fetch_bills

        monkeypatch.setattr(fetch_bills, "fetch_all_committee_bills", lambda *a, **k: [])
        args = build_parser().parse_args(["download-all", "--start_year", "2024"])
        with httpx.Client() as client:
            cmd_download_all(client, args, TEST_API_KEY)  # must not raise


class TestCmdDownloadAllFromFile:
    """`download-all --file` against a hand-written CSV (#156).

    This path reads a user-supplied index, so it meets rows the strict slug codec
    rejects. ADR 0013 made identity the bare slug, but it did not ask this command to
    stop serving a CSV that works today: a `:version` suffix identifies a bill perfectly
    well and used to download it, so it still does, with a warning. Only a row that
    names no bill at all is skipped, and a skip never aborts the run: every remaining
    row is still attempted, and the malformed input is reported at the end by an exit
    status, the way this file's other input errors are.
    """

    def _run(self, tmp_path, monkeypatch, rows):
        """Run the command over `rows`; return the attempted bills and the exit status.

        The attempted bills carry `congress` and `number` as ints, the type
        `download_all_versions` declares. They used to be the strings `parse_bill_id`
        returns, and this stub is why nothing noticed: it replaces the one function
        that would have used them, so the whole class asserted on a call that never
        happened for real. Under the real callee the govinfo floor check compared a
        str to an int and the command died on its first row (#151).
        """
        import fetch_bills

        csv_path = tmp_path / "bills.csv"
        csv_path.write_text("id\n" + "".join(f"{row}\n" for row in rows), encoding="utf-8")

        downloaded = []
        monkeypatch.setattr(
            fetch_bills,
            "download_all_versions",
            lambda client, **kwargs: downloaded.append((kwargs["congress"], kwargs["bill_type"], kwargs["number"])),
        )

        args = build_parser().parse_args(
            ["download-all", "--file", str(csv_path), "--output-dir", str(tmp_path / "out")]
        )
        status = 0
        with httpx.Client() as client:
            try:
                cmd_download_all(client, args, TEST_API_KEY)
            except SystemExit as exc:
                status = exc.code
        return downloaded, status

    def test_legacy_version_suffix_still_downloads_the_bill(self, tmp_path, monkeypatch, capsys):
        downloaded, status = self._run(tmp_path, monkeypatch, ["118-sconres-12:2"])

        assert downloaded == [(118, "sconres", 12)]
        # A served legacy row is not an error: the run is clean and exits clean.
        assert status == 0
        err = capsys.readouterr().err
        assert "118-sconres-12:2" in err
        assert "ADR 0013" in err

    def test_unusable_row_is_skipped_without_aborting_the_run(self, tmp_path, monkeypatch, capsys):
        """The good row after the bad one must still download.

        A bare raise here would abort mid-run, after earlier bills had already been
        written -- a partial corpus that looks like a complete one.
        """
        downloaded, _ = self._run(tmp_path, monkeypatch, ["12345", "119-hr-1"])

        assert downloaded == [(119, "hr", 1)]
        assert "Skipping unusable row '12345'" in capsys.readouterr().err

    def test_skipped_row_makes_the_whole_run_exit_nonzero(self, tmp_path, monkeypatch):
        """A partial corpus must not look like a complete one to a script.

        Before the row-level skip existed, an unparseable row crashed the command and
        `download-all ... && <next step>` stopped there. Skipping keeps the run going,
        so the exit status is what still tells a scripted caller the input was bad.
        """
        _, status = self._run(tmp_path, monkeypatch, ["12345", "119-hr-1"])

        assert status == 1

    def test_run_summarizes_what_it_processed_and_skipped(self, tmp_path, monkeypatch, capsys):
        downloaded, _ = self._run(tmp_path, monkeypatch, ["119-hr-1", "118-sconres-12:2", "12345", "not-a-bill-9"])

        assert downloaded == [(119, "hr", 1), (118, "sconres", 12)]
        # "Processed", not "downloaded": a bill with no text versions available is
        # attempted and counted here too, so the stronger word would overclaim.
        assert "Processed 2 bills, skipped 2 unusable rows." in capsys.readouterr().err

    def test_unusable_row_is_not_blamed_on_its_version_suffix(self, tmp_path, monkeypatch, capsys):
        """A row that names no bill is skipped, with no note about the suffix.

        `12345:2` is unusable for reasons the suffix has nothing to do with, so the
        compatibility note would point at the wrong part of the row.
        """
        downloaded, _ = self._run(tmp_path, monkeypatch, ["12345:2"])

        assert downloaded == []
        err = capsys.readouterr().err
        assert "Skipping unusable row '12345:2'" in err
        assert "ADR 0013" not in err


class TestLazyApiKeyResolution:
    """govinfo #10 steps 5-6: key resolution (and its DEMO_KEY warning) fires only
    on paths that actually reach the Congress.gov API. Never on ``--help`` / no
    args / argparse errors (step 5), and -- once --source lands (step 6) -- never
    on the default keyless govinfo path either. Only ``--source api`` and year-range
    committee discovery resolve a key.
    """

    def _spy_get_api_key(self, monkeypatch):
        """Replace get_api_key with a spy that records each invocation."""
        calls = []

        def spy():
            calls.append(True)
            return "spy-key"

        monkeypatch.setattr("fetch_bills.get_api_key", spy)
        return calls

    def test_no_args_does_not_resolve_key(self, monkeypatch):
        import fetch_bills

        calls = self._spy_get_api_key(monkeypatch)
        monkeypatch.setattr("sys.argv", ["fetch_bills.py"])
        with pytest.raises(SystemExit) as exc:
            fetch_bills.main()
        assert exc.value.code == 0
        assert calls == []

    def test_help_does_not_resolve_key(self, monkeypatch):
        import fetch_bills

        calls = self._spy_get_api_key(monkeypatch)
        monkeypatch.setattr("sys.argv", ["fetch_bills.py", "--help"])
        with pytest.raises(SystemExit) as exc:
            fetch_bills.main()
        assert exc.value.code == 0
        assert calls == []

    def test_argparse_error_does_not_resolve_key(self, monkeypatch):
        import fetch_bills

        calls = self._spy_get_api_key(monkeypatch)
        # 'versions' requires congress/bill_type/number; omitting them makes
        # argparse exit(2) during parse_args, before any key resolution.
        monkeypatch.setattr("sys.argv", ["fetch_bills.py", "versions"])
        with pytest.raises(SystemExit) as exc:
            fetch_bills.main()
        assert exc.value.code != 0
        assert calls == []

    def test_api_source_command_resolves_key(self, monkeypatch):
        # Proves the spy CAN fire: an --source api command resolves the key, so the
        # "not resolved" assertions (default govinfo, help, no-args) can't pass vacuously.
        import fetch_bills

        calls = self._spy_get_api_key(monkeypatch)
        monkeypatch.setattr("fetch_bills.cmd_versions", lambda *a, **k: None)
        monkeypatch.setattr("sys.argv", ["fetch_bills.py", "versions", "118", "hr", "4366", "--source", "api"])
        fetch_bills.main()
        assert calls == [True]

    def test_default_govinfo_command_resolves_no_key(self, monkeypatch):
        # The #10 payoff: the default (keyless) govinfo path must NOT resolve a key.
        import fetch_bills

        calls = self._spy_get_api_key(monkeypatch)
        monkeypatch.setattr("fetch_bills.cmd_versions", lambda *a, **k: None)
        monkeypatch.setattr("sys.argv", ["fetch_bills.py", "versions", "118", "hr", "4366"])
        fetch_bills.main()
        assert calls == []

    def test_year_range_resolves_key_even_on_default_source(self, monkeypatch):
        # Year-range discovery is the committee endpoint (API) even under govinfo,
        # so download-all without --file resolves a key regardless of --source.
        import fetch_bills

        calls = self._spy_get_api_key(monkeypatch)
        monkeypatch.setattr("fetch_bills.cmd_download_all", lambda *a, **k: None)
        monkeypatch.setattr("sys.argv", ["fetch_bills.py", "download-all", "--start_year", "2024"])
        fetch_bills.main()
        assert calls == [True]

    def test_help_emits_no_demo_key_warning(self, monkeypatch, capsys):
        # Consumer-visible symptom, isolated from any real key (env or .env) so
        # the absence is due to lazy resolution, not a key being present.
        import fetch_bills

        monkeypatch.setattr("fetch_bills.load_dotenv", lambda *a, **k: None)
        monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
        monkeypatch.setattr("sys.argv", ["fetch_bills.py", "--help"])
        with pytest.raises(SystemExit):
            fetch_bills.main()
        assert "DEMO_KEY" not in capsys.readouterr().err

    def test_api_source_emits_demo_key_warning(self, monkeypatch, capsys):
        # Known-bad pairing: no key + an --source api command -> the warning MUST
        # appear, otherwise the stderr-absence tests are vacuous.
        import fetch_bills

        monkeypatch.setattr("fetch_bills.load_dotenv", lambda *a, **k: None)
        monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
        monkeypatch.setattr("fetch_bills.cmd_versions", lambda *a, **k: None)
        monkeypatch.setattr("sys.argv", ["fetch_bills.py", "versions", "118", "hr", "4366", "--source", "api"])
        fetch_bills.main()
        assert "DEMO_KEY" in capsys.readouterr().err

    def test_default_govinfo_emits_no_demo_key_warning(self, monkeypatch, capsys):
        # Consumer-visible payoff: with no key, the default govinfo command must not
        # emit the DEMO_KEY barrier warning. Isolated from any real key so the
        # absence is due to lazy-per-source resolution, not a key being present.
        import fetch_bills

        monkeypatch.setattr("fetch_bills.load_dotenv", lambda *a, **k: None)
        monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
        monkeypatch.setattr("fetch_bills.cmd_versions", lambda *a, **k: None)
        monkeypatch.setattr("sys.argv", ["fetch_bills.py", "versions", "118", "hr", "4366"])
        fetch_bills.main()
        assert "DEMO_KEY" not in capsys.readouterr().err


# --- content guard: reject govinfo error pages / empty bodies (#10 trap 1) ---

# A missing govinfo package redirects to an error page. With follow_redirects the
# response is 200 + text/html + ~44KB of markup; without it, an empty 302 body.
# Either one, written into a {n}_{label}.{ext} file, is a corrupt bill silently
# entering the corpus. The guard validates content-type AND magic bytes before
# save_version, independent of redirect policy.
_HTML_ERROR_PAGE = b'<!DOCTYPE html>\n<html lang="en"><head><title>Error</title></head><body>404</body></html>'


class TestValidateDownloaded:
    """Unit tests for the pure content guard."""

    def test_accepts_real_xml_with_declaration(self):
        from fetch_bills import validate_downloaded

        validate_downloaded(b'<?xml version="1.0"?>\n<bill/>', "application/xml", "xml", "u")

    def test_accepts_xml_with_utf8_bom(self):
        # A future source could prepend a UTF-8 BOM; the guard must not reject
        # otherwise-valid XML for it. (No corpus file has one today.)
        from fetch_bills import validate_downloaded

        validate_downloaded(b"\xef\xbb\xbf<?xml version='1.0'?><bill/>", "application/xml", "xml", "u")

    def test_accepts_bare_markup_without_declaration(self):
        # Existing corpus fixtures and the Congress.gov path emit XML without an
        # <?xml prolog; the guard must accept generic markup, only rejecting HTML.
        from fetch_bills import validate_downloaded

        validate_downloaded(b"<bill/>", None, "xml", "u")

    def test_accepts_real_pdf(self):
        from fetch_bills import validate_downloaded

        validate_downloaded(b"%PDF-1.4\n...", "application/pdf", "pdf", "u")

    def test_rejects_html_page_as_xml(self):
        from fetch_bills import validate_downloaded

        with pytest.raises(ValueError):
            validate_downloaded(_HTML_ERROR_PAGE, "text/html", "xml", "u")

    def test_rejects_html_page_as_pdf(self):
        from fetch_bills import validate_downloaded

        with pytest.raises(ValueError):
            validate_downloaded(_HTML_ERROR_PAGE, "text/html", "pdf", "u")

    def test_rejects_html_body_even_if_content_type_lies(self):
        # A spoofed/absent content-type must not let an HTML body through: the
        # magic-byte check is independent of the header.
        from fetch_bills import validate_downloaded

        with pytest.raises(ValueError):
            validate_downloaded(_HTML_ERROR_PAGE, "application/xml", "xml", "u")

    def test_rejects_empty_body(self):
        # The follow_redirects=False case: an empty 302 body must not be saved as
        # a zero-byte bill version.
        from fetch_bills import validate_downloaded

        with pytest.raises(ValueError):
            validate_downloaded(b"", None, "xml", "u")

    def test_rejects_xml_bytes_for_pdf(self):
        from fetch_bills import validate_downloaded

        with pytest.raises(ValueError):
            validate_downloaded(b"<?xml version='1.0'?>", "application/xml", "pdf", "u")


class TestDownloadGuardIntegration:
    """The guard reaches cmd_download: a bad body writes a .error marker, no data file."""

    XML_URL = "https://www.congress.gov/118/bills/hr4366/rh.xml"
    PDF_URL = "https://www.congress.gov/118/bills/hr4366/rh.pdf"

    def _payload(self):
        return {
            "textVersions": [
                {
                    "date": "2023-06-27T04:00:00Z",
                    "type": "Reported in House",
                    "formats": [
                        {"type": "PDF", "url": self.PDF_URL},
                        {"type": "Formatted XML", "url": self.XML_URL},
                    ],
                }
            ]
        }

    def _args(self, tmp_path, fmt):
        return argparse.Namespace(
            congress=118, bill_type="hr", number=4366, version=None, output_dir=tmp_path, format=fmt, source="api"
        )

    @respx.mock
    def test_html_error_page_not_saved_as_xml(self, tmp_path):
        respx.get("https://api.congress.gov/v3/bill/118/hr/4366/text").respond(200, json=self._payload())
        respx.get(self.XML_URL).respond(200, content=_HTML_ERROR_PAGE, headers={"content-type": "text/html"})
        with httpx.Client() as client:
            cmd_download(client, self._args(tmp_path, "xml"), TEST_API_KEY)
        bill_dir = tmp_path / "118-hr-4366"
        assert not (bill_dir / "1_reported-in-house.xml").exists()
        assert (bill_dir / "1_reported-in-house.xml.error").exists()

    @respx.mock
    def test_html_error_page_not_saved_as_pdf(self, tmp_path):
        respx.get("https://api.congress.gov/v3/bill/118/hr/4366/text").respond(200, json=self._payload())
        respx.get(self.PDF_URL).respond(200, content=_HTML_ERROR_PAGE, headers={"content-type": "text/html"})
        with httpx.Client() as client:
            cmd_download(client, self._args(tmp_path, "pdf"), TEST_API_KEY)
        bill_dir = tmp_path / "118-hr-4366"
        assert not (bill_dir / "1_reported-in-house.pdf").exists()
        assert (bill_dir / "1_reported-in-house.pdf.error").exists()

    @respx.mock
    def test_valid_content_still_saves(self, tmp_path):
        respx.get("https://api.congress.gov/v3/bill/118/hr/4366/text").respond(200, json=self._payload())
        respx.get(self.XML_URL).respond(
            200, content=b'<?xml version="1.0"?><bill/>', headers={"content-type": "application/xml"}
        )
        respx.get(self.PDF_URL).respond(200, content=b"%PDF-1.7\n", headers={"content-type": "application/pdf"})
        with httpx.Client() as client:
            cmd_download(client, self._args(tmp_path, "both"), TEST_API_KEY)
        bill_dir = tmp_path / "118-hr-4366"
        assert (bill_dir / "1_reported-in-house.xml").exists()
        assert (bill_dir / "1_reported-in-house.pdf").exists()
        assert not (bill_dir / "1_reported-in-house.xml.error").exists()


# ---- `search` subcommand: title discovery over local BILLSTATUS ZIPs (#240) --


def _write_search_corpus(dirpath):
    """A minimal local BILLSTATUS ZIP with one approps + one non-approps bill."""
    import zipfile

    def doc(number, title, code):
        return (
            f"<billStatus><bill><congress>118</congress><type>HR</type>"
            f"<number>{number}</number><title>{title}</title>"
            f"<committees><item><systemCode>{code}</systemCode></item></committees>"
            f"</bill></billStatus>"
        ).encode()

    with zipfile.ZipFile(dirpath / "118-hr.zip", "w") as zf:
        zf.writestr("BILLSTATUS-118hr4366.xml", doc(4366, "Commerce, Justice, Science Appropriations Act", "hsap00"))
        zf.writestr("BILLSTATUS-118hr5.xml", doc(5, "Parents Bill of Rights Act", "hsed00"))


class TestSearchCommand:
    def test_title_search_prints_matches(self, tmp_path, capsys):
        _write_search_corpus(tmp_path)
        args = build_parser().parse_args(["search", "justice", "science", "--billstatus-dir", str(tmp_path)])
        with httpx.Client() as client:
            from fetch_bills import cmd_search

            rc = cmd_search(client, args, None)
        out = capsys.readouterr().out
        assert rc == 0  # grep-style: matches found
        assert "118-hr-4366" in out
        assert "118-hr-5" not in out

    def test_output_is_tab_separated_id_then_title(self, tmp_path, capsys):
        # Locks the output contract the README documents (`<bill_id>\t<title>`), so it
        # can't silently drift from the docs downstream consumers rely on.
        _write_search_corpus(tmp_path)
        args = build_parser().parse_args(["search", "justice", "science", "--billstatus-dir", str(tmp_path)])
        with httpx.Client() as client:
            from fetch_bills import cmd_search

            cmd_search(client, args, None)
        line = capsys.readouterr().out.strip()
        assert line == "118-hr-4366\tCommerce, Justice, Science Appropriations Act"

    def test_appropriations_facet_filters_by_committee(self, tmp_path, capsys):
        _write_search_corpus(tmp_path)
        # Both titles contain "act"; the facet keeps only the approps-referred bill.
        args = build_parser().parse_args(["search", "act", "--appropriations", "--billstatus-dir", str(tmp_path)])
        with httpx.Client() as client:
            from fetch_bills import cmd_search

            cmd_search(client, args, None)
        out = capsys.readouterr().out
        assert "118-hr-4366" in out
        assert "118-hr-5" not in out

    def test_facet_absent_returns_non_appropriations_bills(self, tmp_path, capsys):
        _write_search_corpus(tmp_path)
        args = build_parser().parse_args(["search", "act", "--billstatus-dir", str(tmp_path)])
        with httpx.Client() as client:
            from fetch_bills import cmd_search

            cmd_search(client, args, None)
        out = capsys.readouterr().out
        assert "118-hr-4366" in out
        assert "118-hr-5" in out

    def test_congress_and_type_filters_narrow_the_index(self, tmp_path, capsys):
        import zipfile

        def doc(congress, btype, number, title):
            return (
                f"<billStatus><bill><congress>{congress}</congress><type>{btype.upper()}</type>"
                f"<number>{number}</number><title>{title}</title>"
                f"<committees></committees></bill></billStatus>"
            ).encode()

        # Two congresses, two types; same title token in each so only the filter distinguishes.
        with zipfile.ZipFile(tmp_path / "118-hr.zip", "w") as zf:
            zf.writestr("BILLSTATUS-118hr1.xml", doc(118, "hr", 1, "Defense Act"))
        with zipfile.ZipFile(tmp_path / "119-hr.zip", "w") as zf:
            zf.writestr("BILLSTATUS-119hr1.xml", doc(119, "hr", 1, "Defense Act"))
        with zipfile.ZipFile(tmp_path / "118-s.zip", "w") as zf:
            zf.writestr("BILLSTATUS-118s1.xml", doc(118, "s", 1, "Defense Act"))

        args = build_parser().parse_args(
            ["search", "defense", "--congress", "118", "--type", "hr", "--billstatus-dir", str(tmp_path)]
        )
        with httpx.Client() as client:
            from fetch_bills import cmd_search

            cmd_search(client, args, None)
        out = capsys.readouterr().out
        assert "118-hr-1" in out
        assert "119-hr-1" not in out  # filtered by --congress
        assert "118-s-1" not in out  # filtered by --type

    def test_main_propagates_search_exit_code(self, tmp_path, monkeypatch):
        # The CLI/agent-visible contract is the process exit code, which flows through
        # main()'s sys.exit(cmd_search(...)) -- not just cmd_search's return. Lock it
        # end-to-end so the wiring can't silently regress to always-0.
        import fetch_bills

        _write_search_corpus(tmp_path)
        d = str(tmp_path)

        monkeypatch.setattr("sys.argv", ["fetch_bills", "search", "justice", "science", "--billstatus-dir", d])
        with pytest.raises(SystemExit) as exc:
            fetch_bills.main()
        assert exc.value.code == 0  # match found

        monkeypatch.setattr("sys.argv", ["fetch_bills", "search", "zzz-nomatch", "--billstatus-dir", d])
        with pytest.raises(SystemExit) as exc:
            fetch_bills.main()
        assert exc.value.code == 1  # searched, nothing matched

        # Exit 2 (no index) must also propagate through main()'s sys.exit wiring, not
        # just cmd_search's return -- point an empty dir at it.
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr("sys.argv", ["fetch_bills", "search", "anything", "--billstatus-dir", str(empty)])
        with pytest.raises(SystemExit) as exc:
            fetch_bills.main()
        assert exc.value.code == 2  # no index to search

    def test_missing_index_message_distinct_from_no_match(self, tmp_path, capsys):
        # A fresh clone has no BILLSTATUS index; that must not read as "your query
        # matched nothing." Empty dir -> the build-the-index message.
        args = build_parser().parse_args(["search", "anything", "--billstatus-dir", str(tmp_path)])
        with httpx.Client() as client:
            from fetch_bills import cmd_search

            rc = cmd_search(client, args, None)
        err = capsys.readouterr().err
        assert rc == 2  # grep-style: can't search (no index)
        assert "No BILLSTATUS index found" in err
        # Point a fresh-clone user at the lightweight on-ramp (#242), not the heavy
        # all-of-112-119 fetch that was the only documented path before it.
        assert "fetch-index" in err

    def test_genuine_no_match_message_when_index_present(self, tmp_path, capsys):
        # Index present but nothing matches -> the no-match message, NOT the
        # missing-index one (the distinction the message split exists to make).
        _write_search_corpus(tmp_path)
        args = build_parser().parse_args(["search", "nonexistent-token-xyz", "--billstatus-dir", str(tmp_path)])
        with httpx.Client() as client:
            from fetch_bills import cmd_search

            rc = cmd_search(client, args, None)
        err = capsys.readouterr().err
        assert rc == 1  # grep-style: searched, nothing matched
        assert "No bills matched" in err
        assert "No BILLSTATUS index found" not in err


# ---- `fetch-index` subcommand: lightweight scoped BILLSTATUS fetch (#242) --------


def _fake_download_landing(*zip_names):
    """A ``download_archives`` stub that lands the given ZIP names (simulates success).

    ``cmd_fetch_index`` verifies the requested archive is on disk after the run, so a
    stub that only returns paths without writing them reads as a *failed* fetch.
    """

    def _fake(from_congress, to_congress, *, bill_types, destination):
        paths = []
        for name in zip_names:
            path = destination / name
            path.write_bytes(b"")
            paths.append(path)
        return paths

    return _fake


class TestFetchIndexCommand:
    """`fetch-index`: a scoped BILLSTATUS fetch so `search` has a usable on-ramp (#242).

    Reuses ``fetch_bill_archives.download_archives`` (download-only, keyless) to pull
    just the scoped ZIP into ``bills/``, leaving ``search`` purely offline.
    """

    def test_requires_congress(self):
        # --congress is the scope; without it there is no lightweight slice to fetch,
        # so argparse must reject the call rather than fall back to fetching everything.
        with pytest.raises(SystemExit):
            build_parser().parse_args(["fetch-index"])

    def test_wires_scoped_single_type_download(self, tmp_path, monkeypatch):
        import fetch_bills

        calls = {}

        def fake_download(from_congress, to_congress, *, bill_types, destination):
            calls.update(
                from_congress=from_congress,
                to_congress=to_congress,
                bill_types=bill_types,
                destination=destination,
            )
            (destination / "118-hr.zip").write_bytes(b"")  # simulate the landed archive
            return [destination / "118-hr.zip"]

        monkeypatch.setattr(fetch_bills, "download_archives", fake_download)
        args = build_parser().parse_args(
            ["fetch-index", "--congress", "118", "--type", "hr", "--billstatus-dir", str(tmp_path)]
        )
        from fetch_bills import cmd_fetch_index

        rc = cmd_fetch_index(None, args, None)
        assert rc == 0  # every requested archive present after the run
        assert calls["from_congress"] == 118
        assert calls["to_congress"] == 118  # single congress: the lightweight slice
        assert calls["bill_types"] == ["hr"]
        # Resolved against cwd so it points where `search` reads (not script-relative).
        assert calls["destination"] == tmp_path.resolve()

    def test_type_omitted_fetches_all_types_for_the_congress(self, tmp_path, monkeypatch):
        import fetch_bills

        calls = {}

        def fake_download(from_congress, to_congress, *, bill_types, destination):
            calls["bill_types"] = bill_types
            return []

        monkeypatch.setattr(fetch_bills, "download_archives", fake_download)
        args = build_parser().parse_args(["fetch-index", "--congress", "118", "--billstatus-dir", str(tmp_path)])
        from fetch_bills import cmd_fetch_index

        cmd_fetch_index(None, args, None)
        assert calls["bill_types"] is None  # None -> download_archives fetches every type

    def test_is_keyless(self):
        # govinfo bulk data: no Congress.gov key. requires_api_key must stay False so
        # main() never resolves a key or prints the DEMO_KEY warning for a fetch-index run.
        import fetch_bills

        args = build_parser().parse_args(["fetch-index", "--congress", "118", "--type", "hr"])
        assert fetch_bills.requires_api_key(args) is False

    def test_exits_nonzero_when_archive_missing(self, tmp_path, monkeypatch, capsys):
        # A 404 (bad congress/type) or network failure makes download_archives write a
        # .error marker and return no path, leaving the requested ZIP absent. fetch-index
        # must surface that and exit non-zero -- not print "ready" and exit 0, which would
        # dead-end in `search` exiting 2 and telling the user to re-run fetch-index.
        import fetch_bills

        monkeypatch.setattr(fetch_bills, "download_archives", lambda *a, **k: [])
        args = build_parser().parse_args(
            ["fetch-index", "--congress", "118", "--type", "hr", "--billstatus-dir", str(tmp_path)]
        )
        from fetch_bills import cmd_fetch_index

        rc = cmd_fetch_index(None, args, None)
        assert rc == 1
        err = capsys.readouterr().err
        assert "Failed to fetch" in err
        assert "118-hr.zip" in err  # names the archive the user expected

    def test_main_propagates_fetch_index_exit_code(self, tmp_path, monkeypatch):
        # Mirror the search exit-code contract: a fetch failure must flow through
        # main()'s sys.exit wiring so scripts/agents can branch on it.
        import fetch_bills

        monkeypatch.setattr(fetch_bills, "download_archives", lambda *a, **k: [])
        monkeypatch.setattr(
            "sys.argv",
            ["fetch_bills", "fetch-index", "--congress", "118", "--type", "hr", "--billstatus-dir", str(tmp_path)],
        )
        with pytest.raises(SystemExit) as exc:
            fetch_bills.main()
        assert exc.value.code == 1

    def test_main_routes_and_succeeds(self, tmp_path, monkeypatch):
        # Happy-path routing: main() dispatches `fetch-index` to the download and exits 0
        # when the archive lands.
        import fetch_bills

        monkeypatch.setattr(fetch_bills, "download_archives", _fake_download_landing("118-hr.zip"))
        monkeypatch.setattr(
            "sys.argv",
            ["fetch_bills", "fetch-index", "--congress", "118", "--type", "hr", "--billstatus-dir", str(tmp_path)],
        )
        with pytest.raises(SystemExit) as exc:
            fetch_bills.main()
        assert exc.value.code == 0


# ---- XML-less gap markers, CLI wiring (#230) ---------------------------------


def _gap_billstatus(items: str) -> bytes:
    return (
        "<billStatus><bill><congress>118</congress><type>HR</type><number>3496</number>"
        f"<textVersions>{items}</textVersions></bill></billStatus>"
    ).encode()


def _gap_item(type_name: str, date: str, code: str | None = None) -> str:
    url = ""
    if code is not None:
        pkg = f"BILLS-118hr3496{code}"
        url = f"<formats><item><url>https://www.govinfo.gov/content/pkg/{pkg}/xml/{pkg}.xml</url></item></formats>"
    return f"<item><type>{type_name}</type><date>{date}</date>{url}</item>"


@respx.mock
def test_download_writes_gap_marker_for_an_all_gap_bill(tmp_path, monkeypatch):
    # #226's real evidence shape (118-hr-3496): every declared version is XML-less,
    # so enumeration yields NO downloadable versions and cmd_download takes its
    # "No text versions available" early return. The marker must still be written --
    # that early return is exactly the case the marker exists to record.
    body = _gap_billstatus(
        _gap_item("Introduced in House", "2023-05-01") + _gap_item("Reported in House", "2023-06-01")
    )
    respx.get(gi.billstatus_url(118, "hr", 3496)).mock(return_value=httpx.Response(200, content=body))
    args = argparse.Namespace(
        congress=118,
        bill_type="hr",
        number=3496,
        version=None,
        format="xml",
        output_dir=tmp_path,
        source="govinfo",
    )
    with httpx.Client() as client:
        cmd_download(client, args, None)
    marker = tmp_path / "118-hr-3496" / gi.GAP_MARKER_NAME
    assert marker.exists(), "all-gap bill wrote no marker"
    payload = json.loads(marker.read_text())
    assert [g["code"] for g in payload["gap_versions"]] == ["ih", "rh"]


@respx.mock
def test_download_writes_no_gap_marker_when_all_versions_served(tmp_path):
    # Negative control: proves the marker above is a real signal, not written on
    # every download.
    body = _gap_billstatus(_gap_item("Introduced in House", "2023-05-01", code="ih"))
    respx.get(gi.billstatus_url(118, "hr", 3496)).mock(return_value=httpx.Response(200, content=body))
    respx.get(url__regex=r".*BILLS-118hr3496ih\.xml").mock(return_value=httpx.Response(200, content=b"<bill/>"))
    args = argparse.Namespace(
        congress=118,
        bill_type="hr",
        number=3496,
        version=None,
        format="xml",
        output_dir=tmp_path,
        source="govinfo",
    )
    with httpx.Client() as client:
        cmd_download(client, args, None)
    assert not (tmp_path / "118-hr-3496" / gi.GAP_MARKER_NAME).exists()


@respx.mock
def test_download_skips_gap_marker_entirely_for_the_api_source(tmp_path):
    # Gaps are a govinfo-format concept. The api source must not gain a govinfo
    # BILLSTATUS request as a side effect of this feature; respx would raise on an
    # unmocked govinfo call, so this asserts isolation rather than just absence.
    respx.get(url__regex=r".*api\.congress\.gov.*").mock(return_value=httpx.Response(200, json={"textVersions": []}))
    args = argparse.Namespace(
        congress=118,
        bill_type="hr",
        number=3496,
        version=None,
        format="xml",
        output_dir=tmp_path,
        source="api",
    )
    with httpx.Client() as client:
        cmd_download(client, args, "KEY")
    assert not (tmp_path / "118-hr-3496" / gi.GAP_MARKER_NAME).exists()


# ---- one BILLSTATUS request per bill (#253) ----------------------------------
#
# Counted at the route, not inferred from timing: the gap marker and the
# downloadable version list are both derived from one parsed BILLSTATUS element,
# so a second request would be a regression worth ~1.1MB and one extra rate-limit
# slot per bill across a download-all sweep.


@respx.mock
def test_download_issues_one_billstatus_request_per_bill(tmp_path):
    # A bill with both halves live at once: one served version to download AND one
    # XML-less gap to record. Doing both must still cost a single request.
    body = _gap_billstatus(
        _gap_item("Introduced in House", "2023-05-01", code="ih") + _gap_item("Reported in House", "2023-06-01")
    )
    route = respx.get(gi.billstatus_url(118, "hr", 3496)).mock(return_value=httpx.Response(200, content=body))
    respx.get(url__regex=r".*BILLS-118hr3496ih\.xml").mock(return_value=httpx.Response(200, content=b"<bill/>"))
    args = argparse.Namespace(
        congress=118,
        bill_type="hr",
        number=3496,
        version=None,
        format="xml",
        output_dir=tmp_path,
        source="govinfo",
    )
    with httpx.Client() as client:
        cmd_download(client, args, None)
    assert route.call_count == 1, "BILLSTATUS fetched more than once for one bill"
    # Both outputs still land, so the count above is a real dedup and not a
    # half-done download.
    assert (tmp_path / "118-hr-3496" / "1_introduced-in-house.xml").exists()
    payload = json.loads((tmp_path / "118-hr-3496" / gi.GAP_MARKER_NAME).read_text())
    assert [g["code"] for g in payload["gap_versions"]] == ["rh"]


@respx.mock
def test_download_all_issues_one_billstatus_request_per_bill(tmp_path):
    # download-all is where the duplicate compounds (~1,000 bills a sweep), so the
    # count is pinned on that path too, in the all-gap shape where enumeration
    # returns [] and only the marker is written.
    body = _gap_billstatus(
        _gap_item("Introduced in House", "2023-05-01") + _gap_item("Reported in House", "2023-06-01")
    )
    route = respx.get(gi.billstatus_url(118, "hr", 3496)).mock(return_value=httpx.Response(200, content=body))
    with httpx.Client() as client:
        download_all_versions(
            client,
            output_dir=tmp_path,
            congress=118,
            bill_type="hr",
            number=3496,
            source="govinfo",
            api_key=None,
            formats=["xml"],
        )
    assert route.call_count == 1, "BILLSTATUS fetched more than once for one bill"
    payload = json.loads((tmp_path / "118-hr-3496" / gi.GAP_MARKER_NAME).read_text())
    assert [g["code"] for g in payload["gap_versions"]] == ["ih", "rh"]


@respx.mock
def test_download_aborts_loudly_when_billstatus_fails(tmp_path, monkeypatch):
    # The flip side of sharing one fetch: there is no second request left to fail
    # softly, so a BILLSTATUS failure is the download's own failure and must stay
    # loud rather than becoming a silent "bill has no versions" (#10).
    monkeypatch.setattr("shared.http.time.sleep", lambda *_: None)  # no real backoff wait
    respx.get(gi.billstatus_url(118, "hr", 3496)).mock(return_value=httpx.Response(500))
    args = argparse.Namespace(
        congress=118,
        bill_type="hr",
        number=3496,
        version=None,
        format="xml",
        output_dir=tmp_path,
        source="govinfo",
    )
    with httpx.Client() as client, pytest.raises(httpx.HTTPError):
        cmd_download(client, args, None)
    assert not (tmp_path / "118-hr-3496" / gi.GAP_MARKER_NAME).exists()
