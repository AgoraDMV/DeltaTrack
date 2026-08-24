"""What exactly does --include-unchanged change in the HTML report?

probe_include_unchanged.py shows the two reports are not byte-identical but differ
by only two bytes. The differing line is the ~700KB embedded JSON payload, so this
locates the changed substring inside it rather than printing the line.
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.compare.xml import compare_xml_trees_html  # noqa: E402

BILL = ROOT / "tests" / "corpus" / "118-hr-8752"
old = normalize_bill(BILL / "1_reported-in-house.xml")
new = normalize_bill(BILL / "2_engrossed-in-house.xml")

off = compare_xml_trees_html(old, new, include_unchanged=False).splitlines()
on = compare_xml_trees_html(old, new, include_unchanged=True).splitlines()

if off == on:
    print("reports are byte-identical; the flag is inert on --format html")
    raise SystemExit(0)

for lineno, (a, b) in enumerate(zip(off, on), start=1):
    if a == b:
        continue
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            continue
        print(f"line {lineno}, {tag}:")
        print(f"  off: ...{a[max(0, i1 - 90) : i2 + 40]}...")
        print(f"  on : ...{b[max(0, j1 - 90) : j2 + 40]}...")
