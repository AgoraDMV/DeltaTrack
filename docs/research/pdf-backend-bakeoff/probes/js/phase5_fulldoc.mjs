// Phase 5 gate-9 decision: measure the LARGEST bill at FULL document length.
//
// This backs the 37.9 s / 3.9 s / 4.6 s figures in RESULTS.md, and it exists as a file
// because the first version of this measurement was run from a scratch script that was
// then deleted -- leaving a load-bearing published number with no reproducible probe.
//
// Why full length rather than the 60-page sample phase5_perf.mjs takes: extrapolating
// that sample linearly put pdfminer at ~134 s, over the pre-registered 60 s ceiling, and
// would have disqualified it on gate 9. Measured whole, it is 37.9 s. Per-page cost is
// front-loaded (cover matter, font warm-up), so a linear projection from the head of a
// bill overstates the total by ~3.5x. Gate decisions are measured, not extrapolated.
//
// Run: node docs/research/pdf-backend-bakeoff/probes/js/phase5_fulldoc.mjs

import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const { loadPyodide } = require("pyodide");

const PROBES = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const REPO = path.resolve(PROBES, "../../../..");
const BILL = path.join(REPO, "tests/corpus/119-hr-1/1_reported-in-house.pdf");

const results = { bill: path.relative(REPO, BILL), backends: {} };

const pyodide = await loadPyodide({ stdout: () => {}, stderr: () => {} });
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
for (const f of ["pdfminer_backend.py", "pypdf_backend.py"]) {
  pyodide.FS.writeFile(`/dt/probes/backends/${f}`, readFileSync(path.join(PROBES, "backends", f)));
}
pyodide.FS.writeFile("/dt/bill.pdf", readFileSync(BILL));

await pyodide.runPythonAsync(`
import sys, os
sys.path.insert(0, "/dt/pkg"); sys.path.insert(0, "/dt/probes")
os.makedirs("/dt/pkg/pypdfium2", exist_ok=True)
# Tripwire: raises rather than returning a plausible value, so a silent fallback to
# PDFium is impossible in the browser path.
stub = "def __getattr__(n):\\n    raise RuntimeError('pypdfium2 called under Pyodide: run invalid')\\n"
open("/dt/pkg/pypdfium2/__init__.py","w").write(stub)
open("/dt/pkg/pypdfium2/raw.py","w").write(stub)
`);
await pyodide.loadPackage("micropip");
await pyodide.runPythonAsync(`import micropip\nawait micropip.install("pdfminer.six")`);

console.log(`FULL DOCUMENT, in Pyodide: ${results.bill}`);

const out = JSON.parse(
  await pyodide.runPythonAsync(`
import json, time
from pathlib import Path
import backends.pdfminer_backend as backend
from reconstruct import reconstruct
t0 = time.perf_counter(); raw, summary = backend.extract(Path("/dt/bill.pdf"), None)
t_ex = time.perf_counter() - t0
t0 = time.perf_counter(); pages, diag = reconstruct(raw, repaired=True)
t_rc = time.perf_counter() - t0
json.dumps({"pages": summary["pages"], "extract_s": round(t_ex, 1), "reconstruct_s": round(t_rc, 1)})
`),
);
results.backends.pdfminer = { ...out, total_s: +(out.extract_s + out.reconstruct_s).toFixed(1) };
console.log(
  `  pdfminer    ${out.pages}pp  extract=${out.extract_s}s  reconstruct=${out.reconstruct_s}s  ` +
    `TOTAL=${results.backends.pdfminer.total_s}s`,
);

const { execFileSync } = require("node:child_process");
for (const [name, script] of [
  ["pdfjs", "dump_pdfjs.mjs"],
  ["pdfium-wasm", "dump_pdfium_wasm.mjs"],
]) {
  const t0 = performance.now();
  const s = execFileSync("node", [path.join(PROBES, "js", script), BILL], {
    cwd: path.join(PROBES, "js"),
    maxBuffer: 2 ** 31 - 1,
    encoding: "utf8",
  });
  const sum = JSON.parse(s.slice(s.lastIndexOf("\n", s.length - 2) + 1)).summary;
  results.backends[name] = {
    pages: sum.pages,
    extract_s: +((performance.now() - t0) / 1000).toFixed(1),
    transfer_mb: Math.round(Buffer.byteLength(s) / 1048576),
  };
  console.log(
    `  ${name.padEnd(11)} ${sum.pages}pp  extract=${results.backends[name].extract_s}s  ` +
      `transfer=${results.backends[name].transfer_mb}MB`,
  );
}

const dest = path.join(REPO, "docs/research/pdf-backend-bakeoff/results/phase5_fulldoc.json");
writeFileSync(dest, JSON.stringify(results, null, 1));
console.log(`wrote ${dest}`);
