"""Show exactly where the CLI-rendered and UI-rendered reports differ."""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"


def report(name, a_path, b_path):
    a = a_path.read_text().splitlines()
    b = b_path.read_text().splitlines()
    print("=" * 70)
    print(f"{name}: CLI vs UI rendered report")
    print("=" * 70)
    shown = 0
    for line in difflib.unified_diff(a, b, "CLI", "UI", n=0, lineterm=""):
        if line.startswith(("---", "+++", "@@")):
            print(line[:200])
            continue
        # Only print the differing payload, truncated
        print(line[:400])
        shown += 1
        if shown > 20:
            print("  ... truncated")
            break
    print()


report("XML", OUT / "cli_xml.html", OUT / "ui_xml.html")
report("PDF", OUT / "cli_pdf.html", OUT / "ui_pdf.html")

print("=" * 70)
print("Embedded diff.json version metadata, per surface")
print("=" * 70)
pat = re.compile(r'<script[^>]*id="diff-json"[^>]*>(.*?)</script>', re.S)
for label in ("cli_xml", "ui_xml", "cli_pdf", "ui_pdf"):
    text = (OUT / f"{label}.html").read_text()
    m = pat.search(text)
    if not m:
        # fall back: find any application/json script block
        m = re.search(r'<script type="application/json"[^>]*>(.*?)</script>', text, re.S)
    if not m:
        print(f"  {label}: no embedded json found")
        continue
    doc = json.loads(m.group(1))
    print(f"  {label}: versions={json.dumps(doc.get('versions'))}")
