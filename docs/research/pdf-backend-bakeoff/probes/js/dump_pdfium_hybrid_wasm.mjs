// Backend adapter: PDFium-WASM emitting the HYBRID contract (contract_hybrid.py).
//
// The portability half of the experiment. `backends/pdfium_hybrid.py` shows the indexed
// text-plus-geometry contract is available from native PDFium; this shows the same
// contract is available from the browser-shippable WASM build with no custom wrapper
// work -- every entry point it needs is already exported by @embedpdf/pdfium.
//
// Emits JSONL, one object per page:
//   {"page_number":1,"width":612,"height":792,
//    "chars":[[cp,generated,baseline,x0,x1,size,vbox,font,upright],...]}
// then a final {"summary":{...}} line. Field order matches contract_hybrid.CHAR_FIELDS.
//
// Run: node dump_pdfium_hybrid_wasm.mjs <pdf> [--limit N]

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { init } = require("@embedpdf/pdfium");

const args = process.argv.slice(2);
const pdfPath = args[0];
const limitIdx = args.indexOf("--limit");
const limit = limitIdx >= 0 ? parseInt(args[limitIdx + 1], 10) : null;

const pdfium = await init({ wasmBinary: readFileSync(require.resolve("@embedpdf/pdfium/pdfium.wasm")) });
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

const boxPtr = pdfium.pdfium.wasmExports.malloc(32);
const matPtr = pdfium.pdfium.wasmExports.malloc(24);
const orgPtr = pdfium.pdfium.wasmExports.malloc(16);
const namePtr = pdfium.pdfium.wasmExports.malloc(256);
const flagsPtr = pdfium.pdfium.wasmExports.malloc(4);

const SOFT_HYPHEN = 0x00ad;
const t0 = performance.now();
let charTotal = 0;
let generatedTotal = 0;
let hyphenTotal = 0;
let mapErrorTotal = 0;
let emptyFonts = 0;
let unnamed = 0;

for (let p = 0; p < total; p++) {
  const page = pdfium.FPDF_LoadPage(doc, p);
  const tp = pdfium.FPDFText_LoadPage(page);
  const width = pdfium.FPDF_GetPageWidthF(page);
  const height = pdfium.FPDF_GetPageHeightF(page);
  const n = pdfium.FPDFText_CountChars(tp);
  const fontCache = new Map();
  const chars = [];

  for (let i = 0; i < Math.max(n, 0); i++) {
    let cp = pdfium.FPDFText_GetUnicode(tp, i);
    const generated = pdfium.FPDFText_IsGenerated(tp, i) === 1;
    const hyphen = pdfium.FPDFText_IsHyphen(tp, i) === 1;
    if (pdfium.FPDFText_HasUnicodeMapError(tp, i) === 1) mapErrorTotal++;
    if (hyphen) {
      cp = SOFT_HYPHEN;
      hyphenTotal++;
    } else if (cp < 0x20 && !generated) {
      cp = 0xfffd;
      unnamed++;
    }

    const okOrigin = pdfium.FPDFText_GetCharOrigin(tp, i, orgPtr, orgPtr + 8);
    const originY = okOrigin ? pdfium.pdfium.getValue(orgPtr + 8, "double") : null;
    const originX = okOrigin ? pdfium.pdfium.getValue(orgPtr, "double") : null;

    if (generated) {
      // Same rule as the native adapter: a generated char keeps only its origin. Its
      // box, matrix, size and font name are placeholders and are emitted as null so
      // nothing downstream can consume them by accident.
      generatedTotal++;
      chars.push([cp, true, originY, originX, null, null, null, "", true]);
      continue;
    }

    const okBox = pdfium.FPDFText_GetCharBox(tp, i, boxPtr, boxPtr + 8, boxPtr + 16, boxPtr + 24);
    const okMat = pdfium.FPDFText_GetMatrix(tp, i, matPtr);
    if (!okBox || !okMat || !okOrigin) continue;
    const left = pdfium.pdfium.getValue(boxPtr, "double");
    const right = pdfium.pdfium.getValue(boxPtr + 8, "double");
    const bottom = pdfium.pdfium.getValue(boxPtr + 16, "double");
    const top = pdfium.pdfium.getValue(boxPtr + 24, "double");
    const a = pdfium.pdfium.getValue(matPtr, "float");
    const b = pdfium.pdfium.getValue(matPtr + 4, "float");
    const size = pdfium.FPDFText_GetFontSize(tp, i) * Math.hypot(a, b);

    const len = pdfium.FPDFText_GetFontInfo(tp, i, namePtr, 256, flagsPtr);
    let font = "";
    if (len > 0) {
      const key = `${namePtr}:${len}`;
      font = fontCache.get(key) ?? pdfium.pdfium.UTF8ToString(namePtr);
      fontCache.set(key, font);
    } else {
      emptyFonts++;
    }

    chars.push([cp, false, originY, left, right, r4(size), [bottom, top], font, Math.abs(b) < 1e-6 && a > 0]);
  }
  charTotal += chars.length;

  process.stdout.write(
    JSON.stringify({ page_number: p + 1, width: r4(width), height: r4(height), chars }) + "\n",
  );
  pdfium.FPDFText_ClosePage(tp);
  pdfium.FPDF_ClosePage(page);
}

process.stdout.write(
  JSON.stringify({
    summary: {
      backend: "pdfium-hybrid-wasm",
      pages: total,
      pages_total: nPages,
      chars: charTotal,
      generated_chars: generatedTotal,
      hyphen_chars: hyphenTotal,
      unicode_map_errors: mapErrorTotal,
      unnamed_ink: unnamed,
      empty_font_names: emptyFonts,
      extract_ms: Math.round(performance.now() - t0),
    },
  }) + "\n",
);

pdfium.FPDF_CloseDocument(doc);

function r4(x) {
  return Math.round(x * 10000) / 10000;
}
