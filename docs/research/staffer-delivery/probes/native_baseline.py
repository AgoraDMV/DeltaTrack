"""Native CPython baseline for the same comparisons Pyodide ran, for timing + parity."""

import json
import time
from pathlib import Path

from deltatrack.compare.xml import compare_xml, compare_xml_html

ROOT = Path("/Users/williamhea/Documents/Code/civictech/appropriations_bills/.claude/worktrees/delivery-spike")
OUT = Path("/Users/williamhea/.claude/jobs/2d422c1f/tmp/pyodide-spike/out")
OUT.mkdir(parents=True, exist_ok=True)

CASES = [
    ("118-hr-4366", "1_reported-in-house.xml", "2_engrossed-in-house.xml", "small"),
    ("118-hr-4366", "3_placed-on-calendar-senate.xml", "4_engrossed-amendment-senate.xml", "senate_rewrite"),
    ("118-hr-4366", "5_engrossed-amendment-house.xml", "6_enrolled-bill.xml", "enrolled"),
]

timings = {}
for bill, a, b, tag in CASES:
    b1 = (ROOT / "tests/corpus" / bill / a).read_bytes()
    b2 = (ROOT / "tests/corpus" / bill / b).read_bytes()
    t = time.perf_counter()
    canon = compare_xml(b1, b2, start_label="v1", end_label="v2")
    timings[tag + "_json_ms"] = round((time.perf_counter() - t) * 1000)
    t = time.perf_counter()
    html = compare_xml_html(b1, b2, start_label="v1", end_label="v2")
    timings[tag + "_html_ms"] = round((time.perf_counter() - t) * 1000)
    (OUT / f"{tag}.native.json").write_text(json.dumps(canon, indent=2, sort_keys=True))
    (OUT / f"{tag}.native.html").write_text(html)

print("NATIVE_TIMINGS " + json.dumps(timings, indent=2))
