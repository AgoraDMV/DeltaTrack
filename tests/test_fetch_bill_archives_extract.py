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
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from bill_index import BillIndex
from fetch_bill_archives import (
    archive_destination,
    archive_error_path,
    archive_extract_dir,
    archive_url,
    build_parser,
    download_archives,
    extract_archive,
    extract_archives,
    parse_bill_archives,
)
from tests.utils import EMPTY_ZIP_BYTES, assert_files, mock_http_requests


def write_archive(source: Path, name: str, members: dict[str, bytes] | None = None) -> Path:
    """Write a well-formed ZIP named ``{name}.zip`` into source."""
    # `is None`, not `or`: an explicitly empty dict means a zero-member ZIP, and
    # falling back on falsiness would silently write a one-member archive instead.
    if members is None:
        members = {f"{name}-1.xml": b"<billStatus/>"}
    path = source / f"{name}.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for member, body in members.items():
            zf.writestr(member, body)
    path.write_bytes(buf.getvalue())
    return path


def archive_bytes(name: str = "119-hr") -> bytes:
    """One well-formed BILLSTATUS archive ZIP, as bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{name}-1.xml", b"<billStatus/>")
    return buf.getvalue()


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
        dest = archive_destination(tmp_path, 119, "hr")
        dest.write_bytes(b"cached, not a real zip")
        route = respx.get(archive_url(119, "hr")).mock(return_value=httpx.Response(200))

        downloaded = download_archives(119, 119, bill_types=["hr"], destination=tmp_path)

        assert downloaded == []  # skipped, so not reported as newly downloaded
        assert not route.called
        assert dest.read_bytes() == b"cached, not a real zip"

    @respx.mock
    def test_successful_download_is_committed_and_reported(self, tmp_path):
        body = archive_bytes()
        respx.get(archive_url(119, "hr")).mock(return_value=httpx.Response(200, content=body))

        downloaded = download_archives(119, 119, bill_types=["hr"], destination=tmp_path)

        dest = archive_destination(tmp_path, 119, "hr")
        assert downloaded == [dest]
        assert dest.read_bytes() == body
        assert not archive_error_path(tmp_path, 119, "hr").exists()

    @respx.mock
    def test_failed_download_writes_an_error_marker_and_commits_no_archive(self, tmp_path):
        respx.get(archive_url(119, "hr")).mock(return_value=httpx.Response(404))

        downloaded = download_archives(119, 119, bill_types=["hr"], destination=tmp_path)

        assert downloaded == []
        # No .zip: a committed-but-failed archive would be skipped forever by the
        # test above, permanently caching the failure as if it were data.
        assert not archive_destination(tmp_path, 119, "hr").exists()
        error_path = archive_error_path(tmp_path, 119, "hr")
        assert error_path.exists()
        assert error_path.read_text(encoding="utf-8")  # carries the reason, not empty

    @respx.mock
    def test_a_later_success_clears_a_stale_error_marker(self, tmp_path):
        # The coherence half: without the clear, a marker from a transient outage
        # would keep describing a failure for an archive that is now present, and
        # anything reading markers to decide what is missing would be wrong forever.
        error_path = archive_error_path(tmp_path, 119, "hr")
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text("earlier failure", encoding="utf-8")
        respx.get(archive_url(119, "hr")).mock(return_value=httpx.Response(200, content=archive_bytes()))

        download_archives(119, 119, bill_types=["hr"], destination=tmp_path)

        assert not error_path.exists()
        assert archive_destination(tmp_path, 119, "hr").exists()

    @respx.mock
    def test_a_failing_archive_does_not_abort_the_batch(self, tmp_path):
        # Tasks are newest-first, so 119 is attempted before 118.
        respx.get(archive_url(119, "hr")).mock(return_value=httpx.Response(500))
        respx.get(archive_url(118, "hr")).mock(return_value=httpx.Response(200, content=archive_bytes("118-hr")))

        downloaded = download_archives(118, 119, bill_types=["hr"], destination=tmp_path)

        assert downloaded == [archive_destination(tmp_path, 118, "hr")]
        assert archive_error_path(tmp_path, 119, "hr").exists()
        assert not archive_error_path(tmp_path, 118, "hr").exists()

    @respx.mock
    def test_a_stale_error_marker_alone_does_not_prevent_a_retry(self, tmp_path):
        # A marker records that a download failed, not that it should stop being
        # attempted; only a present .zip suppresses the request. Pinning this keeps a
        # future "skip anything with an .error marker" optimization from silently
        # making transient failures permanent.
        error_path = archive_error_path(tmp_path, 119, "hr")
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text("earlier failure", encoding="utf-8")
        route = respx.get(archive_url(119, "hr")).mock(return_value=httpx.Response(200, content=archive_bytes()))

        download_archives(119, 119, bill_types=["hr"], destination=tmp_path)

        assert route.called

    @respx.mock
    def test_a_cached_archive_clears_a_stale_marker(self, tmp_path):
        # #259: the skip-if-exists branch used to return before the marker-clearing
        # line, so an archive that was already present kept an .error marker beside it
        # describing a failure that the archive itself disproves. The two states
        # together are contradictory, so whichever a future consumer reads, it reads a
        # wrong answer for one of them.
        dest = archive_destination(tmp_path, 119, "hr")
        dest.write_bytes(archive_bytes())
        error_path = archive_error_path(tmp_path, 119, "hr")
        error_path.write_text("earlier failure", encoding="utf-8")

        downloaded = download_archives(119, 119, bill_types=["hr"], destination=tmp_path)

        assert not error_path.exists()
        # Still skipped, not re-fetched: clearing the marker must not cost the cache.
        # respx is mocking with no route registered, so any request would raise.
        assert downloaded == []
        assert dest.read_bytes() == archive_bytes()


class TestExtractArchive:
    def test_creates_the_destination_and_writes_members(self, tmp_path):
        archive = write_archive(tmp_path, "119-hr", {"a.xml": b"<a/>", "sub/b.xml": b"<b/>"})
        dest = tmp_path / "out"

        extract_archive(archive, dest)

        assert (dest / "a.xml").read_bytes() == b"<a/>"
        assert (dest / "sub" / "b.xml").read_bytes() == b"<b/>"

    @pytest.mark.parametrize(
        "member",
        [
            pytest.param("../escaped.xml", id="parent-traversal"),
            pytest.param("../../escaped.xml", id="double-parent-traversal"),
            pytest.param("/etc/escaped.xml", id="absolute-path"),
            pytest.param("sub/../../escaped.xml", id="traversal-after-descent"),
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
        archive = write_archive(tmp_path, "119-hr", {member: b"<escaped/>"})
        dest = tmp_path / "out"

        extract_archive(archive, dest)

        written = [p for p in dest.rglob("*") if p.is_file()]
        assert written, "nothing extracted, so the containment check proved nothing"
        for path in written:
            assert dest.resolve() in path.resolve().parents
        # Nothing escaped one level up into the directory holding the archive.
        assert not (tmp_path / "escaped.xml").exists()

    def test_raises_on_a_corrupt_archive(self, tmp_path):
        archive = tmp_path / "119-hr.zip"
        archive.write_bytes(b"not a zip")

        with pytest.raises(zipfile.BadZipFile):
            extract_archive(archive, tmp_path / "out")


class TestExtractArchivesCacheCoherence:
    def test_extracts_each_archive_into_a_folder_named_for_its_stem(self, tmp_path):
        # Written out of alphabetical order so the assertion below tests the sort
        # rather than the order the files happened to be created in.
        write_archive(tmp_path, "119-s")
        write_archive(tmp_path, "119-hr")

        extracted = extract_archives(tmp_path)

        # Compared in order, not sorted: extract_archives sorts its glob, and other
        # tests here rely on that ordering being deterministic (the batch-resilience
        # test needs the corrupt archive to come first). Sorting the actual value
        # would discard the very property those tests lean on, leaving the return
        # order free to follow filesystem order unnoticed.
        assert [p.name for p in extracted] == ["119-hr", "119-s"]
        assert (tmp_path / "119-hr" / "119-hr-1.xml").exists()

    def test_existing_folder_is_skipped_and_left_untouched(self, tmp_path):
        # The skip is keyed on folder existence alone, so a pre-existing folder wins
        # over the archive's actual contents. Pinning it keeps the re-run cheap and
        # documents that the folder, not the ZIP, is the cache.
        write_archive(tmp_path, "119-hr", {"fresh.xml": b"<fresh/>"})
        stale_dir = tmp_path / "119-hr"
        stale_dir.mkdir()
        (stale_dir / "stale.xml").write_bytes(b"<stale/>")

        extracted = extract_archives(tmp_path)

        assert extracted == []  # skipped, so not reported as newly extracted
        assert (stale_dir / "stale.xml").exists()
        assert not (stale_dir / "fresh.xml").exists()

    def test_partial_folder_from_a_failed_extract_is_removed(self, tmp_path):
        # The cleanup is what makes the existence-based skip safe: a folder left
        # behind here would be treated as a complete extraction by every later run,
        # silently serving a truncated corpus.
        corrupt = tmp_path / "119-hr.zip"
        corrupt.write_bytes(b"not a zip")

        extracted = extract_archives(tmp_path)

        assert extracted == []
        assert not archive_extract_dir(tmp_path, corrupt).exists()

    def test_a_failed_archive_does_not_abort_the_batch(self, tmp_path):
        # Sorted order puts the corrupt archive first, so a bare raise would cost the
        # healthy ones too.
        (tmp_path / "119-aaa.zip").write_bytes(b"not a zip")
        write_archive(tmp_path, "119-zzz")

        extracted = extract_archives(tmp_path)

        assert [p.name for p in extracted] == ["119-zzz"]
        assert (tmp_path / "119-zzz" / "119-zzz-1.xml").exists()
        assert not (tmp_path / "119-aaa").exists()

    def test_only_zip_files_are_considered(self, tmp_path, capsys):
        # The bills directory holds bills.csv and extracted folders alongside the
        # archives, so the glob is what keeps them out. Asserting the extracted list
        # alone would not catch a widened glob: a non-ZIP that gets attempted fails to
        # open and is swallowed by the same except that handles a corrupt archive, so
        # the list comes out identical either way and only the log betrays it.
        write_archive(tmp_path, "119-hr")
        (tmp_path / "notes.txt").write_text("ignore me")
        (tmp_path / "bills.csv").write_text("id\n")

        extracted = extract_archives(tmp_path)

        assert [p.name for p in extracted] == ["119-hr"]
        assert not (tmp_path / "notes").exists()
        err = capsys.readouterr().err
        assert "notes.txt" not in err
        assert "bills.csv" not in err

    def test_zero_member_archive_still_creates_its_folder(self, tmp_path):
        # A zero-member ZIP is structurally valid and is deliberately not treated as a
        # failed download (see _verify_archive_complete). zipfile.extractall does not
        # create the destination when there is nothing to write, so the explicit
        # mkdir in extract_archive is the only thing that does -- and without the
        # folder the run would report an extraction that left no cache entry, so the
        # next run would extract it again instead of skipping.
        write_archive(tmp_path, "119-hr", members={})

        extracted = extract_archives(tmp_path)

        assert [p.name for p in extracted] == ["119-hr"]
        assert (tmp_path / "119-hr").is_dir()
        assert extract_archives(tmp_path) == []  # now a coherent cache entry

    def test_empty_source_directory_yields_nothing(self, tmp_path):
        assert extract_archives(tmp_path) == []

    def test_missing_source_directory_raises(self, tmp_path):
        missing = tmp_path / "nope"
        with pytest.raises(ValueError, match="Source folder does not exist"):
            extract_archives(missing)

    def test_rerun_after_a_successful_extract_is_a_no_op(self, tmp_path):
        # The cache-coherence property stated end to end: extract, then extract again
        # and get nothing new, with the first run's output intact.
        write_archive(tmp_path, "119-hr")

        first = extract_archives(tmp_path)
        second = extract_archives(tmp_path)

        assert [p.name for p in first] == ["119-hr"]
        assert second == []
        assert (tmp_path / "119-hr" / "119-hr-1.xml").exists()
