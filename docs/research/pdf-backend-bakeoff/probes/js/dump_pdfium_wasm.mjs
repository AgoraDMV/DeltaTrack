// Backend adapter: PDFium-WASM (@embedpdf/pdfium, MIT wrapper around BSD-3 PDFium).
//
// Emits the neutral PdfPage contract as JSONL on stdout, one JSON object per page:
//   {"page_number":1,"width":612.0,"height":792.0,"glyphs":[[cp,x0,y0,x1,y1,baseline,size,font],...]}
// followed by a final {"summary":{...}} line.
//
// Phase 0 gate 1 for this backend is simply that it runs: the four FFI entry points the
// glyph sidecar needs (FPDFText_CountChars / GetCharBox / GetMatrix / GetFontSize) are
// exported by the shipped .wasm, and this probe calls them for real rather than reading
// the symbol table.
//
// Run: node dump_pdfium_wasm.mjs <pdf> [--limit N]

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { init } = require("@embedpdf/pdfium");

const args = process.argv.slice(2);
const pdfPath = args[0];
const limitIdx = args.indexOf("--limit");
const limit = limitIdx >= 0 ? parseInt(args[limitIdx + 1], 10) : null;

const wasmPath = require.resolve("@embedpdf/pdfium/pdfium.wasm");
const wasmBinary = readFileSync(wasmPath);
const pdfium = await init({ wasmBinary });

pdfium.PDFiumExt_Init?.();

const data = new Uint8Array(readFileSync(pdfPath));
const dataPtr = pdfium.pdfium.wasmExports.malloc(data.length);
pdfium.pdfium.HEAPU8.set(data, dataPtr);
const doc = pdfium.FPDF_LoadMemDocument(dataPtr, data.length, "");
if (!doc) {
  console.error("FPDF_LoadMemDocument failed");
  process.exit(2);
}

const nPages = pdfium.FPDF_GetPageCount(doc);
const total = limit ? Math.min(limit, nPages) : nPages;

// Scratch buffers reused across every glyph: 4 doubles for the char box, 6 floats for
// the matrix, a font-name buffer and an int for the font flags.
const boxPtr = pdfium.pdfium.wasmExports.malloc(32);
const matPtr = pdfium.pdfium.wasmExports.malloc(24);
const namePtr = pdfium.pdfium.wasmExports.malloc(256);
const flagsPtr = pdfium.pdfium.wasmExports.malloc(4);

const t0 = performance.now();
let glyphTotal = 0;
let emptyFontNames = 0;
let undecodable = 0;
// Minimum box width (points) for a glyph to count as ink rather than a structural
// marker. PDFium's 0x0A/0x0D breaks measure exactly 0.0 wide; the narrowest real GPO
// glyph on this corpus (the soft hyphen) measures ~3.0.
const INK_WIDTH = 0.5;

for (let p = 0; p < total; p++) {
  const page = pdfium.FPDF_LoadPage(doc, p);
  const textPage = pdfium.FPDFText_LoadPage(page);
  const width = pdfium.FPDF_GetPageWidthF(page);
  const height = pdfium.FPDF_GetPageHeightF(page);
  const n = pdfium.FPDFText_CountChars(textPage);

  const glyphs = [];
  // Font names repeat heavily within a page; cache by the (name, flags) the FFI returns
  // so a 3000-glyph page makes a handful of string decodes rather than 3000.
  const fontCache = new Map();

  for (let i = 0; i < Math.max(n, 0); i++) {
    let cp = pdfium.FPDFText_GetUnicode(textPage, i);

    if (!pdfium.FPDFText_GetCharBox(textPage, i, boxPtr, boxPtr + 8, boxPtr + 16, boxPtr + 24)) {
      continue;
    }
    const left = pdfium.pdfium.getValue(boxPtr, "double");
    const right = pdfium.pdfium.getValue(boxPtr + 8, "double");
    const bottom = pdfium.pdfium.getValue(boxPtr + 16, "double");
    const top = pdfium.pdfium.getValue(boxPtr + 24, "double");

    // Backend-neutral undecodable-glyph rule (see backends/pdfium_native.py): a control
    // codepoint with a zero-width box is a structural marker and is dropped; one with
    // real ink is a glyph this backend could not name, carried as U+FFFD so the loss is
    // visible to the scorer. Keyed on ink, never on a codepoint value.
    if (cp < 0x20) {
      if (right - left < INK_WIDTH) continue;
      cp = 0xfffd;
      undecodable++;
    }

    if (!pdfium.FPDFText_GetMatrix(textPage, i, matPtr)) continue;
    const a = pdfium.pdfium.getValue(matPtr, "float");
    const b = pdfium.pdfium.getValue(matPtr + 4, "float");
    // matrix[5] (f) is the text-object origin y, i.e. the TRUE baseline, shared by every
    // glyph on a printed line. The char-box bottom is not -- descenders sit below it and
    // would split one line into two clusters. See the note in backends/pdfium_native.py.
    const baseline = pdfium.pdfium.getValue(matPtr + 20, "float");
    // GPO defines fonts at size 1 and scales via the text matrix, so the true glyph
    // size is GetFontSize x sqrt(a^2 + b^2) -- the same rule the native sidecar uses.
    const fs = pdfium.FPDFText_GetFontSize(textPage, i);
    const size = fs * Math.sqrt(a * a + b * b);

    // Font identity: FPDFText_GetFontInfo writes the PostScript name into a buffer and
    // returns its byte length. A zero length is the "empty font name" case the source
    // inventory warns about, counted here per backend.
    const len = pdfium.FPDFText_GetFontInfo(textPage, i, namePtr, 256, flagsPtr);
    let font = "";
    if (len > 0) {
      const key = `${namePtr}:${len}`;
      font = fontCache.get(key) ?? pdfium.pdfium.UTF8ToString(namePtr);
      fontCache.set(key, font);
    } else {
      emptyFontNames++;
    }

    // upright: the text matrix carries no rotation/skew component.
    const upright = Math.abs(b) < 1e-6 && a > 0;
    glyphs.push([cp, left, bottom, right, top, round4(baseline), round4(size), font, upright]);
  }
  glyphTotal += glyphs.length;

  process.stdout.write(
    JSON.stringify({
      page_number: p + 1,
      width: round4(width),
      height: round4(height),
      glyphs,
    }) + "\n",
  );

  pdfium.FPDFText_ClosePage(textPage);
  pdfium.FPDF_ClosePage(page);
}

const elapsed = performance.now() - t0;
process.stdout.write(
  JSON.stringify({
    summary: {
      backend: "pdfium-wasm",
      pages: total,
      pages_total: nPages,
      glyphs: glyphTotal,
      empty_font_names: emptyFontNames,
      undecodable_glyphs: undecodable,
      extract_ms: Math.round(elapsed),
    },
  }) + "\n",
);

pdfium.FPDF_CloseDocument(doc);

function round4(x) {
  return Math.round(x * 10000) / 10000;
}
