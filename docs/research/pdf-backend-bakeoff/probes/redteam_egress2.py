"""Red-team item 9: run the second-round vectors against the PROPOSED PRODUCTION POLICY.

Same discipline as the first harness: a no-CSP control must be observed to leak before
any zero elsewhere counts, and the claim is decided by what the SERVER received.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_egress2.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
PORT = 8973

# The exact policy RESULTS.md proposes.
STRICT_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; "
    "object-src 'none'; frame-src 'none'; worker-src 'none'"
)

PAGE = """<!doctype html><meta charset="utf-8"><title>{title}</title>
{csp}
<body><pre id="o">running</pre>
<script src="vectors2.js"></script>
<script>window.__tryAll2("{tag}").then(r=>{{document.getElementById("o").textContent=r+"\\nDONE";}});</script>
"""


class Server:
    def __init__(self):
        self.proc = None
        self.lines: list[str] = []

    def __enter__(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(PROBES / "serve.py"), "--port", str(PORT), "--seconds", "400"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._drain, daemon=True).start()
        for _ in range(60):
            if any("listening" in x for x in self.lines):
                return self
            time.sleep(0.1)
        raise RuntimeError("server did not start")

    def _drain(self):
        for line in self.proc.stdout:
            self.lines.append(line.rstrip())

    def __exit__(self, *_e):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=10)

    @property
    def mark(self):
        return len(self.lines)

    def hits(self, mark: int) -> list[str]:
        return [x.strip() for x in self.lines[mark:] if "EGRESS OBSERVED" in x]


def run_case(browser, server, path: Path) -> dict:
    ctx = browser.new_context()
    page = ctx.new_page()
    mark = server.mark
    page.goto(path.as_uri())
    report = ""
    deadline = time.time() + 40
    while time.time() < deadline:
        try:
            report = page.eval_on_selector("#o", "e => e.textContent")
        except Exception:  # noqa: BLE001
            report = ""
        if "DONE" in report:
            break
        time.sleep(0.25)
    time.sleep(4)
    hits = server.hits(mark)
    for p in ctx.pages:
        try:
            p.close()
        except Exception:  # noqa: BLE001
            pass
    ctx.close()
    return {
        "completed": "DONE" in report,
        "n_vectors": report.count(":attempted") + report.count(":threw"),
        "hits": hits,
        "page_report": report,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO / "docs/research/pdf-backend-bakeoff/results/redteam_egress2.json")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    fx = PROBES / "egress-fixtures"
    fx.mkdir(exist_ok=True)
    (fx / "vectors2.js").write_text((PROBES / "vectors2.js").read_text())
    (fx / "rt2_nocsp.html").write_text(PAGE.format(title="rt2 no CSP", tag="rt2nocsp", csp=""))
    (fx / "rt2_withcsp.html").write_text(
        PAGE.format(
            title="rt2 strict CSP",
            tag="rt2csp",
            csp=f'<meta http-equiv="Content-Security-Policy" content="{STRICT_CSP}">',
        )
    )

    results: dict = {"policy": STRICT_CSP}
    with Server() as server, sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            ctl = run_case(browser, server, fx / "rt2_nocsp.html")
            results["no_csp_control"] = ctl
            print(
                f"no-CSP control : {len(ctl['hits'])} observed, "
                f"{ctl['n_vectors']} vectors, completed={ctl['completed']}",
                flush=True,
            )
            strict = run_case(browser, server, fx / "rt2_withcsp.html")
            results["strict_csp"] = strict
            print(
                f"strict CSP     : {len(strict['hits'])} observed, "
                f"{strict['n_vectors']} vectors, completed={strict['completed']}",
                flush=True,
            )
        finally:
            browser.close()

    def names(hits):
        return sorted({h.split("/")[-1].split("?")[0] for h in hits if "/" in h})

    results["control_vectors_that_leaked"] = names(results["no_csp_control"]["hits"])
    results["POLICY_BYPASSES"] = names(results["strict_csp"]["hits"])
    print("\ncontrol leaked :", results["control_vectors_that_leaked"])
    print("POLICY BYPASSES:", results["POLICY_BYPASSES"] or "none")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
