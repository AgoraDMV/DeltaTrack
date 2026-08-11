#!/usr/bin/env python3
"""Download and vendor committee report HTMLs for the corpus.

Exits with non-zero code if any download fails, so a missing fixture is loud.

"Fails on download errors" has to mean more than "the request raised": govinfo
answers an unknown package with a **302 to an error page served as HTTP 200**, so
``urlopen`` returns happily with 44 KB of HTML titled "Page Not Found | GovInfo".
Checking only for an exception or an empty body writes that page to disk under a
fixture name and reports success -- which is how two error pages were committed as
committee report fixtures (#295 review). Every body is therefore validated as an
actual govinfo text rendition before it is saved, and already-committed fixtures
are re-validated on each run so a bad one cannot survive by already existing.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

# Run-from-anywhere: put the repo root on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tomllib

from scripts.report_pairing import fixture_stem, rendition_url  # noqa: E402
from tests.corpus_paths import DATA_DIR  # noqa: E402


class NotAReportRendition(RuntimeError):
    """The bytes at a package URL are not a govinfo committee report text rendition."""


def load_manifest() -> dict:
    """Load the corpus manifest."""
    manifest_path = Path(__file__).resolve().parents[1] / "tests" / "corpus_manifest.toml"
    with manifest_path.open("rb") as f:
        return tomllib.load(f)


def vendorable_renditions(manifest: dict) -> set[tuple[str, str | None]]:
    """(package, granule) pairs the manifest says are downloadable.

    Keyed on the pair, not the package: a multi-book report is ONE package holding a
    separate granule per book, so keying on the package alone collapses the books
    into a single download and one of them is silently never vendored.

    A source without a ``pkg``, or with ``text_available = false``, is one govinfo
    publishes no text for; it is deliberately absent rather than missing.
    """
    out = set()
    for bill_entry in manifest.get("bill", []):
        for ver in bill_entry.get("versions", []):
            for src in ver.get("committee_report", []) or []:
                if src.get("pkg") and src.get("text_available", True):
                    out.add((src["pkg"], src.get("granule")))
    return out


def validate_rendition(pkg: str, content: bytes) -> None:
    """Raise unless ``content`` is the govinfo text rendition of ``pkg``.

    Two markers, because either alone is passable by an error page: govinfo serves
    report text as a ``<pre>`` block, and titles it "House Report N-M" /
    "Senate Report N-M". The error pages carry neither.
    """
    if not content:
        raise NotAReportRendition(f"{pkg}: empty response")

    text = content.decode("utf-8", errors="replace")
    head = text[:4000]

    if "<pre>" not in text.lower():
        raise NotAReportRendition(
            f"{pkg}: response has no <pre> block, so it is not a report text rendition "
            f"(govinfo serves unknown packages as an HTTP 200 error page). "
            f"First 200 chars: {head[:200]!r}"
        )
    if "House Report" not in head and "Senate Report" not in head:
        raise NotAReportRendition(
            f"{pkg}: response title is not a House/Senate report. First 200 chars: {head[:200]!r}"
        )


def download_report(pkg: str, dest_dir: Path, granule: str | None = None) -> Path:
    """Download one committee report rendition, or validate the committed copy.

    ``granule`` addresses one book within a multi-book package; the fixture is named
    after it, so each book lands in its own file.
    """
    stem = fixture_stem(pkg, granule)
    dest = dest_dir / f"{stem}.htm"

    if dest.exists():
        # Re-validate rather than trusting presence: a previously-saved error page
        # would otherwise be permanent, since nothing would ever re-fetch it.
        validate_rendition(stem, dest.read_bytes())
        print(f"  Already exists (validated): {dest.name}")
        return dest

    print(f"  Downloading {stem}...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(rendition_url(pkg, granule), timeout=120) as resp:  # noqa: S310
        content = resp.read()

    validate_rendition(stem, content)  # before the write, so nothing bad lands on disk

    dest.write_bytes(content)
    print(f"  Saved: {dest.name} ({len(content):,} bytes)")
    return dest


def main():
    manifest = load_manifest()
    renditions = vendorable_renditions(manifest)

    print(f"Found {len(renditions)} report renditions to vendor:")
    for pkg, granule in sorted(renditions):
        print(f"  {fixture_stem(pkg, granule)}")

    dest_dir = DATA_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    for pkg, granule in sorted(renditions):
        download_report(pkg, dest_dir, granule)  # Let exceptions propagate

    print("\nAll reports downloaded and validated successfully!")


if __name__ == "__main__":
    main()
