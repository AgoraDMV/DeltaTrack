"""Tests for fetch_bill_archives.py download integrity (issue #63).

Hermetic: synthetic in-memory ZIPs served through respx, no network. Chunked
responses (no content-length) are modelled the way httpx emits them -- an
iterator body -- because that is exactly the case where the byte-count check
cannot fire and the archive's own structure is the only completeness signal.
"""

from __future__ import annotations

import io
import zipfile

import httpx
import pytest
import respx

from fetch_bill_archives import archive_temp_path, download_archive_zip

ARCHIVE_URL = "https://www.govinfo.gov/bulkdata/BILLSTATUS/999/hr/BILLSTATUS-999-hr.zip"


def _billstatus_zip_bytes() -> bytes:
    """One well-formed BILLSTATUS archive ZIP, as govinfo serves it."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "BILLSTATUS-999hr1.xml",
            b"<billStatus><bill><congress>999</congress><type>HR</type><number>1</number></bill></billStatus>",
        )
    return buf.getvalue()


def _chunked(body: bytes) -> httpx.Response:
    """Response with an iterator body: transfer-encoding chunked, no content-length."""
    return httpx.Response(200, content=iter([body]))


class TestDownloadArchiveZip:
    @respx.mock
    def test_truncated_body_without_content_length_is_not_committed(self, tmp_path):
        """A short read on a chunked response must fail, not cache a partial archive (#63).

        Without content-length the byte-count check cannot fire, so before this
        guard the half-archive was committed to dest and every later run skipped
        re-download because dest existed.
        """
        full = _billstatus_zip_bytes()
        respx.get(ARCHIVE_URL).mock(return_value=_chunked(full[: len(full) // 2]))
        dest = tmp_path / "999-hr.zip"

        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPError):
                download_archive_zip(client, ARCHIVE_URL, dest)

        assert not dest.exists()
        assert not archive_temp_path(dest).exists()

    @respx.mock
    def test_healthy_body_without_content_length_is_committed(self, tmp_path):
        """Chunked transfer encoding is normal, not an error: a complete archive still lands."""
        full = _billstatus_zip_bytes()
        respx.get(ARCHIVE_URL).mock(return_value=_chunked(full))
        dest = tmp_path / "999-hr.zip"

        with httpx.Client() as client:
            download_archive_zip(client, ARCHIVE_URL, dest)

        assert dest.read_bytes() == full
        assert not archive_temp_path(dest).exists()
        with zipfile.ZipFile(dest) as zf:
            assert zf.namelist() == ["BILLSTATUS-999hr1.xml"]

    @respx.mock
    def test_empty_body_without_content_length_is_not_committed(self, tmp_path):
        """A zero-byte chunked response is a failed download, not an empty archive."""
        respx.get(ARCHIVE_URL).mock(return_value=_chunked(b""))
        dest = tmp_path / "999-hr.zip"

        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPError):
                download_archive_zip(client, ARCHIVE_URL, dest)

        assert not dest.exists()

    @respx.mock
    def test_short_read_against_content_length_still_raises(self, tmp_path):
        """The header-present check keeps its behavior: fewer bytes than promised fails."""
        full = _billstatus_zip_bytes()
        respx.get(ARCHIVE_URL).mock(
            return_value=httpx.Response(
                200,
                headers={"content-length": str(len(full))},
                content=iter([full[: len(full) // 2]]),
            )
        )
        dest = tmp_path / "999-hr.zip"

        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPError, match="Incomplete download"):
                download_archive_zip(client, ARCHIVE_URL, dest)

        assert not dest.exists()

    @respx.mock
    def test_healthy_body_with_content_length_is_committed(self, tmp_path):
        """The common path -- server sends content-length and the full archive -- is unchanged."""
        full = _billstatus_zip_bytes()
        respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, content=full))
        dest = tmp_path / "999-hr.zip"

        with httpx.Client() as client:
            download_archive_zip(client, ARCHIVE_URL, dest)

        assert dest.read_bytes() == full
