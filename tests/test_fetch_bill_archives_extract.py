"""Tests for archive cache coherence, download and extract sides (issue #61).

``TestDownloadArchiveZip`` in tests/test_fetch_bill_archives.py covers whether a
partial *body* is committed to disk (#63) -- transfer integrity for one archive. This
file covers the caches on either side of that: which archives a re-run decides to
fetch at all, and turning a cached ZIP into an extracted folder. The failure modes
here are about *reuse* rather than transfer.

The same invariant shape governs both stages. Work is skipped when its output already
exists, which is what keeps a re-run cheap -- but it means the output's mere existence
is taken as proof that the work completed, so anything left behind by a crashed run
would be trusted forever. What makes each skip safe is the failure path removing or
marking its own debris: ``extract_archives`` rmtree's a partial folder, and
``download_archives`` writes an ``.error`` marker and clears it on a later success.
"""

from __future__ import annotations

import io
import stat
from pathlib import Path
import pytest
import respx
import shlex
from unittest.mock import patch
import zipfile

from bill_index import BillIndex
import tools.shared.http as http
import tools.shared.zip as zip
from tests.utils import assert_files, mock_http_requests, archive_bytes, write_archive
from tools.fetch_bill_archives import (
    archive_destination,
    billstatus_filename,
    billstatus_zip_filename,
    billstatus_zip_url as archive_url,
    main,
)
from tools.shared.zip import extract_archive

def fetch_bill_archives(args: str) -> None:
    argv = ["fetch_bill_archives", *shlex.split(args)]
    with patch("sys.argv", argv):
        return main()

def single_member_archive_bytes(congress: int, bill_type: str) -> bytes:
    return archive_bytes(
        {billstatus_filename(congress, bill_type, 1): b"<billStatus/>"}
    )

def write_single_member_archive(source: Path, congress: int, bill_type: str) -> Path:
    path = source / billstatus_zip_filename(congress, bill_type)
    path.write_bytes(single_member_archive_bytes(congress, bill_type))

# def archive_bytes(name: str = "119-hr") -> bytes:
#     """One well-formed BILLSTATUS archive ZIP, as bytes."""
#     buf = io.BytesIO()
#     with zipfile.ZipFile(buf, "w") as zf:
#         zf.writestr(f"{name}-1.xml", b"<billStatus/>")
#     return buf.getvalue()


class TestDownloadArchivesCacheCoherence:
    """Which archives a re-run decides to fetch, and what a failure leaves behind.

    One congress and one bill type per test, so each exercises the cache decision
    rather than the congress/type enumeration.
    """

    @respx.mock
    def test_existing_archive_is_skipped_without_a_request(self, tmp_path):
        # The skip is what makes a re-run over 112-119 cheap; without it the tool
        # re-downloads hundreds of MB. Asserting the route was never called is the
        # point -- an implementation that fetched and then discarded the body would
        # leave the same files on disk.
        write_single_member_archive(tmp_path, 119, "hr")
        route = mock_http_requests(archive_url(119, "hr"), content=b"new content")

        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}")

        assert not route.called

    @respx.mock
    def test_successful_download_is_committed_and_reported(self, tmp_path):
        body = single_member_archive_bytes(119, "hr")
        mock_http_requests(archive_url(119, "hr"), content=body)

        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}")

        assert_files(tmp_path, ["BILLSTATUS-119-hr.zip", "119-hr-1"])
        assert_files(tmp_path / "119-hr-1", ["119-hr-1_status.xml"])

    @respx.mock
    def test_failed_download_writes_an_error_marker_and_commits_no_archive(self, tmp_path):
        mock_http_requests(archive_url(119, "hr"), status_code=404)

        fetch_bill_archives(
            f"--from-congress 119 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}"
        )

        assert_files(tmp_path, ["BILLSTATUS-119-hr.zip.error"])

    @respx.mock
    def test_a_later_success_clears_a_stale_error_marker(self, tmp_path):
        # The coherence half: without the clear, a marker from a transient outage
        # would keep describing a failure for an archive that is now present, and
        # anything reading markers to decide what is missing would be wrong forever.
        error_path = tmp_path / "BILLSTATUS-119-hr.zip.error"
        error_path.write_text("earlier failure", encoding="utf-8")
        mock_http_requests(archive_url(119, "hr"), content=single_member_archive_bytes(119, 'hr'))
        assert_files(tmp_path, ['BILLSTATUS-119-hr.zip.error'])

        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}")

        assert_files(tmp_path, ["BILLSTATUS-119-hr.zip", "119-hr-1"])
        assert_files(tmp_path / "119-hr-1", ["119-hr-1_status.xml"])

    @respx.mock
    def test_a_failing_archive_does_not_abort_the_batch(self, tmp_path):
        mock_http_requests(archive_url(117, "hr"), status_code=500)
        mock_http_requests(archive_url(118, "hr"), content=single_member_archive_bytes(118, 'hr'))
        mock_http_requests(archive_url(119, "hr"), status_code=500)

        fetch_bill_archives(
            f"--from-congress 117 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}"
        )

        assert_files(
            tmp_path,
            {
                "BILLSTATUS-117-hr.zip.error",
                "BILLSTATUS-118-hr.zip",
                "BILLSTATUS-119-hr.zip.error",
                "118-hr-1",
            },
        )
        assert_files(tmp_path / "118-hr-1", ["118-hr-1_status.xml"])

    @respx.mock
    def test_a_stale_error_marker_alone_does_not_prevent_a_retry(self, tmp_path):
        # A marker records that a download failed, not that it should stop being
        # attempted; only a present .zip suppresses the request. Pinning this keeps a
        # future "skip anything with an .error marker" optimization from silently
        # making transient failures permanent.
        target_archive: Path = tmp_path / 'BILLSTATUS-119-hr.zip'
        error_path = http.path_for_error(target_archive)        
        error_path.write_text("earlier failure", encoding="utf-8")
        assert_files(tmp_path, ['BILLSTATUS-119-hr.zip.error'])

        route = mock_http_requests(archive_url(119, "hr"), content=single_member_archive_bytes(119, 'hr'))
        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}")

        assert route.called
        assert_files(tmp_path, ["BILLSTATUS-119-hr.zip", "119-hr-1"])
        assert_files(tmp_path / "119-hr-1", ["119-hr-1_status.xml"])

    @respx.mock
    def test_a_cached_archive_clears_a_stale_marker(self, tmp_path):
        # #259: the skip-if-exists branch used to return before the marker-clearing
        # line, so an archive that was already present kept an .error marker beside it
        # describing a failure that the archive itself disproves. The two states
        # together are contradictory, so whichever a future consumer reads, it reads a
        # wrong answer for one of them.
        dest = tmp_path / "BILLSTATUS-119-hr.zip"
        dest.write_bytes(single_member_archive_bytes(119, "hr"))
        error_path = tmp_path / "BILLSTATUS-119-hr.zip.error"
        error_path.write_text("earlier failure", encoding="utf-8")

        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}")

        assert_files(tmp_path, ["BILLSTATUS-119-hr.zip", "119-hr-1"])
        assert_files(tmp_path / "119-hr-1", ["119-hr-1_status.xml"])


class TestExtractArchive:
    @respx.mock
    def test_creates_the_destination_and_writes_members(self, tmp_path):
        archive = tmp_path / "BILLSTATUS-119-hr.zip"
        archive.write_bytes(single_member_archive_bytes(119, "hr"))
        dest = tmp_path / "out"

        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr --out-dir {dest} --zip-dir {tmp_path}")

        assert_files(dest, ["119-hr-1"])
        assert_files(dest / "119-hr-1", ["119-hr-1_status.xml"])


    @pytest.mark.parametrize(
        "member",
        [
            # Relative paths
            pytest.param("../escaped.xml", id="relative-parent-traversal"),
            pytest.param("../../escaped.xml", id="relative-double-parent-traversal"),
            pytest.param("sub/../../escaped.xml", id="relative-traversal-after-descent"),
            pytest.param("../sub/escaped.xml", id="relative-parent-then-descent"),
            # Absolute paths
            pytest.param("/etc/escaped.xml", id="absolute-unix"),
            pytest.param("/tmp/escaped.xml", id="absolute-tmp"),
            pytest.param("//escaped.xml", id="absolute-double-slash"),
        ],
    )
    def test_members_cannot_escape_the_destination_directory(self, tmp_path, member):
        # These archives are third-party input (govinfo bulk data), so a member path
        # is untrusted. zipfile.extractall sanitizes traversal and absolute paths
        # itself, so this passes today and is not a live vulnerability -- it is here
        # because the obvious refactor, replacing extractall with a per-member loop
        # to add filtering or progress output, reintroduces a real escape while every
        # other test in this file stays green. That is not hypothetical: writing such
        # a loop and running this file did land a file outside the test directory.
        #
        # Containment is asserted structurally, against paths under tmp_path only.
        # Asserting on a fixed absolute location instead would make the test depend
        # on global filesystem state -- shared with every other process on the
        # machine, so a stale file from an unrelated run fails it and a concurrent
        # run makes it flaky.
        dest = tmp_path / "out"
        dest.mkdir()
        archive_dest = dest / "BILLSTATUS-119-hr.zip"
        bytes = archive_bytes({member: b"<escaped/>"})
        archive_dest.write_bytes(bytes)
        route = mock_http_requests(archive_url(119, "hr"), content=bytes)

        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr --out-dir {dest} --zip-dir {dest}")
        assert not route.called

        assert_files(tmp_path, ["out"])
        assert_files(dest, {"BILLSTATUS-119-hr.zip"})

    @respx.mock
    def test_raises_on_a_corrupt_archive(self, tmp_path):
        archive = tmp_path / "BILLSTATUS-119-hr.zip"
        archive.write_bytes(b"not a zip")

        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}")

        assert_files(tmp_path, ["BILLSTATUS-119-hr.zip"])


class TestExtractArchivesCacheCoherence:
    @respx.mock
    def test_extracts_each_archive_into_a_folder_named_for_its_stem(self, tmp_path):
        # Written out of alphabetical order so the assertion below tests the sort
        # rather than the order the files happened to be created in.
        write_single_member_archive(tmp_path, 119, "s")
        write_single_member_archive(tmp_path, 119, "hr")
        out_dir = tmp_path / "out"

        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr s --out-dir {out_dir} --zip-dir {tmp_path}")

        assert_files(out_dir, ["119-hr-1", "119-s-1"])

    @respx.mock
    def test_existing_folder_is_skipped_and_left_untouched(self, tmp_path):
        # The skip is keyed on folder existence alone, so a pre-existing folder wins
        # over the archive's actual contents. Pinning it keeps the re-run cheap and
        # documents that the folder, not the ZIP, is the cache.
        write_single_member_archive(tmp_path, 119, "hr")
        stale_dir = tmp_path / "119-hr-1"
        stale_dir.mkdir()
        (stale_dir / "119-hr-1_status.xml").write_bytes(b"<stale/>")

        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}")

        assert_files(tmp_path, ["BILLSTATUS-119-hr.zip", "119-hr-1"])
        assert_files(stale_dir, ["119-hr-1_status.xml"])
        assert (stale_dir / "119-hr-1_status.xml").read_bytes() == b"<stale/>"

    @respx.mock
    def test_partial_folder_from_a_failed_extract_is_removed(self, tmp_path):
        # The cleanup is what makes the existence-based skip safe: a folder left
        # behind here would be treated as a complete extraction by every later run,
        # silently serving a truncated corpus.
        corrupt = tmp_path / "BILLSTATUS-119-hr.zip"
        corrupt.write_bytes(b"not a zip")

        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}")

        assert_files(tmp_path, ["BILLSTATUS-119-hr.zip"])

    @respx.mock
    def test_a_failed_archive_does_not_abort_the_batch(self, tmp_path):
        # Sorted order puts the corrupt archive first, so a bare raise would cost the
        # healthy ones too.
        (tmp_path / "BILLSTATUS-119-aaa.zip").write_bytes(b"not a zip")
        write_single_member_archive(tmp_path, 119, "zzz")

        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types aaa zzz --out-dir {tmp_path} --zip-dir {tmp_path}")

        assert_files(
            tmp_path, [
                "BILLSTATUS-119-aaa.zip",
                "BILLSTATUS-119-zzz.zip",
                "119-zzz-1"
            ]
        )
        assert_files(tmp_path / "119-zzz-1", ["119-zzz-1_status.xml"])

    @respx.mock
    def test_only_zip_files_are_considered(self, tmp_path, capsys):
        # The bills directory holds bills.csv and extracted folders alongside the
        # archives, so the glob is what keeps them out. Asserting the extracted list
        # alone would not catch a widened glob: a non-ZIP that gets attempted fails to
        # open and is swallowed by the same except that handles a corrupt archive, so
        # the list comes out identical either way and only the log betrays it.
        write_single_member_archive(tmp_path, 119, "hr")
        (tmp_path / "notes.txt").write_text("ignore me")
        (tmp_path / "bills.csv").write_text("id\n")

        mock_http_requests(archive_url(119, "hr"), content=single_member_archive_bytes(119, "hr"))
        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}")
        err = capsys.readouterr().err
        assert "notes.txt" not in err
        assert "bills.csv" not in err


        assert_files(tmp_path, [
            "BILLSTATUS-119-hr.zip",
            "119-hr-1",
            "notes.txt",
            "bills.csv"
        ])

    @respx.mock
    def test_zero_member_archive_writes_no_bill_folder(self, tmp_path):
        # A zero-member ZIP is structurally valid and is deliberately not treated as a
        # failed download (see _verify_archive_complete). Archives hold many bills, so
        # an empty zip has no bill id to name a folder after -- extraction is a no-op.
        (tmp_path / billstatus_zip_filename(119, "hr")).write_bytes(archive_bytes({}))

        fetch_bill_archives(f"--from-congress 119 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}")
        assert_files(tmp_path, ["BILLSTATUS-119-hr.zip"])

    @respx.mock
    def test_rerun_after_a_successful_extract_is_a_no_op(self, tmp_path):
        zip_name = "BILLSTATUS-119-hr.zip"
        member = "BILLSTATUS-119hr1.xml"
        (tmp_path / zip_name).write_bytes(archive_bytes({member: b"first contents"}))
        args = f"--from-congress 119 --to-congress 119 --types hr --out-dir {tmp_path} --zip-dir {tmp_path}"
        fetch_bill_archives(args)

        (tmp_path / zip_name).write_bytes(archive_bytes({member: b"replacement contents"}))
        fetch_bill_archives(args)

        assert_files(tmp_path, ["BILLSTATUS-119-hr.zip", "119-hr-1"])
        assert_files(tmp_path / "119-hr-1", ["119-hr-1_status.xml"])
        assert (tmp_path / "119-hr-1" / "119-hr-1_status.xml").read_bytes() == b"first contents"
