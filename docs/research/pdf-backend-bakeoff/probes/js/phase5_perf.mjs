// Phase 5: performance and memory in the browser runtime, on the LARGEST bills.
//
// Gate 9 is relative to the incumbent, per PRE-REGISTRATION.md: PDFium itself takes
// 5.8-10.9 s natively on a 1000+ page bill, so an absolute "tens of seconds" rule would
// disqualify the incumbent, which is incoherent for a no-regression exercise.
//
// The incumbent cannot run here at all -- pypdfium2 has no Emscripten build, which is the
// entire reason this bake-off exists -- so its column is the NATIVE number and is labelled
// as such. Comparing a browser figure against a native one overstates the challengers'
// penalty, and that is the honest direction to err in.
//
// Run: node docs/research/pdf-backend-bakeoff/probes/js/phase5_perf.mjs [--pages N]

import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const { loadPyodide } = require("pyodide");

const PROBES = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const REPO = path.resolve(PROBES, "../../../..");

const args = process.argv.slice(2);
const pagesIdx = args.indexOf("--pages");
const PAGE_SAMPLE = pagesIdx >= 0 ? parseInt(args[pagesIdx + 1], 10) : 60;

// The three largest corpus documents, all 1000+ pages.
const BILLS = [
  "tests/corpus/117-hr-2471/6_enrolled-bill.pdf",
  "tests/corpus/119-hr-1/1_reported-in-house.pdf",
  "tests/corpus/118-hr-4366/5_engrossed-amendment-house.pdf",
];

const results = { page_sample: PAGE_SAMPLE, boot: {}, bills: {} };

const tBoot = performance.now();
const pyodide = await loadPyodide({ stdout: () => {}, stderr: () => {} });
results.boot.pyodide_ms = Math.round(performance.now() - tBoot);
console.log(`pyodide boot: ${results.boot.pyodide_ms} ms`);

pyodide.FS.mkdirTree("/dt/pkg/deltatrack");
pyodide.FS.mkdirTree("/dt/probes/backends");
function copyTree(hostDir, vfsDir) {
  const { readdirSync, statSync } = require("node:fs");
  for (const name of readdirSync(hostDir)) {
    if (name === "__pycache__") continue;
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
copyTree(path.join(REPO, "src/deltatrack"), "/dt/pkg/deltatrack");
for (const f of ["contract.py", "reconstruct.py"]) {
  pyodide.FS.writeFile(`/dt/probes/${f}`, readFileSync(path.join(PROBES, f)));
}
for (const f of ["pdfminer_backend.py", "pypdf_backend.py", "pymupdf_backend.py"]) {
  pyodide.FS.writeFile(`/dt/probes/backends/${f}`, readFileSync(path.join(PROBES, "backends", f)));
}
await pyodide.runPythonAsync(`
import sys, os, textwrap
sys.path.insert(0, "/dt/pkg"); sys.path.insert(0, "/dt/probes")
os.makedirs("/dt/pkg/pypdfium2", exist_ok=True)
stub = "def __getattr__(n):\\n    raise RuntimeError('pypdfium2 called under Pyodide: run invalid')\\n"
open("/dt/pkg/pypdfium2/__init__.py","w").write(stub)
open("/dt/pkg/pypdfium2/raw.py","w").write(stub)
`);

await pyodide.loadPackage("micropip");
const tInstall = performance.now();
await pyodide.runPythonAsync(`
import micropip
await micropip.install("pdfminer.six")
await micropip.install("pypdf")
`);
await pyodide.loadPackage("pymupdf");
results.boot.install_ms = Math.round(performance.now() - tInstall);
console.log(`backend install/load: ${results.boot.install_ms} ms`);

for (const rel of BILLS) {
  const abs = path.join(REPO, rel);
  pyodide.FS.writeFile("/dt/bill.pdf", readFileSync(abs));
  const bill = { file: rel, size_mb: +(readFileSync(abs).length / 1048576).toFixed(2), backends: {} };
  results.bills[rel] = bill;
  console.log(`\n${rel} (${bill.size_mb} MB)`);

  for (const [mod, name] of [
    ["backends.pdfminer_backend", "pdfminer"],
    ["backends.pypdf_backend", "pypdf"],
    ["backends.pymupdf_backend", "pymupdf"],
  ]) {
    try {
      const out = JSON.parse(
        await pyodide.runPythonAsync(`
import json, time, gc, tracemalloc
from pathlib import Path
import ${mod} as backend
from reconstruct import reconstruct
gc.collect()
tracemalloc.start()
t0 = time.perf_counter()
raw, summary = backend.extract(Path("/dt/bill.pdf"), ${PAGE_SAMPLE})
t_ex = time.perf_counter() - t0
t0 = time.perf_counter()
pages, diag = reconstruct(raw, repaired=True)
t_rc = time.perf_counter() - t0
_cur, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
total_pages = summary.get("pages_total") or summary["pages"]
json.dumps({
  "pages_sampled": summary["pages"],
  "extract_s": round(t_ex, 3),
  "reconstruct_s": round(t_rc, 3),
  "peak_mb": round(peak / 1048576, 1),
  "glyphs": summary.get("glyphs"),
})
`),
      );
      bill.backends[name] = out;
      console.log(
        `  ${name.padEnd(10)} ${out.pages_sampled}pp extract=${out.extract_s}s ` +
          `recon=${out.reconstruct_s}s peak=${out.peak_mb}MB`,
      );
    } catch (e) {
      bill.backends[name] = { error: String(e).slice(0, 400) };
      console.log(`  ${name.padEnd(10)} FAILED ${String(e).slice(0, 160)}`);
    }
  }

  // JS backends run outside Pyodide; their transfer cost is measured in phase3.
  const { execFileSync } = require("node:child_process");
  for (const [name, script] of [
    ["pdfjs", "dump_pdfjs.mjs"],
    ["pdfium-wasm", "dump_pdfium_wasm.mjs"],
  ]) {
    try {
      const t0 = performance.now();
      const out = execFileSync(
        "node",
        [path.join(PROBES, "js", script), abs, "--limit", String(PAGE_SAMPLE)],
        { cwd: path.join(PROBES, "js"), maxBuffer: 1024 * 1024 * 1024, encoding: "utf8" },
      );
      const summary = JSON.parse(out.slice(out.lastIndexOf("\n", out.length - 2) + 1)).summary;
      bill.backends[name] = {
        pages_sampled: summary.pages,
        extract_s: +((performance.now() - t0) / 1000).toFixed(3),
        transfer_mb: +(Buffer.byteLength(out) / 1048576).toFixed(1),
        glyphs: summary.glyphs,
      };
      console.log(
        `  ${name.padEnd(10)} ${summary.pages}pp extract=${bill.backends[name].extract_s}s ` +
          `transfer=${bill.backends[name].transfer_mb}MB`,
      );
    } catch (e) {
      bill.backends[name] = { error: String(e).slice(0, 400) };
      console.log(`  ${name.padEnd(10)} FAILED ${String(e).slice(0, 160)}`);
    }
  }
}

const outPath = path.join(REPO, "docs/research/pdf-backend-bakeoff/results/phase5_perf.json");
writeFileSync(outPath, JSON.stringify(results, null, 1));
console.log(`\nwrote ${outPath}`);
