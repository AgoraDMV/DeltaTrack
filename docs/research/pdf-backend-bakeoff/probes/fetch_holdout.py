"""Restore the P2 holdout corpus from govinfo, verifying every byte against the frozen record.

WHY THIS EXISTS, AND WHY IT IS NOT `select_holdout.py`. The holdout files themselves are not
committed: 88 documents, 16.4 MB, and the repository's standing convention is that bill
source material is fetched rather than vendored (`/bills`, `/bills_bulk_text`,
`bills_corpus` and `/reference` are all gitignored on that reasoning). What IS committed is
`results/holdout_membership.json`, which records for every one of the 88 files its govinfo
package id, its path, its sha256 and its byte count. That file is itself covered by
`validation/PRESERVED-MANIFEST.txt`, so the record this script trusts is frozen and
hash-checked independently of this script.

`select_holdout.py` is the SELECTION procedure and must not be used to restore the corpus.
It re-executes the stratified draw, needs the BILLSTATUS ZIPs and `$CLAUDE_JOB_DIR`, and
would REWRITE `holdout_membership.json` -- the one file the pre-registration says is frozen
and never revised. This script reads that file and never writes it.

WHAT MAKES THE SUBSTITUTION SAFE. Every fetched byte is hashed and compared against the
frozen sha256 before it is written. A govinfo package that has been re-issued, withdrawn or
silently altered therefore FAILS LOUDLY here rather than being scored as if it were the
historical input. That is a property the committed copies did not have: nothing in the tree
verified the vendored bytes against the manifest at all.

Verified 2026-08-07: all 88 files re-fetch byte-identical to the frozen record.

    .venv/bin/python docs/research/pdf-backend-bakeoff/probes/fetch_holdout.py
    .venv/bin/python docs/research/pdf-backend-bakeoff/probes/fetch_holdout.py --verify-only

Exit status is 0 only when every file in the membership is present and hash-correct.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import httpx

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
MEMBERSHIP = REPO / "docs/research/pdf-backend-bakeoff/results/holdout_membership.json"
HOLDOUT_DIR = REPO / "docs/research/pdf-backend-bakeoff/holdout"
CONTENT = "https://www.govinfo.gov/content/pkg"


def wanted() -> list[tuple[str, str, Path, str, int]]:
    """(pkg, fmt, destination, expected sha256, expected bytes) for all 88 files."""
    doc = json.loads(MEMBERSHIP.read_text())
    out = []
    for m in doc["members"]:
        for v in m["versions"]:
            for fmt in ("xml", "pdf"):
                rec = v[fmt]
                out.append((v["pkg"], fmt, HOLDOUT_DIR / rec["path"], rec["sha256"], rec["bytes"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--verify-only",
        action="store_true",
        help="check what is on disk and download nothing",
    )
    args = ap.parse_args()

    files = wanted()
    client = (
        None
        if args.verify_only
        else httpx.Client(headers={"User-Agent": "DeltaTrack-bakeoff-holdout/1.0"}, timeout=300)
    )
    ok = fetched = 0
    problems: list[str] = []

    for pkg, fmt, dest, sha, nbytes in files:
        rel = dest.relative_to(HOLDOUT_DIR)
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == sha:
            ok += 1
            continue
        if args.verify_only:
            problems.append(f"{rel}: {'absent' if not dest.exists() else 'sha256 mismatch'}")
            continue
        url = f"{CONTENT}/{pkg}/{fmt}/{pkg}.{fmt}"
        try:
            r = client.get(url, follow_redirects=True)
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{rel}: fetch failed ({type(exc).__name__}: {exc}) from {url}")
            continue
        got = hashlib.sha256(r.content).hexdigest()
        if got != sha:
            # Not written. A re-issued package is a finding about govinfo, not an input.
            problems.append(
                f"{rel}: sha256 mismatch from {url}\n"
                f"    frozen  {sha} ({nbytes} bytes)\n"
                f"    fetched {got} ({len(r.content)} bytes)"
            )
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        ok += 1
        fetched += 1
        print(f"  fetched {rel}", file=sys.stderr)

    print(f"\n{ok}/{len(files)} files present and hash-correct ({fetched} downloaded)", file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} PROBLEM(S) -- the holdout is NOT restored:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
