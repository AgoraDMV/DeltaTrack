"""Tests for scripts/fetch_test_assets.py."""

from __future__ import annotations

import re
import sys
import urllib.request
from unittest import mock

import pytest

from scripts.fetch_test_assets import ASSETS, build_parser, fetch_asset, main

# Valid destinations: tests/data/<file>.pdf (watermark + subcommittee prints) or
# tests/corpus/<congress>-<type>-<num>/<file>.pdf (catchline repro bills, which keep the
# fetch_bills.py per-bill layout, DeltaTrack#105). Both trees are committed now, so this
# script re-obtains the upstream bytes rather than supplying anything a clone lacks; the
# pattern keeps a new entry from landing outside either fixture tree (#308).
_DEST_RE = re.compile(r"^(tests/data/.+|tests/corpus/\d+-[a-z]+-\d+/.+)\.pdf$")


def test_assets_registry_well_formed():
    assert ASSETS, "registry should not be empty"
    for dest_rel, url in ASSETS:
        assert _DEST_RE.match(dest_rel), dest_rel
        assert url.startswith("https://www.govinfo.gov/"), url


def test_watermark_pdf_registered():
    dests = [dest for dest, _ in ASSETS]
    assert "tests/data/BILLS-118s4795rs.pdf" in dests


def test_catchline_repro_bills_registered():
    # Guard against silent divergence: the SEC.-catchline FP guards in
    # test_pdf_anchor_golden.py load these exact paths and skip-if-absent, so a
    # registry/test path mismatch would mask the guard. Keep the two in sync.
    dests = {dest for dest, _ in ASSETS}
    assert "tests/corpus/117-hr-2471/1_introduced-in-house.pdf" in dests
    assert "tests/corpus/118-hr-2882/1_introduced-in-house.pdf" in dests


def test_skips_existing(tmp_path, monkeypatch):
    dest = tmp_path / "tests" / "data" / "x.pdf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"already")
    monkeypatch.setattr("scripts.fetch_test_assets._ROOT", tmp_path)

    def boom(*args, **kwargs):
        raise AssertionError("should not download when the file already exists")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    wrote = fetch_asset("tests/data/x.pdf", "https://www.govinfo.gov/whatever.pdf")
    assert wrote is False
    assert dest.read_bytes() == b"already"


def test_writes_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.fetch_test_assets._ROOT", tmp_path)

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"%PDF-fake"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: FakeResp())

    wrote = fetch_asset("tests/data/new.pdf", "https://www.govinfo.gov/new.pdf")
    assert wrote is True
    assert (tmp_path / "tests" / "data" / "new.pdf").read_bytes() == b"%PDF-fake"


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["--help"])
    assert excinfo.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_unknown_argument_exits_two_with_usage(capsys):
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["--nope"])
    assert excinfo.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_main_parses_argv_and_rejects_unknown_argument(monkeypatch, capsys):
    """Wiring: main() must run argv through the parser before touching any asset."""
    monkeypatch.setattr(sys, "argv", ["fetch_test_assets.py", "--nope"])
    # Pin the ordering, not just the rejection: SystemExit(2) and "usage:" hold
    # even if the parse is moved to the END of main(), after the fetch loop has
    # already run (#297's shape under a green suite). The work may never start.
    fetch = mock.Mock(side_effect=AssertionError("fetch_asset ran before argv was parsed"))
    monkeypatch.setattr("scripts.fetch_test_assets.fetch_asset", fetch)
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    assert "usage:" in capsys.readouterr().err
    fetch.assert_not_called()
