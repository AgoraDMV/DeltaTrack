#!/usr/bin/env python3
"""Update corpus_manifest.toml with committee report pairings.

Comment-preserving: the manifest carries 40+ lines of documentation (why the file
exists, how the gates read it, how to add a fixture) that a load-and-dump through
a plain TOML writer silently deletes. tomlkit edits the document in place instead.

Two modes:

default (offline)
    Re-derive pairings from the report sources already recorded in the manifest.
    BILLSTATUS said which reports a bill has; that answer does not change, so
    re-applying the *pairing rules* needs no network. This is the mode to run
    after editing scripts/report_pairing.py.

``--refresh``
    Re-fetch BILLSTATUS for every bill and rebuild the source list from scratch.
    Needed only when a bill gains a report.

Package IDs are confirmed against govinfo before being recorded (``--refresh``
only): a predicted ID that does not resolve is stored as ``text_available =
false`` rather than as a fixture that will never exist.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

# Run-from-anywhere. Both roots, mirroring pytest's `pythonpath = [".", "tools"]`:
# tools/fetch_govinfo.py resolves its sibling as a bare `shared.http`, so the repo
# root alone is not enough to import it.
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(1, str(_ROOT / "tools"))

import httpx  # noqa: E402
import tomlkit  # noqa: E402

from scripts.report_pairing import (  # noqa: E402
    ReportSource,
    book_number,
    extract_report_sources,
    get_report_pairing,
    granule_id,
    mark_conference_reports,
    parse_citation,
    predicted_pkg,
    rendition_url,
)
from tools.fetch_govinfo import fetch_billstatus_bill  # noqa: E402

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "tests" / "corpus_manifest.toml"


def load_manifest_doc() -> tomlkit.TOMLDocument:
    """Load the corpus manifest as a tomlkit document (preserves comments)."""
    return tomlkit.parse(MANIFEST_PATH.read_text(encoding="utf-8"))


def write_manifest_doc(doc: tomlkit.TOMLDocument) -> None:
    """Write the manifest document."""
    MANIFEST_PATH.write_text(tomlkit.dumps(doc), encoding="utf-8")


def rendition_resolves(pkg: str, granule: str | None = None) -> bool:
    """Whether govinfo serves a text rendition for this package or granule.

    Checking the status code is not enough: an unknown package 302s to an error
    page that answers 200. Follow the redirect and require the final URL to still
    be under this package's ``/content/pkg/`` path, which the error page is not.
    """
    try:
        with urllib.request.urlopen(rendition_url(pkg, granule), timeout=60) as resp:  # noqa: S310
            return f"/content/pkg/{pkg}/" in resp.geturl()
    except urllib.error.URLError:
        return False


# A package split into parts is not expected to run long; the ceiling only stops an
# unbounded probe loop if govinfo ever starts answering every -ptN.
MAX_GRANULE_PROBE = 12


def discover_granules(pkg: str) -> list[str]:
    """Every ``-ptN`` granule the package serves, in order, stopping at the first gap."""
    found = []
    for part in range(1, MAX_GRANULE_PROBE + 1):
        gid = granule_id(pkg, part)
        if not rendition_resolves(pkg, gid):
            break
        found.append(gid)
    return found


def resolve_pkgs(sources: list[ReportSource], congress: int) -> list[ReportSource]:
    """Attach a confirmed ``pkg`` (and granule, if the package is split) to each source.

    A report is published either as one undivided document or as a package holding
    one granule per book. Both shapes are resolved by asking govinfo rather than by
    predicting: the prediction is the thing that produced a package ID pointing at
    nothing. Anything that cannot be confirmed is marked text-unavailable with the
    reason, so it stays explicit instead of becoming a fixture that never arrives.
    """
    out = []
    for s in sources:
        pkg = predicted_pkg(s.chamber, congress, s.number)
        book_n = book_number(s.book)

        # A cited book is granule N of the package.
        if book_n is not None:
            gid = granule_id(pkg, book_n)
            if rendition_resolves(pkg, gid):
                out.append(replace(s, pkg=pkg, granule=gid))
            else:
                out.append(
                    replace(
                        s,
                        text_available=False,
                        unavailable_reason=f"govinfo serves no text rendition for granule {gid}",
                    )
                )
            continue

        # No book cited: the usual undivided package.
        if rendition_resolves(pkg):
            out.append(replace(s, pkg=pkg))
            continue

        # Some packages are split into parts without BILLSTATUS citing books.
        granules = discover_granules(pkg)
        if len(granules) == 1:
            out.append(replace(s, pkg=pkg, granule=granules[0]))
        elif len(granules) > 1:
            # BILLSTATUS cited one report but the package holds several parts, so
            # which part this citation means is not established. Fail closed rather
            # than picking one.
            out.append(
                replace(
                    s,
                    text_available=False,
                    unavailable_reason=(
                        f"{pkg} is split into {len(granules)} granules but BILLSTATUS cites no book; "
                        f"which part this citation refers to is unresolved"
                    ),
                )
            )
        else:
            out.append(
                replace(
                    s,
                    text_available=False,
                    unavailable_reason=f"govinfo serves no text rendition for {pkg}",
                )
            )
    return out


def sources_from_manifest(bill_entry) -> list[ReportSource]:
    """Every distinct report source already recorded across a bill's versions."""
    seen: dict[str, ReportSource] = {}
    for ver in bill_entry.get("versions", []):
        for raw in ver.get("committee_report", []) or []:
            citation = raw.get("citation")
            if not citation or citation == "none":
                continue
            parsed = parse_citation(citation)
            if not parsed:
                continue
            chamber, _congress, number, book = parsed
            seen.setdefault(
                citation,
                ReportSource(
                    citation=citation,
                    chamber=chamber,
                    number=number,
                    book=book,
                    pkg=raw.get("pkg"),
                    granule=raw.get("granule"),
                    text_available=raw.get("text_available", True),
                    unavailable_reason=raw.get("unavailable_reason"),
                ),
            )
    return mark_conference_reports(list(seen.values()))


def format_report_source(source: ReportSource) -> tomlkit.items.InlineTable:
    """Format a report source as an inline table, omitting defaulted keys."""
    table = tomlkit.inline_table()
    if source.pkg:
        table["pkg"] = source.pkg
    if source.granule:
        table["granule"] = source.granule
    table["citation"] = source.citation
    table["chamber"] = source.chamber
    if source.book:
        table["book"] = source.book
    if source.conference:
        table["conference"] = True
    if not source.text_available:
        table["text_available"] = False
        table["unavailable_reason"] = source.unavailable_reason or "no govinfo text rendition"
    return table


def format_report_pairing(pairing) -> tomlkit.items.Array:
    """Format a ReportPairing as an array of inline tables.

    "No report" is a single entry carrying only a reason -- deliberately with no
    ``pkg`` key, so nothing downstream can mistake a sentinel string for a
    vendorable package.
    """
    arr = tomlkit.array()
    if not pairing.sources:
        table = tomlkit.inline_table()
        table["citation"] = "none"
        table["chamber"] = "none"
        table["reason"] = pairing.reason or "no report available"
        arr.append(table)
    else:
        for s in pairing.sources:
            arr.append(format_report_source(s))
    return arr


def main():
    ap = argparse.ArgumentParser(description="Update corpus_manifest.toml committee report pairings.")
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="re-fetch BILLSTATUS and re-confirm package IDs (network); default is offline re-pairing",
    )
    args = ap.parse_args()

    doc = load_manifest_doc()

    for bill_entry in doc.get("bill", []):
        bill_id = bill_entry["id"]
        congress, bill_type, number = bill_id.split("-")

        if args.refresh:
            print(f"Fetching BILLSTATUS for {bill_id}...", file=sys.stderr)
            with httpx.Client(timeout=30) as client:
                bill_elem = fetch_billstatus_bill(client, int(congress), bill_type, int(number))
            if bill_elem is None:
                print(f"  WARNING: No BILLSTATUS found for {bill_id}", file=sys.stderr)
                continue
            report_sources = resolve_pkgs(extract_report_sources(bill_elem), int(congress))
        else:
            report_sources = sources_from_manifest(bill_entry)

        print(
            f"{bill_id}: {len(report_sources)} report source(s): "
            f"{', '.join(s.citation for s in report_sources) or 'none'}",
            file=sys.stderr,
        )

        # Offline recovery is lossy in one direction and it matters here: sources are
        # read back from the pairings still recorded, so a bill whose every pairing
        # was dropped (which the lineage rule does on purpose -- 118-hr-2882 keeps
        # H. Rept. 118-364 on no version) reads as a bill with no reports at all.
        # Rewriting it then replaces an accurate reason with "bill has no committee
        # reports", which is false and looks authoritative. So when offline recovery
        # finds nothing, only FILL versions that lack an entry; never overwrite one
        # computed when the sources were known. --refresh has the real answer.
        blind = not args.refresh and not report_sources
        if blind:
            print(
                f"  {bill_id}: no sources recoverable offline; filling only versions "
                f"with no entry (re-run with --refresh for an authoritative answer)",
                file=sys.stderr,
            )

        # Every manifested version, whatever formats we hold for it. Which report
        # explains a version is a fact about the legislative text, not about whether
        # DeltaTrack happens to have its XML: skipping PDF-only versions left
        # 114-hr-2029's reported-in-Senate print with no pairing, which is the exact
        # version/chamber example #295 exists to establish.
        for ver in bill_entry.get("versions", []):
            update_bill_version_pairing(
                ver=ver,
                report_sources=report_sources,
                bill_id=bill_id,
                bill_type=bill_type,
                blind=blind,
            )

    write_manifest_doc(doc)
    print("Manifest updated (comments preserved).", file=sys.stderr)


def update_bill_version_pairing(
    *,
    ver: dict,
    report_sources: list,
    bill_id: str,
    bill_type: str,
    blind: bool,
) -> None:
    """Update a single version's committee_report entry.

    This is the core per-version pairing logic, extracted for direct testability.
    Both ``main()`` and the regression tests call this function.
    """
    stage = ver["stage"]
    if blind and ver.get("committee_report"):
        return
    if blind and not ver.get("committee_report"):
        # Blind offline mode cannot determine the pairing for a version
        # that has no existing entry. The report sources for this bill are
        # not recoverable from the manifest (the lineage rule correctly
        # dropped all pairings), so calling get_report_pairing([], ...)
        # would write an invented "bill has no committee reports" reason
        # that is known to be potentially false. Fail closed instead.
        sys.exit(
            f"{bill_id}: cannot determine committee report for new version "
            f"{stage} offline; run scripts/update_manifest_with_reports.py --refresh"
        )
    pairing = get_report_pairing(report_sources, stage, bill_type)
    ver["committee_report"] = format_report_pairing(pairing)
    desc = ", ".join(s.citation for s in pairing.sources) if pairing.sources else "none"
    print(f"    {stage}: {desc} ({pairing.reason or 'ok'})", file=sys.stderr)


if __name__ == "__main__":
    main()
