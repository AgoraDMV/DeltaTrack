"""Second parity probe: JSON shapes, flag semantics, and error surfaces."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

BILL = ROOT / "tests" / "corpus" / "118-hr-8752"
X1, X2 = BILL / "1_reported-in-house.xml", BILL / "2_engrossed-in-house.xml"
OUT = Path(__file__).resolve().parent / "out"

cli = json.loads((OUT / "cli_xml.json").read_text())
ui = json.loads((OUT / "ui_xml.json").read_text())

print("=" * 70)
print("Shared key `changes` — same shape?")
print("=" * 70)
print(f"  CLI changes[0] keys: {sorted(cli['changes'][0])}")
print(f"  UI  changes[0] keys: {sorted(ui['changes'][0])}")
print(f"  CLI len(changes)={len(cli['changes'])}  UI len(changes)={len(ui['changes'])}")
print(f"  CLI summary: {cli['summary']}")
print(f"  UI  summary: {ui['summary']}")

print()
print("=" * 70)
print("`--financial` semantics: does it change the JSON vs HTML path the same way?")
print("=" * 70)
from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import bill_diff_to_dict, diff_bills, filter_diff  # noqa: E402

old_tree, new_tree = normalize_bill(X1), normalize_bill(X2)
res = filter_diff(diff_bills(old_tree, new_tree), include_unchanged=False, filter_text=None, financial_only=False)
plain = bill_diff_to_dict(res, financial=False)
enriched = bill_diff_to_dict(res, financial=True)
pk, ek = sorted(plain["changes"][0]), sorted(enriched["changes"][0])
print(f"  bill_diff_to_dict(financial=False) change keys: {pk}")
print(f"  bill_diff_to_dict(financial=True)  change keys: {ek}")
print(f"  keys ONLY present when financial=True: {sorted(set(ek) - set(pk))}")
print("  -> CLI json path passes financial=args.financial (default False)")
print("  -> compare/xml.py hardcodes financial=True for BOTH html and the UI's json")

print()
print("=" * 70)
print("Which knobs exist on which surface?")
print("=" * 70)
from deltatrack.diff_bill import build_parser as xml_parser  # noqa: E402
from deltatrack.diff_pdf import build_parser as pdf_parser  # noqa: E402

sub = [a for a in xml_parser()._subparsers._group_actions[0].choices["compare"]._actions]
print(f"  diff_bill.py compare : {[o for a in sub for o in a.option_strings]}")
print(f"  diff_pdf.py          : {[o for a in pdf_parser()._actions for o in a.option_strings]}")
print("  POST /api/compare    : ['output', 'format']  (query params only)")

print()
print("=" * 70)
print("Error surface: an unsupported (unnumbered) PDF layout")
print("=" * 70)
from deltatrack.compare.pdf import UnsupportedLayoutError  # noqa: E402

enrolled = sorted(ROOT.glob("tests/corpus/**/*enrolled*.pdf"))
print(f"  enrolled fixtures found: {[p.name for p in enrolled][:3]}")
if enrolled:
    target = enrolled[0]
    other = next(p for p in sorted(target.parent.glob("*.pdf")) if p != target)
    from deltatrack.diff_pdf import main as pdf_main

    try:
        pdf_main([str(other), str(target), "-o", str(OUT / "decline.html")])
        print("  CLI: rendered without declining (!)")
    except UnsupportedLayoutError as exc:
        print("  CLI: raises UnsupportedLayoutError UNCAUGHT -> traceback for the user")
        print(f"       message: {exc.message[:80]}...")
    except SystemExit as exc:
        print(f"  CLI: SystemExit({exc.code})")
    from fastapi.testclient import TestClient

    from web.app import app

    client = TestClient(app)
    with open(other, "rb") as fa, open(target, "rb") as fb:
        r = client.post(
            "/api/compare?output=html&format=pdf",
            files={"start_file": (other.name, fa, "app/x"), "end_file": (target.name, fb, "app/x")},
        )
    print(f"  UI : HTTP {r.status_code} -> {str(r.json().get('detail'))[:80]}...")

print()
print("=" * 70)
print("Error surface: malformed XML")
print("=" * 70)
bad = OUT / "bad.xml"
bad.write_text("not xml at all")
from deltatrack.diff_bill import build_parser, cmd_compare  # noqa: E402

try:
    a = build_parser().parse_args(["compare", str(bad), str(X2), "--format", "html", "-o", str(OUT / "bad.html")])
    cmd_compare(a)
    print("  CLI: succeeded (!)")
except SystemExit as exc:
    print(f"  CLI: SystemExit({exc.code})")
except Exception as exc:
    print(f"  CLI: uncaught {type(exc).__name__}: {str(exc)[:80]}")

from fastapi.testclient import TestClient  # noqa: E402

from web.app import app  # noqa: E402

client = TestClient(app)
with open(bad, "rb") as fa, open(X2, "rb") as fb:
    r = client.post(
        "/api/compare?output=html&format=xml",
        files={"start_file": (bad.name, fa, "app/x"), "end_file": (X2.name, fb, "app/x")},
    )
print(f"  UI : HTTP {r.status_code} -> {str(r.json().get('detail'))[:90]}")
