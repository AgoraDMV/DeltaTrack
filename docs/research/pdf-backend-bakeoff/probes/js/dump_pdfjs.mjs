// Backend adapter: PDF.js (Apache-2.0), emitting the neutral PdfPage contract as JSONL.
//
// PDF.js is the one candidate that cannot satisfy the contract directly. It exposes
// geometry at TEXT-ITEM granularity (~12-13 chars per item: str, dir, width, height,
// transform, fontName, hasEOL) with no per-character box, and disableCombineTextItems
// no longer changes that in pdfjs-dist 6.x. So this adapter SYNTHESIZES per-character
// boxes by distributing the item's measured width across its characters.
//
// Which of "synthesize boxes in the adapter" vs "make the pure layer tolerant of
// item-level input" gets chosen is itself a finding the spec asks for. Synthesis is
// chosen here because it keeps ONE neutral reconstruction layer for every backend; a
// tolerant pure layer would be a second code path that only PDF.js exercises, and the
// bake-off would then be comparing two pipelines again.
//
// Two known artifacts this handles:
//   - Font names: item.fontName is an opaque generated id (g_d0_f1). The real name only
//     resolves after getOperatorList() populates page.commonObjs, so that call is made
//     per page and its cost is reported separately.
//   - Inter-word spaces are lost at font boundaries (`Providedfurther,That`), the same
//     italic-to-roman artifact ADR 0003 recorded. Because the reconstruction layer
//     rebuilds spacing from x-gaps rather than from emitted space glyphs, the artifact
//     is handled downstream by geometry -- provided the synthesized boxes are accurate,
//     which is exactly what this bake-off measures.
//
// Run: node dump_pdfjs.mjs <pdf> [--limit N]

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const pdfjs = await import(require.resolve("pdfjs-dist/legacy/build/pdf.mjs"));

const args = process.argv.slice(2);
const pdfPath = args[0];
const limitIdx = args.indexOf("--limit");
const limit = limitIdx >= 0 ? parseInt(args[limitIdx + 1], 10) : null;

const data = new Uint8Array(readFileSync(pdfPath));
const doc = await pdfjs.getDocument({
  data,
  isEvalSupported: false,
  useSystemFonts: false,
  // No network at any point: fail rather than fetch standard fonts or cmaps.
  standardFontDataUrl: undefined,
  cMapUrl: undefined,
}).promise;

const total = limit ? Math.min(limit, doc.numPages) : doc.numPages;
let glyphTotal = 0;
let emptyFontNames = 0;
let tText = 0;
let tOps = 0;
const t0 = performance.now();

for (let p = 1; p <= total; p++) {
  const page = await doc.getPage(p);
  const viewport = page.getViewport({ scale: 1 });

  const tA = performance.now();
  const content = await page.getTextContent();
  tText += performance.now() - tA;

  // Font-name resolution requires the operator list to have run.
  const tB = performance.now();
  await page.getOperatorList();
  tOps += performance.now() - tB;

  const nameCache = new Map();
  const resolveFont = (id) => {
    if (!id) return "";
    if (nameCache.has(id)) return nameCache.get(id);
    let name = "";
    try {
      const obj = page.commonObjs.get(id);
      name = (obj && (obj.name || obj.loadedName)) || "";
    } catch {
      name = "";
    }
    // Subset tags (ABCDEF+Name) carry no role information; strip so role keying works.
    if (name.length > 7 && name[6] === "+") name = name.slice(7);
    nameCache.set(id, name);
    return name;
  };

  const glyphs = [];
  for (const it of content.items) {
    if (it.str === undefined || it.str.length === 0) continue;
    const tm = it.transform; // [a, b, c, d, e, f]
    const x = tm[4];
    const y = tm[5];
    // The item's rendered size is the vertical scale of the text matrix; item.height is
    // unreliable for rotated text, so derive from the matrix as the native path does.
    const size = Math.hypot(tm[2], tm[3]) || it.height || 0;
    const font = resolveFont(it.fontName);
    // upright: transform[1] is the vertical shear; zero means a horizontal baseline.
    const upright = Math.abs(tm[1]) < 1e-6 && tm[0] > 0;
    if (!font) emptyFontNames += it.str.length;

    // Distribute the item's measured width across its characters. Uniform distribution
    // is wrong for proportional fonts at the per-character level; what matters for the
    // reconstruction layer is (a) the line's baseline, which is exact, (b) the left edge
    // of the first character, which is exact, and (c) inter-ITEM gaps, which are exact.
    // Intra-item character boxes are approximations and are labelled as such.
    const w = it.width || 0;
    const per = it.str.length ? w / it.str.length : 0;
    for (let k = 0; k < it.str.length; k++) {
      const cp = it.str.codePointAt(k);
      if (cp === undefined || cp < 0x20) continue;
      const cx = x + k * per;
      glyphs.push([
        cp,
        round4(cx),
        round4(y),
        round4(cx + per),
        round4(y + size),
        round4(y),
        round4(size),
        font,
        upright,
      ]);
    }
  }
  glyphTotal += glyphs.length;

  process.stdout.write(
    JSON.stringify({
      page_number: p,
      width: round4(viewport.width),
      height: round4(viewport.height),
      glyphs,
    }) + "\n",
  );
  page.cleanup();
}

process.stdout.write(
  JSON.stringify({
    summary: {
      backend: "pdfjs",
      pages: total,
      pages_total: doc.numPages,
      glyphs: glyphTotal,
      empty_font_names: emptyFontNames,
      extract_ms: Math.round(performance.now() - t0),
      get_text_content_ms: Math.round(tText),
      get_operator_list_ms: Math.round(tOps),
      geometry_note: "per-item geometry; character boxes synthesized by width division",
    },
  }) + "\n",
);

function round4(x) {
  return Math.round(x * 10000) / 10000;
}
