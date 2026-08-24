"""Run the CLI path and the web path over the SAME inputs and report divergence.

Not a test. Evidence for the CLI/UI parity audit: it exercises the real entry
points (argparse main() for the CLI, the FastAPI route via TestClient for the UI)
rather than reasoning about them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

BILL = ROOT / "tests" / "corpus" / "118-hr-8752"
X1, X2 = BILL / "1_reported-in-house.xml", BILL / "2_engrossed-in-house.xml"
P1, P2 = BILL / "1_reported-in-house.pdf", BILL / "2_engrossed-in-house.pdf"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

from fastapi.testclient import TestClient  # noqa: E402

from web.app import app  # noqa: E402

client = TestClient(app)


def post(fmt, output, a, b):
    with open(a, "rb") as fa, open(b, "rb") as fb:
        r = client.post(
            f"/api/compare?output={output}&format={fmt}",
            files={
                "start_file": (a.name, fa, "application/octet-stream"),
                "end_file": (b.name, fb, "application/octet-stream"),
            },
        )
    return r


print("=" * 70)
print("XML - JSON output: CLI `diff_bill.py compare --format json` vs UI ?output=json")
print("=" * 70)

from deltatrack.diff_bill import build_parser, cmd_compare  # noqa: E402

args = build_parser().parse_args(["compare", str(X1), str(X2), "--format", "json", "-o", str(OUT / "cli_xml.json")])
cmd_compare(args)
cli_json = json.loads((OUT / "cli_xml.json").read_text())

r = post("xml", "json", X1, X2)
print(f"  UI status: {r.status_code}")
ui_json = r.json()
(OUT / "ui_xml.json").write_text(json.dumps(ui_json, indent=2))

print(f"  CLI top-level keys: {sorted(cli_json)}")
print(f"  UI  top-level keys: {sorted(ui_json)}")
print(f"  shared keys       : {sorted(set(cli_json) & set(ui_json))}")
print(f"  IDENTICAL?        : {cli_json == ui_json}")

print()
print("=" * 70)
print("XML - HTML output: CLI --format html vs UI ?output=html")
print("=" * 70)

args = build_parser().parse_args(["compare", str(X1), str(X2), "--format", "html", "-o", str(OUT / "cli_xml.html")])
cmd_compare(args)
cli_html = (OUT / "cli_xml.html").read_text()

r = post("xml", "html", X1, X2)
ui_html = r.text
(OUT / "ui_xml.html").write_text(ui_html)
print(f"  UI status: {r.status_code}")
print(f"  CLI bytes: {len(cli_html)}   UI bytes: {len(ui_html)}")
print(f"  IDENTICAL?: {cli_html == ui_html}")

print()
print("=" * 70)
print("PDF - HTML output: CLI diff_pdf.py vs UI ?format=pdf&output=html")
print("=" * 70)

from deltatrack.diff_pdf import main as pdf_main  # noqa: E402

pdf_main([str(P1), str(P2), "-o", str(OUT / "cli_pdf.html")])
cli_pdf_html = (OUT / "cli_pdf.html").read_text()

r = post("pdf", "html", P1, P2)
ui_pdf_html = r.text
(OUT / "ui_pdf.html").write_text(ui_pdf_html)
print(f"  UI status: {r.status_code}")
print(f"  CLI bytes: {len(cli_pdf_html)}   UI bytes: {len(ui_pdf_html)}")
print(f"  IDENTICAL?: {cli_pdf_html == ui_pdf_html}")

print()
print("=" * 70)
print("PDF - JSON output: does the CLI have one?")
print("=" * 70)
from deltatrack.diff_pdf import build_parser as pdf_parser  # noqa: E402

opts = [a for act in pdf_parser()._actions for a in act.option_strings]
print(f"  diff_pdf.py options: {opts}")
r = post("pdf", "json", P1, P2)
print(f"  UI ?output=json status: {r.status_code}, keys={sorted(r.json())}")
