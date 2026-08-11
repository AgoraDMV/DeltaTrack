"""Re-fetch, from govinfo, the PDF test assets that fetch_bills.py cannot produce.

These are PDFs pulled straight from govinfo rather than via fetch_bills.py, whose
default format is XML. They are public domain (17 U.S.C. 105).

**Every asset listed below is now committed to the repository**, so a fresh clone
already has them and running this script prints "already present" for all of them.
That reverses the original design, in which they were gitignored and fetched on
demand: ADR 0015 committed the curated fixture set instead, because gates that
parametrized over "whatever this machine happened to have downloaded" ran on
different sets per machine and passed green in CI while asserting nothing.

What this script is still for: re-obtaining an asset that was deleted locally, and
recording where each one came from, so the committed corpus stays reproducible from
its upstream source rather than being a set of binaries with no provenance. Adding a
new asset here does NOT commit it: `git add` it too. No .gitignore edit is needed —
both destination trees are tracked by default, which is the inversion #308 made.

Currently:
- tests/data/BILLS-118s4795rs.pdf - the reported-in-Senate (watermarked) print
  of S.4795, read by tests/test_pdf_watermark_recall.py.
- tests/data/subcommittee/BILLS-118hr*rh.pdf - one FY2025 reported-in-House print
  per appropriations subcommittee, read by the major-level cross-subcommittee
  tests (DeltaTrack#105). Major/department heading vocabulary differs per
  subcommittee, so these guard against overfitting to one or two bills. CJS and
  Homeland are covered by existing fixtures (118-s-4795, 118-hr-8752).

Usage:
  uv run python scripts/fetch_test_assets.py        # fetch any missing assets
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_GOVINFO = "https://www.govinfo.gov/content/pkg"


def _gov(pkg: str) -> str:
    return f"{_GOVINFO}/{pkg}/pdf/{pkg}.pdf"


# FY2025 House reported prints, one per appropriations subcommittee not already
# covered by an existing fixture (DeltaTrack#105). govinfo package -> subcommittee.
_SUBCOMMITTEE_PACKAGES = {
    "BILLS-118hr9027rh": "agriculture",
    "BILLS-118hr8774rh": "defense",
    "BILLS-118hr8997rh": "energy-water",
    "BILLS-118hr8773rh": "financial-services",
    "BILLS-118hr8998rh": "interior",
    "BILLS-118hr9029rh": "labor-hhs",
    "BILLS-118hr8772rh": "legislative-branch",
    "BILLS-118hr8580rh": "milcon-va",
    "BILLS-118hr8771rh": "state-foreign-ops",
    "BILLS-118hr9028rh": "transportation-hud",
}

# SEC.-catchline false-positive repro bills (introduced-in-House). Used by the
# catchline guards in test_pdf_anchor_golden.py (a wrapped SEC. catchline must not
# surface as an account or a major). They are committed fixtures under tests/corpus/<id>/
# and keep the fetch_bills.py per-bill layout the tests reference; fetched from govinfo
# here to get the PDF format specifically (fetch_bills.py's default format is XML).
_CATCHLINE_BILLS = {
    "tests/corpus/117-hr-2471/1_introduced-in-house.pdf": "BILLS-117hr2471ih",
    "tests/corpus/118-hr-2882/1_introduced-in-house.pdf": "BILLS-118hr2882ih",
}

# (destination path relative to the repo root, govinfo URL)
ASSETS: list[tuple[str, str]] = [
    ("tests/data/BILLS-118s4795rs.pdf", _gov("BILLS-118s4795rs")),
    *((f"tests/data/subcommittee/{pkg}.pdf", _gov(pkg)) for pkg in _SUBCOMMITTEE_PACKAGES),
    *((dest, _gov(pkg)) for dest, pkg in _CATCHLINE_BILLS.items()),
]


def fetch_asset(dest_rel: str, url: str) -> bool:
    """Download url to dest_rel (relative to repo root) if missing.

    Returns True when a file was written, False when it was already present.
    """
    dest = _ROOT / dest_rel
    if dest.exists():
        print(f"  already present: {dest_rel}")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (govinfo, https)
        dest.write_bytes(resp.read())
    print(f"  saved: {dest_rel}")
    return True


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)


def main() -> None:
    build_parser().parse_args()
    for dest_rel, url in ASSETS:
        fetch_asset(dest_rel, url)


if __name__ == "__main__":
    main()
