"""Phase 4 follow-up: is the WebRTC channel that survives CSP actually closable?

The main harness found that a strict CSP blocks all fourteen subresource vectors and does
NOT block WebRTC: five STUN binding requests reached the logging server. CSP has no
directive governing ICE, so this is a policy gap rather than a misconfiguration, and
reporting it without testing a mitigation would leave the delivery decision no better off.

Three candidate mitigations, measured rather than assumed:

  A. sandboxed iframe  -- run the engine inside `<iframe sandbox="allow-scripts">`.
  B. Permissions-Policy -- `allow="camera 'none'; microphone 'none'"` and friends.
  C. nothing           -- the baseline, for comparison.

Also measured: whether document content can actually RIDE this channel. A STUN binding
request carries no page data, so the channel is only an exfiltration route if an attacker
can encode data into the STUN server's HOSTNAME, which turns it into a DNS side channel.
That is tested directly rather than reasoned about.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/phase4_webrtc.py
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
PORT = 8973

STRICT_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; "
    "object-src 'none'; frame-src 'none'; worker-src 'none'"
)
# frame-src must permit the sandboxed child, so the sandbox variant relaxes exactly that
# one directive and nothing else.
SANDBOX_CSP = STRICT_CSP.replace("frame-src 'none'", "frame-src 'self' blob: data:")

CHILD = """<!doctype html><meta charset="utf-8"><body><pre id="o">running</pre><script>
(async () => {
  const out = [];
  try {
    const p = new RTCPeerConnection({ iceServers: [{ urls: "stun:127.0.0.1:%(port)d" }] });
    p.createDataChannel("x");
    const o = await p.createOffer();
    await p.setLocalDescription(o);
    out.push("webrtc:attempted");
  } catch (e) { out.push("webrtc:threw(" + e.name + ")"); }
  await new Promise(r => setTimeout(r, 2500));
  document.getElementById("o").textContent = out.join("\\n") + "\\nDONE";
})();
</script>"""

PARENT = """<!doctype html><meta charset="utf-8"><title>%(title)s</title>
%(csp)s
<body><pre id="o">parent</pre>
<iframe id="f" %(sandbox)s src="child.html" style="width:10px;height:10px"></iframe>
<script>
  // Mirror the child's result into the parent so one poll reads both.
  setInterval(() => {
    try {
      const d = document.getElementById("f").contentDocument;
      if (d && d.getElementById("o")) {
        document.getElementById("o").textContent = "child: " + d.getElementById("o").textContent;
      }
    } catch (e) { document.getElementById("o").textContent = "child: opaque (sandboxed)\\nDONE"; }
  }, 300);
</script>"""


class Server:
    def __init__(self):
        self.proc = None
        self.lines: list[str] = []

    def __enter__(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(PROBES / "serve.py"), "--port", str(PORT), "--seconds", "300"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._drain, daemon=True).start()
        for _ in range(50):
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

    def stun_since(self, mark: int) -> list[str]:
        return [x for x in self.lines[mark:] if "[stun]" in x or "[udp]" in x]

    @staticmethod
    def source_ports(hits: list[str]) -> set[str]:
        """Distinct UDP source ports in a set of hits.

        Load-bearing for the comparison: STUN retransmits, so N datagrams may be one
        connection retrying. If every variant reported the same source port, they would
        be one attempt counted three times rather than three independent attempts, and
        the whole comparison would be void.
        """
        return {h.rsplit(":", 1)[-1].strip() for h in hits}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    fx = PROBES / "egress-fixtures"
    fx.mkdir(exist_ok=True)
    (fx / "child.html").write_text(CHILD % {"port": PORT})

    variants = {
        "C_baseline_no_sandbox": {
            "csp": f'<meta http-equiv="Content-Security-Policy" content="{SANDBOX_CSP}">',
            "sandbox": "",
        },
        "A_sandbox_allow_scripts": {
            "csp": f'<meta http-equiv="Content-Security-Policy" content="{SANDBOX_CSP}">',
            "sandbox": 'sandbox="allow-scripts"',
        },
        "B_permissions_policy": {
            "csp": f'<meta http-equiv="Content-Security-Policy" content="{SANDBOX_CSP}">',
            "sandbox": "allow=\"camera 'none'; microphone 'none'; display-capture 'none'\"",
        },
    }

    results: dict = {"variants": {}}
    with Server() as server, sync_playwright() as pw:
        browser = pw.chromium.launch()
        for name, cfg in variants.items():
            (fx / f"parent_{name}.html").write_text(
                PARENT % {"title": name, "csp": cfg["csp"], "sandbox": cfg["sandbox"]}
            )
            ctx = browser.new_context()
            page = ctx.new_page()
            mark = server.mark
            page.goto((fx / f"parent_{name}.html").as_uri())
            report = ""
            deadline = time.time() + 20
            while time.time() < deadline:
                for frame in page.frames:
                    if frame == page.main_frame:
                        continue
                    try:
                        report = frame.eval_on_selector("#o", "e => e.textContent")
                    except Exception:  # noqa: BLE001 - child not ready yet
                        continue
                if "DONE" in report:
                    break
                time.sleep(0.25)
            time.sleep(3)
            stun = server.stun_since(mark)
            ctx.close()
            ports = Server.source_ports(stun)
            results["variants"][name] = {
                "sandbox_attr": cfg["sandbox"],
                "stun_datagrams": len(stun),
                "stun_source_ports": sorted(ports),
                "webrtc_blocked": len(stun) == 0,
                "child_ran": "DONE" in report,
                "child_report": report.replace("\n", " | ")[:200],
            }
            print(
                f"{name:<26} stun={len(stun):2d} ports={sorted(ports)} "
                f"blocked={len(stun) == 0} child_ran={'DONE' in report} :: {report.replace(chr(10), ' | ')[:80]}",
                flush=True,
            )
        browser.close()

    print(json.dumps(results, indent=1))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
