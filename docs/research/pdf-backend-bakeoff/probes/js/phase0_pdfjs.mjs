// Phase 0 gate 3: PDF.js whole-document cost, including the per-page getOperatorList()
// call that font-name resolution requires.
//
// The spec records 154 ms for a full-document getTextContent() on a 94-page bill and
// 64 ms for getOperatorList() on ONE page. The open question is what that per-page
// charge totals across a real 1000-page appropriations bill, because it is charged per
// page and does not appear in the getTextContent() figure.
//
// Run: node docs/research/pdf-backend-bakeoff/probes/js/phase0_pdfjs.mjs <pdf> [<pdf>...]

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const pdfjsPath = require.resolve("pdfjs-dist/legacy/build/pdf.mjs");
const pdfjs = await import(pdfjsPath);

async function measure(path) {
  const data = new Uint8Array(readFileSync(path));

  const tLoad0 = performance.now();
  const doc = await pdfjs.getDocument({
    data,
    // Fully offline: no standard-font or cmap fetching over the network.
    isEvalSupported: false,
    useSystemFonts: false,
  }).promise;
  const tLoad = performance.now() - tLoad0;

  let tText = 0;
  let tOps = 0;
  let items = 0;
  let chars = 0;
  let fontIds = new Set();
  let resolvedNames = new Set();
  let unresolved = 0;

  for (let p = 1; p <= doc.numPages; p++) {
    const page = await doc.getPage(p);

    const t0 = performance.now();
    const content = await page.getTextContent();
    tText += performance.now() - t0;

    for (const it of content.items) {
      if (it.str === undefined) continue;
      items++;
      chars += it.str.length;
      if (it.fontName) fontIds.add(it.fontName);
    }

    // Font-name resolution: commonObjs is only populated after the operator list runs.
    const t1 = performance.now();
    await page.getOperatorList();
    tOps += performance.now() - t1;

    for (const id of fontIds) {
      if (resolvedNames.has(id)) continue;
      try {
        const obj = page.commonObjs.get(id);
        if (obj && obj.name) resolvedNames.add(`${id} -> ${obj.name}`);
        else unresolved++;
      } catch {
        unresolved++;
      }
    }
    page.cleanup();
  }

  return {
    path,
    pages: doc.numPages,
    tLoad,
    tText,
    tOps,
    items,
    chars,
    charsPerItem: chars / items,
    fonts: [...resolvedNames].sort(),
    unresolved,
  };
}

for (const path of process.argv.slice(2)) {
  const r = await measure(path);
  console.log(
    `${r.path}\n` +
      `  pages=${r.pages} load=${r.tLoad.toFixed(0)}ms ` +
      `getTextContent=${r.tText.toFixed(0)}ms getOperatorList=${r.tOps.toFixed(0)}ms ` +
      `total=${(r.tLoad + r.tText + r.tOps).toFixed(0)}ms\n` +
      `  items=${r.items} chars=${r.chars} chars/item=${r.charsPerItem.toFixed(1)} ` +
      `unresolved_font_reads=${r.unresolved}\n` +
      `  fonts: ${r.fonts.join(", ")}`,
  );
}
