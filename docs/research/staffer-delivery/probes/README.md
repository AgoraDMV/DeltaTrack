# Delivery-spike probes

Frozen reproduction artifacts for [`../README.md`](../README.md). Not maintained
source: they hardcode paths and exist to reproduce that document's numbers. Excluded
from lint by the `docs/research/**/probes` rule in `pyproject.toml`.

**Production code is not modified by any of these.** Where the engine needs
`pypdfium2` importable under WASM, a stub is written to a scratch directory and placed
on `sys.path`; it raises on any PDFium call that is actually reached, so a silent wrong
answer is not possible.

## Setup

```bash
# Node harnesses
mkdir -p /tmp/dt-spike && cd /tmp/dt-spike && npm init -y
npm install pyodide pdfjs-dist

# Engine environment (from the repo root)
source ./init
```

The `.mjs` harnesses carry an absolute `ROOT` pointing at the checkout they were run
from. Edit that constant before re-running them elsewhere.

## What each probe answers

| Probe | Question |
|---|---|
| **`verify_parity.py`** | **Do native CPython and Pyodide produce identical output? One command, SHA-256 both sides, non-zero exit on mismatch.** |
| `parity_pyodide.mjs` | Pyodide half of `verify_parity.py`. Not run directly. |
| `exp1_imports.mjs` | Which `deltatrack` modules import under Pyodide, and why do the rest fail? |
| `exp1_xml_e2e.mjs` | Does the full XML comparison pipeline run under Pyodide on real bills? |
| `native_baseline.py` | Native CPython timings and canonical output, for the parity comparison. |
| `exp_pdfjs_granularity.mjs` | What glyph geometry does PDF.js expose, and at what granularity? |
| `dt_launcher.py` | Packaged-executable entry point (PyInstaller). Its `--selftest` opens a real PDF, so it fails if the native binary was dropped. |
| `probe_static_app.py` | Drives `static-app/` under Playwright from `file://` and from HTTP, reporting which browser capabilities are blocked. |
| `static-app/` | Minimal browser DeltaTrack: capability probes plus a real in-page comparison. Needs `pyodide/` and `engine.zip` staged (below). |
| `single-file/index.html` | Isolates what ONE self-contained HTML file can still do from `file://`. |
| `build_single_file.py` | Builds the 17.8 MB self-contained `deltatrack-standalone.html`. |

## Staging the large assets

The Pyodide runtime and the built standalone file are **not committed** (12.8 MB and
17.8 MB). Recreate them:

```bash
SA=docs/research/staffer-delivery/probes/static-app
mkdir -p $SA/pyodide
cp /tmp/dt-spike/node_modules/pyodide/{pyodide.mjs,pyodide.asm.mjs,pyodide.asm.wasm,python_stdlib.zip,pyodide-lock.json} $SA/pyodide/
(cd src && zip -qr ../$SA/engine.zip deltatrack -x '*__pycache__*')
# plus the pypdfium2 stub the harnesses write to /tmp/dt-spike/shim
(cd /tmp/dt-spike/shim && zip -qr <repo>/$SA/engine.zip pypdfium2)

uv run python docs/research/staffer-delivery/probes/build_single_file.py
```

## The parity check, which is the one that matters

The memo's headline claim is byte-identical output across runtimes. This turns that from
an assertion into a repeatable gate:

```bash
uv run python docs/research/staffer-delivery/probes/verify_parity.py --node-dir /tmp/dt-spike
```

It runs both runtimes over the same committed fixtures, hashes each artifact with
SHA-256 **inside** the runtime that produced it, prints the interpreter, platform and
dependency versions behind each column, and exits non-zero on any mismatch.

**Run the negative control before trusting a pass.** A comparison that has only ever
passed cannot distinguish "the runtimes agree" from "the comparison is broken":

```bash
uv run python docs/research/staffer-delivery/probes/verify_parity.py --mutate --node-dir /tmp/dt-spike
```

`--mutate` corrupts the native output by one character, so every HTML hash must diverge
while the canonical hashes stay identical. If `--mutate` reports a pass, the harness is
broken and its green runs mean nothing.

## Running

```bash
cd /tmp/dt-spike
node exp1_imports.mjs
node exp1_xml_e2e.mjs
node exp_pdfjs_granularity.mjs <repo>/tests/corpus/118-hr-4366/1_reported-in-house.pdf

# from the repo root
uv run python docs/research/staffer-delivery/probes/native_baseline.py
python3 -m http.server 8971 --bind 127.0.0.1 --directory docs/research/staffer-delivery/probes/static-app &
uv run python docs/research/staffer-delivery/probes/probe_static_app.py
```

Packaged executable:

```bash
uv venv pkgvenv --python 3.12
VIRTUAL_ENV=$PWD/pkgvenv uv pip install pyinstaller pypdfium2 .
./pkgvenv/bin/pyinstaller --onefile --name DeltaTrack \
  docs/research/staffer-delivery/probes/dt_launcher.py
./dist/DeltaTrack --selftest --pdf tests/corpus/118-hr-4366/1_reported-in-house.pdf

# negative control: the probe must FAIL when the native binary is excluded
./pkgvenv/bin/pyinstaller --onefile --name DeltaTrackNoPdfium --exclude-module pypdfium2 \
  docs/research/staffer-delivery/probes/dt_launcher.py
./dist/DeltaTrackNoPdfium --selftest   # expected: ModuleNotFoundError at pdf_text.py
```
