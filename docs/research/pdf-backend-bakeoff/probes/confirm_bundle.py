"""Concern E: what each finalist costs to DELIVER, in bytes that cross the wire.

PRE-REGISTRATION-CONFIRMATORY.md, "Concern E -- bundle size and architecture". The audit
named this the axis the PDFium-WASM vs pdfminer decision most likely turns on, and the
exploratory run did not measure it at all. Its stated expectation was that "pdfminer adds
no binary at all, which is the axis on which it could still win despite being ~8x slower."

THE UNIT IS OVER-THE-WIRE BYTES, and getting it wrong is easy in a way that flatters
pdfminer. A `.wasm` is raw and compresses hard; a `.whl` is already a ZIP, so gzipping it
again buys almost nothing. Comparing a gzipped wasm against an uncompressed wheel, or a
wheel's on-disk expansion against a wasm's file size, both give the wrong answer. Each
component is therefore weighed as the bytes a browser actually downloads:

    wasm / js   file size, and gzip, because a server serves them compressed
    wheel       the published wheel size, uncompressed further (it is a ZIP already)

Sources are authoritative rather than local: wheel sizes come from PyPI's own metadata and
from the Pyodide CDN for the wasm32 builds. The venv's macOS binaries are NOT used --
`cryptography`'s local `_rust.abi3.so` is 11.8 MB of native arm64 that would never ship to
a browser, and taking it for the artifact cost would be wrong in the other direction.

This does NOT build a single-file bundle. Nobody has written that bundler, and inventing
one here would measure the bundler rather than the backend. Load, init and latency are
Concern D's instruments on an idle machine; size is deterministic and needs neither.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/confirm_bundle.py
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import urllib.request
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
JS = PROBES / "js" / "node_modules"
PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v314.0.3/full"


def local_component(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "name": path.name,
        "source": "installed artifact",
        "bytes": len(data),
        "gzip": len(gzip.compress(data, 9)),
        "wire": len(gzip.compress(data, 9)),
    }


def pypi_wheel(name: str) -> dict | None:
    """Published pure-python wheel size. Already a ZIP, so wire == file size."""
    try:
        d = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=30))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {name}: {exc}", file=sys.stderr)
        return None
    urls = [f for f in d["urls"] if f["packagetype"] == "bdist_wheel"]
    pure = [f for f in urls if "py3-none-any" in f["filename"]] or urls
    if not pure:
        return None
    f = pure[0]
    return {
        "name": f["filename"],
        "source": "PyPI",
        "version": d["info"]["version"],
        "bytes": f["size"],
        "gzip": f["size"],
        "wire": f["size"],
    }


def pyodide_wheel(filename: str) -> dict | None:
    """wasm32 wheel from the Pyodide distribution. Also a ZIP."""
    try:
        req = urllib.request.Request(f"{PYODIDE_CDN}/{filename}", method="GET")
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {filename}: {exc}", file=sys.stderr)
        return None
    return {"name": filename, "source": "Pyodide CDN", "bytes": len(data), "gzip": len(data), "wire": len(data)}


def total(components: list[dict]) -> dict:
    return {
        "bytes": sum(c["bytes"] for c in components),
        "wire": sum(c["wire"] for c in components),
        "components": components,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO / "docs/research/pdf-backend-bakeoff/results/confirm_bundle.json")
    args = ap.parse_args()

    print("weighing the shared baseline...", file=sys.stderr)
    pyo = JS / "pyodide"
    baseline = [
        local_component(pyo / n)
        for n in ("pyodide.asm.wasm", "pyodide.asm.mjs", "pyodide.mjs", "python_stdlib.zip")
        if (pyo / n).exists()
    ]
    src = sorted((REPO / "src" / "deltatrack").rglob("*.py"))
    blob = b"".join(p.read_bytes() for p in src)
    baseline.append(
        {
            "name": f"deltatrack sources ({len(src)} files)",
            "source": "this tree",
            "bytes": len(blob),
            "gzip": len(gzip.compress(blob, 9)),
            "wire": len(gzip.compress(blob, 9)),
        }
    )

    print("weighing pdfium-wasm...", file=sys.stderr)
    pdfium = [
        local_component(JS / "@embedpdf/pdfium/dist/pdfium.wasm"),
        local_component(JS / "@embedpdf/pdfium/dist/index.browser.js"),
    ]

    print("weighing pdfminer (PyPI + Pyodide CDN)...", file=sys.stderr)
    core = [w for w in (pypi_wheel("pdfminer.six"), pypi_wheel("charset-normalizer")) if w]
    crypto = [
        w
        for w in (
            pyodide_wheel("cryptography-47.0.0-cp314-abi3-pyemscripten_2026_0_wasm32.whl"),
            pypi_wheel("cffi"),
            pypi_wheel("six"),
        )
        if w
    ]

    result = {
        "unit": "over-the-wire bytes: gzip for raw wasm/js, published wheel size for wheels (already ZIP)",
        "baseline": total(baseline),
        "backends": {
            "pdfium-wasm": total(pdfium),
            "pdfminer (core only)": total(core),
            "pdfminer (as micropip resolves it, with cryptography)": total(core + crypto),
        },
    }
    for name, t in result["backends"].items():
        t["artifact_wire"] = result["baseline"]["wire"] + t["wire"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1))

    def mb(n):
        return f"{n / 1e6:7.2f} MB"

    print("\nShared baseline, carried by both artifacts")
    for c in baseline:
        print(f"  {c['name'][:44]:44} {mb(c['bytes'])} raw  {mb(c['wire'])} wire")
    print(f"  {'TOTAL':44} {mb(result['baseline']['bytes'])} raw  {mb(result['baseline']['wire'])} wire")

    print("\nBackend cost, over the wire")
    for name, t in result["backends"].items():
        print(f"\n  {name}")
        for c in t["components"]:
            print(f"    {c['name'][:46]:46} {mb(c['wire'])}  ({c['source']})")
        print(f"    {'incremental':46} {mb(t['wire'])}")
        print(f"    {'FULL ARTIFACT':46} {mb(t['artifact_wire'])}")

    a = result["backends"]["pdfium-wasm"]["wire"]
    b = result["backends"]["pdfminer (core only)"]["wire"]
    c = result["backends"]["pdfminer (as micropip resolves it, with cryptography)"]["wire"]
    print(f"\n  pdfminer core       / pdfium-wasm = {b / a:.2f}x")
    print(f"  pdfminer resolved   / pdfium-wasm = {c / a:.2f}x")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
