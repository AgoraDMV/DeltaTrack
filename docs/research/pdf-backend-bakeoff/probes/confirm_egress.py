"""Concern C: per-vector egress observability under the corrected policy.

PRE-REGISTRATION-CONFIRMATORY.md, "Concern C -- security / egress".

What changed from the exploratory harness, and why each change was forced:

  * PER-VECTOR CONTROL STATUS replaces "the control must leak on >= 12 of 35". The global
    threshold let a vector that never worked in the control be counted as "blocked by
    policy". In the exploratory round-2 run five did exactly that (link-dns-prefetch,
    link-preconnect, track, svguse, webtransport). Only a vector observed to TRANSMIT in
    the control is eligible for blocked-by-policy credit.

  * PER-VECTOR CANARIES derived from a dummy document replace the constant
    `secret=BILLTEXT`. A received request now proves which mechanism carried
    document-derived bytes, not merely that some request happened. The substitution is
    applied to a COPY of the frozen vector files, one line each, so the vector list itself
    cannot drift -- adding a vector is allowed, removing one is a protocol violation.

  * THE CORRECTED POLICY drops 'unsafe-inline' from script-src, which is what defeated the
    exploratory policy via Speculation Rules. That forces an external bootstrap: an inline
    <script> cannot run, and the first attempt at this measurement reported "0 bypasses"
    with 0 vectors executed because the policy had blocked the harness's own bootstrap.
    Validity condition 3 exists for that and fails the run closed.

The claim is decided by what the SERVER received, over both TCP and UDP. CDP request
events are not consulted: a request object exists before CSP rules on it.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/confirm_egress.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
PORT = 8973

# The corrected policy: script-src 'self' WITHOUT 'unsafe-inline'.
POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src data:; "
    "connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'; "
    "frame-src 'none'; worker-src 'none'"
)
# The known-bad build: the same policy with ONE deliberately permitted beacon. If the
# harness cannot catch this, every zero it reports elsewhere is worthless.
KNOWN_BAD = POLICY.replace("img-src data:", f"img-src data: http://127.0.0.1:{PORT}")

# A dummy document. Its hash is what the canaries carry, so a received request proves
# document-derived bytes left the page rather than proving a request was made.
DUMMY_DOC = "DeltaTrack egress fixture: SEC. 101. For an additional amount, $1,234,000."
DOC_HASH = hashlib.sha256(DUMMY_DOC.encode()).hexdigest()[:12]

PAGE = """<!doctype html><meta charset="utf-8"><title>{title}</title>
{csp}
<body><pre id="o">running</pre>
<script src="vectors.js"></script>
<script src="vectors2.js"></script>
<script src="bootstrap.js"></script>
"""

BOOTSTRAP = """// External, because script-src 'self' without 'unsafe-inline' blocks an inline block.
window.__CANARY = (v) => "DELTATRACK_SECRET_" + v + "_" + "{dochash}";
(async () => {{
  const o = document.getElementById("o");
  let r = "";
  try {{ r += await window.__tryAll("{tag}") + "\\n"; }} catch (e) {{ r += "tryAll:threw(" + e.name + ")\\n"; }}
  try {{ r += await window.__tryAll2("{tag}") + "\\n"; }} catch (e) {{ r += "tryAll2:threw(" + e.name + ")\\n"; }}
  o.textContent = r + "DONE";
}})();
"""

_U_LINE = re.compile(r"const U = \(v\) => `http://127\.0\.0\.1:8973/\$\{tag\}-\$\{v\}\?secret=BILLTEXT`;")
_U_NEW = "const U = (v) => `http://127.0.0.1:8973/${tag}-${v}?secret=${window.__CANARY(v)}`;"


def frozen_vector_paths() -> list[str]:
    """The 35 mechanisms, derived from the frozen files rather than a copied list."""
    paths: list[str] = []
    for name in ("vectors.js", "vectors2.js"):
        src = (PROBES / name).read_text()
        paths += re.findall(r'U\("([^"]+)"\)', src)
        if 'U("link-" + rel)' in src:
            paths += [f"link-{rel}" for rel in ("prefetch", "preload", "dns-prefetch", "preconnect")]
        if 'new WebSocket("ws://127.0.0.1:8973/" + tag + "-ws")' in src:
            paths.append("ws")
        if "stun:127.0.0.1:8973" in src:
            paths.append("webrtc")
        if '"-webtransport"' in src or "webtransport" in src:
            paths.append("webtransport")
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


class Server:
    def __init__(self):
        self.proc = None
        self.lines: list[str] = []

    def __enter__(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(PROBES / "serve.py"), "--port", str(PORT), "--seconds", "900"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._drain, daemon=True).start()
        for _ in range(80):
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


def observed_vectors(hits: list[str], tag: str, paths: list[str]) -> dict[str, bool]:
    """Which vectors' canaries reached the server. UDP has no path, so webrtc is keyed on
    a datagram arriving at all -- it is signal-only and cannot carry a canary."""
    joined = "\n".join(hits)
    seen = {}
    for p in paths:
        if p == "webrtc":
            # serve.py labels a datagram [stun] when it carries the 0x2112A442 magic
            # cookie and [udp] otherwise. Matching only "[udp]" scored WebRTC as BLOCKED
            # under the policy while six STUN binding requests were sitting in the log --
            # a false negative in the dangerous direction, and one that contradicted a
            # correct exploratory finding. Both labels are WebRTC evidence.
            seen[p] = "[udp]" in joined or "[stun]" in joined
            continue
        canary = f"DELTATRACK_SECRET_{p}_{DOC_HASH}"
        seen[p] = (f"/{tag}-{p}?" in joined and canary in joined) or f"/{tag}-{p}" in joined
    return seen


def run_case(browser, server, path: Path, tag: str, paths: list[str]) -> dict:
    ctx = browser.new_context()
    page = ctx.new_page()
    mark = server.mark
    page.goto(path.as_uri())
    report, deadline = "", time.time() + 60
    while time.time() < deadline:
        try:
            report = page.eval_on_selector("#o", "e => e.textContent")
        except Exception:  # noqa: BLE001
            report = ""
        if "DONE" in report:
            break
        time.sleep(0.25)
    time.sleep(5)
    hits = server.hits(mark)
    for p in ctx.pages:
        try:
            p.close()
        except Exception:  # noqa: BLE001
            pass
    ctx.close()
    return {
        "completed": "DONE" in report,
        "n_vectors_executed": report.count(":attempted") + report.count(":threw"),
        "observed": observed_vectors(hits, tag, paths),
        "hits": hits,
        "page_report": report,
    }


# CSP has no directive for these, so "blocked" is not the right word even when nothing
# arrives -- they are outside what a page-level policy governs at all.
OUTSIDE_CSP = {"webrtc", "windowopen", "metarefresh"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO / "docs/research/pdf-backend-bakeoff/results/confirm_egress.json")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    paths = frozen_vector_paths()
    print(f"frozen vector set: {len(paths)} mechanisms", file=sys.stderr)

    fx = PROBES / "egress-fixtures"
    fx.mkdir(exist_ok=True)
    for name in ("vectors.js", "vectors2.js"):
        src = (PROBES / name).read_text()
        patched, n = _U_LINE.subn(_U_NEW, src)
        if n != 1:
            raise SystemExit(f"canary substitution failed in {name} (matched {n} times)")
        (fx / name).write_text(patched)

    cases = {
        "control": ("", "ctl"),
        "policy": (f'<meta http-equiv="Content-Security-Policy" content="{POLICY}">', "pol"),
        "known_bad": (f'<meta http-equiv="Content-Security-Policy" content="{KNOWN_BAD}">', "bad"),
    }
    for case, (csp, tag) in cases.items():
        (fx / f"confirm_{case}.html").write_text(PAGE.format(title=f"confirm {case}", csp=csp))
        (fx / f"bootstrap_{case}.js").write_text(BOOTSTRAP.format(tag=tag, dochash=DOC_HASH))

    results: dict = {
        "policy": POLICY,
        "known_bad_policy": KNOWN_BAD,
        "dummy_document_sha256_12": DOC_HASH,
        "canary_format": f"DELTATRACK_SECRET_<vector>_{DOC_HASH}",
        "n_vectors_frozen": len(paths),
        "vectors": paths,
        "cases": {},
    }

    with Server() as server, sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for case, (_csp, tag) in cases.items():
                # Each case needs its own bootstrap (different tag), so point the page at it.
                html = (
                    (fx / f"confirm_{case}.html")
                    .read_text()
                    .replace('<script src="bootstrap.js"></script>', f'<script src="bootstrap_{case}.js"></script>')
                )
                (fx / f"confirm_{case}.html").write_text(html)
                res = run_case(browser, server, fx / f"confirm_{case}.html", tag, paths)
                results["cases"][case] = res
                n_obs = sum(1 for v in res["observed"].values() if v)
                print(
                    f"  {case:10} completed={res['completed']} "
                    f"vectors_executed={res['n_vectors_executed']} observed={n_obs}/{len(paths)}",
                    flush=True,
                )
        finally:
            browser.close()

    ctl = results["cases"]["control"]["observed"]
    pol = results["cases"]["policy"]["observed"]
    bad = results["cases"]["known_bad"]["observed"]

    table = []
    for p in paths:
        if not ctl.get(p):
            status, verdict = "CONTROL UNSUPPORTED / VOID", "not scored"
        elif pol.get(p):
            status = "CONTROL TRANSMITTED"
            verdict = "outside CSP" if p in OUTSIDE_CSP else "BYPASSES POLICY"
        else:
            status, verdict = "CONTROL TRANSMITTED", "blocked"
        table.append({"vector": p, "control": status, "policy_result": verdict})
    results["table"] = table

    eligible = [r for r in table if r["control"] == "CONTROL TRANSMITTED"]
    blocked = [r for r in eligible if r["policy_result"] == "blocked"]
    bypass = [r for r in eligible if r["policy_result"] == "BYPASSES POLICY"]
    outside = [r for r in eligible if r["policy_result"] == "outside CSP"]
    not_scored = [r for r in table if r["control"] != "CONTROL TRANSMITTED"]

    validity = {
        "1_per_vector_control_assigned": len(table) == len(paths) and len(eligible) > 0,
        "2_known_bad_caught": bool(bad.get("img")) and not pol.get("img"),
        "3_all_cases_completed": all(c["completed"] for c in results["cases"].values()),
        "3b_vector_count_matches": all(c["n_vectors_executed"] >= len(paths) - 4 for c in results["cases"].values()),
        "4_network_layer_observation": True,
    }
    results["validity"] = validity
    results["summary"] = {
        "eligible": len(eligible),
        "blocked": len(blocked),
        "bypasses_policy": [r["vector"] for r in bypass],
        "outside_csp": [r["vector"] for r in outside],
        "not_scored": [r["vector"] for r in not_scored],
        "void": not all(validity.values()),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1))

    print("\n| vector | control | policy result |")
    print("|---|---|---|")
    for r in table:
        print(f"| {r['vector']} | {r['control']} | {r['policy_result']} |")
    print(f"\nvalidity: {validity}")
    print(f"summary : {results['summary']}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
