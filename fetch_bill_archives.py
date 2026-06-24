#!/usr/bin/env -S uv run --quiet python
"""
fetch_bill_archives:

Downloads bulk bill data using GovInfo BILLSTATUS bulk archive ZIP files.
This is a separate API and separate logic from the usual congres.gov API.
It is meant for large volumes of bills. When combined with bill_index,
fetch_bill_archives creates a large index of bill metadata that can be
used for data analysis and testing.
"""

from __future__ import annotations

import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator

import httpx

from bill_index import BillIndex, InsertMode, make_bill_id
from shared.bill_types import BILL_TYPES

BillMetadata = dict[str, Any]

# Workaround so that the script always runs correctly when running an an IDE
PROJECT_DIR = Path(__file__).resolve().parent

DEFAULT_BILLS_DIR = PROJECT_DIR / "bills"

GOVINFO_BILLSTATUS_ZIP_URL = (
    "https://www.govinfo.gov/bulkdata/BILLSTATUS/{congress}/{bill_type}/BILLSTATUS-{congress}-{bill_type}.zip"
)

_POPULAR_TITLE_RE = re.compile(r"^popular\s+titles?\b", re.IGNORECASE)
_BILLSTATUS_XML_GLOB = "BILLSTATUS*.xml"
_BILLSTATUS_XML_NAME_RE = re.compile(r"^BILLSTATUS-(\d+)([a-z]+)(\d+)\.xml$", re.IGNORECASE)
LOG_PERFORMANCE = False


# STEP 1: Download zip archives
# The fastest way to get massive amounts of bill metadata is to download complete zip archives from govinfo bulk data.
# Bill archives are stored per congress and bill type. Each zip file has per-bill metadata for up to thousands of bills.
def archive_url(congress: int, bill_type: str) -> str:
    """Build direct download URL for one BILLSTATUS archive ZIP."""
    return GOVINFO_BILLSTATUS_ZIP_URL.format(congress=congress, bill_type=bill_type)


def resolve_destination(destination: Path | str | None = None) -> Path:
    """Resolve destination relative to this script's project directory."""
    path = Path(destination or DEFAULT_BILLS_DIR)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    return path


def archive_destination(destination: Path, congress: int, bill_type: str) -> Path:
    """Build the output path for one BILLSTATUS archive ZIP."""
    return destination / f"{congress}-{bill_type}.zip"


def archive_error_path(destination: Path, congress: int, bill_type: str) -> Path:
    """Build the error marker path for one failed archive download."""
    return destination / f"{congress}-{bill_type}.error"


def _print_download_progress(downloaded: int, total: int) -> None:
    """Print a single-line download progress update to stderr."""
    if total:
        pct = downloaded * 100 // total
        mb_done = downloaded / (1024 * 1024)
        mb_total = total / (1024 * 1024)
        print(f"\r  {mb_done:.1f}/{mb_total:.1f} MB ({pct}%)", end="", file=sys.stderr, flush=True)
    else:
        mb_done = downloaded / (1024 * 1024)
        print(f"\r  {mb_done:.1f} MB downloaded", end="", file=sys.stderr, flush=True)


def archive_temp_path(dest: Path) -> Path:
    """Build temporary path used while downloading one archive."""
    return dest.with_suffix(dest.suffix + ".part")


def _progress_prefix(index: int, total: int) -> str:
    """Build a ``current/total:`` progress prefix for batch status lines."""
    return f"{index}/{total}:"


def enumerate_tasks(
    from_congress: int,
    to_congress: int,
    *,
    bill_types: list[str] | None = None,
) -> list[tuple[int, str]]:
    """Return newest-first (congress, bill_type) tasks for a validated selection."""
    selected_types = _validate_archive_params(from_congress, to_congress, bill_types)
    congresses = reversed(range(from_congress, to_congress + 1))
    return [(congress, bill_type) for congress in congresses for bill_type in selected_types]


# STEP 1: Download archives
# The bulk data API has zip files per congress and bill type. Each ZIP file has per-bill metadata.
def download_archive_zip(client: httpx.Client, url: str, dest: Path) -> None:
    """Stream one archive ZIP to disk atomically, printing progress when possible."""
    temp_path = archive_temp_path(dest)
    if temp_path.exists():
        temp_path.unlink()

    try:
        with client.stream("GET", url, follow_redirects=True, timeout=300) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0) or 0)
            downloaded = 0
            with temp_path.open("wb") as fh:
                for chunk in response.iter_bytes(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    downloaded += len(chunk)
                    _print_download_progress(downloaded, total)
            print(file=sys.stderr)
            if total and downloaded != total:
                raise httpx.HTTPError(f"Incomplete download: got {downloaded} of {total} bytes")
        temp_path.replace(dest)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def download_archives(
    from_congress: int,
    to_congress: int,
    *,
    bill_types: list[str] | None = None,
    destination: Path | str | None = None,
) -> list[Path]:
    """Download BILLSTATUS archive ZIPs for congress/type combinations."""
    destination = resolve_destination(destination)
    destination.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    tasks = enumerate_tasks(from_congress, to_congress, bill_types=bill_types)
    total = len(tasks)

    with httpx.Client(timeout=300) as client:
        for index, (congress, bill_type) in enumerate(tasks, start=1):
            prefix = _progress_prefix(index, total)
            dest = archive_destination(destination, congress, bill_type)
            error_path = archive_error_path(destination, congress, bill_type)

            if dest.exists():
                print(f"{prefix} Skipping existing archive: {dest.name}", file=sys.stderr)
                continue

            url = archive_url(congress, bill_type)
            print(f"{prefix} Downloading {dest.name}", file=sys.stderr)
            print(f"  {url}", file=sys.stderr)
            try:
                download_archive_zip(client, url, dest)
            except Exception as exc:
                error_path.write_text(str(exc), encoding="utf-8")
                print(f"{prefix} Failed {dest.name}: wrote {error_path.name}", file=sys.stderr)
                continue

            if error_path.exists():
                error_path.unlink()
            downloaded.append(dest)
            print(f"{prefix} Saved: {dest.name}", file=sys.stderr)

    return downloaded


# Step 2: Extract archives
# Once we have zip files per congress and bill type, we need to extract the per-bill metadata from the archives.
def archive_extract_dir(source: Path, archive: Path) -> Path:
    """Build extraction directory for one archive (same stem as the zip)."""
    return source / archive.stem


def extract_archive(archive: Path, dest_dir: Path) -> None:
    """Extract one archive ZIP into dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest_dir)


def extract_archives(source: Path | str | None = None) -> list[Path]:
    """Extract all ZIP archives in source, skipping existing folders."""
    source = resolve_destination(source)
    if not source.is_dir():
        raise ValueError(f"Source folder does not exist: {source}")

    extracted: list[Path] = []
    archives = sorted(source.glob("*.zip"))
    total = len(archives)

    for index, archive in enumerate(archives, start=1):
        prefix = _progress_prefix(index, total)
        dest_dir = archive_extract_dir(source, archive)
        if dest_dir.exists():
            print(f"{prefix} Skipping existing folder: {dest_dir.name}", file=sys.stderr)
            continue

        print(f"{prefix} Extracting {archive.name}", file=sys.stderr)
        try:
            extract_archive(archive, dest_dir)
        except Exception as exc:
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            print(f"{prefix} Failed {archive.name}: {exc}", file=sys.stderr)
            continue

        extracted.append(dest_dir)

    return extracted


def iter_billstatus_files(
    from_congress: int,
    to_congress: int,
    *,
    bill_types: list[str] | None = None,
    destination: Path | str | None = None,
) -> Iterator[Path]:
    """Yield BILLSTATUS XML files for archive folders matching the congress/type selection."""
    for congress, bill_type in enumerate_tasks(
        from_congress,
        to_congress,
        bill_types=bill_types,
    ):
        yield from enumerate_files(congress, bill_type, destination=destination)


def enumerate_files(
    congress: int,
    bill_type: str,
    *,
    destination: Path | str | None = None,
) -> list[Path]:
    """Return BILLSTATUS XML files for one extracted archive folder."""
    destination = resolve_destination(destination)
    archive_dir = archive_extract_dir(
        destination,
        archive_destination(destination, congress, bill_type),
    )
    if not archive_dir.is_dir():
        return []
    return sorted(archive_dir.glob(_BILLSTATUS_XML_GLOB))


def _bill_id_from_xml_path(xml_path: Path | str) -> str | None:
    """Derive bill id from BILLSTATUS xml file name without opening the file."""
    match = _BILLSTATUS_XML_NAME_RE.match(Path(xml_path).name)
    if not match:
        return None
    congress, bill_type, number = match.groups()
    return make_bill_id(congress, bill_type.lower(), number)


def _xml_path_from_bill_id(bill_id: str) -> Path:
    """Derive BILLSTATUS XML file path from bill id."""
    congress, bill_type, number = bill_id.split("-")
    return Path(f"BILLSTATUS-{congress}{bill_type}{number}.xml")


def _pick_bill_title(bill: ET.Element) -> str:
    """Prefer a popular title; otherwise use the first listed title."""
    titles = bill.find("titles")
    if titles is not None:
        for item in titles.findall("item"):
            title_type = item.findtext("titleType", "")
            if _POPULAR_TITLE_RE.match(title_type):
                title = item.findtext("title", "").strip()
                if title:
                    return title

        for item in titles.findall("item"):
            title = item.findtext("title", "").strip()
            if title:
                return title

    return bill.findtext("title", "").strip()


def _bill_number(bill: ET.Element) -> str:
    """Read bill number from modern or legacy BILLSTATUS XML."""
    return (bill.findtext("number") or bill.findtext("billNumber") or "").strip()


def _bill_type_slug(bill: ET.Element) -> str:
    """Read bill type slug from modern or legacy BILLSTATUS XML."""
    return (bill.findtext("type") or bill.findtext("billType") or "").strip().lower()


def _committee_count(bill: ET.Element) -> int:
    """Count committees across modern and legacy BILLSTATUS XML layouts."""
    items = bill.findall("committees/item")
    if not items:
        items = bill.findall("committees/billCommittees/item")
    return len(items)


def _first_summary_length(bill: ET.Element) -> int:
    """Return character length of the first CRS summary text, if present."""
    summaries = bill.find("summaries")
    if summaries is None:
        return 0

    for tag_path in ("summary", "billSummaries/item", "item"):
        first_summary = summaries.find(tag_path)
        if first_summary is not None:
            return len((first_summary.findtext("text", "") or "").strip())

    return 0


def _days_active(introduced_date: str, last_action_date: str) -> int | None:
    """Return days between introduction and last action, if both dates are present."""
    if not introduced_date or not last_action_date:
        return None
    start = date.fromisoformat(introduced_date)
    end = date.fromisoformat(last_action_date)
    return (end - start).days


def extract_bill_metadata_from_archive_xml(source: Path | str) -> BillMetadata:
    """
    Convert one GovInfo BILLSTATUS XML file into succinct bill metadata.
    XML data is from responses to requests of the form:
    https://www.govinfo.gov/bulkdata/BILLSTATUS/119/hr/BILLSTATUS-119hr123.xml

    """
    xml_path = Path(source)
    bill = ET.parse(xml_path).getroot().find("bill")
    if bill is None:
        raise ValueError(f"No <bill> element found in {xml_path}")

    congress = bill.findtext("congress", "").strip()
    number = _bill_number(bill)
    bill_type = _bill_type_slug(bill)
    if not congress or not number or not bill_type:
        raise ValueError(f"Missing congress, type, or number in {xml_path}")

    introduced_date = bill.findtext("introducedDate", "").strip()
    last_action_date = bill.findtext("latestAction/actionDate", "").strip()

    return {
        "id": make_bill_id(congress, bill_type, number),
        "title": _pick_bill_title(bill),
        "introducedDate": introduced_date,
        "lastActionDate": last_action_date,
        "daysActive": _days_active(introduced_date, last_action_date),
        "status": bill.findtext("latestAction/text", "").strip(),
        "policyArea": bill.findtext("policyArea/name", "").strip(),
        "historySize": xml_path.stat().st_size,
        "summaryLength": _first_summary_length(bill),
        "actionCount": len(bill.findall("actions/item")),
        "versionCount": len(bill.findall("textVersions/item")),
        "budgetEstimateCount": len(bill.findall("cboCostEstimates/item")),
        "amendmentCount": len(bill.findall("amendments/amendment")),
        "relatedBillsCount": len(bill.findall("relatedBills/item")),
        "committeeCount": _committee_count(bill),
        "sponsorCount": len(bill.findall("sponsors/item")),
    }


def _validate_archive_params(
    from_congress: int,
    to_congress: int,
    bill_types: list[str] | None,
) -> list[str]:
    """Validate congress range and bill types; return selected type slugs."""
    if from_congress > to_congress:
        raise ValueError(f"from_congress ({from_congress}) must be <= to_congress ({to_congress})")

    selected_types = bill_types or list(BILL_TYPES)
    unknown = [bill_type for bill_type in selected_types if bill_type not in BILL_TYPES]
    if unknown:
        raise ValueError(f"Unknown bill types: {unknown}")
    return selected_types


def parse_bill_archives(
    from_congress: int,
    to_congress: int,
    *,
    bill_types: list[str] | None = None,
    destination: Path | str | None = None,
    index: BillIndex | None = None,
    mode: InsertMode = "skip",
):
    """Parse BILLSTATUS XML for archive folders matching the congress/type selection."""
    destination = resolve_destination(destination)
    tasks = enumerate_tasks(from_congress, to_congress, bill_types=bill_types)
    task_count = len(tasks)
    index = index or BillIndex(DEFAULT_BILLS_DIR / "bills.csv")
    for task_index, (congress, bill_type) in enumerate(tasks, start=1):
        prefix = _progress_prefix(task_index, task_count)

        enum_start = perf_counter()
        bill_xml_paths = enumerate_files(congress, bill_type, destination=destination)
        enumerate_secs = perf_counter() - enum_start
        bill_ids = [_bill_id_from_xml_path(xml_path) for xml_path in bill_xml_paths]
        bill_paths_by_id = {bill_id: xml_path for xml_path, bill_id in zip(bill_xml_paths, bill_ids)}
        new_bill_ids, existing_bill_ids = index.find_new_and_existing_bill_ids(bill_ids)
        parse_bill_ids = new_bill_ids if mode == "skip" else bill_ids
        parse_bill_paths = [bill_paths_by_id[bill_id] for bill_id in parse_bill_ids]

        extract_start = perf_counter()
        records = [extract_bill_metadata_from_archive_xml(xml_path) for xml_path in parse_bill_paths]
        extract_secs = perf_counter() - extract_start

        merge_start = perf_counter()
        index.add_bills(records, mode=mode)
        merge_secs = perf_counter() - merge_start

        status_parts = []
        if existing_bill_ids:
            status_parts.append(f"found {len(existing_bill_ids)} existing bills")
        if new_bill_ids:
            status_parts.append(f"added {len(new_bill_ids)} new bills")
        updated_count = len(existing_bill_ids) if mode != "skip" else 0
        if updated_count:
            status_parts.append(f"updated {updated_count} bills")

        print(
            f"{prefix} {congress}-{bill_type} - {', '.join(status_parts)}",
            file=sys.stderr,
        )

        if LOG_PERFORMANCE:
            print(
                (
                    f"{prefix} {congress}-{bill_type} performance - "
                    f"enumerating files: {enumerate_secs:.3f}s, "
                    f"extracting metadata: {extract_secs:.3f}s, "
                    f"merging index: {merge_secs:.3f}s"
                ),
                file=sys.stderr,
            )

    if index is not None:
        print(
            (f"Done parsing: bill index saved at {index.csv_path.resolve()} with {len(index.bills)} records"),
            file=sys.stderr,
        )


def fetch_bill_archives(
    from_congress: int,
    to_congress: int,
    *,
    bill_types: list[str] | None = None,
    destination: Path | str | None = None,
    index: BillIndex | None = None,
    mode: InsertMode = "merge",
) -> list[BillMetadata]:
    """Download, extract, and index GovInfo BILLSTATUS bulk archives.

    Each phase skips work that is already done: existing ZIPs, extracted folders,
    and bill ids already present in the index (when merging).
    """
    destination = resolve_destination(destination)

    print("Phase 1/3: Download archives", file=sys.stderr)
    download_archives(
        from_congress,
        to_congress,
        bill_types=bill_types,
        destination=destination,
    )

    print("Phase 2/3: Extract archives", file=sys.stderr)
    extract_archives(destination)

    print("Phase 3/3: Parse metadata into index", file=sys.stderr)
    return parse_bill_archives(
        from_congress,
        to_congress,
        bill_types=bill_types,
        destination=destination,
        index=index,
        mode=mode,
    )


if __name__ == "__main__":
    fetch_bill_archives(112, 119, index=BillIndex(DEFAULT_BILLS_DIR / "bills.csv"))
