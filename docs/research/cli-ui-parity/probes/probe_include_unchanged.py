"""Does --include-unchanged do anything on the HTML path?

filter_diff() keeps unchanged nodes when asked, but xml_diff_to_canonical()
drops every entry whose change_type is "unchanged" before the document is built.
If both are true the flag is already inert on --format html, which decides
whether it can survive the removal of --format json's internal shape.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.compare.xml import compare_xml_trees_html  # noqa: E402
from deltatrack.diff_bill import bill_diff_to_dict, diff_bills, filter_diff  # noqa: E402

BILL = ROOT / "tests" / "corpus" / "118-hr-8752"
old = normalize_bill(BILL / "1_reported-in-house.xml")
new = normalize_bill(BILL / "2_engrossed-in-house.xml")
raw = diff_bills(old, new)

off = len(bill_diff_to_dict(filter_diff(raw, include_unchanged=False))["changes"])
on = len(bill_diff_to_dict(filter_diff(raw, include_unchanged=True))["changes"])
print(f"filter_diff  include_unchanged=False -> {off} changes")
print(f"filter_diff  include_unchanged=True  -> {on} changes")
print(f"  the flag does reach filter_diff: {on != off}")
print()

html_off = compare_xml_trees_html(old, new, include_unchanged=False)
html_on = compare_xml_trees_html(old, new, include_unchanged=True)
print(f"HTML report, --include-unchanged off : {len(html_off)} bytes")
print(f"HTML report, --include-unchanged on  : {len(html_on)} bytes")
print(f"  reports byte-identical: {html_off == html_on}")
print()
if html_off == html_on:
    print("=> --include-unchanged is ALREADY inert on --format html.")
    print("   It only ever had an effect on --format json's internal shape.")
