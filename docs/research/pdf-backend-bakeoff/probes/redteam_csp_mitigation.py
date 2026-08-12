"""Red-team follow-up: does removing 'unsafe-inline' actually close the Speculation Rules bypass?

This backs the corrected CSP that RESULTS.md recommends, and it exists as a file because
the first version was run from a scratch script that was then deleted -- leaving the
document's central security recommendation with no reproducible probe.

THE VACUOUS-PASS TRAP THIS PROBE EXISTS TO AVOID. The obvious test is to serve the same
fixture under `script-src 'self'` and count bypasses. Run that way it reports **zero
bypasses** -- and also `completed=False, 0 vectors`, because the policy blocked the
fixture's own INLINE bootstrap script and nothing ever executed. A zero from a page that
did not run is indistinguishable from a zero from a page that ran and was contained.

So the mitigation variants load their bootstrap from an EXTERNAL file, and every variant
asserts `completed=True` with the full vector count before its bypass list is believed.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_csp_mitigation.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
sys.path.insert(0, str(PROBES))

from redteam_egress2 import Server, run_case  # noqa: E402

BASE = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; "
    "form-action 'none'; base-uri 'none'; object-src 'none'; frame-src 'none'; "
    "worker-src 'none'"
)

# `inline` variants keep the original bootstrap and are expected to be VOID under a
# policy that forbids inline script -- kept in the matrix precisely to demonstrate the
# false pass rather than to hide it.
VARIANTS = {
    "published policy (script-src 'self' 'unsafe-inline')": (
        BASE + "; script-src 'self' 'unsafe-inline'",
        "inline",
    ),
    "VOID CONTROL: script-src 'self', inline bootstrap": (BASE + "; script-src 'self'", "inline"),
    "corrected policy (script-src 'self', external bootstrap)": (
        BASE + "; script-src 'self'",
        "external",
    ),
}

INLINE_PAGE = """<!doctype html><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<body><pre id="o">running</pre>
<script src="vectors2.js"></script>
<script>window.__tryAll2("{tag}").then(function(r){{document.getElementById("o").textContent=r+"\\nDONE";}});</script>
"""

EXTERNAL_PAGE = """<!doctype html><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<body><pre id="o">running</pre>
<script src="vectors2.js"></script>
<script src="boot_mitigation.js"></script>
"""

BOOT = 'window.__tryAll2("{tag}").then(function(r){{document.getElementById("o").textContent=r+"\\nDONE";}});'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO / "docs/research/pdf-backend-bakeoff/results/redteam_csp_mitigation.json",
    )
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    fx = PROBES / "egress-fixtures"
    fx.mkdir(exist_ok=True)
    (fx / "vectors2.js").write_text((PROBES / "vectors2.js").read_text())

    results: dict = {"variants": {}}
    with Server() as server, sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for i, (name, (csp, boot)) in enumerate(VARIANTS.items()):
                tag = f"mit{i}"
                page_file = fx / f"mitigation_{i}.html"
                if boot == "external":
                    (fx / "boot_mitigation.js").write_text(BOOT.format(tag=tag))
                    page_file.write_text(EXTERNAL_PAGE.format(csp=csp, tag=tag))
                else:
                    page_file.write_text(INLINE_PAGE.format(csp=csp, tag=tag))

                r = run_case(browser, server, page_file)
                bypasses = sorted({h.split("/")[-1].split("?")[0] for h in r["hits"] if "/" in h})
                # A run that did not execute its vectors proves nothing, whatever its
                # bypass count. Say so rather than recording a zero.
                valid = r["completed"] and r["n_vectors"] >= 19
                results["variants"][name] = {
                    "csp": csp,
                    "bootstrap": boot,
                    "completed": r["completed"],
                    "n_vectors_run": r["n_vectors"],
                    "VALID": valid,
                    "bypasses": bypasses if valid else None,
                    "note": None if valid else "VOID: vectors did not run; zero is meaningless",
                }
                print(
                    f"{name:<56} valid={valid!s:<5} vectors={r['n_vectors']:2d} "
                    f"bypasses={bypasses if valid else 'VOID'}",
                    flush=True,
                )
        finally:
            browser.close()

    v = results["variants"]
    pub = v["published policy (script-src 'self' 'unsafe-inline')"]
    fix = v["corrected policy (script-src 'self', external bootstrap)"]
    results["conclusion"] = {
        "published_policy_bypasses": pub["bypasses"],
        "corrected_policy_bypasses": fix["bypasses"],
        "speculation_rules_closed": bool(
            pub["bypasses"]
            and fix["bypasses"] is not None
            and any("speculation" in b for b in pub["bypasses"])
            and not any("speculation" in b for b in fix["bypasses"])
        ),
        "remaining_outside_csp": [b for b in (fix["bypasses"] or []) if "windowopen" in b],
    }
    print("\n" + json.dumps(results["conclusion"], indent=1))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
