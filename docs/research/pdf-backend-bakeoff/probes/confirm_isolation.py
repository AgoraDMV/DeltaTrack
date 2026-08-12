"""Concern C, second claim: the ENVIRONMENT cannot reach the network, not just the page.

PRE-REGISTRATION-CONFIRMATORY.md, "Environment-level isolation, as a separate and stronger
claim". Browser policy and environment isolation support different sentences and must not
be conflated:

    browser policy         "our app does not transmit through these mechanisms"
    environment isolation  "the process cannot reach the network at all"

BOTH controls run inside the same invocation window, and neither alone is sufficient:

  * KNOWN-BAD INSIDE THE SANDBOX -- a deliberate beacon fired from the sandboxed process
    that must NOT arrive. This is what attributes the silence to the sandbox. An
    unsandboxed beacon proves only that the server works, in a different environment from
    the one under test.
  * OBSERVER LIVENESS OUTSIDE THE SANDBOX -- an unsandboxed beacon to the same listener in
    an overlapping window that MUST arrive. Without it, "nothing received" cannot be
    distinguished from a dead listener.

A run missing either control is VOID, not a pass.

Both beacons target our own loopback listener, so the payload is inert if the guard fails
open: the worst outcome of a broken sandbox is a request we wanted to see anyway. A third
check confirms an EXTERNAL host fails to resolve inside the sandbox, so a pass cannot come
from loopback being blocked by something other than the policy.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/confirm_isolation.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
PORT = 8973
CANARY_SANDBOXED = "DELTATRACK_SECRET_isolation_sandboxed"
CANARY_LIVENESS = "DELTATRACK_SECRET_isolation_liveness"

SANDBOX_PROFILE = """(version 1)
(allow default)
(deny network*)
"""

WORKER = r'''
"""Runs INSIDE the sandbox. Fires the known-bad beacon, probes an external host, then does
real work -- a full PDF comparison -- which must still succeed with networking denied."""
import hashlib, json, socket, sys, urllib.request
from pathlib import Path

REPO = Path(sys.argv[1])
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "docs/research/pdf-backend-bakeoff/probes"))

out = {}

# 1. Known-bad beacon. Must NOT reach the listener.
try:
    urllib.request.urlopen(
        f"http://127.0.0.1:{sys.argv[2]}/isolation-knownbad?secret={sys.argv[3]}", timeout=5
    ).read()
    out["knownbad_request_raised"] = False
except Exception as exc:
    out["knownbad_request_raised"] = True
    out["knownbad_error"] = type(exc).__name__

# 2. External host. Must fail to resolve.
try:
    socket.gethostbyname("www.govinfo.gov")
    out["external_resolved"] = True
except Exception as exc:
    out["external_resolved"] = False
    out["external_error"] = type(exc).__name__

# 3. Real work: a full PDF comparison through the production entry point.
try:
    from deltatrack.compare.pdf import compare_pdfs
    v1 = (REPO / "tests/corpus/118-hr-4366/1_reported-in-house.pdf").read_bytes()
    v2 = (REPO / "tests/corpus/118-hr-4366/2_engrossed-in-house.pdf").read_bytes()
    canon = compare_pdfs(v1, v2)
    blob = json.dumps(canon, sort_keys=True, default=str)
    out["comparison_ok"] = True
    out["comparison_sha256"] = hashlib.sha256(blob.encode()).hexdigest()
    out["n_changes"] = len(canon.get("changes") or [])
except Exception as exc:
    out["comparison_ok"] = False
    out["comparison_error"] = f"{type(exc).__name__}: {exc}"

print(json.dumps(out))
'''


class Server:
    def __init__(self):
        self.proc = None
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

    def received(self, needle: str) -> bool:
        return any(needle in x for x in self.lines)


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    r = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    return r.returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out", type=Path, default=REPO / "docs/research/pdf-backend-bakeoff/results/confirm_isolation.json"
    )
    args = ap.parse_args()

    tmp = Path(os.environ.get("CLAUDE_JOB_DIR", "/tmp")) / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    profile = tmp / "nonet.sb"
    profile.write_text(SANDBOX_PROFILE)
    worker = tmp / "isolation_worker.py"
    worker.write_text(WORKER)

    results: dict = {
        "primary": "macOS sandbox-exec (deny network*)",
        "canaries": {"sandboxed": CANARY_SANDBOXED, "liveness": CANARY_LIVENESS},
    }

    with Server() as server:
        # Control B: observer liveness, OUTSIDE the sandbox, overlapping window.
        import urllib.request

        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/isolation-liveness?secret={CANARY_LIVENESS}", timeout=10
            ).read()
        except Exception as exc:  # noqa: BLE001
            results["liveness_request_error"] = f"{type(exc).__name__}: {exc}"

        # The run under test, carrying control A inside it.
        t0 = time.perf_counter()
        proc = subprocess.run(
            [
                "sandbox-exec",
                "-f",
                str(profile),
                sys.executable,
                str(worker),
                str(REPO),
                str(PORT),
                CANARY_SANDBOXED,
            ],
            capture_output=True,
            text=True,
            timeout=900,
        )
        results["sandboxed_elapsed_s"] = round(time.perf_counter() - t0, 2)
        results["sandboxed_returncode"] = proc.returncode
        try:
            results["sandboxed"] = json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            results["sandboxed"] = {}
            results["sandboxed_stdout"] = proc.stdout[-2000:]
            results["sandboxed_stderr"] = proc.stderr[-2000:]

        time.sleep(3)
        results["server_saw_liveness"] = server.received(CANARY_LIVENESS)
        results["server_saw_sandboxed_knownbad"] = server.received(CANARY_SANDBOXED)

    # The unsandboxed comparison, for output identity: isolation must not change the answer.
    try:
        sys.path.insert(0, str(REPO / "src"))
        import hashlib

        from deltatrack.compare.pdf import compare_pdfs

        canon = compare_pdfs(
            (REPO / "tests/corpus/118-hr-4366/1_reported-in-house.pdf").read_bytes(),
            (REPO / "tests/corpus/118-hr-4366/2_engrossed-in-house.pdf").read_bytes(),
        )
        blob = json.dumps(canon, sort_keys=True, default=str)
        results["unsandboxed_comparison_sha256"] = hashlib.sha256(blob.encode()).hexdigest()
    except Exception as exc:  # noqa: BLE001
        results["unsandboxed_comparison_error"] = f"{type(exc).__name__}: {exc}"

    sb = results.get("sandboxed", {})
    checks = {
        "observer_liveness (unsandboxed beacon ARRIVED)": results.get("server_saw_liveness") is True,
        "known_bad_inside_sandbox (beacon did NOT arrive)": results.get("server_saw_sandboxed_knownbad") is False,
        "external_host_unresolvable_inside_sandbox": sb.get("external_resolved") is False,
        "comparison_succeeded_with_network_denied": sb.get("comparison_ok") is True,
        "output_identical_to_unsandboxed": (
            sb.get("comparison_sha256") is not None
            and sb.get("comparison_sha256") == results.get("unsandboxed_comparison_sha256")
        ),
    }
    results["checks"] = checks
    results["verdict"] = "PASS" if all(checks.values()) else "VOID / FAIL"

    # The stronger claim, attempted rather than inferred.
    if docker_available():
        results["linux_container"] = "docker daemon available -- run --network none separately"
    else:
        results["linux_container"] = "NOT RUN -- docker daemon unavailable at execution time"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1))

    print("\nEnvironment isolation, macOS sandbox-exec (deny network*)")
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f"\nverdict: {results['verdict']}")
    print(f"linux container: {results['linux_container']}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
