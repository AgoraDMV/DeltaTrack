"""Tests for scripts/fetch_test_assets.py."""

from __future__ import annotations

import re
import urllib.request

from scripts.fetch_test_assets import ASSETS, fetch_asset

# Valid destinations: test_data/<file>.pdf (watermark + subcommittee prints) or
# bills/<congress>-<type>-<num>/<file>.pdf (catchline repro bills sharing the
# fetch_bills.py layout, DeltaTrack#105). Both gitignored, fetched on demand.
_DEST_RE = re.compile(r"^(test_data/.+|bills/\d+-[a-z]+-\d+/.+)\.pdf$")


def test_assets_registry_well_formed():
    assert ASSETS, "registry should not be empty"
    for dest_rel, url in ASSETS:
        assert _DEST_RE.match(dest_rel), dest_rel
        assert url.startswith("https://www.govinfo.gov/"), url


def test_watermark_pdf_registered():
    dests = [dest for dest, _ in ASSETS]
    assert "test_data/BILLS-118s4795rs.pdf" in dests


def test_catchline_repro_bills_registered():
    # Guard against silent divergence: the SEC.-catchline FP guards in
    # test_pdf_anchor_golden.py load these exact paths and skip-if-absent, so a
    # registry/test path mismatch would mask the guard. Keep the two in sync.
    dests = {dest for dest, _ in ASSETS}
    assert "bills/117-hr-2471/1_introduced-in-house.pdf" in dests
    assert "bills/118-hr-2882/1_introduced-in-house.pdf" in dests


def test_skips_existing(tmp_path, monkeypatch):
    dest = tmp_path / "test_data" / "x.pdf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"already")
    monkeypatch.setattr("scripts.fetch_test_assets._ROOT", tmp_path)

    def boom(*args, **kwargs):
        raise AssertionError("should not download when the file already exists")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    wrote = fetch_asset("test_data/x.pdf", "https://www.govinfo.gov/whatever.pdf")
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

    wrote = fetch_asset("test_data/new.pdf", "https://www.govinfo.gov/new.pdf")
    assert wrote is True
    assert (tmp_path / "test_data" / "new.pdf").read_bytes() == b"%PDF-fake"
