"""Tests for fetch_bill_text_archives.py download integrity (issue #212).

Hermetic: synthetic in-memory ZIPs served through respx, no network. Chunked
responses (no content-length) are modelled the way httpx emits them -- an
iterator body -- because that is exactly the case where the byte-count check
cannot fire and the archive's own structure is the only completeness signal.
"""

from __future__ import annotations

import shlex
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from fetch_bill_text_archives import download_zip
from fetch_bill_text_archives import main as fetch_bill_text_archives_main
from fetch_govinfo import sessions_for_congress
from shared.bill_types import BILL_TYPES
from tests.utils import (
    EMPTY_ZIP_BYTES,
    archive_bytes,
    assert_files,
    assert_message_contains_strings,
    mock_http_requests,
)

ARCHIVE_URL = "https://www.govinfo.gov/bulkdata/BILLS/999/1/hr/BILLS-999-1-hr.zip"


def _bills_zip_bytes() -> bytes:
    """One well-formed BILLS archive ZIP, as govinfo serves it."""
    return archive_bytes(
        {"BILLS-999hr1ih.xml": b"<bill><congress>999</congress><type>HR</type><number>1</number></bill>"}
    )


def _chunked(body: bytes) -> httpx.Response:
    """Response with an iterator body: transfer-encoding chunked, no content-length."""
    return httpx.Response(200, content=iter([body]))


def _temp_path(dest: Path) -> Path:
    """The in-progress download path, as download_zip derives it inline."""
    return dest.with_suffix(dest.suffix + ".part")


def run_fetch_bill_text_archives(command: str) -> None:
    args = shlex.split(command)
    fetch_bill_text_archives_main(args)


class TestDownloadZip:
    @respx.mock
    def test_truncated_body_without_content_length_is_not_committed(self, tmp_path):
        """A short read on a chunked response must fail, not cache a partial archive (#212).

        Without content-length the byte-count check cannot fire, so before this
        guard the half-archive was committed to dest and every later run skipped
        re-download because dest existed.
        """
        full = _bills_zip_bytes()
        respx.get(ARCHIVE_URL).mock(return_value=_chunked(full[: len(full) // 2]))
        dest = tmp_path / "BILLS-999-1-hr.zip"

        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPError):
                download_zip(client, ARCHIVE_URL, dest)

        assert not dest.exists()
        assert not _temp_path(dest).exists()

    @respx.mock
    def test_healthy_body_without_content_length_is_committed(self, tmp_path):
        """Chunked transfer encoding is normal, not an error: a complete archive still lands."""
        full = _bills_zip_bytes()
        respx.get(ARCHIVE_URL).mock(return_value=_chunked(full))
        dest = tmp_path / "BILLS-999-1-hr.zip"

        with httpx.Client() as client:
            assert download_zip(client, ARCHIVE_URL, dest) is True

        assert dest.read_bytes() == full
        assert not _temp_path(dest).exists()
        with zipfile.ZipFile(dest) as zf:
            assert zf.namelist() == ["BILLS-999hr1ih.xml"]

    @respx.mock
    def test_empty_body_without_content_length_is_not_committed(self, tmp_path):
        """A zero-byte chunked response is a failed download, not an empty archive."""
        respx.get(ARCHIVE_URL).mock(return_value=_chunked(b""))
        dest = tmp_path / "BILLS-999-1-hr.zip"

        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPError):
                download_zip(client, ARCHIVE_URL, dest)

        assert not dest.exists()

    @respx.mock
    def test_short_read_against_content_length_still_raises(self, tmp_path):
        """The header-present check keeps its behavior: fewer bytes than promised fails."""
        full = _bills_zip_bytes()
        respx.get(ARCHIVE_URL).mock(
            return_value=httpx.Response(
                200,
                headers={"content-length": str(len(full))},
                content=iter([full[: len(full) // 2]]),
            )
        )
        dest = tmp_path / "BILLS-999-1-hr.zip"

        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPError, match="Incomplete"):
                download_zip(client, ARCHIVE_URL, dest)

        assert not dest.exists()

    @respx.mock
    def test_healthy_body_with_content_length_is_committed(self, tmp_path):
        """The common path -- server sends content-length and the full archive -- is unchanged."""
        full = _bills_zip_bytes()
        respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, content=full))
        dest = tmp_path / "BILLS-999-1-hr.zip"

        with httpx.Client() as client:
            assert download_zip(client, ARCHIVE_URL, dest) is True

        assert dest.read_bytes() == full


class TestBillTypes:
    @respx.mock
    def test_happy_path_downloads_for_case_insensitive_bill_type(self, tmp_path):
        mock_http_requests(content=EMPTY_ZIP_BYTES)
        run_fetch_bill_text_archives(
            f"--from-congress 119 --to-congress 119 --types HR --zip-dir {tmp_path} --download-only"
        )
        assert_files(tmp_path, {"BILLS-119-1-hr.zip", "BILLS-119-2-hr.zip"})

    def test_error_path_reports_invalid_bill_type(self, tmp_path):
        with pytest.raises(ValueError) as excinfo:
            run_fetch_bill_text_archives(
                f"--from-congress 119 --to-congress 119 --types not-a-type --zip-dir {tmp_path} --download-only"
            )
        assert_message_contains_strings(str(excinfo.value), ["Unknown bill type", "not-a-type"])
        assert_files(tmp_path, [])

    @respx.mock
    def test_no_types_argument_defaults_to_all(self, tmp_path):
        mock_http_requests(content=EMPTY_ZIP_BYTES)
        run_fetch_bill_text_archives(f"--from-congress 119 --to-congress 119 --zip-dir {tmp_path} --download-only")
        assert_files(
            tmp_path,
            {
                f"BILLS-119-{session}-{bill_type}.zip"
                for session in sessions_for_congress(119)
                for bill_type in BILL_TYPES
            },
        )

    @respx.mock
    def test_types_containing_all_fetches_all_types(self, tmp_path):
        mock_http_requests(content=EMPTY_ZIP_BYTES)
        run_fetch_bill_text_archives(
            f"--from-congress 119 --to-congress 119 --types hr all --zip-dir {tmp_path} --download-only"
        )
        assert_files(
            tmp_path,
            {
                f"BILLS-119-{session}-{bill_type}.zip"
                for session in sessions_for_congress(119)
                for bill_type in BILL_TYPES
            },
        )
