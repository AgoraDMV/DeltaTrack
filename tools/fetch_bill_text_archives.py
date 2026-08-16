#!/usr/bin/env -S uv run --quiet python
"""
fetch_bill_text_archives:

Bulk builder for a multi-version bill-text corpus, on top of the govinfo access
layer in ``fetch_govinfo.py``. The companion to ``fetch_bill_archives.py``
(which fetches BILLSTATUS *metadata*); this fetches the BILLS *text* collection.

Downloads the per-(congress, session, type) BILLS ZIPs from govinfo bulk data
(no API key, no rate limit), then converts them into the corpus layout the diff
pipeline reads: ``bills/<congress>-<type>-<number>/<index>_<version-slug>.xml``.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict, namedtuple
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

import fetch_govinfo as gi
from bill_index import BillIndex
from diff_bill import extract_amounts
from shared.bill_types import BILL_TYPES
from shared.http import download_archives as http_download_archives, download_zip
from shared.zip import ArchiveFile, extract_archive, iterate_archive

type BillId = str
type BillVersionCode = str

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_BILLS_DIR = PROJECT_DIR / "bills"

DEFAULT_BILL_TYPES = ["all"]
BillVersion = namedtuple("BillVersion", ["version_code", "archive_file"])

# ---- STEP 1: download the per-(congress, session, type) BILLS ZIPs -----------
def download_archives(congresses: list[int], bill_types: list[str], zip_dir: Path) -> list[Path]:
    """Download BILLS ZIPs for each (congress, session, type); skip existing."""
    tasks = [
        (congress, session, bill_type)
        for congress in congresses
        for session in gi.sessions_for_congress(congress)
        for bill_type in bill_types
    ]
    urls = [gi.bills_zip_url(congress, session, bill_type) for congress, session, bill_type in tasks]

    def path_by_url(_url: str, index: int) -> Path:
        congress, session, bill_type = tasks[index]
        return Path(f"BILLS-{congress}-{session}-{bill_type}.zip")

    with httpx.Client(timeout=300) as client:
        return http_download_archives(
            client,
            urls,
            zip_dir,
            url_to_path=path_by_url,
        )


# ---- STEP 2: convert ZIP members into the bills/<id>/<index>_<slug>.xml layout
def convert_archives(
    zip_dir: Path,
    out_dir: Path,
    *,
    from_congress: int = 0,
    to_congress: int = sys.maxsize,
    bill_types: list[str] | None = None,
    min_versions: int = 1,
    skip_existing_dirs: bool = True,
) -> dict[str, int]:
    """Group ZIP members by bill, order versions, and write the corpus layout.

    Args:
    ``zip_dir``: Directory of downloaded ``BILLS-*.zip`` archives to convert. Downloads archives as needed while skipping duplicate downloads.
    ``out_dir``: Destination root for ``bills/<id>/<n>_<slug>.xml`` corpus files.    
    ``min_versions``: Minimum version count to keep a bill (1 = all bills; 2+ = cross-version matchable corpus).
    ``skip_existing_dirs``: When true, skip bills whose output directory already exists.

    Returns:
        Counters for bills seen, written, skipped, and related convert diagnostics.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stats: Counter[str] = Counter()
    zip_paths = sorted(zip_dir.glob("BILLS-*.zip"))
    bill_types = set(bill_types or BILL_TYPES.keys())
    def zip_path_matches_parameters(zp: Path) -> bool:
        congress, bill_type = gi.parse_bill_archive_filename(zp.name)
        return congress in range(from_congress, to_congress + 1) and bill_type in bill_types
    zip_paths = list(filter(zip_path_matches_parameters, zip_paths))

    # aggregated versions per bill - the main data structure to work from:
    bill_version_codes_by_id: dict[BillId, list[BillVersionCode]] = defaultdict(list) 
    # optional bookkeeping of all bill versions encountered. Flags when a bill txt appears in more than one archive
    archive_files_by_bill_basename: dict[str, list[ArchiveFile]] = defaultdict(list) 
    # optional bookkeeping of unknown bill versions codes encountered.
    unknown_codes: Counter[str] = Counter()

    # Pass 1.1 - aggregate bill files: assemble versions per bill, filter invalid bills + versions
    # The main outcome of this pass is to organize per-bill versions for all relevant bill texts
    print(f"Examining {len(zip_paths)} bulk data zip files...", file=sys.stderr)
    readable_zip_paths: list[Path] = []
    for zp in zip_paths:
        try:
            for filename, _ in iterate_archive(zp, pattern="*.xml"):
                parsed = gi.parse_bill_version_filename(filename)
                if parsed is None:
                    print(f"  not a bill file: {filename}", file=sys.stderr)
                    continue
                congress, bill_type, number, version_code = parsed
                bill_id = gi.create_bill_id(congress, bill_type, number)

                # maintain archives by bill basename to detect duplicates. A version that
                # appears in more than one archive (e.g. it spans both session ZIPs) is
                # kept from the first archive only, so it isn't double-counted below.
                archive_file = ArchiveFile(zip_path=zp, file_path=filename)
                basename = Path(filename).name
                archive_files_by_bill_basename[basename].append(archive_file)
                if len(archive_files_by_bill_basename[basename]) > 1:
                    print(f"  Bill version {basename} appears in multiple archives: {archive_files_by_bill_basename[basename]}", file=sys.stderr)
                    continue

                # aggregate bill versions by bill id
                # archive files automatically list bill versions in chronological order instead of alphabetically
                bill_version_codes_by_id[bill_id].append(version_code)

                # maintain invalid version codes (optional, for bookkeeping only)
                _code_description, code_tier = gi.resolve_code(version_code)
                if code_tier == 0:
                    unknown_codes[version_code] += 1
            readable_zip_paths.append(zp)
        except zipfile.BadZipFile:
            stats["corrupt_zip_skipped"] += 1
            print(f"  skipped corrupt ZIP during counting: {zp.name}", file=sys.stderr)
            continue
    zip_paths = readable_zip_paths

    # 1.2: Filter bills with too few versions and bills that already exist
    print(f"Removing bills with too few versions and pre-existing bills from {len(archive_files_by_bill_basename)} bill texts...", file=sys.stderr)
    stats["bills_seen"] = len(bill_version_codes_by_id)
    eligible = {bill_id for bill_id, versions in bill_version_codes_by_id.items() if len(versions) >= min_versions}
    existing = {bill_id for bill_id in eligible if skip_existing_dirs and (out_dir / bill_id).exists()}
    valid_bill_ids = eligible - existing
    bill_version_codes_by_id = { id: bill_version_codes_by_id[id] for id in valid_bill_ids }

    stats["below_min_versions_skipped"] = stats["bills_seen"] - len(eligible)
    stats["existing_dir_skipped"] = len(existing)
    
    if len(valid_bill_ids) == 0:
        print("No new bills found")
        return dict(stats)

    # Pass 2: unarchive zip files and write bill versions to the corpus
    # The outcome of this pass is to create bill data and metadata from the archive files.
    bill_text_count = sum(map(len, bill_version_codes_by_id.values()))
    print(f"Saving {len(valid_bill_ids)} bills and {bill_text_count} bill texts to {out_dir}...")
    bill_metadata: list[dict[str, Any]] = []

    bills_written: set[BillId] = set()
    bills_skipped: set[BillId] = set()
    def handle_bill_file(filename: str, _zf_file_index: int, _zf: zipfile.ZipFile) -> str | None:
        # file processing: reorganize into folders by bill id folders with named versions. Example:
        # 119-hr-1/
        #  1_introduced-in-house.xml
        #  2_reported-in-house.xml
        nonlocal bills_written, bills_skipped
        congress, bill_type, number, version_code = gi.parse_bill_version_filename(filename)
        bill_id = gi.create_bill_id(congress, bill_type, number)
        # cross-reference bills with the registry of valid bills and versions.
        # this handler gets called on all files because it leverages the extract_archive utility.
        # returning None skips the file, saving expensive I/O
        bill_versions = bill_version_codes_by_id.get(bill_id, [])
        if not bill_versions:
            bills_skipped.add(bill_id)
            return None

        code_description = gi.sanitize(gi.resolve_code(version_code)[0])
        index = bill_version_codes_by_id[bill_id].index(version_code)
        bills_written.add(bill_id)
        return f"{bill_id}/{index + 1}_{code_description}.xml"  # named version

    for index, path in enumerate(zip_paths):
        print(f"  {index + 1}/{len(zip_paths)}: extracting {path}...")
        extract_archive(
            path, 
            out_dir=out_dir, 
            overwrite_existing=not skip_existing_dirs,
            file_handler=handle_bill_file,
            file_content_handler=handle_bill_file_content,
        )
    stats["bills_written"] = len(bills_written)

    if unknown_codes:
        print(f"  unresolved version codes (tier 0): {dict(unknown_codes)}", file=sys.stderr)
    version_hist = Counter([len(codes) for codes in bill_version_codes_by_id.values()])
    print(f"  version-count histogram (versions -> #bills): {dict(sorted(version_hist.items()))}", file=sys.stderr)
    return dict(stats)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from-congress", type=int, default=118)
    p.add_argument("--to-congress", type=int, default=119)
    p.add_argument("--types", nargs="+", default=list(DEFAULT_BILL_TYPES))
    p.add_argument("--zip-dir", type=Path, default=PROJECT_DIR / "bills_bulk_text")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_BILLS_DIR)
    p.add_argument(
        "--min-versions",
        type=int,
        default=1,
        help="Keep bills with >= this many versions (1=every bill, 2+=matchable test corpus)",
    )
    p.add_argument("--download-only", action="store_true", help="Download ZIPs, skip conversion")
    p.add_argument("--convert-only", action="store_true", help="Convert already-downloaded ZIPs")
    p.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Overwrite bill dirs that already exist (default: skip, protects the curated corpus)",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    congresses = list(range(args.from_congress, args.to_congress + 1))
    if not args.convert_only:
        download_archives(congresses, args.types, args.zip_dir)
    if not args.download_only:
        stats = convert_archives(
            args.zip_dir,
            args.out_dir,
            from_congress=args.from_congress,
            to_congress=args.to_congress,
            bill_types=args.types,
            min_versions=args.min_versions,
            skip_existing_dirs=not args.overwrite_existing,
            bill_index_path=args.bill_index_file,
        )
        print(f"convert stats: {stats}", file=sys.stderr)


if __name__ == "__main__":
    main()
