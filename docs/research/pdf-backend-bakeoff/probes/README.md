# Bake-off probes

Frozen reproduction artifacts for [`../RESULTS.md`](../RESULTS.md) and
[`../RED-TEAM.md`](../RED-TEAM.md). Not maintained source: they exist to reproduce those
documents' numbers. Excluded from lint by the `docs/research/**/probes` rule in
`pyproject.toml`.

**Production code is not modified by any of these.** The engine is imported from
`src/deltatrack` unchanged. Where the browser path needs `pypdfium2` importable under
WASM, a stub is written into the Pyodide filesystem that **raises** on any real PDFium
call, so a silent fallback to the incumbent is impossible rather than merely unlikely.

## Setup

The spike's dependencies are **not** in `pyproject.toml`, deliberately: they are
benchmark-only and three of them (PyMuPDF especially) should never reach the product's
dependency set. Install them into the worktree venv explicitly.

```bash
uv pip install --python .venv/bin/python -r docs/research/pdf-backend-bakeoff/probes/requirements.txt
```

```bash
cd docs/research/pdf-backend-bakeoff/probes/js && npm install
```

`node_modules/`, `package-lock.json` and the generated `egress-fixtures/` are gitignored;
the WASM runtimes are not committed, per the spec's "commit the builder, not the binary"
rule. Node 22 and a Playwright Chromium (`.venv/bin/python -m playwright install chromium`)
are assumed.

**Versions the published numbers were produced with** — record these when re-running,
because several results are version-sensitive:

| Component | Version |
|---|---|
| pypdfium2 (incumbent) | 5.12.1, bundling PDFium **152.0.7947.0** |
| `@embedpdf/pdfium` | 2.15.0, engine from the `embedpdf/runtime` fork @ `608d50ef` |
| pdfjs-dist | 6.2.108 |
| pdfminer.six / pypdf / PyMuPDF | 20260107 / 6.14.2 / 1.28.0 |
| pyodide | 314.0.3 (Python 3.14) |
| Playwright / Chromium | 1.60.0 |

All measurements are macOS 15 / arm64. **Nothing was run on Windows.**

## Reproducing each published number

Run from the repo root. Long runs write incrementally, so they can be inspected mid-flight.

| # | Command | Produces | Wall time |
|---|---|---|---|
| 0 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/phase0_speed.py 25` | pdfminer-vs-incumbent speed gate | ~1 min |
| 0 | `node docs/research/pdf-backend-bakeoff/probes/js/phase0_pdfjs.mjs tests/corpus/118-hr-4366/1_reported-in-house.pdf` | PDF.js whole-document + font-resolution cost | ~2 s |
| 1 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_phase1.py --out docs/research/pdf-backend-bakeoff/results/phase1.json --cross-check-lcs` | `phase1.json` (52 docs × 6 backends) | **~25 min** |
| 1 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/report_phase1.py --results docs/research/pdf-backend-bakeoff/results/phase1.json` | the Phase 1 tables | seconds |
| 2 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_phase2.py --out docs/research/pdf-backend-bakeoff/results/phase2.json` | `phase2.json` (15 pairs × 6 × 2 modes) | **~60 min** |
| 2 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/report_phase2.py --results docs/research/pdf-backend-bakeoff/results/phase2.json` | T4 / T2 / per-bill tables | seconds |
| 3 | `node docs/research/pdf-backend-bakeoff/probes/js/phase3_pyodide.mjs tests/corpus/118-hr-4366/1_reported-in-house.pdf --pages 20` | `phase3_pyodide.json`, browser-vs-native parity | ~1 min |
| 4 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/phase4_egress.py --out docs/research/pdf-backend-bakeoff/results/phase4.json` | `phase4.json`, the 4-part egress proof | ~2 min |
| 4 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/phase4_webrtc.py --out docs/research/pdf-backend-bakeoff/results/phase4_webrtc.json` | WebRTC mitigation matrix | ~1 min |
| 5 | `node docs/research/pdf-backend-bakeoff/probes/js/phase5_perf.mjs --pages 60` | `phase5_perf.json`, 60-page sample | ~5 min |
| 5 | `node docs/research/pdf-backend-bakeoff/probes/js/phase5_fulldoc.mjs` | `phase5_fulldoc.json` — **the gate-9 decision** | ~3 min |
| B | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/score_tierb.py --out docs/research/pdf-backend-bakeoff/results/tierb.json` | `tierb.json`, 12 non-corpus documents | ~10 min |
| — | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/fill_results.py` | regenerates RESULTS.md's tables from raw JSON | seconds |

### Red-team probes

These back [`../RED-TEAM.md`](../RED-TEAM.md) and the audit section of `RESULTS.md`.

| Command | Produces |
|---|---|
| `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_ablation.py` | `redteam_ablation.json` — **the result that withdrew the headline**: 8 ablations × 6 backends on XML-referenced metrics only |
| `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_unguarded.py` | `redteam_unguarded.json` — the 2 declined pairs scored anyway (the 15/15) |
| `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_validate_amounts.py` | `redteam_amount_validation.json` — 43 amounts vs an independent extractor |
| `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_egress2.py` | `redteam_egress2.json` — 19 further vectors; finds the two policy bypasses |
| `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_csp_mitigation.py` | `redteam_csp_mitigation.json` — proves removing `'unsafe-inline'` closes Speculation Rules |

## Things that will bite a re-runner

- **Phase 1 and Phase 2 are the long poles** (~25 and ~60 min). Both write their JSON after
  every document/pair, so progress is inspectable and a killed run is not wasted.
- **Do not run a timing probe concurrently with anything else.** Phase 5's numbers were
  taken on an idle machine; running them alongside Phase 2 would silently inflate them.
- **`score_phase2.py` applies production's unnumbered-layout guard** and marks two pairs
  declined. That is deliberate — see the correction note in `RESULTS.md`. To see the
  unguarded numbers, use `redteam_unguarded.py`, not a modified `score_phase2.py`.
- **Egress probes bind 127.0.0.1:8973 over both TCP and UDP.** A stale `serve.py` from a
  killed run will make the next one look like it observed nothing.
- **The CSP mitigation probe deliberately includes a VOID variant** that runs zero vectors.
  That is not a bug: it demonstrates the false pass that an inline bootstrap produces under
  `script-src 'self'`, which is how the first version of this measurement went wrong.
- **Node backends stream JSONL over stdout.** A 1000-page bill is ~130 MB of JSON; the
  harness reads it page-by-page rather than buffering, and passes
  `--max-old-space-size=8192`.
- **`.venv/bin/python`, not `python`.** From a worktree, `uv sync` or `PYTHONPATH=$PWD/src`;
  never `uv pip install -e .`, which clobbers the shared venv.


## Reproducing the CONFIRMATORY run

Protocol: [`../PRE-REGISTRATION-CONFIRMATORY.md`](../PRE-REGISTRATION-CONFIRMATORY.md).
Results: [`../RESULTS-CONFIRMATORY.md`](../RESULTS-CONFIRMATORY.md). Every table in that
document is generated by `fill_confirmatory.py`; none is transcribed.

Run from the repo root. **Order matters only where noted.**

| # | Command | Produces | Wall time |
|---|---|---|---|
| 0 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/fetch_holdout.py` | **run this first**: restores the 88 holdout files from govinfo and verifies every byte against the frozen `holdout_membership.json`. Network | ~2 min |
| 0 | `.venv/bin/python docs/research/pdf-backend-bakeoff/probes/select_holdout.py` | the SELECTION procedure, which rewrites `holdout_membership.json`. Needs BILLSTATUS ZIPs in `$BAKEOFF_BILLSTATUS` and `$CLAUDE_JOB_DIR`. **Not the way to restore the corpus** — the membership is frozen and must not be regenerated; re-running is for auditing the draw only | ~10 min + fetch |
| 1 | `… probes/score_confirmatory.py --population p1 --out …/results/confirm_p1.json` | Concern B raw, 52 docs × 3 backends × 6 sabotages × 2 modes | **~75 min** |
| 1 | `… probes/score_confirmatory.py --population p2 --out …/results/confirm_p2.json` | same, 44 holdout docs | ~15 min |
| 2 | `… probes/report_confirmatory.py --results …/confirm_p1.json --mode strict` | Δ, cluster bootstrap, B0 rows, quoted-block stratum. Repeat with `--mode repaired` and for `p2` | seconds |
| 3 | `… probes/score_migration.py --population p1 --out …/results/migration_p1.json` | Concern A, 15 pairs | ~25 min |
| 3 | `… probes/score_migration.py --population p2 --out …/results/migration_p2.json` | Concern A, 32 holdout pairs | ~15 min |
| 4 | `… probes/confirm_egress.py` | per-vector control/policy matrix, 35 mechanisms | ~3 min |
| 4 | `… probes/confirm_isolation.py` | environment isolation, both controls | ~2 min |
| 5 | `… probes/confirm_sensitivity.py` | the mandatory parameter sweep | **~33 min** |
| 6 | `… probes/confirm_bundle.py` | Concern E, over-the-wire bytes. **Network** (PyPI + Pyodide CDN) | ~1 min |
| 7 | `… probes/confirm_perf.py` | Concern D. **Voids itself above load average 1.0** | ~5 min |
| 8 | `… probes/confirm_safe_failure.py` | P3 robustness + gate S-1 | ~5 min |
| 9 | `… probes/confirm_vs_production.py` | glyph layer vs production's text API | ~12 min |
| — | `… probes/fill_confirmatory.py` | regenerates every table in `RESULTS-CONFIRMATORY.md` | seconds |

### The holdout corpus is fetched, not committed

The 88 P2 holdout documents (16.4 MB) are **not in git**. `results/holdout_membership.json`
is, and it records the govinfo package id, sha256 and byte count of every one of them, so
the population is fully specified and hash-verifiable without the bytes. `fetch_holdout.py`
restores them and refuses to write any file whose sha256 does not match the frozen record;
`--verify-only` checks a tree without downloading. All 88 re-fetched byte-identical on
2026-08-07.

`score_confirmatory.py --population p2` and `score_migration.py --population p2` now **fail
loudly** if any holdout file is absent. They used to skip missing documents, which meant a
tree without the corpus scored zero documents, wrote a well-formed results file and exited
0 — a vacuous pass in the holdout arm specifically.

### What a reviewer should check first

1. **`confirm_vs_production.py`** — the result that reframed Concern A. Both PDFium builds
   produce 302 heading labels production does not; pdfminer produces 5.
2. **`report_confirmatory.py --mode repaired`** — the result that dissolved pdfminer's text
   lead into PDFium's soft-hyphen repair delta.
3. **`confirm_safe_failure.py`** — gate S-1's failure. Two different scanned pages compare
   as "0 changes".
4. **Commit order, not file timestamps**, for anything claiming to have been frozen before
   scoring: `holdout_membership.json` precedes every score file, and `gold_adjudicated.json`
   must precede any join to `gold_key.json`.

### Things that will bite a re-runner

- **`score_confirmatory.py` on P1 is the long pole** (~75 min; the omnibus bills run
  150–270 s each). It writes JSON after every document, so a killed run is not wasted.
- **`confirm_perf.py` measures NATIVE extraction, not in-browser**, which is a logged
  deviation from gate D-1. Its numbers are not comparable to the exploratory Pyodide figures.
- **The sabotage controls are scored as pseudo-backends** and must never be pooled with the
  candidates. `report_confirmatory.py` keeps them out of Δ; a hand-written query might not.
- **B2's primary stratum cannot discriminate on this corpus.** Every P1 document where the
  backends' heading recovery differs carries `<quoted-block>` and is excluded from it. Read
  the quoted-block stratum alongside it or the metric reads as agreement.


## Reproducing the HYBRID run

Results: [`../RESULTS-HYBRID.md`](../RESULTS-HYBRID.md), whose every table is generated by
`fill_hybrid.py`. This run asks which layer should own generic PDF text reconstruction, and
it introduces a second adapter contract (`contract_hybrid.py`) alongside `contract.py`.

Run from the repo root. **Order does not matter**; only `fill_hybrid.py` must run last.

| # | Command | Produces | Wall time |
|---|---|---|---|
| 1 | `… probes/probe_charstream.py tests/corpus/114-hr-2029/4_reported-in-senate.pdf --page 99 --grep "CEMETERY ADMIN"` | the per-index char dump; **read this first**, it is the whole mechanism | seconds |
| 2 | `… probes/probe_space_separability.py <pdfs…> --pages 30 --json-out …/results/probe_separability.json` | `probe_separability.json` — the result that says no `_SPACE_FACTOR` works | ~4 min / doc |
| 3 | `… probes/probe_failure_headings.py --out …/results/probe_failure_headings.json` | the four named headings on four paths | ~25 min |
| 4 | `… probes/probe_backend_spacing.py --out …/results/probe_backend_spacing.json` | which backends satisfy the contract, and how each marks a synthesised char | ~1 min |
| 5 | `… probes/probe_hybrid_signals.py <pdfs…> --limit 40 --out …/results/probe_hybrid_signals.json` | generated-char geometry, signal coverage, font-role separation | ~2 min |
| 6 | `node probes/js/probe_wasm_textapi.mjs <pdf> --page 99` | WASM entry-point availability, exercised not inspected | ~5 s |
| 7 | `… probes/probe_hybrid_portability.py <pdfs…> --limit 40 --out …/results/hybrid_portability.json` | native-vs-WASM, raw stream AND reconstructed pages | ~5 min |
| 8 | `… probes/score_hybrid.py --out …/results/hybrid_docs.json` | H1–H5 over 52 documents × 4 paths | **~90 min** |
| 9 | `… probes/score_hybrid.py --pairs --out …/results/hybrid_pairs.json` | H6, the canonical diff over 15 pairs | **~90 min** |
| — | `… probes/fill_hybrid.py` | regenerates every table in `RESULTS-HYBRID.md` | seconds |

### What a reviewer should check first

1. **`probe_backend_spacing.py`** — all four candidate backends' own text keeps the word
   space and none produces the joined form. The defect belongs to the seam, not to any
   engine. This is the result that reversed the portability assessment in `RESULTS-HYBRID.md`.
2. **`probe_space_separability.py`** — `separable: false` in every print class. Read this
   before considering any change to `_SPACE_FACTOR`.
3. **`probe_hybrid_signals.py`** — the three zero columns are the falsifiable form of
   "generated characters carry an origin and nothing else".

### Things that will bite a re-runner

- **`reconstruct_hybrid.cluster_lines` sorts by baseline to ASSIGN a character to a line
  and then restores engine order within it.** Do not simplify that to a single sort: origins
  on one printed line differ by float noise (measured at 0.003 pt between a heading's
  full-size initial and its small caps), which is enough to hoist the initial to the front
  of the line and render `MILITARY` as `M6 ILITARY`. The first version of this probe had
  that bug and it read as a PDFium reading-order failure on 2.2–7.3 % of lines.
- **An out-of-order diagnostic must ignore space characters.** PDFium places a space's box
  at the pen position, which can sit up to ~1 pt behind the preceding glyph's left edge.
  Counting those reports 63 % of lines as scrambled when none are.
- **Native and WASM PDFium do NOT emit the same character stream.** The WASM build omits
  the line-trailing space native keeps. `probe_hybrid_portability.py` classifies every
  divergence rather than checking that the count is small, and asserts on the reconstructed
  pages, which are identical.
- **`score_hybrid.py` runs `pdfminer` too**, which is the long pole on the omnibus bills.
  It writes JSON after every document, so a killed run is not wasted.
- **Nothing in this run is a timing measurement.** Several probes were executed
  concurrently with each other; no wall-clock figure here is comparable to Phase 5's.

### Added after the first HYBRID pass

Both of these exist because a claim in `RESULTS-HYBRID.md` was read off the code rather
than measured, and measuring it changed the answer.

| Command | Produces |
|---|---|
| `… probes/probe_normalize_raw.py --only-declined --out …/results/probe_normalize_raw.json` | **the result that falsified "normalize_raw retires in full"**: uppercase syllable breaks are left dangling on unnumbered layouts |
| `… probes/probe_normalize_raw.py --limit-docs 14 --out …/results/probe_normalize_raw_all.json` | the scope table showing the gap is confined to production-declined documents |

`probe_hybrid_signals.py` also gained **S4**, which compares the sidecar's VALUES against
production's rather than checking they exist. That is what found production's descender
defect: `_cluster_baselines` clusters on the character box bottom with a tolerance of
0.5 × median size, and on a 14 pt line carrying both open quotes and a descender the spread
is 8.81 pt against 7.0, so the descender lands on a line of its own and `first_word_right`
comes back one glyph short.

**A metric of this run's own was withdrawn.** `probe_normalize_raw`'s first fused-token
test paired tokens against the other rendering's whole-document bag. At ~100k tokens
"does some split of this token into two tokens present somewhere exist" is satisfiable by
coincidence, and it reported `pro` + `vided` as a fusion — production's `pro` was from
`a pro rata share` on another page. If you re-run this probe, do not reintroduce a
bag-membership test; the hyphen-carrying set difference it was replaced with cannot be
satisfied by chance.
