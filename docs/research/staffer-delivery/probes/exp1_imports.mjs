/* Experiment 1a: which DeltaTrack engine modules import under Pyodide?
 *
 * Mounts the real src/deltatrack tree into the Pyodide filesystem and attempts
 * each module in dependency order, recording the exact failure for each.
 */
import { loadPyodide } from "pyodide";

const SRC = "/Users/williamhea/Documents/Code/civictech/appropriations_bills/.claude/worktrees/delivery-spike/src";

const MODULES = [
  "deltatrack",
  "deltatrack.similarity",
  "deltatrack.version_stems",
  "deltatrack.structure_tree",
  "deltatrack.bill_tree",
  "deltatrack.diff_bill",
  "deltatrack.formatters._text",
  "deltatrack.formatters.view_model",
  "deltatrack.formatters.text_serializer",
  "deltatrack.formatters.canonical",
  "deltatrack.formatters.diff_html",
  "deltatrack.compare.xml",
  "deltatrack.parsers.pdf_text",
  "deltatrack.parsers.pdf_anchors",
  "deltatrack.parsers.committee_report",
  "deltatrack.compare.pdf",
  "deltatrack.diff_pdf",
];

const t0 = performance.now();
const pyodide = await loadPyodide();
const tBoot = performance.now() - t0;

pyodide.mountNodeFS("/dt_src", SRC);
await pyodide.runPythonAsync(`
import sys
sys.path.insert(0, "/dt_src")
import platform
print("PYVER", sys.version.split()[0], platform.machine(), sys.platform)
`);

const results = [];
for (const mod of MODULES) {
  const t = performance.now();
  try {
    await pyodide.runPythonAsync(`import ${mod}`);
    results.push({ mod, ok: true, ms: +(performance.now() - t).toFixed(1), err: null });
  } catch (e) {
    // last non-empty line of the Python traceback
    const lines = String(e.message).trim().split("\n").filter((l) => l.trim());
    results.push({ mod, ok: false, ms: +(performance.now() - t).toFixed(1), err: lines[lines.length - 1] });
  }
}

console.log(`\nPyodide boot: ${tBoot.toFixed(0)} ms (cold, Node, local files)\n`);
console.log("MODULE IMPORT RESULTS");
console.log("=".repeat(88));
for (const r of results) {
  console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.mod.padEnd(38)} ${String(r.ms).padStart(8)} ms  ${r.err ?? ""}`);
}
const pass = results.filter((r) => r.ok).length;
console.log("=".repeat(88));
console.log(`${pass}/${results.length} engine modules import unchanged under Pyodide.`);
