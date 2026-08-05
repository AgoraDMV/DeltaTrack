/* What granularity of glyph geometry does PDF.js actually expose?
 *
 * DeltaTrack's PDFium path (parsers/pdf_text.py::_page_glyph_sizes) builds
 * (bottom, left, right, codepoint, size) PER CHARACTER, then clusters by baseline.
 * ADR 0003 measured TEXT-LINE parity, not glyph-geometry parity. This probes
 * whether the geometry the heading-level recovery (ADR 0012) depends on is
 * reachable from PDF.js at all, and at what granularity.
 */
import * as pdfjsLib from "pdfjs-dist/legacy/build/pdf.mjs";
import fs from "node:fs";

const PDF = process.argv[2];
const data = new Uint8Array(fs.readFileSync(PDF));

const t0 = performance.now();
const doc = await pdfjsLib.getDocument({ data, useSystemFonts: false, standardFontDataUrl: "node_modules/pdfjs-dist/standard_fonts/" }).promise;
const tLoad = performance.now() - t0;
console.log(`PDF: ${PDF.split("/").pop()}  pages=${doc.numPages}  load=${tLoad.toFixed(0)}ms`);

const tX = performance.now();
let totalItems = 0, totalChars = 0;
const page = await doc.getPage(3);
const tc = await page.getTextContent();
for (const it of tc.items) { totalItems++; totalChars += (it.str || "").length; }

console.log(`\npage 3: ${totalItems} text items covering ${totalChars} chars`);
console.log(`  -> mean chars per item: ${(totalChars / totalItems).toFixed(2)}`);
console.log("\nFirst 6 items, full shape:");
for (const it of tc.items.slice(0, 6)) {
  console.log("  " + JSON.stringify({
    str: it.str, dir: it.dir, width: it.width, height: it.height,
    transform: it.transform ? it.transform.map((n) => +n.toFixed(2)) : null,
    fontName: it.fontName, hasEOL: it.hasEOL,
  }));
}
const keys = new Set();
for (const it of tc.items) Object.keys(it).forEach((k) => keys.add(k));
console.log("\nAll keys present on text items:", [...keys].join(", "));
console.log("Per-character box available directly?", [...keys].some((k) => /charbox|chars|glyphs/i.test(k)) ? "YES" : "NO");

// Time a full-document text extraction, the realistic browser cost.
const tAll = performance.now();
let lines = 0;
for (let p = 1; p <= doc.numPages; p++) {
  const pg = await doc.getPage(p);
  const c = await pg.getTextContent();
  lines += c.items.filter((i) => i.hasEOL).length;
}
console.log(`\nfull-document getTextContent: ${(performance.now() - tAll).toFixed(0)} ms for ${doc.numPages} pages (${lines} EOL-marked items)`);
