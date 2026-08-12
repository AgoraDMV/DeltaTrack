// H2 -- does PDF.js expose per-character origin AND advance anywhere, or only per item?
//
// Phase 2's g03 answered "no" from `getTextContent()`, whose items average ~13 characters.
// That is the API the browser channel would actually use, but it is not the only one, and
// concluding "unsupported" from the convenient API is the same false-negative shape that
// nearly killed pdfminer and PyMuPDF in g03. So the lower-level path is tested too.
//
//   getTextContent()    item.transform[4] is an ITEM origin; item.width is the ITEM width.
//   getOperatorList()   OPS.showText carries an ARRAY of glyph objects. Each glyph has a
//                       `width` in 1/1000 text-space units -- a genuine per-character font
//                       advance. It carries NO position: numbers interleaved in the array
//                       are TJ adjustments, and the pen origin exists only inside PDF.js's
//                       own text-state machine, which the API does not expose.
//
// The extended contract needs BOTH facts per character. This probe reports each separately
// so the verdict names which one is missing rather than saying "PDF.js fails".
//
// Run: NODE_PATH=../../probes/js/node_modules node h02_pdfjs_percharacter.mjs <pdf> <page>

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

// Same resolution route as phase 2's g02: NODE_PATH is honoured by createRequire but not
// by a bare ESM specifier, so the package is resolved through require and then imported
// by file URL. This keeps the phase-1 probes/js tree unmodified.
const require = createRequire(import.meta.url);
const pdfjs = await import(pathToFileURL(require.resolve("pdfjs-dist/legacy/build/pdf.mjs")).href);

const file = process.argv[2];
const pageNo = parseInt(process.argv[3] ?? "1", 10);

const doc = await pdfjs.getDocument({ data: new Uint8Array(readFileSync(file)) }).promise;
const page = await doc.getPage(pageNo);

// ---- the API the browser channel would use -------------------------------------------
const tc = await page.getTextContent();
let chars = 0;
for (const it of tc.items) chars += (it.str || "").length;
const textContent = {
  items: tc.items.length,
  chars,
  chars_per_item: +(chars / Math.max(tc.items.length, 1)).toFixed(1),
  per_item_origin: tc.items.every((i) => Array.isArray(i.transform)),
  per_item_width: tc.items.every((i) => typeof i.width === "number"),
  per_character_origin: false,
  per_character_advance: false,
};

// ---- the lower-level path ------------------------------------------------------------
const ops = await page.getOperatorList();
const SHOW = pdfjs.OPS.showText;
let showTextOps = 0;
let glyphObjects = 0;
let glyphsWithWidth = 0;
let glyphsWithAnyPositionField = 0;
const positionFieldNames = new Set();
const sampleGlyphKeys = new Set();
const sampleWidths = [];

for (let i = 0; i < ops.fnArray.length; i++) {
  if (ops.fnArray[i] !== SHOW) continue;
  showTextOps++;
  const arr = ops.argsArray[i][0];
  if (!Array.isArray(arr)) continue;
  for (const g of arr) {
    if (typeof g === "number") continue; // a TJ adjustment, not a glyph
    glyphObjects++;
    for (const k of Object.keys(g)) sampleGlyphKeys.add(k);
    if (typeof g.width === "number") {
      glyphsWithWidth++;
      if (sampleWidths.length < 8) sampleWidths.push({ u: g.unicode, width: g.width });
    }
    // Any field that could carry a pen position. Named explicitly so the absence is a
    // measured absence and not "I did not look".
    for (const k of ["x", "y", "origin", "transform", "matrix", "position", "pos"]) {
      if (k in g) {
        glyphsWithAnyPositionField++;
        positionFieldNames.add(k);
        break;
      }
    }
  }
}

// How much machinery would a consumer have to own to recover the pen origin itself? Count
// the text-state operators it would have to interpret, so "reimplement text showing" is a
// measured statement and not a rhetorical one.
const STATE_OPS = [
  "setTextMatrix",
  "moveText",
  "nextLine",
  "moveTextWithLeading",
  "setCharSpacing",
  "setWordSpacing",
  "setHScale",
  "setLeading",
  "setLeadingMoveText",
  "setFont",
  "setTextRise",
  "beginText",
  "endText",
];
const stateOpCounts = {};
for (const name of STATE_OPS) {
  const code = pdfjs.OPS[name];
  if (code === undefined) continue;
  const n = ops.fnArray.reduce((acc, f) => acc + (f === code ? 1 : 0), 0);
  if (n) stateOpCounts[name] = n;
}

const operatorList = {
  showText_ops: showTextOps,
  text_state_ops_a_consumer_would_have_to_interpret: stateOpCounts,
  glyph_objects: glyphObjects,
  glyphs_with_a_width: glyphsWithWidth,
  width_coverage: glyphObjects ? +(glyphsWithWidth / glyphObjects).toFixed(4) : null,
  glyph_object_keys: [...sampleGlyphKeys].sort(),
  glyphs_with_any_position_field: glyphsWithAnyPositionField,
  position_field_names_found: [...positionFieldNames],
  sample_widths: sampleWidths,
};

// A negative control on the negative result: if the width field were absent too, the
// verdict would be "no per-character facts at all", which is a different claim. Assert
// which of the two facts is actually present so the finding cannot drift.
const verdict = {
  per_character_advance_available:
    operatorList.glyphs_with_a_width > 0 && operatorList.width_coverage > 0.99,
  per_character_origin_available: operatorList.glyphs_with_any_position_field > 0,
  extended_contract_emittable: false,
  why: null,
};
verdict.extended_contract_emittable =
  verdict.per_character_advance_available && verdict.per_character_origin_available;
verdict.why = verdict.extended_contract_emittable
  ? "both facts available"
  : verdict.per_character_advance_available
    ? "advance is available per character via getOperatorList; PEN ORIGIN is not exposed by any API -- it lives only inside PDF.js's text-state machine, so recovering it means reimplementing PDF text showing (Tm/Td/TJ/Tc/Tw/Tz/Tf) outside the library"
    : "neither fact is available per character";

console.log(JSON.stringify({ pdf: file, page: pageNo, textContent, operatorList, verdict }, null, 1));
