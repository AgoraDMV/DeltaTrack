#!/usr/bin/env -S uv run --quiet python
"""
fetch_bill_archives:

Companion to ``fetch_bill_text_archives.py``. Downloads BILLSTATUS bulk ZIPs and
extracts them into ``bills/<id>/<id>_status.xml``.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from shared.bill_index import BillIndex, make_bill_id
from shared.bill_types import resolve_bill_types
from shared.http import download_archives as http_download_archives
from shared.zip import extract_archive

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BILLS_DIR = PROJECT_DIR / "bills"
DEFAULT_ZIP_DIR = PROJECT_DIR / "bills_bulk_status"
BILLSTATUS_ZIP_FORMAT = "BILLSTATUS-{congress}-{bill_type}.zip"

GOVINFO_BASE_URL = "https://www.govinfo.gov/bulkdata/"
GOVINFO_BILLSTATUS_ZIP_URL_FORMAT = (
    GOVINFO_BASE_URL + "BILLSTATUS/{congress}/{bill_type}/BILLSTATUS-{congress}-{bill_type}.zip"
)
GOVINFO_BILL_FILENAME_RE = re.compile(
    r"^BILLSTATUS-(\d+)([a-z]+)(\d+)\.xml$",
    re.IGNORECASE,
)
GOVINFO_BILLSTATUS_FILENAME_FORMAT = "BILLSTATUS-{congress}{bill_type}{number}.xml"


def parse_billstatus_filename(filename: str) -> tuple[int, str, int]:  # (congress, bill_type, number)
    """``BILLSTATUS-119hr1.xml`` → ``(119, "hr", 1)``."""
    match = GOVINFO_BILL_FILENAME_RE.match(Path(filename).name)
    if not match:
        return (0, "", 0)
    congress, bill_type, number = match.groups()
    return int(congress), bill_type, int(number)


def archive_destination(destination: Path, congress: int, bill_type: str) -> Path:
    """Return the local path for one BILLSTATUS archive."""
    return destination / BILLSTATUS_ZIP_FORMAT.format(congress=congress, bill_type=bill_type)


def billstatus_zip_url(congress: int, bill_type: str) -> str:
    return GOVINFO_BILLSTATUS_ZIP_URL_FORMAT.format(congress=congress, bill_type=bill_type)


def billstatus_zip_filename(congress: int, bill_type: str) -> str:
    return BILLSTATUS_ZIP_FORMAT.format(congress=congress, bill_type=bill_type)


def billstatus_filename(congress: int, bill_type: str, number: int) -> str:
    return GOVINFO_BILLSTATUS_FILENAME_FORMAT.format(congress=congress, bill_type=bill_type, number=number)


def enumerate_congresses(from_congress: int, to_congress: int) -> list[int]:
    return list(
        range(from_congress, to_congress + 1)
        if from_congress <= to_congress
        else range(from_congress, to_congress - 1, -1)
    )


def enumerate_tasks(
    from_congress: int,
    to_congress: int,
    *,
    bill_types: list[str] | None = None,
) -> list[tuple[int, str]]:
    """Return the BILLSTATUS archive scopes for a congress range."""
    return [
        (congress, bill_type)
        for congress in enumerate_congresses(from_congress, to_congress)
        for bill_type in resolve_bill_types(bill_types)
    ]


def download_archives(
    from_congress: int,
    to_congress: int,
    bill_types: list[str],
    destination: Path,
    *,
    overwrite_existing: bool = False,
) -> list[Path]:
    """Download BILLSTATUS ZIPs for each (congress, type); skip existing unless overwriting."""
    tasks = enumerate_tasks(from_congress, to_congress, bill_types=bill_types)
    urls = [billstatus_zip_url(congress, bill_type) for congress, bill_type in tasks]
    with httpx.Client(timeout=300) as client:
        return http_download_archives(
            client,
            urls,
            destination,
            url_to_path=lambda url, index: archive_destination(Path(), *tasks[index]),
            skip_existing=not overwrite_existing,
        )


def extract_bill_metadata(xml_content: str | bytes, bill_id: str) -> dict[str, Any]:
    """Pull a short status summary from one BILLSTATUS XML. ``bill_id`` comes from the filename."""
    if isinstance(xml_content, bytes):
        xml_content = xml_content.decode("utf-8", errors="replace")
    bill = ET.fromstring(xml_content).find("bill")
    if bill is None:
        raise ValueError(f"No <bill> element in {bill_id}")

    introduced = bill.findtext("introducedDate", "").strip()
    last_action = bill.findtext("latestAction/actionDate", "").strip()
    days_active = None
    if introduced and last_action:
        days_active = (date.fromisoformat(last_action) - date.fromisoformat(introduced)).days

    committees = bill.findall("committees/item") or bill.findall("committees/billCommittees/item")
    return {
        "id": bill_id,
        "title": (bill.findtext("title") or "").strip(),
        "introducedDate": introduced,
        "lastActionDate": last_action,
        "daysActive": days_active,
        "status": bill.findtext("latestAction/text", "").strip(),
        "policyArea": bill.findtext("policyArea/name", "").strip(),
        "historySize": len(xml_content),
        "actionCount": len(bill.findall("actions/item")),
        "versionCount": len(bill.findall("textVersions/item")),
        "amendmentCount": len(bill.findall("amendments/amendment")),
        "relatedBillsCount": len(bill.findall("relatedBills/item")),
        "committeeCount": len(committees),
    }


def convert_archives(
    zip_dir: Path,
    out_dir: Path,
    *,
    from_congress: int,
    to_congress: int,
    bill_types: list[str],
    overwrite_existing: bool = False,
    bill_index_path: Path | None = None,
) -> None:
    """Extract BILLSTATUS members via ``extract_archive`` into ``<id>/<id>_status.xml``."""
    tasks = enumerate_tasks(from_congress, to_congress, bill_types=bill_types)
    zip_paths = [archive_destination(zip_dir, congress, bill_type) for congress, bill_type in tasks]
    bill_index = BillIndex(csv_path=bill_index_path) if bill_index_path else None
    records: list[dict[str, Any]] = []

    def handle_file(filename: str, _i: int, _zf: zipfile.ZipFile) -> str | None:
        congress, bill_type, number = parse_billstatus_filename(filename)
        bill_id = f"{congress}-{bill_type}-{number}"
        return f"{bill_id}/{bill_id}_status.xml"

    def handle_content(content: bytes, filename: str, _i: int, _zf: zipfile.ZipFile) -> bytes:
        if bill_index is not None:
            congress, bill_type, number = parse_billstatus_filename(filename)
            bill_id = make_bill_id(congress, bill_type, number)
            try:
                records.append(extract_bill_metadata(content, bill_id))
            except Exception as exc:
                print(f"  error extracting metadata from {filename}: {exc}", file=sys.stderr)
                records.append({"id": bill_id, "bill_status_error": str(exc)})
        return content

    for i, path in enumerate(zip_paths):
        print(f"  {i + 1}/{len(zip_paths)}: extracting {path.name}...", file=sys.stderr)
        try:
            extract_archive(
                path,
                out_dir=out_dir,
                files=GOVINFO_BILL_FILENAME_RE,
                overwrite_existing=overwrite_existing,
                file_handler=handle_file,
                file_content_handler=handle_content,
            )
        except Exception as exc:
            if not path.exists():
                print(f"  {path.name} not found, skipping", file=sys.stderr)
            else:
                print(f"  error extracting {path.name}: {exc}", file=sys.stderr)

    if bill_index is not None and records:
        bill_index.add_bills(records, mode="merge")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from-congress", type=int, default=118)
    p.add_argument("--to-congress", type=int, default=119)
    p.add_argument(
        "--types",
        nargs="+",
        default=["all"],
        help="Bill types to download. Use 'all' to include every key from shared/BILL_TYPES.",
    )
    p.add_argument("--zip-dir", type=Path, default=DEFAULT_ZIP_DIR)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_BILLS_DIR)
    p.add_argument("--bill-index-file", type=Path, help="Optional CSV to merge per-bill metadata")
    p.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Re-download ZIPs and overwrite extracted status files (default: skip existing)",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    download_archives(
        args.from_congress,
        args.to_congress,
        args.types,
        args.zip_dir,
        overwrite_existing=args.overwrite_existing,
    )
    convert_archives(
        args.zip_dir,
        args.out_dir,
        from_congress=args.from_congress,
        to_congress=args.to_congress,
        bill_types=args.types,
        overwrite_existing=args.overwrite_existing,
        bill_index_path=args.bill_index_file,
    )


if __name__ == "__main__":
    main()
