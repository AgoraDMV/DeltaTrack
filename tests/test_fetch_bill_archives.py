"""Tests for fetch_bill_archives.py download integrity (issue #63).

Hermetic: synthetic in-memory ZIPs served through respx, no network. Chunked
responses (no content-length) are modelled the way httpx emits them -- an
iterator body -- because that is exactly the case where the byte-count check
cannot fire and the archive's own structure is the only completeness signal.
"""

from __future__ import annotations

import re
import shlex
import zipfile

import httpx
import pytest
import respx

from fetch_bill_archives import archive_temp_path, download_archive_zip
from fetch_bill_archives import main as fetch_bill_archives_main
from shared.bill_types import BILL_TYPES
from tests.utils import (
    EMPTY_ZIP_BYTES,
    archive_bytes,
    assert_files,
    mock_http_requests,
    assert_message_contains_strings,
)

ARCHIVE_URL = "https://www.govinfo.gov/bulkdata/BILLSTATUS/999/hr/BILLSTATUS-999-hr.zip"

def run_fetch_bill_archives(command: str) -> None:
    args = shlex.split(command)
    return fetch_bill_archives_main(args)

def _billstatus_zip_bytes() -> bytes:
    """One well-formed BILLSTATUS archive ZIP, as govinfo serves it."""
    return archive_bytes({
        "BILLSTATUS-999hr1.xml": b"""
        <billStatus><bill><congress>999</congress><type>HR</type><number>1</number></bill></billStatus>
        """
    })


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


class TestBillTypes:
    @respx.mock
    def test_happy_path_downloads_for_case_insensitive_bill_type(self, tmp_path):
        mock_http_requests(content=EMPTY_ZIP_BYTES)
        run_fetch_bill_archives(
            f"--from-congress 119 --to-congress 119 --types HR Hjres --destination {tmp_path} --download-only"
        )
        assert_files(tmp_path, {"119-hr.zip", "119-hjres.zip"})

    def test_error_path_reports_invalid_bill_type(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as excinfo:
            run_fetch_bill_archives(f"--types not-a-type --destination {tmp_path}")
        assert excinfo.value.code == 2
        out, err = capsys.readouterr()
        err = re.sub("[.,'\[\]{}]", "", err)
        assert_message_contains_strings(
            err,
            [
                "argument --types: invalid choice: not-a-type",
                "choose from all hr s hjres sjres hres sres hconres sconres",
            ],
        )
        assert_files(tmp_path, [])

    @respx.mock
    def test_no_types_argument_defaults_to_all(self, tmp_path):
        mock_http_requests(content=EMPTY_ZIP_BYTES)
        run_fetch_bill_archives(f"--from-congress 119 --to-congress 119 --destination {tmp_path} --download-only")
        assert_files(tmp_path, {f"119-{bill_type}.zip" for bill_type in BILL_TYPES})

    @respx.mock
    def test_types_containing_all_fetches_all_types(self, tmp_path):
        mock_http_requests(content=EMPTY_ZIP_BYTES)
        run_fetch_bill_archives(
            f"--from-congress 119 --to-congress 119 --types hr all --destination {tmp_path} --download-only"
        )
        assert_files(tmp_path, {f"119-{bill_type}.zip" for bill_type in BILL_TYPES})
