# Spike specification: browser PDF backend bake-off + zero-egress proof

- Status: **specification only. Not yet run.** Written 2026-08-05 as the handoff for a
  fresh session.
- Predecessor: [`../staffer-delivery/README.md`](../staffer-delivery/README.md), which
  established that the XML pipeline runs byte-identically under Pyodide and left the
  PDF path as the open question.
- Prioritised **ahead of** the Windows-platform work and ahead of any delivery-channel
  ADR, because the PDF answer can invalidate the browser architecture entirely.

## Why this is the right next spike

The delivery spike found that DeltaTrack's engine runs unmodified in the browser and
emits byte-identical output, so the only thing standing between a staffer and a
no-install local tool is **PDF text extraction**. ADR 0002 chose PDFium on extraction
quality; ADR 0003 measured PDF.js text-line parity but not the per-glyph geometry that
ADR 0012's heading recovery depends on. Nobody has measured whether *any* browser-viable
backend produces an accurate **diff**.

The three outcomes the requester named, restated as decision consequences:

| Outcome | What it means |
|---|---|
| PyMuPDF works well in Pyodide | PDFium was making browser delivery harder than necessary |
| PyMuPDF wins but AGPL is disqualifying | Tells us exactly what a PDFium-WASM effort is worth |
| PDF.js matches or beats both | Best case: Apache-2.0, huge deployment history, no Python-native binary |
| None gives accurate diffs | We learn this **before** committing to browser architecture |

---

## Decide this before writing any code

**DeltaTrack is Apache-2.0. PyMuPDF is AGPL-3.0.** Those are one-way compatible: Apache
code can be absorbed into an AGPL work, not the reverse. Shipping PyMuPDF inside
DeltaTrack would push the **distributed combination** to AGPL-3.0 and change this
project's own licensing posture, for an audience (congressional offices, and BillTrax as
a downstream consumer per ADR 0005) where that is a live adoption question rather than a
formality. Artifex sells a commercial license, which is a cost and a procurement step.

This is not a tie-breaker to apply after scoring. It changes what the bake-off is *for*:

- **If AGPL is acceptable**, PyMuPDF is a candidate backend and can win outright.
- **If AGPL is disqualifying**, PyMuPDF is still worth running, but as a **ceiling
  reference**: it establishes the best score any backend could plausibly achieve, which
  is precisely what tells us whether a PDFium-WASM effort is worth funding. Label it
  that way in the results so nobody later reads a PyMuPDF win as a shippable
  recommendation.

**Answer this first, record the answer here, then start.** The rest of the design does
not change; only the interpretation of a PyMuPDF win does.

---

## The two methodological traps

These are the reasons a bake-off like this usually produces an unfalsifiable result.
Both must be closed in the design, not noticed afterwards.

### Trap 1: XML is not a drop-in reference for PDF text

Using XML as the reference instead of current PDFium output is the right call, and it
removes the circularity of grading challengers against the incumbent. But the two
documents are genuinely different artifacts for the same bill version. The PDF carries
GPO margin line numbers, page chrome, running heads, watermarks, soft-hyphen line
breaks, and typographic ligatures. The XML carries none of them, and encodes nesting
positionally (see [`docs/bill-structure.md`](../../bill-structure.md)).

Compare them naively and **every backend scores badly for reasons that have nothing to
do with the backend**, and the ranking becomes noise.

**Required:** define and freeze a normalization + alignment step *before* scoring, and
validate it by running it on the **current PDFium output**, which is known-good. If the
incumbent does not score near-ceiling under your normalization, the normalization is
wrong, not PDFium. That check is the calibration gate for the whole exercise, and it is
cheap.

### Trap 2: the XML-derived diff is not ground truth either

The terminal metric compares a PDF-derived diff against an XML-derived diff. A
disagreement has three possible causes, and the metric cannot distinguish them:

1. the PDF backend got it wrong,
2. the XML pipeline got it wrong,
3. the two documents genuinely differ.

**Required:** for every disputed change above a materiality threshold, adjudicate
against [ADR 0009](../../decisions/0009-validation-ground-truth.md)'s independently
authored committee reports, not against either pipeline. Report the terminal metric as
*agreement*, and report adjudicated *accuracy* separately for the disputed subset.
Do not present agreement as accuracy.

---

## Design: isolate the backend, not the pipeline

This is the single most important structural decision, and it makes the comparison
apples-to-apples.

The delivery spike established that `parsers/pdf_text.py` contains only **three**
PDFium-touching functions (`extract_clean_pages`, `_page_glyph_sizes`, `_char_box`); the
other ~15 (`normalize_raw`, `strip_page_chrome`, `rejoin_soft_hyphens`,
`normalize_glyphs`, `parse_lines`, `_cluster_baselines`, `_line_text`,
`_first_word_right`, `_attach_geometry`, …) are pure Python over already-extracted data.

**Every backend must feed the same pure cleaning layer.** Define one adapter contract:

```
backend(pdf_bytes) -> for each page:
    page_text : str
    glyphs    : sequence of (bottom, left, right, codepoint, size)
```

That tuple shape is exactly what `_page_glyph_sizes` produces today. Each backend
implements only that, and everything downstream is the existing, unmodified DeltaTrack
code.

If instead each backend gets its own cleaning path, you are comparing **pipelines**, not
backends, and a backend can win on a better-tuned cleaner while being worse at
extraction. Do not do that.

**Known granularity mismatch, already measured:** PDF.js exposes geometry at *text-item*
granularity (~13 chars/item, keys `str, dir, width, height, transform, fontName,
hasEOL`), with **no per-character box**, and `disableCombineTextItems` no longer changes
this in pdfjs-dist 6.x. The adapter must therefore synthesize per-character boxes by
distributing item width, or the pure layer must be shown tolerant of item-level input.
Which of those is chosen is itself a finding worth recording. Note also that naive item
joining loses inter-word spaces at font boundaries
(`Providedfurther,That…`), the same italic-to-roman artifact ADR 0003 recorded, so the
adapter needs a gap-based word joiner.

---

## Corpus and N

Counted from `tests/corpus/` on 2026-08-05. Reproduce with the snippet in
[Appendix: corpus census](#appendix-corpus-census).

| Metric | Unit | N |
|---|---|---|
| Per-document metrics (text, line numbers, headings, citations) | bill version with both PDF and XML | **52** across 30 bills |
| Terminal metric (PDF-derived diff vs XML-derived diff) | **consecutive** version pair with both formats on both sides | **15** across 8 bills |

The 15 pairs concentrate in `118-hr-4366` (5), `113-hr-3547` (3) and `115-hr-5895` (2).
**Report per-bill results, not just an aggregate**, or one bill dominates the headline
number. Parametrize over `tests/corpus_manifest.toml` rather than a hardcoded list, per
[ADR 0015](../../decisions/0015-corpus-test-fixtures.md) and the standing convention in
AGENTS.md that enumerated lists drift.

Include at least one **watermarked Senate document** (`tests/data/BILLS-118s4795rs.pdf`)
and the committee report (`tests/data/CRPT-118srpt198.pdf`), because ADR 0002 and ADR
0003 both record that watermark and table handling is where engines diverge most.

**Out of scope, and say so in the results:** draft and pre-introduction PDFs. ADR 0003
flags them as the untested, hardest case, and the corpus has none. This spike does not
close that gap, and a "PDF is solved" conclusion would be overclaiming.

---

## Phases, with kill-gates

Each phase has an exit condition that can end the spike early. The point is to avoid
spending a session on a backend that was already disqualified.

### Phase 0. Cheap gates and pre-registration (target: under an hour)

1. **PDFium-WASM FFI gate.** Does any credible PDFium WASM build expose
   `FPDFText_CountChars`, `FPDFText_GetCharBox`, `FPDFText_GetMatrix`,
   `FPDFText_GetFontSize`? If not, PDFium-WASM is out **before** any harness work, and
   the bake-off is two candidates.
2. **PyMuPDF-in-Pyodide gate.** `pymupdf` is in the Pyodide distribution (confirmed in
   the delivery spike). Load it and open a real bill PDF. If it fails, it is out.
3. **PDF.js headless gate.** Already demonstrated: 94-page bill, full-document
   `getTextContent()` in 154 ms.
4. **Pre-register the scoring.** Write the metrics, weights and pass thresholds into
   this document **before** seeing any results. A bake-off whose metrics are chosen
   after the fact is not a bake-off.
5. **Calibrate the reference** (Trap 1): run current PDFium through the scorer and
   confirm it lands near ceiling.

### Phase 1. Per-document scoring, native Python (N=52)

Score each backend through the shared adapter, on:

- **Text recovery** vs normalized XML.
- **GPO line-number recovery** — the anchor ADR 0002 exists to protect. Report exact
  recovery rate, not approximate text similarity.
- **Heading hierarchy** — the ADR 0012 / ADR 0014 leveled tree, with its
  conservation check.
- **Citations / breadcrumbs** — `breadcrumb_for` output agreement.

### Phase 2. Terminal metric (N=15)

`pdf_diff_to_canonical(...)` vs `xml_diff_to_canonical(...)` for the same pair. Both
already converge on the canonical JSON contract ([ADR 0006](../../decisions/0006-canonical-diff-contract.md)),
so this is a structured comparison, not a text one. Score change-set agreement
(precision/recall over changes), and separately over `amount_entries`, since money is
the highest-consequence field.

Adjudicate disputes per Trap 2. **A backend that wins Phase 1 and loses Phase 2 loses**,
because the diff is the product.

### Phase 3. Winner in Pyodide / browser

Run the winning backend in-browser, not merely in native Python. Reuse the harnesses in
[`../staffer-delivery/probes/`](../staffer-delivery/probes/). Confirm the browser result
matches the native result for that backend, ideally byte-identically, as the XML path
already does.

### Phase 4. Fully offline build + zero-egress proof

Produce an offline build (no CDN, no runtime package resolution; note that `micropip`
reached jsdelivr in the delivery spike, so wheels must be pre-bundled).

**This is a guardrail test, so the probe must be built to fail.** Asserting an absence
is the vacuous-pass case: a request counter that reads zero looks identical whether the
guard works or the counter is broken. Required, all three:

1. **Sever the network entirely** (Playwright `context.route("**", route.abort())` or
   offline mode) and confirm a full comparison still **succeeds**. This is the inert
   form: if the build needed the network, it fails closed rather than leaking.
2. **Instrument and count** every request at the CDP layer during a comparison, and
   assert zero.
3. **Known-bad control:** build a variant that deliberately makes one request (a beacon,
   a font, an analytics ping) and prove the harness **catches it**. Without this, the
   zero-egress claim is unfalsifiable and worth nothing.

Also record temp-file and persistence behaviour, since ADR 0005's safety contract is
about persistence and ADR 0011's is about transmission, and they are different axes.

### Phase 5. Performance and memory

Startup, comparison time and peak memory on the **largest** bills, in-browser. Compare
against the delivery spike's XML baselines (Pyodide boot ~1.2 s, engine import ~0.3 s,
Senate rewrite 842–905 ms). Include the largest appropriations bills, not only
convenient ones.

### Phase 6. Licensing and distribution memo

**Recorded separately from the technical score**, per the requester's instruction. For
the winner and the runner-up: license, obligations triggered by *distributing a WASM
binary*, whether AGPL §13's network-interaction clause is even engaged by a purely
client-side tool (arguably not, but distribution obligations still attach), commercial
licensing cost and procurement burden, and the effect on DeltaTrack's own Apache-2.0
posture and on BillTrax as a downstream consumer.

---

## Working rules for the session that runs this

- **Do not modify production code.** Same rule as the delivery spike. Backends go in an
  adapter layer under this directory's `probes/`; the shared pure layer is imported
  from `src/deltatrack` unchanged. If the spike shows `parsers/pdf_text.py` must be
  split, that is a **finding and a follow-up PR**, not part of the spike.
- **Work in a fresh worktree**, not in `delivery-spike`.
- **Frozen probes live in `docs/research/pdf-backend-bakeoff/probes/`**, which the
  existing `docs/research/**/probes` rule already excludes from lint.
- **Do not commit large binaries** (WASM runtimes, built bundles). Commit the builder.
- Report per-bill, and state N next to every aggregate.
- If a phase's result makes a later phase pointless, stop and say so.

---

## What a result looks like

The spike succeeds if it can complete these sentences with evidence:

1. "The best browser-viable PDF backend is ___, scoring ___ on diff agreement over 15
   pairs, adjudicated to ___ accuracy on the disputed subset."
2. "It runs in the browser at ___ startup and ___ per comparison on the largest bill."
3. "A full comparison makes zero network requests, and our harness is proven to detect a
   request when one is deliberately introduced."
4. "Its licensing implication for an Apache-2.0 project distributing a WASM binary is
   ___."
5. Or: "None of the candidates produces accurate PDF diffs, because ___", which is a
   successful outcome of this spike and redirects the delivery decision to a packaged
   executable for the PDF path.

---

## Appendix: corpus census

```python
from pathlib import Path
import re
for d in sorted(Path("tests/corpus").iterdir()):
    if not d.is_dir(): continue
    stems = {}
    for f in d.iterdir():
        m = re.match(r"(\d+)_([a-z-]+)\.(pdf|xml)$", f.name)
        if m: stems.setdefault(int(m.group(1)), set()).add(m.group(3))
    both = sorted(n for n, v in stems.items() if v == {"pdf", "xml"})
    adj = [(a, b) for a, b in zip(both, both[1:]) if b == a + 1]
    if both: print(d.name, len(both), "versions,", len(adj), "adjacent pairs")
```
