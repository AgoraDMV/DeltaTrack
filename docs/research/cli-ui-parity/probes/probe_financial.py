"""Does `--financial` mean the same thing on the CLI's json and html paths?"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from deltatrack.bill_tree import normalize_bill  # noqa: E402
from deltatrack.diff_bill import bill_diff_to_dict, diff_bills, filter_diff  # noqa: E402

BILL = ROOT / "tests" / "corpus" / "118-hr-8752"
old_tree = normalize_bill(BILL / "1_reported-in-house.xml")
new_tree = normalize_bill(BILL / "2_engrossed-in-house.xml")
res = filter_diff(diff_bills(old_tree, new_tree))

plain = bill_diff_to_dict(res, financial=False)
rich = bill_diff_to_dict(res, financial=True)

with_fin = [c for c in rich["changes"] if "financial" in c]
print(f"changes carrying a `financial` block when financial=True : {len(with_fin)}/{len(rich['changes'])}")
print(
    f"changes carrying a `financial` block when financial=False: "
    f"{len([c for c in plain['changes'] if 'financial' in c])}/{len(plain['changes'])}"
)
print(f"top-level `financial_summary` present, financial=True : {'financial_summary' in rich}")
print(f"top-level `financial_summary` present, financial=False: {'financial_summary' in plain}")
print()
print("CLI --format json : bill_diff_to_dict(financial=args.financial)   <- default False")
print("CLI --format html : compare/xml.py hardcodes financial=True")
print("UI  ?output=json  : compare/xml.py hardcodes financial=True")
print()
print("=> `--financial` on the json path both FILTERS and ENRICHES;")
print("   on the html path it only FILTERS (enrichment is always on).")
print("   Same flag, two meanings, decided by a sibling flag.")
