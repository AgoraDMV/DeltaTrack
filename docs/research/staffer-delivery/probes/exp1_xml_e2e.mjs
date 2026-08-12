/* Experiment 1b: run the FULL DeltaTrack XML comparison pipeline under Pyodide.
 *
 * Production code is NOT modified. Instead a stub `pypdfium2` is placed on
 * sys.path AHEAD of nothing (the real one is absent under WASM anyway). This is a
 * faithful proxy for the real adaptation -- splitting parsers/pdf_text.py into a
 * pure-text half and a PDFium-backed half -- because the XML path never CALLS any
 * PDFium function; it only fails at import time. If the stub is ever called, it
 * raises, so a silent wrong-answer is impossible.
 */
import { loadPyodide } from "pyodide";
import fs from "node:fs";

const ROOT = "/Users/williamhea/Documents/Code/civictech/appropriations_bills/.claude/worktrees/delivery-spike";
const SHIM = "/Users/williamhea/.claude/jobs/2d422c1f/tmp/pyodide-spike/shim";

// --- build the stub package on the host, then mount it read-only -------------
fs.mkdirSync(`${SHIM}/pypdfium2`, { recursive: true });
const TRIPWIRE = `
class _Tripwire:
    """Any actual use of PDFium under WASM must fail loudly, never silently."""
    def __init__(self, name): self._name = name
    def __call__(self, *a, **k):
        raise RuntimeError(f"PDFium call {self._name} reached under Pyodide -- not a pure-Python path")
    def __getattr__(self, attr): return _Tripwire(f"{self._name}.{attr}")

def __getattr__(name): return _Tripwire(name)
`;
fs.writeFileSync(`${SHIM}/pypdfium2/__init__.py`, TRIPWIRE);
fs.writeFileSync(`${SHIM}/pypdfium2/raw.py`, TRIPWIRE);

const t0 = performance.now();
const pyodide = await loadPyodide();
const tBoot = performance.now() - t0;

pyodide.mountNodeFS("/dt_src", `${ROOT}/src`);
pyodide.mountNodeFS("/dt_shim", SHIM);
pyodide.mountNodeFS("/dt_corpus", `${ROOT}/tests/corpus`);

const tImp0 = performance.now();
await pyodide.runPythonAsync(`
import sys
sys.path.insert(0, "/dt_src")
sys.path.insert(0, "/dt_shim")
from deltatrack.compare.xml import compare_xml, compare_xml_html
print("IMPORT OK: deltatrack.compare.xml")
`);
const tImport = performance.now() - tImp0;

// Re-run the FULL matrix, not only the ten that failed before. Reporting "17/17" while
// re-testing just the previously-failing ten would combine a fresh result with a
// remembered one and present the total as one run -- a claim outrunning its evidence.
const ALL = [
  "deltatrack", "deltatrack.similarity", "deltatrack.version_stems",
  "deltatrack.structure_tree", "deltatrack.bill_tree", "deltatrack.diff_bill",
  "deltatrack.formatters._text", "deltatrack.formatters.view_model",
  "deltatrack.formatters.text_serializer", "deltatrack.formatters.canonical",
  "deltatrack.formatters.diff_html", "deltatrack.compare.xml",
  "deltatrack.parsers.pdf_text", "deltatrack.parsers.pdf_anchors",
  "deltatrack.parsers.committee_report", "deltatrack.compare.pdf", "deltatrack.diff_pdf",
];
const PREVIOUSLY_FAILING = [
  "deltatrack.structure_tree", "deltatrack.bill_tree", "deltatrack.diff_bill",
  "deltatrack.formatters.text_serializer", "deltatrack.formatters.canonical",
  "deltatrack.compare.xml", "deltatrack.parsers.pdf_text", "deltatrack.parsers.pdf_anchors",
  "deltatrack.compare.pdf", "deltatrack.diff_pdf",
];
pyodide.globals.set("_all_mods", ALL.join(","));
const stillBroken = await pyodide.runPythonAsync(`
import importlib, json
bad = []
for m in _all_mods.split(","):
    try:
        importlib.import_module(m)
    except Exception as e:
        bad.append(f"{m}: {type(e).__name__}: {e}")
json.dumps(bad)
`);
const bad = JSON.parse(stillBroken);
const prevOk = PREVIOUSLY_FAILING.filter((m) => !bad.some((b) => b.startsWith(m + ":"))).length;
console.log(`\nPyodide boot: ${tBoot.toFixed(0)} ms | engine import: ${tImport.toFixed(0)} ms`);
console.log(
  `Full matrix re-run with the stub present: ${ALL.length - bad.length}/${ALL.length} import ` +
    `(of which ${prevOk}/${PREVIOUSLY_FAILING.length} previously failed on pypdfium2).`
);
if (bad.length) console.log("  still failing:", bad);

// --- real bill comparisons ---------------------------------------------------
const CASES = [
  ["118-hr-4366", "1_reported-in-house.xml", "2_engrossed-in-house.xml", "small: House-passed step"],
  ["118-hr-4366", "3_placed-on-calendar-senate.xml", "4_engrossed-amendment-senate.xml", "LARGE: Senate rewrite"],
  ["118-hr-4366", "5_engrossed-amendment-house.xml", "6_enrolled-bill.xml", "LARGE: 1.8MB vs 1.8MB enrolled"],
];

console.log("\nEND-TO-END XML COMPARISONS UNDER PYODIDE");
console.log("=".repeat(96));
for (const [bill, a, b, note] of CASES) {
  pyodide.globals.set("_p1", `/dt_corpus/${bill}/${a}`);
  pyodide.globals.set("_p2", `/dt_corpus/${bill}/${b}`);
  const out = await pyodide.runPythonAsync(`
import json, time
from pathlib import Path
b1 = Path(_p1).read_bytes(); b2 = Path(_p2).read_bytes()
t = time.perf_counter()
html = compare_xml_html(b1, b2, start_label="v1", end_label="v2")
el_html = time.perf_counter() - t
t = time.perf_counter()
canon = compare_xml(b1, b2, start_label="v1", end_label="v2")
el_json = time.perf_counter() - t
json.dumps({
  "in_mb": round((len(b1)+len(b2))/1e6, 2),
  "html_ms": round(el_html*1000), "json_ms": round(el_json*1000),
  "html_kb": round(len(html)/1024),
  "schema": canon.get("schema_version"),
  "changes": len(canon.get("changes", [])),
  "has_doctype": html.lstrip().lower().startswith("<!doctype html"),
  "embeds_json": "diff.json" in html or "application/json" in html,
})
`);
  const r = JSON.parse(out);
  console.log(`${note}`);
  console.log(`  input ${r.in_mb} MB | canonical JSON ${r.json_ms} ms | standalone HTML ${r.html_ms} ms`);
  console.log(`  schema v${r.schema} | ${r.changes} changes | report ${r.html_kb} KB | doctype:${r.has_doctype} embedded-json:${r.embeds_json}`);
}
console.log("=".repeat(96));
