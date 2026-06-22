#!/usr/bin/env python3

"""Download bill text versions from Congress.gov.

Uses the Congress.gov API v3 to fetch bill text in XML format
for downstream comparison between versions.
"""

import argparse
import datetime
import os
import re
import sys
import time
from pathlib import Path
from shared.http import request_with_retry, api_get
from shared.bill_types import BILL_TYPES
from bill_index import BillIndex, parse_bill_id

import httpx
from dotenv import load_dotenv

BASE_URL = "https://api.congress.gov/v3"

def sanitize_version_name(name: str) -> str:
    """Convert a version type like 'Reported in House' to 'reported-in-house'."""
    if not name:
        return "unknown"
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "unknown"


def congress_for_year(year: int) -> int:
    """Map a calendar year to its Congress number.

    The 1st Congress began in 1789. Each Congress spans two years.
    """
    return (year - 1789) // 2 + 1


APPROPRIATIONS_COMMITTEES = [
    ("house", "hsap00"),
    ("senate", "ssap00"),
]


def get_api_key() -> str:
    """Load API key from environment, with DEMO_KEY fallback."""
    key = os.environ.get("CONGRESS_API_KEY", "DEMO_KEY")
    if key == "DEMO_KEY":
        print(
            "WARNING: Using DEMO_KEY (30 req/hr). Get a key at https://api.congress.gov/sign-up/",
            file=sys.stderr,
        )
    return key

def fetch_all_committee_bills(
    client: httpx.Client, chamber: str, committee_code: str, *, api_key: str, page_size: int = 250
) -> list[dict]:
    """Fetch all bills from a committee, paginating through the full list."""
    path = f"/committee/{chamber}/{committee_code}/bills"
    all_bills = []
    offset = 0

    while True:
        data = api_get(
            client,
            path,
            api_key=api_key,
            params={"limit": page_size, "offset": offset, "format": "json"},
        )
        bills = data.get("committee-bills", {}).get("bills", [])
        all_bills.extend(bills)
        total = data.get("pagination", {}).get("count", 0)
        offset += page_size
        if offset >= total:
            break

    return all_bills


def format_version_list(versions: list[dict]) -> str:
    """Format text versions as a numbered list for display."""
    if not versions:
        return "No text versions available."
    lines = []
    for i, v in enumerate(versions, 1):
        date_raw = v.get("date")
        date_str = date_raw[:10] if date_raw else "no date"
        lines.append(f"  {i}. {v.get('type', 'Unknown')} ({date_str})")
    return "\n".join(lines)


def fetch_text_versions(
    client: httpx.Client, congress: int, bill_type: str, number: int, *, api_key: str
) -> list[dict]:
    """Fetch all text versions for a bill, in chronological order (oldest first)."""
    path = f"/bill/{congress}/{bill_type}/{number}/text"
    data = api_get(client, path, api_key=api_key, params={"format": "json"})
    versions = data.get("textVersions", [])
    # Sort chronologically (oldest first). Null-dated versions (e.g. Enrolled Bill)
    # get the max date so they sort alongside the latest entries, with type name
    # as tiebreaker (Enrolled Bill < Public Law alphabetically).
    max_date = max((v.get("date") for v in versions if v.get("date")), default="")
    versions.sort(key=lambda v: (v.get("date") or max_date, v.get("type", "")))
    return versions


def version_path(
    output_dir: Path,
    congress: int,
    bill_type: str,
    number: int,
    index: int,
    version_type: str,
    ext: str = "xml",
) -> Path:
    """Build the output path for a version file without writing anything."""
    bill_dir = output_dir / f"{congress}-{bill_type}-{number}"
    filename = f"{index}_{sanitize_version_name(version_type)}.{ext}"
    return bill_dir / filename


def save_version(
    content: bytes,
    output_dir: Path,
    congress: int,
    bill_type: str,
    number: int,
    index: int,
    version_type: str,
    ext: str = "xml",
) -> Path:
    """Write version content to a structured output path. Returns the file path."""
    path = version_path(output_dir, congress, bill_type, number, index, version_type, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def download_bill_version(client: httpx.Client, url: str, timeout: int = 60) -> bytes:
    """Download raw XML content from a congress.gov URL, with retry."""
    resp = request_with_retry(client, url, timeout=timeout)
    return resp.content if resp else b""

# Backwards-compatible name used by older unit tests/docs.
def download_version_xml(client: httpx.Client, url: str) -> bytes:
    return download_bill_version(client, url)

def get_xml_url(version: dict) -> str | None:
    """Extract the XML format URL from a version's formats list."""
    for fmt in version.get("formats", []):
        if fmt.get("type") == "Formatted XML":
            return fmt.get("url")
    return None


def get_pdf_url(version: dict) -> str | None:
    """Extract the PDF format URL from a version's formats list."""
    for fmt in version.get("formats", []):
        if fmt.get("type") == "PDF":
            return fmt.get("url")
    return None


_FORMAT_URL_GETTERS = {"xml": get_xml_url, "pdf": get_pdf_url}


def formats_from_arg(value: str) -> list[str]:
    """Expand a --format choice ('xml', 'pdf', 'both') into formats to fetch."""
    return ["xml", "pdf"] if value == "both" else [value]


def download_version(
    client: httpx.Client,
    version: dict,
    *,
    output_dir: Path,
    congress: int,
    bill_type: str,
    number: int,
    index: int,
    total: int,
    formats: list[str],
    timeout: int = 60,
) -> None:
    """Download the requested format(s) for a single version, skipping existing files."""
    vtype = version.get("type", "unknown")
    for fmt in formats:
        url = _FORMAT_URL_GETTERS[fmt](version)
        if not url:
            print(f"  Skipping version {index} ({vtype}): no {fmt.upper()} available", file=sys.stderr)
            continue
        dest = version_path(output_dir, congress, bill_type, number, index, vtype, ext=fmt)
        if dest.exists():
            print(f"  Already exists: {dest}", file=sys.stderr)
            continue
        print(f"  Downloading version {index}/{total} ({fmt}): {vtype}...", file=sys.stderr)
        try:
            content = download_bill_version(client, url, timeout=timeout)
            save_version(content, output_dir, congress, bill_type, number, index, vtype, ext=fmt)
            print(f"  Saved: {dest}", file=sys.stderr)
        except Exception as exc:
            # Don't kill the whole batch: write an error marker beside the target.
            error_path = Path(str(dest) + ".error")
            error_path.parent.mkdir(parents=True, exist_ok=True)
            error_path.write_text(str(exc), encoding="utf-8")
            print(f"  FAILED: wrote {error_path.name}", file=sys.stderr)
            continue


def cmd_versions(client: httpx.Client, args: argparse.Namespace, api_key: str):
    """Show available text versions for a bill."""
    versions = fetch_text_versions(client, args.congress, args.bill_type, args.number, api_key=api_key)
    label, _ = BILL_TYPES.get(args.bill_type, (args.bill_type.upper(), ""))
    print(f"\nText versions for {label} {args.number} ({args.congress}th Congress):\n")
    print(format_version_list(versions))
    print()


def cmd_download(client: httpx.Client, args: argparse.Namespace, api_key: str):
    """Download text versions for a single bill."""
    versions = fetch_text_versions(client, args.congress, args.bill_type, args.number, api_key=api_key)

    if not versions:
        print("No text versions available.", file=sys.stderr)
        return

    if args.version is not None:
        if args.version < 1 or args.version > len(versions):
            print(f"Version {args.version} out of range (1-{len(versions)}).", file=sys.stderr)
            sys.exit(1)
        targets = [(args.version, versions[args.version - 1])]
    else:
        targets = list(enumerate(versions, 1))

    formats = formats_from_arg(args.format)
    for index, version in targets:
        download_version(
            client,
            version,
            output_dir=args.output_dir,
            congress=args.congress,
            bill_type=args.bill_type,
            number=args.number,
            index=index,
            total=len(versions),
            formats=formats,
        )


def download_all_versions(
    client: httpx.Client,
    *,
    output_dir: Path,
    congress: int,
    bill_type: str,
    number: int,
    api_key: str,
    formats: list[str],
    timeout: int = 60,
) -> None:
    """Download every available text version for one bill."""
    label, _ = BILL_TYPES.get(bill_type, (bill_type.upper(), ""))
    print(f"\n{label} {number} ({congress}th Congress):", file=sys.stderr)

    versions = fetch_text_versions(client, congress, bill_type, number, api_key=api_key)
    if not versions:
        print("  No text versions available", file=sys.stderr)
        return

    total = len(versions)
    for version_index, version in enumerate(versions, 1):
        download_version(
            client,
            version,
            output_dir=output_dir,
            congress=congress,
            bill_type=bill_type,
            number=number,
            index=version_index,
            total=total,
            formats=formats,
            timeout=timeout,
        )


def cmd_download_all(client: httpx.Client, args: argparse.Namespace, api_key: str):
    """Download all appropriations bill versions for a year range."""
    if args.start_year is None and args.end_year is None and args.file is None:
        print("start_year, end_year, or file must be provided.", file=sys.stderr)
        sys.exit(1)
    formats = formats_from_arg(args.format)
    if args.file:
        index = BillIndex(args.file)
        bill_ids = [b["id"].strip() for b in index.bills if b.get("id", "").strip()]

        print(f"Downloading {len(bill_ids)} bills from {args.file}", file=sys.stderr)
        for raw_slug in bill_ids:
            ident = parse_bill_id(raw_slug)
            download_all_versions(
                client,
                output_dir=args.output_dir,
                congress=ident.congress,
                bill_type=ident.bill_type,
                number=ident.number,
                api_key=api_key,
                formats=formats,
            )

        return


    start_year = args.start_year or 1789
    end_year = args.end_year or datetime.now().year
    if args.start_year > args.end_year:
        print(f"start_year ({args.start_year}) must be <= end_year ({args.end_year}).", file=sys.stderr)
        sys.exit(1)
    target_congresses = sorted({congress_for_year(y) for y in range(args.start_year, args.end_year + 1)})
    print(f"Target congresses: {target_congresses}", file=sys.stderr)

    # Fetch all bills from both committees
    all_bills = []
    for chamber, code in APPROPRIATIONS_COMMITTEES:
        print(f"Fetching bills from {chamber} appropriations...", file=sys.stderr)
        all_bills.extend(fetch_all_committee_bills(client, chamber, code, api_key=api_key))

    # Deduplicate and filter to target congresses
    seen = set()
    filtered = []
    for bill in all_bills:
        congress = bill.get("congress")
        if congress not in target_congresses:
            continue
        key = (congress, bill.get("type"), bill.get("number"))
        if key not in seen:
            seen.add(key)
            filtered.append(bill)

    print(f"Found {len(filtered)} bills for congresses {target_congresses}", file=sys.stderr)

    for bill in filtered:
        congress = bill.get("congress")
        bill_type = bill.get("type", "").lower()
        number = bill.get("number")
        formats = formats_from_arg(args.format)
        download_all_versions(
            client,
            output_dir=args.output_dir,
            congress=int(congress),
            bill_type=bill_type,
            number=int(number),
            api_key=api_key,
            formats=formats,
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Download appropriations bill text versions from Congress.gov",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # versions: list available text versions
    p_ver = subparsers.add_parser("versions", help="List available text versions for a bill")
    p_ver.add_argument("congress", type=int, help="Congress number (e.g. 118)")
    p_ver.add_argument("bill_type", choices=sorted(BILL_TYPES.keys()), help="Bill type (e.g. hr, s)")
    p_ver.add_argument("number", type=int, help="Bill number")

    # download: download versions for a single bill
    p_dl = subparsers.add_parser("download", help="Download bill text versions")
    p_dl.add_argument("congress", type=int, help="Congress number (e.g. 118)")
    p_dl.add_argument("bill_type", choices=sorted(BILL_TYPES.keys()), help="Bill type (e.g. hr, s)")
    p_dl.add_argument("number", type=int, help="Bill number")
    p_dl.add_argument("--version", type=int, default=None, help="Specific version number (1-indexed)")
    p_dl.add_argument("--output-dir", type=Path, default=Path("bills"), help="Output directory")
    p_dl.add_argument(
        "--format", choices=["xml", "pdf", "both"], default="both", help="Format(s) to download (default: pdf)"
    )

    # download-all: bulk download for a year range
    p_all = subparsers.add_parser("download-all", help="Download all appropriations bill versions for a year range")
    p_all.add_argument("--start_year", type=int, default = None, help="Start year (e.g. 2024)")
    p_all.add_argument("--end_year", type=int, default = None, help="End year (e.g. 2026)")
    p_all.add_argument("--file", type=Path, default=None, help="CSV file path with an 'id' column")
    p_all.add_argument("--output-dir", type=Path, default=Path("bills"), help="Output directory")
    p_all.add_argument(
        "--format", choices=["xml", "pdf", "both"], default="both", help="Format(s) to download (default: pdf)"
    )

    return parser


def main():
    load_dotenv()
    api_key = get_api_key()
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    args = parser.parse_args()

    with httpx.Client(timeout=30) as client:
        if args.command == "versions":
            cmd_versions(client, args, api_key)
        elif args.command == "download":
            cmd_download(client, args, api_key)
        elif args.command == "download-all":
            cmd_download_all(client, args, api_key)


if __name__ == "__main__":
    main()
