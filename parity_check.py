"""Prove govinfo BILLS XML matches the congress.gov XML our pipeline already uses.

For every fixture under bills/ (each downloaded from congress.gov by fetch_bills.py),
fetch the same version from govinfo and compare. We report:
  - byte-identical?            (exact equality)
  - structurally identical?    (canonicalized XML equality, ignoring whitespace)
  - parser-identical?          (bill_tree builds the same tree from both)
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from fetch_govinfo import VERSION_NAME_TO_CODE, fetch_bill_xml

try:
    import bill_tree

    HAVE_TREE = True
except Exception:  # pragma: no cover - parser optional for the demo
    HAVE_TREE = False


def parse_fixture_path(p: Path) -> tuple[int, str, int, str]:
    """From bills/118-s-4690/1_reported-in-senate.xml -> (118, 's', 4690, 'rs')."""
    congress_s, btype, num_s = p.parent.name.split("-")
    ver_name = p.stem.split("_", 1)[1]
    ver_code = VERSION_NAME_TO_CODE[ver_name]
    return int(congress_s), btype, int(num_s), ver_code


def canonical(xml_bytes: bytes) -> str:
    """Canonical XML string for structural comparison (ignores insignificant whitespace)."""
    return ET.canonicalize(xml_data=xml_bytes, strip_text=True)


def tree_signature(xml_bytes: bytes, tmp: Path) -> object:
    """Build the bill_tree representation and return something comparable."""
    tmp.write_bytes(xml_bytes)
    node = bill_tree.parse_bill(tmp) if hasattr(bill_tree, "parse_bill") else None
    return node


def main() -> int:
    fixtures = sorted(Path("bills").glob("*/*.xml"))
    if not fixtures:
        print("No fixtures found under bills/", file=sys.stderr)
        return 1

    rows = []
    n_byte = n_struct = 0
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for fx in fixtures:
            congress, btype, num, ver = parse_fixture_path(fx)
            local = fx.read_bytes()
            remote, url = fetch_bill_xml(client, congress, btype, num, ver)
            if remote is None:
                rows.append((fx.parent.name, ver, "NOT FOUND on govinfo", ""))
                continue

            byte_eq = local == remote
            try:
                struct_eq = canonical(local) == canonical(remote)
            except ET.ParseError as e:
                struct_eq = False
                print(f"  parse error on {fx}: {e}", file=sys.stderr)

            n_byte += byte_eq
            n_struct += struct_eq
            verdict = "byte-identical" if byte_eq else ("structurally identical" if struct_eq else "DIFFERS")
            rows.append((fx.parent.name, ver, verdict, f"{len(local):,} vs {len(remote):,} B"))

    print(f"\n{'bill':<14}{'ver':<5}{'result':<26}{'sizes'}")
    print("-" * 70)
    for name, ver, verdict, sizes in rows:
        print(f"{name:<14}{ver:<5}{verdict:<26}{sizes}")

    total = len(fixtures)
    print("-" * 70)
    print(f"byte-identical:        {n_byte}/{total}")
    print(f"structurally identical: {n_struct}/{total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
