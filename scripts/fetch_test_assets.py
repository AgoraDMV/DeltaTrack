"""Fetch external test assets that fetch_bills.py cannot produce.

A few slow tests read files sourced directly from govinfo rather than the
Congress.gov bill API. They are public domain (17 U.S.C. 105) but large
binaries, so they are gitignored and fetched on demand here, keeping the
test corpus reproducible without committing PDFs.

Currently:
- test_data/BILLS-118s4795rs.pdf - the reported-in-Senate (watermarked) print
  of S.4795, read by tests/test_pdf_watermark_recall.py.
- test_data/subcommittee/BILLS-118hr*rh.pdf - one FY2025 reported-in-House print
  per appropriations subcommittee, read by the major-level cross-subcommittee
  tests (DeltaTrack#105). Major/department heading vocabulary differs per
  subcommittee, so these guard against overfitting to one or two bills. CJS and
  Homeland are covered by existing fixtures (118-s-4795, 118-hr-8752).

Usage:
  uv run python scripts/fetch_test_assets.py        # fetch any missing assets
"""

from __future__ import annotations

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
# surface as an account or a major). They live under bills/<id>/ to match the
# fetch_bills.py layout the tests already reference; sourcing them from govinfo here
# means the guards run in CI instead of skipping when no Congress.gov key is set.
_CATCHLINE_BILLS = {
    "bills/117-hr-2471/1_introduced-in-house.pdf": "BILLS-117hr2471ih",
    "bills/118-hr-2882/1_introduced-in-house.pdf": "BILLS-118hr2882ih",
}

# (destination path relative to the repo root, govinfo URL)
ASSETS: list[tuple[str, str]] = [
    ("test_data/BILLS-118s4795rs.pdf", _gov("BILLS-118s4795rs")),
    *((f"test_data/subcommittee/{pkg}.pdf", _gov(pkg)) for pkg in _SUBCOMMITTEE_PACKAGES),
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


def main() -> None:
    for dest_rel, url in ASSETS:
        fetch_asset(dest_rel, url)


if __name__ == "__main__":
    main()
