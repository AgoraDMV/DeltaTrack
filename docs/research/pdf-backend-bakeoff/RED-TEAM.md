# Red team: an adversarial audit of this spike's own conclusion

Run 2026-08-05, immediately after [`RESULTS.md`](RESULTS.md) was written, on the
instruction to **assume the headline conclusion is wrong and try to reject it**. Nothing
here is a defence of the result; where the result survived a test, the test is reported
with the same weight as the ones it failed.

**Outcome: the headline did not survive as written.** "PDFium-WASM is the best browser
backend" is not supported. "PDFium-WASM is the only drop-in replacement for the incumbent"
is. `RESULTS.md` has been corrected accordingly.

Probes: [`probes/redteam_ablation.py`](probes/redteam_ablation.py),
[`probes/redteam_unguarded.py`](probes/redteam_unguarded.py),
[`probes/redteam_validate_amounts.py`](probes/redteam_validate_amounts.py),
[`probes/redteam_egress2.py`](probes/redteam_egress2.py),
[`probes/vectors2.js`](probes/vectors2.js).

---

## Classification summary

| # | Finding | Class |
|---|---|---|
| 1 | T4, the load-bearing metric, uses PDFium as its own reference | **Invalidates** the "best backend" framing |
| 2 | `repaired` mode lifts only PDFium (+0.0415); without it PDFium ranks below all three permissive challengers | **Invalidates** the quality ranking |
| 3 | Speculation Rules and `window.open` defeat the published CSP | **Invalidates** the zero-egress claim as written |
| 4 | `_SPACE_FACTOR = 0.25` is load-bearing only for PDFium | **Weakens** |
| 5 | Corpus is effectively one typesetting class, not 52 documents' worth of diversity | **Weakens** generalization |
| 6 | Breadcrumb agreement scored against PDFium; pdfminer beats PDFium on an independent oracle | **Weakens** |
| 7 | `@embedpdf/pdfium` provenance: source path missing, licence disagreement, single maintainer, fork | **Requires follow-up** |
| 8 | Population narrowed 52→42 and 15→13 after seeing results | **No issue** — tested, PDFium-WASM is 15/15 unguarded |
| 9 | Shared data / cache / fallback between the two PDFium paths | **No issue** — different builds, differing glyph streams, no caching |
| 10 | Published tables mis-transcribed from raw results | **No issue** — recomputed independently, exact match |
| 11 | Post-hoc `align_to_body` step favouring a backend | **No issue** — uniform +0.089, ranking unchanged |
| 12 | Reported amounts not actually present in the source PDFs | **No issue** — 43/43 verified against an independent extractor |

---

## 1. The load-bearing metric could not rank the winner

`T4` compares each backend's canonical diff against **native PDFium's**. PDFium-WASM is
the same algorithm from a different build, so a perfect score is close to expected. T4 was
also an **addition to the spec**, introduced mid-spike, and the original conclusion rested
on it almost entirely.

Re-ranking on the two references with no PDFium in them — token F1 against the XML body,
and anchor labels against the XML tree:

| Backend | text F1 vs XML | heading F1 vs XML | rank |
|---|---|---|---|
| pdfminer | 0.9309 | **0.6253** | **1** |
| pymupdf *(ceiling)* | 0.9305 | **0.6253** | 2 |
| pdfium-native | 0.9310 | 0.5864 | 3 |
| **pdfium-wasm** | 0.9310 | 0.5864 | **4** |
| pdfjs | 0.9305 | 0.4058 | 5 |
| pypdf | 0.9176 | 0.4010 | 6 |

**PDFium-WASM never ranked first in any of eight ablations.**

### A false reversal this reviewer fell for, recorded as a caution

An intermediate version of the heading oracle compared **level-by-level** — PDF `account`
anchors against XML `account` nodes. That produced an apparent reversal: PDFium looked
like it over-detected accounts 46-to-27 with 23 spurious, and PDF.js looked more precise.

It was wrong. The two pipelines **assign different level names to the same objects**: the
XML's `agency` level holds `Military construction, air force`, which the PDF calls an
`account`. Comparing level-agnostically (account + agency + heading on both sides)
reverses the reversal — PDFium F1 0.732, PDF.js 0.506. The original PDF.js finding stands.
Trap 1 in the spec warns about exactly this and it still caught a reviewer looking for a
reason to reject.

## 2. `repaired` mode exists to rescue PDFium

PDFium's glyph API returns `0x02` for the GPO soft hyphen — 83,758 glyphs across the
corpus. The `repaired` rule reads a line-final unnamed glyph as a hyphen. Keying it on
position rather than codepoint made it *available* to every backend; it is *useful* to
only one.

| Mode | pdfium | pdfminer | pymupdf | pdfjs | pypdf |
|---|---|---|---|---|---|
| repaired (published default) | 0.9310 | 0.9309 | 0.9305 | 0.9305 | 0.9176 |
| strict | **0.8895** | 0.9309 | 0.9305 | 0.9305 | 0.9176 |

Strict-mode ranking on the full 52: **pdfminer 0.9131, pymupdf 0.9126, pdfjs 0.9126,
pdfium 0.8781, pypdf 0.8729.** Every headline number in the first draft used `repaired`.

## 3. Two mechanisms defeat the published CSP

19 further vectors, control leaking 14 of 19. Under the exact published policy,
**Speculation Rules prefetch** and **`window.open`** reached the server carrying the
marker.

Removing `'unsafe-inline'` from `script-src` blocks Speculation Rules — verified
**non-vacuously**: a first attempt showed 0 bypasses but `completed=False, 0 vectors`,
i.e. the policy had blocked the harness's own inline bootstrap. Re-run with an external
bootstrap, all 19 vectors execute and the bypass is gone.

`window.open` is outside CSP. The first draft's claim that top-level navigation is
"user-visible, because the page would disappear" is **false** for it.

## 4. A PDFium-tuned constant inside the "neutral" layer

`_SPACE_FACTOR = 0.25` was inherited from `parsers/pdf_text.py`, which was tuned against
PDFium. Perturbing it to 0.4:

| Backend | heading F1 @ 0.25 | @ 0.40 |
|---|---|---|
| pdfium-native / pdfium-wasm | 0.5864 | **0.2057** |
| pdfminer | 0.6253 | 0.3088 |
| pymupdf | 0.6253 | **0.6253** |
| pdfjs | 0.4058 | **0.4058** |
| pypdf | 0.4010 | **0.4010** |

PDFium is the most sensitive backend to a constant chosen for PDFium. The other layer
additions are rank-neutral, and the `upright` flag in fact helps the challengers: removing
it costs pdfminer and PyMuPDF text F1 while leaving PDFium unchanged.

## 8. The population narrowing did not manufacture the parity

Production genuinely declines both excluded pairs, verified through the real
`compare_pdfs` entry point with an accepted control. Scored anyway with the guard
disabled:

| Pair | pdfium-wasm identical amounts / changes |
|---|---|
| 115-hr-5895/4→5 | **True / True** |
| 118-hr-4366/5→6 | **True / True** |

So PDFium-WASM is **15/15 unguarded and 13/13 guarded**. The exclusion changed pypdf's
gate 2/3 verdict, not PDFium-WASM's result.

## 9. No shared data, cache, or fallback

| | native | WASM |
|---|---|---|
| Binary | `libpdfium.dylib`, 7.15 MB | `pdfium.wasm`, 4.63 MB |
| Version | PDFium **152.0.7947.0**, `pdfium-binaries` | `embedpdf/runtime` fork @ `608d50ef` |
| Process | in-process ctypes | separate Node subprocess over JSONL |

Their **glyph streams genuinely differ** — native emits ~18 more space glyphs per page —
which is positive proof of independent computation. No caching or memoization exists in
the harness. The derived geometry nonetheless converges, because the reconstruction
layer's gap fallback absorbs the missing space glyphs; that is worth knowing in both
directions, since a layer that absorbs input differences can also mask backend differences.

## 12. Reported amounts are really in the documents

43 sampled amount entries from PDFium-WASM's canonical diff, checked against **PyMuPDF's
own `get_text()`** — a different library, sharing nothing with the pipeline under test.
All 43 verified on the side claimed.

A first version of this check compared integer amounts (`194000000`) against text printing
`$194,000,000` and reported **0/43**. That is a check structurally incapable of matching,
and it looks identical to catastrophic failure. Recorded because it nearly became a
finding.

---

## What an independent reviewer should reproduce first

1. **`redteam_ablation.py`** — the independent-metric ranking. It is the result that
   changed the conclusion.
2. **`redteam_unguarded.py`** — the 15/15, which is what keeps the drop-in claim alive
   after the population narrowing is challenged.
3. **`redteam_egress2.py`** — the Speculation Rules bypass and the verified fix.

## The claim in `RESULTS.md` I am least confident in

Not the backend choice — the **Tier B conclusion**. `RESULTS.md` says Tier A passing
licenses "browser PDF architecture is viable on published GPO material". Given that the
accepted corpus is effectively **one typesetting class**, even that may be too broad:
what was really demonstrated is viability on *GPO-typeset appropriations bills from the
113th–119th Congress carrying margin line numbers*. Every word of that qualification is
load-bearing, and none of it was measured against a counterexample.
