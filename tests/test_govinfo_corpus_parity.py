"""Parity gate: govinfo enumeration reproduces the on-disk corpus filenames (#10).

The #10 migration made BILLSTATUS date the single version-ordering authority and the
govinfo version code the naming authority. That legitimately renamed corpus files
(``4_reported-to-senate`` -> ``4_reported-in-senate``; 115-hr-1625 enrolled ``7_`` ->
``6_`` once the url-less Engrossed-Amendment-House phantom is excluded from the count).
This gate locks that alignment: every version filename already on disk must be one
govinfo enumeration would produce *today*, so a future ordering/naming change can't
leave the corpus pinned to stale names that then silently mis-key the property gates.

Live BILLSTATUS fetch per bill, so it is ``slow`` + ``network``: skipped by default, run
with ``pytest --run-network -m slow``. It fetches BILLSTATUS directly rather than reading
a cache so it validates the *current* live enumeration, not a snapshot that could drift
with it.

The ``network`` marker replaced REQUIRE_CORPUS=1 in #278: the requirement is a network,
which no fixture scheme can supply, and the marker says that where the env var did not.

WHY THIS RUNS ON A SCHEDULE AND NOT AFTER A DOWNLOAD (#342). The obvious automation —
fetch the corpus, then check it — is vacuous, and it fails GREEN. ``fetch_bills`` names
each file from the same ``enumerate_versions`` call this gate compares against, so
download-then-check compares a value with itself and would pass every run forever,
including the run where the naming actually changed. The gate carries information only
against filenames chosen EARLIER: the committed fixtures, whose names were frozen in git
when each bill was fetched. Hence a schedule over the committed set, and no download step.
"""

from __future__ import annotations

import re

import httpx
import pytest

import fetch_govinfo as gi
from fetch_bills import sanitize_version_name
from tests.conftest import manifest_bill_ids
from tests.corpus_paths import sweep_bill_dirs

pytestmark = [pytest.mark.slow, pytest.mark.network]

# bills/<congress>-<type>-<number>. Non-matching entries (bulk .zip archives, .error
# markers) are not per-bill corpus dirs and are skipped.
_DIR_RE = re.compile(r"^(\d+)-([a-z]+)-(\d+)$")

# The curated corpus is a *subset* of each bill's versions and may carry a version the
# bill textVersions enumeration path does not serve. 119-hr-1's Public Law text is the
# PLAW-* collection (a different govinfo collection, excluded by design), hand-added to
# the corpus. Keyed by bill dir -> the on-disk stems enumeration will not reproduce.
_ACCEPTED_EXTRA_STEMS: dict[str, set[str]] = {
    "119-hr-1": {"6_public-law"},
}

# Floor: every bill the committed manifest names must be on disk and compared. Derived,
# not a hardcoded count (#342): the old floor pinned 31 dirs, the size of one maintainer's
# fully downloaded corpus, so the gate could not run anywhere else — a clean checkout has
# only the committed fixtures and failed the floor before comparing anything.
#
# Deriving it from tests/corpus_manifest.toml makes the requirement "the committed set is
# intact", which every checkout can satisfy, and names WHICH bill is missing rather than
# reporting a count that shrank. It still fails closed on a partial corpus, which is the
# point (#167: an empty corpus would otherwise pass as "0 compared, 0 stale").
#
# The COMPARISON walks both trees (tests/corpus/ + bills/), not just the manifest. In automation
# that is exactly the committed set; on a machine with bills downloaded it also checks
# those, so scheduling this loses no local coverage.


def _corpus_dirs():
    # Both trees (#308): the committed fixtures in tests/corpus/ AND any bills downloaded
    # into bills/. In automation that is exactly the committed set (which satisfies the
    # manifest floor below); on a maintainer's machine it also checks downloaded bills.
    return [d for d in sweep_bill_dirs() if _DIR_RE.match(d.name)]


def missing_manifest_dirs(dirs) -> list[str]:
    """Manifested bills with no directory among ``dirs``. Must be empty.

    Split out from the test so the floor is unit-testable WITHOUT a network (see
    test_corpus_manifest). The gate itself only runs under ``--run-network``, so a floor
    written inline would be exercised solely on a maintainer's machine — and a floor never
    shown to fire cannot distinguish "the corpus is intact" from "the check is broken"."""
    return sorted(set(manifest_bill_ids()) - {d.name for d in dirs})


def _enumeration_stems(client: httpx.Client, congress: int, btype: str, number: int) -> set[str]:
    """The ``{index}_{slug}`` stems download would write for this bill, from live enumeration."""
    versions = gi.enumerate_versions(client, congress, btype, number)
    return {f"{i}_{sanitize_version_name(v['type'])}" for i, v in enumerate(versions, 1)}


def test_govinfo_enumeration_reproduces_corpus_filenames():
    """Every on-disk version stem must be one govinfo enumeration produces now.

    Subset invariant, not set equality: the corpus keeps only some versions of a bill,
    so enumeration may list stems absent from disk (fine — just not fetched). The failure
    is the reverse — a stem ON disk that enumeration does NOT produce, i.e. a stale name.
    """
    dirs = _corpus_dirs()
    # Completeness floor: without it an empty/partial corpus would pass as
    # "0 compared, 0 stale" (#167 fail-open).
    absent = missing_manifest_dirs(dirs)
    assert not absent, (
        f"parity gate is missing {len(absent)} bill(s) the committed manifest names: "
        f"{absent}. An incomplete corpus would pass without comparing them. These are "
        "committed fixtures, so a missing one means the checkout is damaged rather than "
        "unfetched — see tests/corpus_manifest.toml."
    )

    client = httpx.Client(timeout=30, follow_redirects=True)
    compared = 0
    stale: dict[str, list[str]] = {}
    try:
        for d in dirs:
            congress, btype, number = _DIR_RE.match(d.name).groups()
            enum_stems = _enumeration_stems(client, int(congress), btype, int(number))
            disk_stems = {f.stem for f in d.iterdir() if f.suffix in (".xml", ".pdf")}
            drift = disk_stems - enum_stems - _ACCEPTED_EXTRA_STEMS.get(d.name, set())
            compared += 1
            if drift:
                stale[d.name] = sorted(drift)
    finally:
        client.close()

    # Guards the loop actually ran to completion over every discovered dir.
    assert compared == len(dirs), f"compared {compared} of {len(dirs)} dirs (enumeration aborted early)"
    assert not stale, (
        f"{sum(len(v) for v in stale.values())} on-disk stem(s) across {len(stale)} bill(s) "
        "diverge from govinfo enumeration — stale names. Re-download the bill "
        "(./tools/fetch_bills.py download <congress> <type> <number> --format both), or add to "
        f"_ACCEPTED_EXTRA_STEMS if legitimate (e.g. a Public Law text): {stale}"
    )
