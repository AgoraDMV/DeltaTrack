// Phase 3: run the candidate backends where they would actually ship -- in the browser
// runtime -- and check the result against what native Python produced.
//
// Three questions, and they are different:
//
//   1. Does the backend LOAD under Pyodide at all? The spec records pdfminer.six as
//      "installs via micropip (verified)", but pdfminer now depends on `cryptography`,
//      which is a Rust extension rather than pure Python. Whether that resolves under
//      Pyodide is a fact about today's dependency tree, not about 2026-08-05's, so it is
//      re-measured here rather than carried forward.
//   2. Does it produce the SAME glyph facts in the browser as natively? The delivery
//      spike established byte-identical output for the XML path; the PDF path has never
//      been checked.
//   3. What does it cost? Including, for the JS backends, the price of moving glyphs
//      across the JS/Python boundary -- a cost that does not exist natively and that no
//      earlier measurement includes.
//
// Run: node docs/research/pdf-backend-bakeoff/probes/js/phase3_pyodide.mjs <pdf> [--pages N]

import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const { loadPyodide } = require("pyodide");

const PROBES = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const REPO = path.resolve(PROBES, "../../../..");

const args = process.argv.slice(2);
const pdfPath = args[0] ?? path.join(REPO, "tests/corpus/118-hr-4366/1_reported-in-house.pdf");
const pagesIdx = args.indexOf("--pages");
const pageLimit = pagesIdx >= 0 ? parseInt(args[pagesIdx + 1], 10) : 20;

const results = { pdf: pdfPath, page_limit: pageLimit, boot: {}, backends: {} };

console.log(`booting pyodide (pdf=${path.basename(pdfPath)}, pages=${pageLimit})`);
const tBoot = performance.now();
const pyodide = await loadPyodide({ stdout: () => {}, stderr: (s) => console.error("  py:", s) });
results.boot.pyodide_ms = Math.round(performance.now() - tBoot);
console.log(`  pyodide ready in ${results.boot.pyodide_ms} ms`);

// --- stage the engine + probe sources into the Pyodide filesystem -------------
const tStage = performance.now();
pyodide.FS.mkdirTree("/dt/src");
pyodide.FS.mkdirTree("/dt/probes/backends");

function copyTree(hostDir, vfsDir) {
  const { readdirSync, statSync } = require("node:fs");
  for (const name of readdirSync(hostDir)) {
    if (name === "__pycache__" || name === "node_modules") continue;
    const hp = path.join(hostDir, name);
    const vp = `${vfsDir}/${name}`;
    if (statSync(hp).isDirectory()) {
      pyodide.FS.mkdirTree(vp);
      copyTree(hp, vp);
    } else if (name.endsWith(".py")) {
      pyodide.FS.writeFile(vp, readFileSync(hp));
    }
  }
}
copyTree(path.join(REPO, "src/deltatrack"), "/dt/src");
// The engine's package dir must keep its name for `import deltatrack` to work.
pyodide.FS.mkdirTree("/dt/pkg/deltatrack");
copyTree(path.join(REPO, "src/deltatrack"), "/dt/pkg/deltatrack");
for (const f of ["contract.py", "reconstruct.py"]) {
  pyodide.FS.writeFile(`/dt/probes/${f}`, readFileSync(path.join(PROBES, f)));
}
for (const f of ["pdfminer_backend.py", "pypdf_backend.py", "pymupdf_backend.py"]) {
  pyodide.FS.writeFile(`/dt/probes/backends/${f}`, readFileSync(path.join(PROBES, "backends", f)));
}
pyodide.FS.writeFile("/dt/bill.pdf", readFileSync(pdfPath));
results.boot.stage_ms = Math.round(performance.now() - tStage);

await pyodide.runPythonAsync(`
import sys
sys.path.insert(0, "/dt/pkg")
sys.path.insert(0, "/dt/probes")
`);

// --- pypdfium2 stub: the engine imports it on a path the PDF pipeline never calls ---
// Same technique the delivery spike used. It RAISES on any real PDFium call, so a silent
// wrong answer is impossible; if the stub is ever reached the run fails loudly.
await pyodide.runPythonAsync(`
import os, textwrap
os.makedirs("/dt/pkg/pypdfium2", exist_ok=True)
stub = textwrap.dedent('''
    class _Tripwire:
        def __getattr__(self, name):
            raise RuntimeError(
                "pypdfium2 was actually CALLED under Pyodide (attr=%r). The browser path "
                "must not reach PDFium; this run is invalid." % name
            )
    def __getattr__(name):
        return getattr(_Tripwire(), name)
''')
open("/dt/pkg/pypdfium2/__init__.py", "w").write(stub)
open("/dt/pkg/pypdfium2/raw.py", "w").write(stub)
`);

// --- micropip install gate ----------------------------------------------------
await pyodide.loadPackage("micropip");
for (const pkg of ["pdfminer.six", "pypdf"]) {
  const t = performance.now();
  try {
    await pyodide.runPythonAsync(`
import micropip
await micropip.install(${JSON.stringify(pkg)})
`);
    results.backends[pkg] = { install: "ok", install_ms: Math.round(performance.now() - t) };
    console.log(`  micropip install ${pkg}: OK (${results.backends[pkg].install_ms} ms)`);
  } catch (e) {
    results.backends[pkg] = { install: "FAILED", error: String(e).slice(0, 600) };
    console.log(`  micropip install ${pkg}: FAILED -- ${String(e).slice(0, 300)}`);
  }
}

// PyMuPDF ships in the Pyodide distribution rather than via micropip.
try {
  const t = performance.now();
  await pyodide.loadPackage("pymupdf");
  results.backends["pymupdf"] = { install: "ok", install_ms: Math.round(performance.now() - t) };
  console.log(`  loadPackage pymupdf: OK (${results.backends["pymupdf"].install_ms} ms)`);
} catch (e) {
  results.backends["pymupdf"] = { install: "FAILED", error: String(e).slice(0, 600) };
  console.log(`  loadPackage pymupdf: FAILED -- ${String(e).slice(0, 300)}`);
}

// --- run each installed backend through the neutral layer, in-browser ---------
const PY_RUN = (mod, name) => `
import json, time, sys
from pathlib import Path
import ${mod} as backend
from reconstruct import reconstruct
t0 = time.perf_counter()
raw, summary = backend.extract(Path("/dt/bill.pdf"), ${pageLimit})
t_extract = time.perf_counter() - t0
t0 = time.perf_counter()
pages, diag = reconstruct(raw, repaired=True)
t_recon = time.perf_counter() - t0
json.dumps({
  "backend": ${JSON.stringify(name)},
  "summary": summary,
  "diag": diag,
  "extract_s": round(t_extract, 3),
  "reconstruct_s": round(t_recon, 3),
  "n_pages": len(pages),
  "text_sha": __import__("hashlib").sha256(
      "\\n".join(p.text for p in pages).encode()
  ).hexdigest(),
  "line_numbers": [[p.page_number, l.line_number] for p in pages for l in p.print_lines if l.line_number],
})
`;

for (const [mod, name] of [
  ["backends.pdfminer_backend", "pdfminer"],
  ["backends.pypdf_backend", "pypdf"],
  ["backends.pymupdf_backend", "pymupdf"],
]) {
  const key = name === "pdfminer" ? "pdfminer.six" : name;
  if (results.backends[key]?.install !== "ok") {
    console.log(`  ${name}: skipped (not installed)`);
    continue;
  }
  try {
    const out = JSON.parse(await pyodide.runPythonAsync(PY_RUN(mod, name)));
    Object.assign(results.backends[key], out, { ran: true });
    console.log(
      `  ${name}: ran in-browser -- extract=${out.extract_s}s reconstruct=${out.reconstruct_s}s ` +
        `pages=${out.n_pages} sha=${out.text_sha.slice(0, 16)}`,
    );
  } catch (e) {
    results.backends[key].ran = false;
    results.backends[key].run_error = String(e).slice(0, 800);
    console.log(`  ${name}: RUN FAILED -- ${String(e).slice(0, 300)}`);
  }
}

// --- JS backends: extract in JS, hand the glyphs to Pyodide ------------------
// This is the architecture a PDF.js or PDFium-WASM browser build actually implies, and
// it carries a cost that exists in NO earlier measurement: the glyph facts have to cross
// the JS/Python boundary. That transfer is charged per document and is invisible to both
// the native benchmark and the in-JS extraction benchmark, so it is measured separately
// here rather than folded into an extraction number.
for (const [name, script] of [
  ["pdfjs", "dump_pdfjs.mjs"],
  ["pdfium-wasm", "dump_pdfium_wasm.mjs"],
]) {
  const entry = { install: "n/a (native JS/WASM)" };
  results.backends[name] = entry;
  try {
    const { execFileSync } = require("node:child_process");
    const t0 = performance.now();
    const jsonl = execFileSync(
      "node",
      [path.join(PROBES, "js", script), path.resolve(pdfPath), "--limit", String(pageLimit)],
      { cwd: path.join(PROBES, "js"), maxBuffer: 1024 * 1024 * 1024, encoding: "utf8" },
    );
    entry.extract_s = Number(((performance.now() - t0) / 1000).toFixed(3));
    entry.transfer_bytes = Buffer.byteLength(jsonl);

    // Cross the boundary: hand the JSONL over as one string and parse it inside Python.
    const t1 = performance.now();
    pyodide.globals.set("_jsonl", jsonl);
    const out = JSON.parse(
      await pyodide.runPythonAsync(`
import json, hashlib
from contract import read_stream
from reconstruct import reconstruct
pages_raw, summary = read_stream(iter(_jsonl.splitlines()))
pages, diag = reconstruct(pages_raw, repaired=True)
json.dumps({
  "summary": summary,
  "diag": diag,
  "n_pages": len(pages),
  "text_sha": hashlib.sha256("\\n".join(p.text for p in pages).encode()).hexdigest(),
})
`),
    );
    entry.boundary_and_reconstruct_s = Number(((performance.now() - t1) / 1000).toFixed(3));
    Object.assign(entry, out, { ran: true });
    console.log(
      `  ${name}: extract=${entry.extract_s}s boundary+reconstruct=` +
        `${entry.boundary_and_reconstruct_s}s transfer=` +
        `${(entry.transfer_bytes / 1048576).toFixed(1)}MB sha=${out.text_sha.slice(0, 16)}`,
    );
  } catch (e) {
    entry.ran = false;
    entry.run_error = String(e).slice(0, 800);
    console.log(`  ${name}: RUN FAILED -- ${String(e).slice(0, 300)}`);
  }
}

const outPath = path.join(REPO, "docs/research/pdf-backend-bakeoff/results/phase3_pyodide.json");
writeFileSync(outPath, JSON.stringify(results, null, 1));
console.log(`wrote ${outPath}`);
