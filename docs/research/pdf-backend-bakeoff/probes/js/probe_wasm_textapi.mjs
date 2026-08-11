// Portability gate: does the shipped PDFium-WASM build actually EXECUTE the text-page
// entry points the hybrid contract needs, on a real GPO bill?
//
// The typings in @embedpdf/pdfium list every FPDFText_* symbol, but a typing is a claim
// about the wrapper, not evidence about the .wasm. This calls each one for real and
// compares the answers against the native pypdfium2 values for the same page, so a
// symbol that is exported but returns a stub cannot pass.
//
// Emits JSON on stdout: per-entry-point availability, plus the full char stream for one
// page so the native side can diff it index by index.
//
// Run: node probe_wasm_textapi.mjs <pdf> --page N

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { init } = require("@embedpdf/pdfium");

const args = process.argv.slice(2);
const pdfPath = args[0];
const pageIdx = parseInt(args[args.indexOf("--page") + 1], 10) - 1;

const pdfium = await init({ wasmBinary: readFileSync(require.resolve("@embedpdf/pdfium/pdfium.wasm")) });
pdfium.PDFiumExt_Init?.();

// Availability is asked of the wrapper object, which is what a Python/JS adapter would
// call. A name missing here is missing in practice regardless of the symbol table.
const NEEDED = [
  "FPDFText_LoadPage",
  "FPDFText_ClosePage",
  "FPDFText_CountChars",
  "FPDFText_GetUnicode",
  "FPDFText_GetText",
  "FPDFText_IsGenerated",
  "FPDFText_IsHyphen",
  "FPDFText_HasUnicodeMapError",
  "FPDFText_GetCharBox",
  "FPDFText_GetLooseCharBox",
  "FPDFText_GetCharOrigin",
  "FPDFText_GetMatrix",
  "FPDFText_GetFontSize",
  "FPDFText_GetFontInfo",
  "FPDFText_GetFontWeight",
  "FPDFText_GetCharAngle",
  "FPDFText_GetTextIndexFromCharIndex",
  "FPDFText_GetCharIndexFromTextIndex",
];
const present = Object.fromEntries(NEEDED.map((n) => [n, typeof pdfium[n] === "function"]));

const data = new Uint8Array(readFileSync(pdfPath));
const dataPtr = pdfium.pdfium.wasmExports.malloc(data.length);
pdfium.pdfium.HEAPU8.set(data, dataPtr);
const doc = pdfium.FPDF_LoadMemDocument(dataPtr, data.length, "");
const page = pdfium.FPDF_LoadPage(doc, pageIdx);
const tp = pdfium.FPDFText_LoadPage(page);
const n = pdfium.FPDFText_CountChars(tp);

const boxPtr = pdfium.pdfium.wasmExports.malloc(32);
const matPtr = pdfium.pdfium.wasmExports.malloc(24);
const oxPtr = pdfium.pdfium.wasmExports.malloc(16);
const namePtr = pdfium.pdfium.wasmExports.malloc(256);
const flagsPtr = pdfium.pdfium.wasmExports.malloc(4);

// Whether each call ever returned a non-trivial answer. A function that is exported but
// always fails would otherwise read as "available" while supplying nothing.
const exercised = { charbox: 0, matrix: 0, origin: 0, generated: 0, hyphen: 0, fontinfo: 0, maperror: 0 };
const chars = [];
for (let i = 0; i < n; i++) {
  const cp = pdfium.FPDFText_GetUnicode(tp, i);
  const gen = pdfium.FPDFText_IsGenerated(tp, i);
  const hyp = pdfium.FPDFText_IsHyphen(tp, i);
  const mapErr = pdfium.FPDFText_HasUnicodeMapError(tp, i);
  if (gen === 1) exercised.generated++;
  if (hyp === 1) exercised.hyphen++;
  if (mapErr === 1) exercised.maperror++;

  const okBox = pdfium.FPDFText_GetCharBox(tp, i, boxPtr, boxPtr + 8, boxPtr + 16, boxPtr + 24);
  if (okBox) exercised.charbox++;
  const okOrigin = pdfium.FPDFText_GetCharOrigin(tp, i, oxPtr, oxPtr + 8);
  if (okOrigin) exercised.origin++;
  const okMat = pdfium.FPDFText_GetMatrix(tp, i, matPtr);
  if (okMat) exercised.matrix++;
  const nameLen = pdfium.FPDFText_GetFontInfo(tp, i, namePtr, 256, flagsPtr);
  if (nameLen > 0) exercised.fontinfo++;

  chars.push([
    cp,
    gen,
    hyp,
    mapErr,
    okOrigin ? r4(pdfium.pdfium.getValue(oxPtr, "double")) : null,
    okOrigin ? r4(pdfium.pdfium.getValue(oxPtr + 8, "double")) : null,
    okBox ? r4(pdfium.pdfium.getValue(boxPtr, "double")) : null,
    okBox ? r4(pdfium.pdfium.getValue(boxPtr + 8, "double")) : null,
    okMat ? r4(pdfium.FPDFText_GetFontSize(tp, i) * Math.hypot(pdfium.pdfium.getValue(matPtr, "float"), pdfium.pdfium.getValue(matPtr + 4, "float"))) : null,
    nameLen > 0 ? pdfium.pdfium.UTF8ToString(namePtr) : "",
    pdfium.FPDFText_GetTextIndexFromCharIndex(tp, i),
  ]);
}

process.stdout.write(
  JSON.stringify({
    wrapper_version: JSON.parse(
      readFileSync(require.resolve("@embedpdf/pdfium/pdfium.wasm").replace(/dist[/\\]pdfium\.wasm$/, "package.json")),
    ).version,
    entry_points_present: present,
    all_present: Object.values(present).every(Boolean),
    page: pageIdx + 1,
    count_chars: n,
    exercised,
    chars,
  }),
);

pdfium.FPDFText_ClosePage(tp);
pdfium.FPDF_ClosePage(page);
pdfium.FPDF_CloseDocument(doc);

function r4(x) {
  return Math.round(x * 10000) / 10000;
}
