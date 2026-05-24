"""Prototype: general bill discovery via govinfo bulk data (no committee filter).

Demonstrates the two ways a user actually finds a bill:
  1. by number  -> direct URL, works for ANY bill/type/congress, no index needed.
  2. by title   -> a local title index built from one BILLSTATUS per-type ZIP.

Also prints the distribution of bills by text-version count and by appropriations
referral, so the corpus-scope decision can be made on real numbers rather than a
guessed filter.

Usage:
  uv run python discover.py number 118 s 4690
  uv run python discover.py search 118 s "appropriations act, 2025"
  uv run python discover.py stats  118 s
"""

import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from fetch_govinfo import VERSION_NAME_TO_CODE, billstatus_url

BULK_BASE = "https://www.govinfo.gov/bulkdata"
CACHE = Path(".cache")
APPROPS_CODES = {"hsap00", "ssap00"}


@dataclass
class BillRecord:
    congress: int
    bill_type: str
    number: int
    title: str
    version_types: list[str] = field(default_factory=list)
    committee_codes: set[str] = field(default_factory=set)
    is_approps_subject: bool = False

    @property
    def n_versions(self) -> int:
        return len(self.version_types)

    @property
    def referred_to_approps(self) -> bool:
        return bool(self.committee_codes & APPROPS_CODES)


def download_billstatus_zip(congress: int, bill_type: str) -> Path:
    """Download (and cache) the per-type BILLSTATUS ZIP for a congress."""
    CACHE.mkdir(exist_ok=True)
    dest = CACHE / f"BILLSTATUS-{congress}-{bill_type}.zip"
    if dest.exists():
        return dest
    url = f"{BULK_BASE}/BILLSTATUS/{congress}/{bill_type}/BILLSTATUS-{congress}-{bill_type}.zip"
    print(f"Downloading {url} ...", file=sys.stderr)
    with httpx.Client(timeout=300, follow_redirects=True) as c:
        resp = c.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    print(f"  cached {dest.stat().st_size:,} bytes", file=sys.stderr)
    return dest


def parse_billstatus(xml_bytes: bytes) -> BillRecord | None:
    """Extract discovery fields from one BILLSTATUS document."""
    bill = ET.fromstring(xml_bytes).find(".//bill")
    if bill is None:
        return None
    num = bill.findtext("number") or bill.findtext("billNumber")
    btype = (bill.findtext("type") or bill.findtext("billType") or "").lower()
    congress = bill.findtext("congress")
    if not (num and btype and congress):
        return None
    versions = [it.findtext("type") or "" for it in bill.findall(".//textVersions/item")]
    codes = {c.text for c in bill.findall(".//committees//systemCode") if c.text}
    subjects = {s.text for s in bill.findall(".//subjects//name") if s.text}
    return BillRecord(
        congress=int(congress),
        bill_type=btype,
        number=int(num),
        title=bill.findtext("title") or "",
        version_types=versions,
        committee_codes=codes,
        is_approps_subject="Appropriations" in subjects,
    )


def build_index(congress: int, bill_type: str) -> list[BillRecord]:
    """Parse every BILLSTATUS doc in the per-type ZIP into a list of records."""
    zpath = download_billstatus_zip(congress, bill_type)
    records: list[BillRecord] = []
    with zipfile.ZipFile(zpath) as zf:
        for name in zf.namelist():
            if not name.endswith(".xml"):
                continue
            rec = parse_billstatus(zf.read(name))
            if rec:
                records.append(rec)
    return records


# --- commands -------------------------------------------------------------


def cmd_number(congress: int, bill_type: str, number: int) -> None:
    """Resolve a single bill directly from its number, no index/filter needed."""
    url = billstatus_url(congress, bill_type, number)
    with httpx.Client(timeout=60, follow_redirects=True) as c:
        resp = c.get(url)
    if resp.status_code != 200:
        print(f"Not found: {url} ({resp.status_code})", file=sys.stderr)
        return
    rec = parse_billstatus(resp.content)
    print(f"\n{bill_type.upper()}. {number} ({congress}th Congress)")
    print(f"  title    : {rec.title}")
    print(f"  versions : {rec.n_versions} -> {', '.join(rec.version_types) or '(none)'}")
    print(f"  approps  : committee={rec.referred_to_approps} subject={rec.is_approps_subject}")
    print("  text URLs (probe both sessions):")
    for vt in rec.version_types:
        code = VERSION_NAME_TO_CODE.get(_slug(vt), "??")
        print(f"    {vt:<22} -> BILLS-{congress}{bill_type}{number}{code}.xml")


def cmd_search(congress: int, bill_type: str, query: str) -> None:
    """Title substring search over the local index (general, no committee filter)."""
    q = query.lower()
    idx = build_index(congress, bill_type)
    hits = [r for r in idx if q in r.title.lower()]
    print(f"\n{len(hits)} title match(es) for {query!r} among {len(idx):,} {bill_type.upper()} bills:\n")
    for r in sorted(hits, key=lambda r: r.number)[:25]:
        flag = "A" if r.referred_to_approps else " "
        print(f"  [{flag}] {bill_type.upper()}.{r.number:<6} v{r.n_versions}  {r.title[:80]}")


def cmd_stats(congress: int, bill_type: str) -> None:
    """Show how each candidate scope filter prunes the firehose."""
    idx = build_index(congress, bill_type)
    total = len(idx)
    with_text = sum(1 for r in idx if r.n_versions >= 1)
    multi = sum(1 for r in idx if r.n_versions >= 2)
    approps_com = sum(1 for r in idx if r.referred_to_approps)
    approps_subj = sum(1 for r in idx if r.is_approps_subject)
    print(f"\nScope filters for {congress}th Congress, type {bill_type.upper()} ({total:,} bills):")
    print(f"  all bills                         : {total:,}")
    print(f"  >=1 published text version        : {with_text:,}")
    print(f"  >=2 published text versions       : {multi:,}   <- would DROP single-version approps bills")
    print(f"  referred to Appropriations cmte   : {approps_com:,}")
    print(f"  'Appropriations' subject term     : {approps_subj:,}")


def _slug(name: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    cmd = args[0]
    if cmd == "number":
        cmd_number(int(args[1]), args[2].lower(), int(args[3]))
    elif cmd == "search":
        cmd_search(int(args[1]), args[2].lower(), args[3])
    elif cmd == "stats":
        cmd_stats(int(args[1]), args[2].lower())
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
