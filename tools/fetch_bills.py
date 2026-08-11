#!/usr/bin/env python3

"""Download bill text versions for downstream comparison.

Fetches from govinfo bulk data by default (``--source govinfo``; keyless, no rate
limit); the Congress.gov API v3 remains available via ``--source api``. Handles
XML and PDF (``--format``).
"""

import argparse
import codecs
import datetime
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

import fetch_govinfo as gi
from bill_index import BillIdentifier, BillIndex, parse_bill_id
from fetch_bill_archives import archive_destination, download_archives, enumerate_tasks
from shared.bill_types import BILL_TYPES
from shared.http import api_get, request_with_retry

BASE_URL = "https://api.congress.gov/v3"

# Bill-text sources. Default is govinfo (keyless, no rate limit; issue #10); the
# Congress.gov API path stays fully supported via --source api.
SOURCES = ("govinfo", "api")
DEFAULT_SOURCE = "govinfo"


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


def enumerate_bill_versions(
    client: httpx.Client, congress: int, bill_type: str, number: int, *, source: str, api_key: str | None
) -> list[dict]:
    """Return one bill's versions from the selected source, API-dict-shaped.

    The seam that makes --source a one-line switch: govinfo enumeration
    (:func:`fetch_govinfo.enumerate_versions`) emits the same
    ``{type, date, formats:[{type, url}]}`` shape the Congress.gov API returns, so
    :func:`download_version` and :func:`format_version_list` -- and their tests --
    are untouched. govinfo needs no key; the API path keeps its key.
    """
    if source == "govinfo":
        gi.require_supported_congress(congress)
        return gi.enumerate_versions(client, congress, bill_type, number)
    return fetch_text_versions(client, congress, bill_type, number, api_key=api_key)


def enumerate_versions_and_gaps(
    client: httpx.Client, congress: int, bill_type: str, number: int, *, source: str, api_key: str | None
) -> tuple[list[dict], list[dict] | None]:
    """The download paths' enumeration: versions plus XML-less gap records, one fetch.

    Returns ``(versions, gaps)`` where ``versions`` is the same API-dict-shaped list
    :func:`enumerate_bill_versions` returns and ``gaps`` is the #230 gap-marker
    records -- or ``None`` on the API source, meaning "this source has no opinion
    about gaps, leave any marker alone" (distinct from ``[]``, "no gaps: clear it").
    Gaps are a govinfo *format* concept -- a version GPO never composed XML for --
    so the API path fetches no BILLSTATUS it does not otherwise need.

    Both halves are pure functions of one parsed BILLSTATUS ``<bill>`` element, so
    this issues a single request per bill (#253). Deriving them separately, via
    :func:`enumerate_bill_versions` plus a gap fetch, doubles per-bill BILLSTATUS
    traffic and rate-limit exposure across a ``download-all`` sweep.

    :func:`enumerate_bill_versions` stays the narrow, API-shaped seam for `versions`
    and any other consumer that wants only the downloadable list (#10).
    """
    if source != "govinfo":
        return fetch_text_versions(client, congress, bill_type, number, api_key=api_key), None
    gi.require_supported_congress(congress)
    bill = gi.fetch_billstatus_bill(client, congress, bill_type, number)
    if bill is None:
        return [], []
    gi.warn_urlless_gaps(bill)
    return gi.versions_from_billstatus(bill), gi.urlless_declared_version_records(bill)


def record_gap_versions(
    *, congress: int, bill_type: str, number: int, output_dir: Path, gaps: list[dict] | None
) -> None:
    """Persist (or clear) the bill's XML-less gap marker (#230).

    ``gaps`` comes from :func:`enumerate_versions_and_gaps`; ``None`` (the API
    source) writes and clears nothing.

    Called *before* the caller's "no versions" early return on purpose: a bill whose
    every declared version is XML-less enumerates to nothing (#226's 118-hr-3496),
    which is precisely the case the marker exists to record. Writing it only
    alongside a successful download would miss exactly that bill.

    There is no fetch-failure path left to guard: the gap records now come from the
    same BILLSTATUS response the download itself is built on, so a failure there
    aborts the download loudly instead of silently degrading one side artifact.
    """
    if gaps is None:
        return
    bill_id = f"{congress}-{bill_type}-{number}"
    gi.write_gap_marker(output_dir / bill_id, bill_id, gaps)


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
    """Download raw content from a bill-version URL (govinfo or congress.gov), with retry."""
    resp = request_with_retry(client, url, timeout=timeout)
    return resp.content if resp else b""


# Backwards-compatible name used by older unit tests/docs.
def download_version_xml(client: httpx.Client, url: str) -> bytes:
    return download_bill_version(client, url)


def validate_downloaded(content: bytes, content_type: str | None, fmt: str, url: str) -> None:
    """Raise ``ValueError`` unless ``content`` really is the expected ``fmt``.

    Guards the corpus against a govinfo package that does not exist: the
    ``/content/pkg`` URL 302-redirects to an error page, so the fetch returns
    either an empty redirect body (``follow_redirects=False``) or ``200`` +
    ``text/html`` + ~44 KB of markup (``follow_redirects=True``). Written into a
    ``{n}_{label}.{ext}`` file, either one is a silently corrupt bill version
    (#10 trap 1). This runs before :func:`save_version`, so a bad body becomes a
    loud ``.error`` marker instead of a plausible-looking file. Checks the
    content-type header *and* the leading magic bytes, so it holds regardless of
    the client's redirect policy and even if a header lies.

    XML accepts a bare ``<...>`` root (the Congress.gov path and older corpus
    fixtures omit the ``<?xml`` prolog) but rejects an HTML document; PDF requires
    the ``%PDF-`` signature.
    """
    body = content[len(codecs.BOM_UTF8) :] if content.startswith(codecs.BOM_UTF8) else content
    body = body.lstrip()
    ct = (content_type or "").split(";")[0].strip().lower()

    def fail(reason: str) -> None:
        raise ValueError(
            f"Expected {fmt.upper()} from {url} but {reason} ({len(content)} bytes, starts {content[:20]!r})"
        )

    if not body:
        fail("the response body was empty")
    if ct == "text/html":
        fail(f"content-type was {ct!r} (likely a govinfo error page)")
    if fmt == "pdf":
        if not body.startswith(b"%PDF-"):
            fail("the body is not a PDF (no %PDF- signature)")
    else:  # xml
        head = body[:64].lower()
        if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
            fail("the body is an HTML document, not XML")
        if not body.startswith(b"<"):
            fail("the body does not start with a markup tag")


def fetch_version(client: httpx.Client, url: str, fmt: str, timeout: int = 60) -> bytes:
    """Download one version file and validate it is really ``fmt`` before returning.

    Parallels :func:`download_bill_version` but keeps the response so
    :func:`validate_downloaded` can see the content-type header, so the batch
    downloader never writes a govinfo error page or empty redirect body into the
    corpus (#10 trap 1). Raises ``ValueError`` on a bad body; the caller turns
    that into an ``.error`` marker beside the target.
    """
    resp = request_with_retry(client, url, timeout=timeout)
    content = resp.content if resp else b""
    content_type = resp.headers.get("content-type") if resp else None
    validate_downloaded(content, content_type, fmt, url)
    return content


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
            content = fetch_version(client, url, fmt, timeout=timeout)
            save_version(content, output_dir, congress, bill_type, number, index, vtype, ext=fmt)
            print(f"  Saved: {dest}", file=sys.stderr)
        except Exception as exc:
            # Don't kill the whole batch: write an error marker beside the target.
            error_path = Path(str(dest) + ".error")
            error_path.parent.mkdir(parents=True, exist_ok=True)
            error_path.write_text(str(exc), encoding="utf-8")
            print(f"  FAILED: wrote {error_path.name}", file=sys.stderr)
            continue


def cmd_versions(client: httpx.Client, args: argparse.Namespace, api_key: str | None):
    """Show available text versions for a bill."""
    versions = enumerate_bill_versions(
        client, args.congress, args.bill_type, args.number, source=args.source, api_key=api_key
    )
    label, _ = BILL_TYPES.get(args.bill_type, (args.bill_type.upper(), ""))
    print(f"\nText versions for {label} {args.number} ({args.congress}th Congress):\n")
    print(format_version_list(versions))
    print()


def cmd_search(client: httpx.Client, args: argparse.Namespace, api_key: str | None) -> int:
    """Find bills by title over the local BILLSTATUS index (#10 acceptance).

    Keyless: reads the BILLSTATUS ZIPs already on disk (downloaded by the
    ``fetch-index`` subcommand or fetch_bill_archives.py); no network, no client use.
    ``--congress``/``--type`` narrow the index; ``--appropriations`` applies the
    committee facet.

    Returns a ``grep``-style exit code so CLI/agent callers can branch without
    parsing stdout: ``0`` matches found, ``1`` searched but nothing matched, ``2``
    no index to search (can't run). ``main`` propagates it via ``sys.exit``.
    """
    index = gi.build_title_index(args.billstatus_dir)
    # An empty index means no BILLSTATUS ZIPs were found (a real corpus yields
    # thousands of bills), which is a different problem from "your query matched
    # nothing" -- and the likely one on a fresh clone, where bills/ has no index
    # yet. Report it distinctly (exit 2, grep's "error" code) so the user/agent isn't
    # told to check a download that a plain no-match would also blame. Note `bills/`
    # is resolved relative to the current directory, so run from the project root
    # (where fetch_bill_archives writes it).
    if not index:
        print(
            f"No BILLSTATUS index found in {args.billstatus_dir} -- fetch one first, e.g. "
            "`fetch_bills fetch-index --congress 118 --type hr` (run from the project root). "
            "See the README.",
            file=sys.stderr,
        )
        return 2
    if args.congress is not None or args.bill_type is not None:
        index = {
            bid: entry
            for bid, entry in index.items()
            for congress, btype, _number in [bid.split("-")]
            if (args.congress is None or congress == str(args.congress))
            and (args.bill_type is None or btype == args.bill_type)
        }
    query = " ".join(args.query)
    matches = gi.search_titles(index, query, appropriations=args.appropriations)
    if not matches:
        # grep's "no lines selected" code: a successful search that found nothing,
        # distinct from the exit-2 "couldn't search" case above.
        print(f"No bills matched {query!r}.", file=sys.stderr)
        return 1
    for bill_id, title in matches:
        print(f"{bill_id}\t{title}")
    return 0


def cmd_fetch_index(client: httpx.Client, args: argparse.Namespace, api_key: str | None) -> int:
    """Download the scoped BILLSTATUS ZIP(s) that keyless `search` reads (#242).

    The lightweight on-ramp for title search: reuses fetch_bill_archives.download_archives
    (its download phase only -- no extract, no CSV index) to pull just the scoped
    BILLSTATUS archive(s) into ``--billstatus-dir``, where `search` finds them offline.
    ``--type`` omitted fetches every type for the congress.

    Returns a shell exit code: ``0`` if every requested archive is present after the
    run (freshly downloaded or already on disk), ``1`` if any is missing.
    download_archives swallows a failed download into a ``.error`` marker and returns
    only successes, so a bad congress/type or a network failure would otherwise print
    "ready" and exit 0 -- and then `search` dead-ends at exit 2. Checking the archives
    are actually on disk turns that into a loud, branchable failure (matching search's
    grep-style exit codes). ``--billstatus-dir`` is resolved against the current
    directory so it names the same place `search` reads (download_archives would
    otherwise anchor a relative path to its own script dir).

    Kept a separate verb from `search` on purpose: `search` never reaches the network,
    so fetching is always an explicit step. ``client``/``api_key`` are unused --
    download_archives opens its own client and govinfo bulk data needs no key.
    """
    destination = args.billstatus_dir.resolve()
    bill_types = [args.bill_type] if args.bill_type else None
    saved = download_archives(
        args.congress,
        args.congress,
        bill_types=bill_types,
        destination=destination,
    )
    tasks = enumerate_tasks(args.congress, args.congress, bill_types=bill_types)
    missing = [
        archive_destination(destination, congress, btype)
        for congress, btype in tasks
        if not archive_destination(destination, congress, btype).exists()
    ]
    if missing:
        names = ", ".join(path.name for path in missing)
        print(
            f"Failed to fetch {len(missing)} of {len(tasks)} BILLSTATUS archive(s) into "
            f"{destination}: {names}. See the .error marker(s) beside them, and check the "
            "congress/type exists and your network is up.",
            file=sys.stderr,
        )
        return 1
    search_hint = f"fetch_bills search --congress {args.congress}"
    if args.bill_type:
        search_hint += f" --type {args.bill_type}"
    print(
        f"BILLSTATUS archives ready in {destination} "
        f"({len(saved)} newly downloaded, {len(tasks) - len(saved)} already present). "
        f"Search them with: {search_hint} <terms>",
        file=sys.stderr,
    )
    return 0


def cmd_download(client: httpx.Client, args: argparse.Namespace, api_key: str | None):
    """Download text versions for a single bill."""
    versions, gaps = enumerate_versions_and_gaps(
        client, args.congress, args.bill_type, args.number, source=args.source, api_key=api_key
    )
    record_gap_versions(
        congress=args.congress,
        bill_type=args.bill_type,
        number=args.number,
        output_dir=args.output_dir,
        gaps=gaps,
    )

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
    source: str,
    api_key: str | None,
    formats: list[str],
    timeout: int = 60,
) -> None:
    """Download every available text version for one bill."""
    label, _ = BILL_TYPES.get(bill_type, (bill_type.upper(), ""))
    print(f"\n{label} {number} ({congress}th Congress):", file=sys.stderr)

    versions, gaps = enumerate_versions_and_gaps(client, congress, bill_type, number, source=source, api_key=api_key)
    record_gap_versions(congress=congress, bill_type=bill_type, number=number, output_dir=output_dir, gaps=gaps)
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


def identify_csv_row(raw_slug: str) -> BillIdentifier | None:
    """Resolve one `--file` row to a bill identity, or None if the row is unusable.

    This is the boundary where a user-supplied CSV meets the strict slug codec, so it
    is also where compatibility is spent deliberately rather than by accident:

    - A legacy `:version` suffix is stripped with a warning, not refused. The bill is
      fully identifiable, and `bill_index` itself documented that form before ADR 0013
      retired it, so a CSV written against those docs is a reasonable artifact. This
      command downloads every version regardless, which is what the suffixed row
      already got.
    - Anything genuinely unidentifiable is reported and skipped, so one bad row cannot
      abort a long run partway through and leave a half-downloaded corpus behind.
    """
    slug = raw_slug.split(":", 1)[0]

    try:
        ident = parse_bill_id(slug)
    except ValueError as exc:
        print(f"Skipping unusable row '{raw_slug}': {exc}", file=sys.stderr)
        return None

    # Only after the row is known to name a bill: a note about the suffix on a row that
    # is being skipped anyway reads as if the suffix were the problem.
    if slug != raw_slug:
        print(
            f"Note: ignoring the version suffix on '{raw_slug}'. A bill's identity is the "
            f"slug '{slug}' and a version is a separate per-bill ordinal (ADR 0013); "
            "this command downloads every version anyway.",
            file=sys.stderr,
        )

    return ident


def cmd_download_all(client: httpx.Client, args: argparse.Namespace, api_key: str | None):
    """Download all appropriations bill versions for a year range."""
    if args.start_year is None and args.end_year is None and args.file is None:
        print("start_year, end_year, or file must be provided.", file=sys.stderr)
        sys.exit(1)
    formats = formats_from_arg(args.format)
    if args.file:
        index = BillIndex(args.file)
        bill_ids = [b["id"].strip() for b in index.bills if b.get("id", "").strip()]

        print(f"Downloading {len(bill_ids)} bills from {args.file}", file=sys.stderr)
        processed = 0
        skipped = 0
        for raw_slug in bill_ids:
            ident = identify_csv_row(raw_slug)
            if ident is None:
                skipped += 1
                continue

            # parse_bill_id returns the slug's parts as strings; download_all_versions
            # is typed for ints and the govinfo floor check compares numerically, so a
            # bare str raised TypeError on the first row (#151). The year-range path
            # below has always coerced -- this boundary is the one that did not.
            download_all_versions(
                client,
                output_dir=args.output_dir,
                congress=int(ident.congress),
                bill_type=ident.bill_type,
                number=int(ident.number),
                source=args.source,
                api_key=api_key,
                formats=formats,
            )
            processed += 1

        # Skipped rows are reported here as well as inline: on a long run the per-row
        # warnings scroll past, and a partial result that looks like a complete one is
        # the failure worth surfacing. "Processed" rather than "downloaded" because a
        # bill with no text versions available is attempted and counted here too.
        print(f"Processed {processed} bills, skipped {skipped} unusable rows.", file=sys.stderr)
        if skipped:
            # A malformed row is bad input, and this file's other input errors exit 1.
            # The whole run still completes first, so one typo neither aborts the run
            # nor lets `download-all ... && <next step>` proceed on a partial corpus.
            sys.exit(1)
        return

    start_year = args.start_year or 1789
    end_year = args.end_year or datetime.datetime.now().year
    if start_year > end_year:
        print(f"start_year ({start_year}) must be <= end_year ({end_year}).", file=sys.stderr)
        sys.exit(1)
    target_congresses = sorted({congress_for_year(y) for y in range(start_year, end_year + 1)})
    print(f"Target congresses: {target_congresses}", file=sys.stderr)

    # Fail fast on a pre-113 range before the (API) committee discovery: govinfo
    # can't serve those bills, and discovery might return zero for them, turning
    # an unsupported request into a silent "found 0 bills" (issue #10 trap 7).
    if args.source == "govinfo":
        for c in target_congresses:
            gi.require_supported_congress(c)

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
            source=args.source,
            api_key=api_key,
            formats=formats,
        )


def _add_source_arg(sub: argparse.ArgumentParser) -> None:
    """Add the shared --source flag (default govinfo, keyless; issue #10)."""
    sub.add_argument(
        "--source",
        choices=list(SOURCES),
        default=DEFAULT_SOURCE,
        help=f"Bill-text source (default: {DEFAULT_SOURCE}; govinfo needs no API key)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Download appropriations bill text versions (govinfo bulk data or Congress.gov API)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # versions: list available text versions
    p_ver = subparsers.add_parser("versions", help="List available text versions for a bill")
    p_ver.add_argument("congress", type=int, help="Congress number (e.g. 118)")
    p_ver.add_argument("bill_type", choices=sorted(BILL_TYPES.keys()), help="Bill type (e.g. hr, s)")
    p_ver.add_argument("number", type=int, help="Bill number")
    _add_source_arg(p_ver)

    # download: download versions for a single bill
    p_dl = subparsers.add_parser("download", help="Download bill text versions")
    p_dl.add_argument("congress", type=int, help="Congress number (e.g. 118)")
    p_dl.add_argument("bill_type", choices=sorted(BILL_TYPES.keys()), help="Bill type (e.g. hr, s)")
    p_dl.add_argument("number", type=int, help="Bill number")
    p_dl.add_argument("--version", type=int, default=None, help="Specific version number (1-indexed)")
    p_dl.add_argument("--output-dir", type=Path, default=Path("bills"), help="Output directory")
    # INVARIANT: the default is XML, always. XML is the authoritative published
    # source (ADR 0010: prefer published XML); PDF is opt-in for the
    # pre-publication / last-resort path and must be requested with --format.
    # Not `both` either: PDF is the source of necessity, XML the source of choice.
    # PDF's use here is narrower (pre-publication / last resort) and its extraction
    # lossier, so defaulting to both would make every user fetch a second, lossier
    # artifact per version to serve the minority case.
    # Do not change this default — test_parser_format_defaults_to_xml fails if either
    # subcommand's default drifts (it last regressed to pdf unnoticed in a "lint"
    # commit), and test_default_download_writes_the_xml_the_diff_consumes fails if a
    # default `download` stops producing the .xml at all.
    p_dl.add_argument(
        "--format", choices=["xml", "pdf", "both"], default="xml", help="Format(s) to download (default: xml)"
    )
    _add_source_arg(p_dl)

    # download-all: bulk download for a year range
    p_all = subparsers.add_parser("download-all", help="Download all appropriations bill versions for a year range")
    p_all.add_argument("--start_year", type=int, default=None, help="Start year (e.g. 2024)")
    p_all.add_argument("--end_year", type=int, default=None, help="End year (e.g. 2026)")
    p_all.add_argument("--file", type=Path, default=None, help="CSV file path with an 'id' column")
    p_all.add_argument("--output-dir", type=Path, default=Path("bills"), help="Output directory")
    # Default xml by decision — see the invariant note on the `download` subcommand
    # above (ADR 0010). PDF is opt-in via --format.
    p_all.add_argument(
        "--format", choices=["xml", "pdf", "both"], default="xml", help="Format(s) to download (default: xml)"
    )
    _add_source_arg(p_all)

    # search: title discovery over the local BILLSTATUS index (keyless; #10).
    # Appropriations is a facet (--appropriations), not the discovery gate it is on
    # the committee-API path. Scope is whatever BILLSTATUS ZIPs are present locally.
    p_search = subparsers.add_parser("search", help="Find bills by title over the local BILLSTATUS index (keyless)")
    p_search.add_argument("query", nargs="+", help="Title search terms (case-insensitive, all must match)")
    p_search.add_argument("--congress", type=int, default=None, help="Restrict to a Congress (e.g. 118)")
    p_search.add_argument(
        "--type",
        dest="bill_type",
        choices=sorted(BILL_TYPES.keys()),
        default=None,
        help="Restrict to a bill type (e.g. hr, s)",
    )
    p_search.add_argument(
        "--appropriations",
        action="store_true",
        help="Facet: keep only bills referred to the appropriations committee",
    )
    p_search.add_argument(
        "--billstatus-dir",
        type=Path,
        default=Path("bills"),
        help="Directory of BILLSTATUS ZIPs (default: bills/, from fetch-index or fetch_bill_archives.py)",
    )

    # fetch-index: the lightweight on-ramp for `search` (#242). Downloads only the
    # scoped BILLSTATUS archive(s) search reads (tens of MB for one congress/type),
    # reusing fetch_bill_archives' download phase -- NOT the heavy multi-GB
    # all-of-112-119 bulk fetch. Keyless (govinfo bulk data). Kept a separate verb so
    # `search` stays purely offline; fetching is always explicit.
    p_fetch_index = subparsers.add_parser(
        "fetch-index",
        help="Download the scoped BILLSTATUS ZIP(s) that `search` reads (keyless; tens of MB, not the full bulk set)",
    )
    p_fetch_index.add_argument("--congress", type=int, required=True, help="Congress to fetch (e.g. 118)")
    p_fetch_index.add_argument(
        "--type",
        dest="bill_type",
        choices=sorted(BILL_TYPES.keys()),
        default=None,
        help="Bill type to fetch (e.g. hr, s); omit to fetch every type for the congress",
    )
    p_fetch_index.add_argument(
        "--billstatus-dir",
        type=Path,
        default=Path("bills"),
        help="Directory to write BILLSTATUS ZIPs (default: bills/, where `search` reads them)",
    )

    return parser


def requires_api_key(args: argparse.Namespace) -> bool:
    """Whether this invocation touches the Congress.gov API (so needs a key).

    The default govinfo source is keyless. Two things still hit the API:
      - ``--source api`` (anywhere): the enumeration + text fetch use the API.
      - ``download-all`` over a year range (no ``--file``): appropriations-bill
        *discovery* is the committee endpoint even when the text comes from
        govinfo (issue #10 scope: discovery=API, text=govinfo).
    """
    if getattr(args, "source", None) == "api":
        return True
    return args.command == "download-all" and args.file is None


def main():
    load_dotenv()
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    args = parser.parse_args()
    # Resolve the API key lazily: only paths that actually reach the Congress.gov
    # API (see requires_api_key) resolve it and can emit the DEMO_KEY warning. The
    # default keyless govinfo path must stay silent -- that warning was the barrier
    # #10 exists to remove. help / no-args / argparse-error already exited above.
    api_key = get_api_key() if requires_api_key(args) else None

    try:
        with httpx.Client(timeout=30) as client:
            if args.command == "versions":
                cmd_versions(client, args, api_key)
            elif args.command == "download":
                cmd_download(client, args, api_key)
            elif args.command == "download-all":
                cmd_download_all(client, args, api_key)
            elif args.command == "search":
                sys.exit(cmd_search(client, args, api_key))
            elif args.command == "fetch-index":
                sys.exit(cmd_fetch_index(client, args, api_key))
    except gi.CongressNotAvailable as exc:
        # Actionable one-liner, no traceback: pre-113 under the default govinfo
        # source points the user at --source api (issue #10 trap 7).
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
