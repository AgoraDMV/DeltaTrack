// G2 -- are the extended-glyph fields actually reachable in the BROWSER build?
//
// The extended-glyph design needs two facts the current glyph contract does not carry:
// the pen origin X, and the font advance width. The origin comes from
// FPDFText_GetCharOrigin, which the glyph backend already calls. The advance needs a
// three-call chain that the bake-off has never exercised in WASM:
//
//     FPDFText_GetTextObject(textPage, i)     -> FPDF_PAGEOBJECT   [Experimental]
//     FPDFTextObj_GetFont(obj)                -> FPDF_FONT         [Experimental]
//     FPDFFont_GetGlyphWidth(font, cp, sz, *) -> bool              [Experimental]
//
// `@embedpdf/pdfium` 2.15.0 DECLARES all three in dist/vendor/functions.d.ts. A declaration
// is not an execution: the whole point of the bake-off's Phase 0 gate was that an exported
// symbol can still be a stub, a wrong-arity binding, or a function whose pointer-out
// parameter never lands in the heap view the wrapper exposes. So each is called for real,
// on a GPO page, and the values are printed for comparison against the native run.
//
// Emits one JSON object on stdout:
//   {ok, exported:{...}, chars, withTextObject, withFont, withAdvance,
//    zeroAdvance, sample:[{cp, ox, size, emAdv}...]}
//
// Run from this directory, resolving the spike's node_modules WITHOUT copying anything
// into probes/ -- the phase-1 tree is preserved byte-for-byte:
//
//   NODE_PATH=../../probes/js/node_modules node g02_wasm_advance.mjs <pdf> [--page N]

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { init } = require("@embedpdf/pdfium");

const args = process.argv.slice(2);
const pdfPath = args[0];
const pageIdx = args.indexOf("--page") >= 0 ? parseInt(args[args.indexOf("--page") + 1], 10) - 1 : 0;

const pdfium = await init({ wasmBinary: readFileSync(require.resolve("@embedpdf/pdfium/pdfium.wasm")) });
pdfium.PDFiumExt_Init?.();

const NEEDED = ["FPDFText_GetTextObject", "FPDFTextObj_GetFont", "FPDFFont_GetGlyphWidth", "FPDFText_GetCharOrigin"];
const exported = {};
for (const n of NEEDED) exported[n] = typeof pdfium[n] === "function";

const data = new Uint8Array(readFileSync(pdfPath));
const dataPtr = pdfium.pdfium.wasmExports.malloc(data.length);
pdfium.pdfium.HEAPU8.set(data, dataPtr);
const doc = pdfium.FPDF_LoadMemDocument(dataPtr, data.length, "");
if (!doc) {
  console.log(JSON.stringify({ ok: false, error: "FPDF_LoadMemDocument failed", exported }));
  process.exit(2);
}

const page = pdfium.FPDF_LoadPage(doc, pageIdx);
const tp = pdfium.FPDFText_LoadPage(page);
const n = pdfium.FPDFText_CountChars(tp);

const orgPtr = pdfium.pdfium.wasmExports.malloc(16);
const wPtr = pdfium.pdfium.wasmExports.malloc(4);

let withTextObject = 0;
let withFont = 0;
let withAdvance = 0;
let zeroAdvance = 0;
const zeroCps = {};
const sample = [];
const seq = [];
// Cache keyed on the font pointer, exactly as the native probe does, so the two are
// measuring the same call pattern and the cost comparison stays honest.
const widthCache = new Map();

for (let i = 0; i < n; i++) {
  const cp = pdfium.FPDFText_GetUnicode(tp, i);
  pdfium.FPDFText_GetCharOrigin(tp, i, orgPtr, orgPtr + 8);
  const ox = pdfium.pdfium.HEAPF64[orgPtr / 8];
  const size = pdfium.FPDFText_GetFontSize(tp, i);

  const obj = pdfium.FPDFText_GetTextObject(tp, i);
  if (!obj) continue;
  withTextObject++;
  const font = pdfium.FPDFTextObj_GetFont(obj);
  if (!font) continue;
  withFont++;

  const key = font + ":" + cp;
  let emAdv = widthCache.get(key);
  if (emAdv === undefined) {
    // font_size = 1000 returns the raw 1/1000-em advance, matching the native probe.
    const ok = pdfium.FPDFFont_GetGlyphWidth(font, cp, 1000.0, wPtr);
    emAdv = ok ? pdfium.pdfium.HEAPF32[wPtr / 4] / 1000.0 : null;
    widthCache.set(key, emAdv);
  }
  if (emAdv !== null) {
    withAdvance++;
    if (emAdv === 0) {
      zeroAdvance++;
      zeroCps["0x" + cp.toString(16)] = (zeroCps["0x" + cp.toString(16)] || 0) + 1;
    }
  }
  if (sample.length < 12 && cp > 32) {
    sample.push({ cp, ch: String.fromCharCode(cp), ox: +ox.toFixed(3), size, emAdv });
  }
  // Full per-character [codepoint, advance] sequence, for the index-aligned comparison
  // against native in the findings. Keyed by codepoint alone it would collapse two fonts
  // on one page onto one value, which is what made the first native-vs-WASM comparison
  // report a false mismatch on '9'.
  seq.push([cp, emAdv]);
}

pdfium.FPDFText_ClosePage(tp);
pdfium.FPDF_ClosePage(page);
pdfium.FPDF_CloseDocument(doc);

console.log(
  JSON.stringify({
    ok: Object.values(exported).every(Boolean) && withAdvance > 0,
    exported,
    page: pageIdx + 1,
    chars: n,
    withTextObject,
    withFont,
    withAdvance,
    zeroAdvance,
    zeroAdvanceCodepoints: zeroCps,
    sample,
    seq,
  }),
);
