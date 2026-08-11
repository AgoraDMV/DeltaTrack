"""The govinfo HTML rendition: URL, fetch, and plain-text extraction (#249).

Every version govinfo publishes carries a third rendition beside the XML and the PDF:
an HTML page whose body is a single `<pre>` block holding GPO's authoritative ASCII
layout. This covers building its URL, pulling the body out, and failing loudly when a
version has no rendition.

Hermetic by construction. The fixture is a real rendition committed under
`tests/fixtures/govinfo/`, so these run in CI with no network; the fetch path is
exercised through respx. Nothing here reaches govinfo, which also means a govinfo
outage cannot turn this suite red. A synthetic fixture would not do: the point of
most of these assertions is what GPO actually emits, and a hand-written page would
only prove the reader agrees with its author.

Fixture provenance: vendored public-domain (17 U.S.C. 105) govinfo source, fetched
2026-07-21 from
https://www.govinfo.gov/content/pkg/BILLS-118hr8282ih/html/BILLS-118hr8282ih.htm --
118-hr-8282 introduced-in-house, chosen as the smallest bill already in the corpus.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
import respx

from fetch_govinfo import (
    RenditionNotAvailable,
    bill_text_from_htm,
    fetch_bill_htm,
    package_content_url,
)

FIXTURE = Path(__file__).parent / "fixtures" / "govinfo" / "BILLS-118hr8282ih.htm"
PKG = "BILLS-118hr8282ih"


def rendition_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


class TestRenditionUrl:
    def test_htm_is_served_from_the_html_directory(self):
        # The directory does NOT match the extension for this format, unlike xml and
        # pdf. The symmetric .../{pkg}/htm/{pkg}.htm redirects to govinfo's error page,
        # so a builder that derived the directory from the extension would produce a
        # URL that resolves to an error document -- a 200 carrying no bill. Pinned
        # because that failure is silent at the URL layer.
        assert package_content_url(PKG, "htm") == f"https://www.govinfo.gov/content/pkg/{PKG}/html/{PKG}.htm"

    def test_xml_and_pdf_peers_are_unchanged(self):
        assert package_content_url(PKG, "xml") == f"https://www.govinfo.gov/content/pkg/{PKG}/xml/{PKG}.xml"
        assert package_content_url(PKG, "pdf") == f"https://www.govinfo.gov/content/pkg/{PKG}/pdf/{PKG}.pdf"

    def test_an_unknown_format_raises_rather_than_composing_a_url(self):
        with pytest.raises(KeyError):
            package_content_url(PKG, "txt")


class TestExtractBody:
    def test_extracts_the_bill_body_and_discards_the_html_chrome(self):
        text = bill_text_from_htm(rendition_html())

        assert "SEC. 2. SANCTIONS WITH RESPECT TO THE INTERNATIONAL CRIMINAL COURT." in text
        assert "IN THE HOUSE OF REPRESENTATIVES" in text
        # Chrome is gone: no tags survive, opening or closing.
        assert "<pre>" not in text
        assert "</pre>" not in text
        assert "<html>" not in text
        assert "<body>" not in text

    def test_html_entities_are_unescaped(self):
        # GPO writes its own markers as entities inside the <pre>: `&lt;DOC&gt;` and
        # the closing `&lt;all&gt;`. A reader that skipped unescaping would hand the
        # downstream parser literal "&lt;" sequences in the middle of the text.
        text = bill_text_from_htm(rendition_html())
        assert "<DOC>" in text
        assert "<all>" in text
        assert "&lt;" not in text
        assert "&gt;" not in text

    def test_line_structure_is_preserved(self):
        """Load-bearing: the downstream parser reads structure off leading whitespace
        and line breaks, so neither may be normalized away.

        Three separate properties, because they fail independently: section
        enumerators sit at column 0, centered headers keep their indent, and blank
        lines survive as separators.
        """
        text = bill_text_from_htm(rendition_html())
        lines = text.split("\n")

        section_lines = [ln for ln in lines if ln.startswith("SEC. ")]
        assert len(section_lines) >= 2, "SEC. enumerators are not at column 0"

        centered = [ln for ln in lines if ln.strip() == "IN THE HOUSE OF REPRESENTATIVES"]
        assert centered, "the centered header line was not found intact"
        assert centered[0].startswith("    "), "a centered header lost its leading whitespace"

        assert "" in lines, "blank separator lines were collapsed"
        # And the body is genuinely multi-line, not one joined run.
        assert len(lines) > 100

    def test_the_gpo_provenance_header_is_kept(self):
        # Inside the <pre>, so it is part of the published document rather than
        # chrome. Kept deliberately: whether a consumer wants it is that consumer's
        # decision, and dropping it here would be unrecoverable.
        text = bill_text_from_htm(rendition_html())
        assert "[Congressional Bills 118th Congress]" in text


class TestFailsLoudly:
    def test_html_without_a_pre_block_raises(self):
        # What govinfo's error page looks like to this parser: a 200 carrying a real
        # HTML document that holds no bill. Returning "" here would surface as a
        # version whose text is legitimately empty.
        with pytest.raises(RenditionNotAvailable, match="no <pre> block"):
            bill_text_from_htm("<html><body><h1>Page not found</h1></body></html>")

    def test_an_empty_pre_block_raises(self):
        with pytest.raises(RenditionNotAvailable, match="empty <pre> block"):
            bill_text_from_htm("<html><body><pre>\n   \n</pre></body></html>")

    @respx.mock
    def test_a_version_with_no_rendition_raises(self):
        respx.get(package_content_url(PKG, "htm")).mock(return_value=httpx.Response(404))
        with httpx.Client() as client, pytest.raises(RenditionNotAvailable, match="HTTP 404"):
            fetch_bill_htm(client, PKG)

    @respx.mock
    def test_a_redirect_is_not_followed_into_an_error_page(self):
        # govinfo answers a missing rendition with a redirect to its error page. The
        # client does not follow redirects, so this must surface as a failure and not
        # as a successfully fetched error document.
        respx.get(package_content_url(PKG, "htm")).mock(
            return_value=httpx.Response(302, headers={"location": "https://www.govinfo.gov/error"})
        )
        with httpx.Client() as client, pytest.raises(RenditionNotAvailable, match="HTTP 302"):
            fetch_bill_htm(client, PKG)


class TestFetch:
    @respx.mock
    def test_fetch_returns_the_extracted_body(self):
        respx.get(package_content_url(PKG, "htm")).mock(return_value=httpx.Response(200, text=rendition_html()))

        with httpx.Client() as client:
            text = fetch_bill_htm(client, PKG)

        assert "SEC. 3. DEFINITIONS." in text
        assert "<pre>" not in text


class TestFixtureIsARealRendition:
    """Floor: every test above reads one committed file, so a truncated or
    substituted fixture would quietly weaken all of them at once."""

    def test_fixture_has_the_shape_govinfo_serves(self):
        raw = rendition_html()
        assert raw.startswith("<html><body><pre>")
        assert raw.rstrip().endswith("</pre></body></html>")
        assert "[H.R. 8282 Introduced in House (IH)]" in raw
        # A real bill body, not a stub: sections, and the closing GPO marker.
        assert len(re.findall(r"^SEC\. \d+\.", raw, re.MULTILINE)) >= 2
        assert "&lt;all&gt;" in raw
