"""Build test_data/validation_<slug>.json for each committee-report jurisdiction.

External ground truth for #8: each Senate appropriations committee report is read for its
3-line account summary blocks (committee-recommendation amounts, in actual dollars), which
tests/test_validate_extraction.py validates against the reported bill's XML. Mirrors the
hand-curated validation_leg_branch.json, but generated deterministically from the report.

Sources are fetched from govinfo (both gitignored locally); the JSON fixtures are committed.
The jurisdiction registry lives in validation_sources.py.

Usage:
  uv run python scripts/build_validation.py              # build from local report HTML
  uv run python scripts/build_validation.py --fetch      # fetch missing sources first
  uv run python scripts/build_validation.py --fetch cjs  # restrict to one slug
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

# Run-from-anywhere: put the repo root on the path so root-level modules import. pytest
# gets this via pyproject's pythonpath; a plain `python scripts/...` invocation does not.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsers.committee_report import extract_pre_text, parse_summary_blocks  # noqa: E402
from validation_sources import BY_SLUG, JURISDICTIONS, Jurisdiction  # noqa: E402

_GOVINFO = "https://www.govinfo.gov/content/pkg"


def _fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  fetching {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (govinfo, https)
        dest.write_bytes(resp.read())


def fetch_sources(j: Jurisdiction) -> None:
    """Download the report HTML and bill XML for a jurisdiction if not already present."""
    if not j.report_html_path.exists():
        _fetch(f"{_GOVINFO}/{j.report_pkg}/html/{j.report_pkg}.htm", j.report_html_path)
    if not j.bill_xml_path.exists():
        _fetch(f"{_GOVINFO}/{j.bill_pkg}/xml/{j.bill_pkg}.xml", j.bill_xml_path)


def build_fixture(j: Jurisdiction) -> dict:
    accounts = parse_summary_blocks(extract_pre_text(j.report_html_path.read_text(encoding="utf-8", errors="replace")))
    rows = [
        {
            "bill": j.bill_id,
            "version": j.version,
            "fy": j.fy,
            "chamber": j.chamber,
            "title": acc.title,  # enclosing agency, e.g. "DEPARTMENT OF JUSTICE"
            "excel_name": acc.heading,
            "expected_amount": acc.committee_recommendation,
        }
        for acc in accounts
    ]
    return {
        "source": f"{j.report_pkg}, {j.display} explanatory statement for {j.bill_pkg}",
        "note": (
            f"{j.display} {j.fy} (Reported in Senate) account amounts, extracted from the "
            "committee report's 3-line summary blocks and validated against the bill XML. "
            "Committee-recommendation amounts are in actual dollars; `title` is the enclosing "
            "appropriations title/agency, used for agency-scoped recall. External ground truth "
            "for GitHub #8. Regenerate with scripts/build_validation.py."
        ),
        "accounts": rows,
    }


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--fetch"]
    do_fetch = "--fetch" in sys.argv
    targets = [BY_SLUG[s] for s in args] if args else JURISDICTIONS
    for j in targets:
        if do_fetch:
            fetch_sources(j)
        if not j.report_html_path.exists():
            print(f"skip {j.slug}: {j.report_html_path} not present (use --fetch)")
            continue
        data = build_fixture(j)
        j.fixture_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {j.fixture_path} ({len(data['accounts'])} accounts)")


if __name__ == "__main__":
    main()
