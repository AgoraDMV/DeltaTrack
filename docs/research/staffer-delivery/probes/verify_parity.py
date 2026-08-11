#!/usr/bin/env python3
"""Prove, in one command, that native CPython and Pyodide produce identical DeltaTrack output.

The delivery memo's strongest claim is that the engine emits byte-identical canonical JSON
and HTML under Pyodide. That claim was originally verified by hand, which makes it an
assertion rather than evidence. This harness makes it reproducible: it runs both runtimes
over the same committed fixtures, hashes each output with SHA-256, compares, prints the
environment that produced each result, and **exits non-zero on any mismatch**.

    uv run python docs/research/staffer-delivery/probes/verify_parity.py

Prerequisite: a Node install with the `pyodide` package. Point at it with
``--node-dir`` (default: ./node_modules beside this file, then $DT_PYODIDE_DIR).

    npm install pyodide          # inside the chosen directory

Proving the harness can fail
----------------------------
A comparison that has only ever passed cannot distinguish "the runtimes agree" from
"the comparison is broken". ``--mutate`` perturbs the native side by one character
before hashing, so the harness must report a mismatch and exit non-zero. Run it once
that way before trusting a green result.

    uv run python .../verify_parity.py --mutate    # expected: FAIL, exit 1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]  # probes/ -> staffer-delivery/ -> research/ -> docs/ -> repo root

# (tag, bill, old, new). Committed corpus fixtures, so this needs no download. Chosen to
# span the range: a small step, the large Senate rewrite, and a 1.8 MB-per-side enrolled
# pair whose diff is tiny (exercises big input, small output).
FIXTURES = [
    ("small", "118-hr-4366", "1_reported-in-house.xml", "2_engrossed-in-house.xml"),
    ("senate_rewrite", "118-hr-4366", "3_placed-on-calendar-senate.xml", "4_engrossed-amendment-senate.xml"),
    ("enrolled", "118-hr-4366", "5_engrossed-amendment-house.xml", "6_enrolled-bill.xml"),
]


def sha(x: str | bytes) -> str:
    return hashlib.sha256(x.encode("utf-8") if isinstance(x, str) else x).hexdigest()


def run_native(mutate: bool) -> dict:
    from deltatrack.compare.xml import compare_xml, compare_xml_html

    results = {}
    for tag, bill, a, b in FIXTURES:
        d = ROOT / "tests/corpus" / bill
        b1, b2 = (d / a).read_bytes(), (d / b).read_bytes()
        t = time.perf_counter()
        canon_txt = json.dumps(compare_xml(b1, b2, start_label="v1", end_label="v2"), indent=2, sort_keys=True)
        html = compare_xml_html(b1, b2, start_label="v1", end_label="v2")
        if mutate:
            # Deliberate one-character corruption, to prove the comparison can fail.
            html = "X" + html[1:]
        results[tag] = {
            "canonical_sha256": sha(canon_txt),
            "html_sha256": sha(html),
            "canonical_bytes": len(canon_txt.encode("utf-8")),
            "html_bytes": len(html.encode("utf-8")),
            "elapsed_ms": round((time.perf_counter() - t) * 1000),
        }
    try:
        import pypdfium2

        pdfium = f"present ({pypdfium2.version.PYPDFIUM_INFO})"
    except Exception:  # noqa: BLE001
        pdfium = "absent"
    return {
        "runtime": "native CPython",
        "python_version": sys.version.split()[0],
        "platform": f"{platform.machine()}/{sys.platform}",
        "pypdfium2": pdfium,
        "results": results,
    }


def run_pyodide(node_dir: Path) -> dict:
    specs = [f"{tag}:{bill}:{a}:{b}" for tag, bill, a, b in FIXTURES]
    proc = subprocess.run(
        ["node", str(HERE / "parity_pyodide.mjs"), str(node_dir), str(ROOT), *specs],
        capture_output=True,
        text=True,
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("PARITY_JSON ")), None)
    if line is None:
        sys.stderr.write(proc.stdout + "\n" + proc.stderr + "\n")
        raise SystemExit("Pyodide run produced no PARITY_JSON line (see output above).")
    return json.loads(line[len("PARITY_JSON ") :])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--node-dir", type=Path, default=None, help="directory containing node_modules/pyodide")
    ap.add_argument("--mutate", action="store_true", help="corrupt the native output to prove this check can fail")
    args = ap.parse_args()

    node_dir = args.node_dir or (Path(os.environ["DT_PYODIDE_DIR"]) if os.environ.get("DT_PYODIDE_DIR") else HERE)
    if not (node_dir / "node_modules" / "pyodide").is_dir():
        print(f"Pyodide not found under {node_dir}/node_modules.", file=sys.stderr)
        print(f"  cd {node_dir} && npm install pyodide", file=sys.stderr)
        print("  or pass --node-dir / set DT_PYODIDE_DIR to a directory that has it.", file=sys.stderr)
        return 2

    if args.mutate:
        print("!! --mutate: native output is deliberately corrupted. A MISMATCH is the correct result.\n")

    nat = run_native(args.mutate)
    pyo = run_pyodide(node_dir)

    print("environment")
    print(f"  native : CPython {nat['python_version']} on {nat['platform']}, pypdfium2 {nat['pypdfium2']}")
    print(
        f"  pyodide: CPython {pyo['python_version']} on {pyo['platform']}, "
        f"pyodide {pyo.get('pyodide_version')}, node {pyo.get('node_version')}"
    )
    print(f"           pypdfium2 {pyo.get('pypdfium2')}, boot {pyo.get('boot_ms')} ms")
    print()

    ok = True
    hdr = f"{'fixture':<16}{'artifact':<12}{'bytes':>10}  {'native sha256':<18}{'pyodide sha256':<18}result"
    print(hdr)
    print("-" * len(hdr))
    for tag, *_ in FIXTURES:
        n, p = nat["results"][tag], pyo["results"][tag]
        for artifact, key in (("canonical", "canonical_sha256"), ("html", "html_sha256")):
            match = n[key] == p[key]
            ok &= match
            size = n["canonical_bytes"] if artifact == "canonical" else n["html_bytes"]
            print(
                f"{tag:<16}{artifact:<12}{size:>10}  {n[key][:16]:<18}{p[key][:16]:<18}"
                f"{'IDENTICAL' if match else 'MISMATCH'}"
            )
        print(f"{'':<16}{'timing':<12}{'':>10}  native {n['elapsed_ms']} ms vs pyodide {p['elapsed_ms']} ms")

    print()
    if ok:
        print(f"PASS: {len(FIXTURES)} fixtures x 2 artifacts identical across both runtimes.")
        if args.mutate:
            print("BUT --mutate was set and nothing failed. The comparison is broken.", file=sys.stderr)
            return 1
        return 0
    print("FAIL: at least one artifact differs between native CPython and Pyodide.", file=sys.stderr)
    return 0 if args.mutate else 1


if __name__ == "__main__":
    raise SystemExit(main())
