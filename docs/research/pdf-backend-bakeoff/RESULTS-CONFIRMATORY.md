# Results: confirmatory run

- Protocol: [`PRE-REGISTRATION-CONFIRMATORY.md`](PRE-REGISTRATION-CONFIRMATORY.md), frozen
  and amended **before execution**, commits `be07b71` and `37f6be8`.
- Harness corrections made before any score existed:
  [`results/HARNESS-VALIDATION.md`](results/HARNESS-VALIDATION.md).
  Deviations after the first score: [`results/DEVIATIONS.md`](results/DEVIATIONS.md).
- **This does not replace [`RESULTS.md`](RESULTS.md)**, which remains the record of the
  exploratory spike and its audit. Where this run contradicts it, both stand and the
  contradiction is named.

> **Every number here is macOS 15 / arm64.** Nothing was run on Windows, which is the
> platform the target user is on. Engine properties carry over; OS and security-stack
> properties do not.

> **A, B and C use different references and license different conclusions. They are never
> combined into a score, a table, or a verdict.** Substituting an A result for a B
> conclusion is what produced the withdrawn headline in the exploratory run.

---

# Concern A — production migration parity

**Question.** If we replace pypdfium2, does any output production currently returns to
users change? **Reference: today's native pypdfium2 through the neutral glyph layer.** This
section cannot support an accuracy conclusion.

> **Do not read this section alone.** Its reference is the *harness incumbent*, and
> [§ The finding that reframes Concern A](#the-finding-that-reframes-concern-a) shows that
> the harness incumbent itself differs from **production** on heading labels — 302 spurious
> and 280 missed across 33 documents, which PDFium-WASM reproduces exactly. "Safe to swap
> the backend" is not "safe to move to the glyph architecture".

## A.1 Replication corpus (P1, 15 pairs)

<!-- A_P1 -->

**Primary mode `repaired`. 13 production-accepted pairs are the migration gate; 2 production-declined pairs are diagnostics and decide nothing.**

| | pdfium-wasm | pdfminer |
|---|---|---|
| A1 amounts identical (13 accepted) | **13/13** | **13/13** |
| A2 changes identical (13 accepted) | **13/13** | 6/13 |
| A4 full text identical (13 accepted) | **13/13** | 4/13 |
| A5 line numbers identical (13 accepted) | **13/13** | **13/13** |
| A1 amounts identical (2 declined, diagnostic) | **2/2** | **2/2** |
| A2 changes identical (2 declined, diagnostic) | **2/2** | 0/2 |

**Evidential content.** 9 of the 13 accepted pairs carry any amount entries at all; the rest pass A1 vacuously (empty multiset on both sides) and are not evidence of amount parity in either direction. 13 carry any changes.

**B0 controls — each must FAIL its own gate, and can only do so where the gate has content.**

| control | gate | broke the gate | on content-bearing pairs | verdict |
|---|---|---|---|---|
| SA1 | A1 | 10/13 | 9/9 | **live** |
| SA2 | A2 | 11/13 | 11/13 | **UNPROVEN on 2 content-bearing pair(s)** |
| SA3 | A4 | 13/13 | 13/13 | **live** |

<!-- /A_P1 -->

## A.2 Holdout (P2)

<!-- A_P2 -->

**Primary mode `repaired`. 30 production-accepted pairs are the migration gate; 2 production-declined pairs are diagnostics and decide nothing.**

| | pdfium-wasm | pdfminer |
|---|---|---|
| A1 amounts identical (30 accepted) | **30/30** | 27/30 |
| A2 changes identical (30 accepted) | **30/30** | 16/30 |
| A4 full text identical (30 accepted) | **30/30** | 11/30 |
| A5 line numbers identical (30 accepted) | **30/30** | **30/30** |
| A1 amounts identical (2 declined, diagnostic) | **2/2** | **2/2** |
| A2 changes identical (2 declined, diagnostic) | **2/2** | 0/2 |

**Evidential content.** 3 of the 30 accepted pairs carry any amount entries at all; the rest pass A1 vacuously (empty multiset on both sides) and are not evidence of amount parity in either direction. 30 carry any changes.

**B0 controls — each must FAIL its own gate, and can only do so where the gate has content.**

| control | gate | broke the gate | on content-bearing pairs | verdict |
|---|---|---|---|---|
| SA1 | A1 | 12/30 | 3/3 | **live** |
| SA2 | A2 | 26/30 | 26/30 | **UNPROVEN on 4 content-bearing pair(s)** |
| SA3 | A4 | 26/30 | 26/30 | **UNPROVEN on 4 content-bearing pair(s)** |

<!-- /A_P2 -->


## A.3 How to read Concern A

**PDFium-WASM reproduces the incumbent exactly on 43 accepted pairs and 4 declined ones**,
across both populations, including bill classes no probe had seen: non-appropriations House
and Senate bills, a joint resolution, a watermarked Senate print, a chamber-crossing
amendment print. On the same pairs pdfminer matches amounts and line numbers but diverges on
change segmentation (agreeing on 22 of 43, diverging on 21) and full text (agreeing on 15 of 43, diverging on 28).

**This is evidence about migration risk and about nothing else.** Reproducing today's output
exactly says a swap changes nothing a staffer reads; it says nothing about whether either
backend reads the document correctly. That substitution is what produced the withdrawn
headline in the exploratory run.

**The amount-identity result is thinner than its 43/43 suggests, and the controls are what
exposed that.** A pair whose amount multiset is empty on both sides passes A1 vacuously.
Only **9 of 13** P1 pairs and **3 of 30** holdout pairs carry any amount entries at all — the
holdout's non-appropriations bills barely contain dollar figures. SA1 breaks A1 on **every one
of those 12**, so the gate is demonstrably live, but amount parity rests on **12 substantive
pairs**, not 43. The exploratory run's own "13/13 identical `amount_entries`" carried the same
three empty pairs and did not say so.

SA2 and SA3 are each unproven on some pairs and are marked rather than counted: on very small
change sets, deleting one printed line does not always alter the change-signature multiset,
and deleting one glyph from a cover page changes no text that survives chrome stripping.

---

# Concern B — independent document accuracy

**No metric here takes a PDFium-derived value as ground truth.** Primary mode is `strict`.
Replication and holdout are reported separately and never pooled.

## B.1 Replication corpus (P1) — controls

<!-- B_P1_B0 -->

**Every metric's own control, reported beside it. A Δ without its control row is not reviewable.**

| metric | control | Δ from sabotage | practical δ | verdict |
|---|---|---|---|---|
| B1 | S1 | +0.2390 | 0.01 | fires |
| B2 | S2b | +0.0535 | 0.02 | fires |
| B3a | S3 | +0.0464 | 0.005 | fires |
| B5 | S4 | +0.6106 | 0.01 | fires |
| B6 | S5 | +0.3221 | 0.02 | fires |

| separability | own metric | B2 | verdict |
|---|---|---|---|
| S4 | B5 +0.6106 | +0.1702 | **NOT SEPARABLE** |
| S5 | B6 +0.3221 | +0.0729 | **SEPARABLE** |

<!-- /B_P1_B0 -->

## B.2 Replication corpus (P1) — paired cluster bootstrap

<!-- B_P1_DELTA -->

Δ = score(pdfminer) − score(pdfium-wasm); positive favours pdfminer. 10,000 paired cluster resamples by bill, seed 20260805, `strict` mode.

| metric | pdfium-wasm | pdfminer | Δ | 95% CI | practical δ | verdict |
|---|---|---|---|---|---|---|
| B1 | 0.8711 | 0.9099 | +0.0422 | [+0.0380, +0.0454] | 0.01 | pdfminer LEADS |
| B2 | 0.5282 | 0.5282 | +0.0000 | [+0.0000, +0.0000] | 0.02 | identical on every document (not merely indistinguishable) |
| B3a | 1.0000 | 1.0000 | +0.0000 | [+0.0000, +0.0000] | 0.005 | identical on every document (not merely indistinguishable) |
| B5 | 0.7489 | 0.7513 | +0.0013 | [+0.0000, +0.0029] | 0.01 | indistinguishable |
| B6 | 0.4668 | 0.4668 | +0.0000 | [+0.0000, +0.0000] | 0.02 | identical on every document (not merely indistinguishable) |

<!-- /B_P1_DELTA -->

## B.3 Holdout (P2) — controls

<!-- B_P2_B0 -->

**Every metric's own control, reported beside it. A Δ without its control row is not reviewable.**

| metric | control | Δ from sabotage | practical δ | verdict |
|---|---|---|---|---|
| B1 | S1 | +0.1890 | 0.01 | fires |
| B2 | S2b | +0.0059 | 0.02 | **did not fire — metric VOID** |
| B3a | S3 | +0.0451 | 0.005 | fires |
| B5 | S4 | +0.2079 | 0.01 | fires |
| B6 | S5 | +0.1571 | 0.02 | fires |

| separability | own metric | B2 | verdict |
|---|---|---|---|
| S4 | B5 +0.2079 | +0.0112 | **SEPARABLE** |
| S5 | B6 +0.1571 | +0.0072 | **SEPARABLE** |

<!-- /B_P2_B0 -->

## B.4 Holdout (P2) — paired cluster bootstrap

<!-- B_P2_DELTA -->

Δ = score(pdfminer) − score(pdfium-wasm); positive favours pdfminer. 10,000 paired cluster resamples by bill, seed 20260805, `strict` mode.

| metric | pdfium-wasm | pdfminer | Δ | 95% CI | practical δ | verdict |
|---|---|---|---|---|---|---|
| B1 | 0.7549 | 0.8291 | +0.0638 | [+0.0346, +0.1183] | 0.01 | pdfminer LEADS |
| B2 | 0.0000 | 0.0000 | +0.0000 | [+0.0000, +0.0000] | 0.02 | VOID (control did not fire) |
| B3a | 1.0000 | 1.0000 | +0.0000 | [+0.0000, +0.0000] | 0.005 | identical on every document (not merely indistinguishable) |
| B5 | | | | | 0.01 | insufficient data |
| B6 | | | | | 0.02 | insufficient data |

<!-- /B_P2_DELTA -->


## B.5 How to read Concern B

**The mode decides the answer, and only one mode is shippable.**

| | strict | repaired (the mode a production adapter would ship) |
|---|---|---|
| P1 text (B1) | pdfminer leads +0.0422 | **indistinguishable**, 0.9098 vs 0.9099 |
| P2 holdout text (B1) | pdfminer leads +0.0638 | **indistinguishable**, +0.0001 |
| P1 structure (B2/B3a/B5/B6) | identical on every document | identical on every document |

pdfminer's strict-mode text lead is almost entirely accounted for by PDFium's soft-hyphen
repair delta: **+0.0422 against +0.0388** on P1, **+0.0638 against +0.0741** on the holdout.
pdfminer's repair delta is exactly **0.0000** in both, because the rule only ever fires for
PDFium.

Those two figures are not computed the same way — the lead is bill-weighted, the repair
delta is a per-document mean — so the near-cancellation is corroboration, not arithmetic.
**The load-bearing evidence is the direct measurement:** in `repaired` mode the B1 delta is
+0.0000 on P1 and +0.0001 on the holdout, both well inside the 0.010 practical threshold. Production
already performs the equivalent repair for the text API in `normalize_raw`, so a glyph-path
adapter would carry it too.

**Where B2 is silent, it is silent for two different reasons, and neither is similarity.**

- **P1 primary stratum: no opportunity to fire.** Every P1 document where the two backends'
  heading recovery differs carries `<quoted-block>`, and the exclusion that protects B2 from
  the DeltaTrack#11 reference defect removes all of them. The stratum reports "identical on
  every document" over 26 documents that could not have differed.
- **P2 holdout: nothing to measure.** 7 of 44 holdout documents carry any account or agency
  heading; 37 carry none. Its B2 control moves the metric by +0.0059 against a 0.020
  threshold, so **B2 is VOID on the holdout** — by the population's construction, not the
  metric's fault. Ten of twelve holdout bills are non-appropriations, and the appropriations
  heading tree is what B2/B5/B6 measure.

**A design tension worth carrying forward:** one 12-bill holdout cannot both test
generalization *beyond* appropriations and exercise metrics that only exist *within* it.
These strata bought the first and spent the second.

**On the quoted-block stratum, where B2 can move, pdfminer leads — and the mechanism is
diagnosed rather than inferred.** PDFium loses the word space inside heading labels at GPO
small-caps boundaries: `FAMILYHOUSING`, `NAVYAND`, `ARMYNATIONAL`, `AMERICANBATTLE`. On
`114-hr-2029/4` that is 17 malformed labels, **none of which match anything in the XML**,
against 2 for pdfminer. The neutral layer inserts a space when the x-gap exceeds
`_SPACE_FACTOR × size`; at those boundaries the gap is ~4.3 pt against a threshold of
exactly 0.25 × 14.0 = **3.50**, and the two backends resolve the small-cap size differently
(PDFium 11.2 pt, pdfminer 10.5 pt). They land on opposite sides of one knife-edge.

Two things follow, and they point in opposite directions:

1. The malformed labels are **wrong regardless of the reference's completeness** — GPO
   prints "FAMILY HOUSING" with a space — so this is a real defect of the
   PDFium-plus-this-layer combination, not an artifact of the XML drop.
2. Whether it is PDFium's defect or the **constant's** is what the sensitivity sweep decides,
   and `_SPACE_FACTOR = 0.25` is the value the exploratory audit already flagged as
   inherited from PDFium-tuned production. A lead that exists only at the default is
   reported as *"leads at the default parameterization only"*.

**Separability, and a trap in reading it.** On P1, S5 is separable and **S4 is not**: moving
a heading into another heading's slot costs B5 0.61 but also costs B2 0.17, so this pipeline
cannot move a heading without changing whether it is detected. That is a real coupling in
`extract_anchors`, not a defect in B5. On P2 both read "separable" **only because B2 cannot
move there at all**, so the P2 separability verdict is not evidence and the P1 one stands.


---

# The finding that reframes Concern A

**Production does not use the glyph path.** `parsers/pdf_text.py` reads PDFium's *text* API;
the neutral glyph layer is something this bake-off built to compare backends fairly, and it
is also what a browser architecture would have to use. Those are not the same pipeline, and
Concern A's reference is the harness incumbent — native pypdfium2 **through the glyph
layer** — not production's current output.

Measured over the 33 production-accepted corpus documents that carry any headings, against
`extract_clean_pages` as the production reference:

| path | exact heading-set match | labels production does **not** produce | production labels **missed** |
|---|---|---|---|
| PDFium-native via the glyph layer | 26/33 | **302** | **280** |
| PDFium-WASM via the glyph layer | 26/33 | **302** | **280** |
| **pdfminer via the glyph layer** | **29/33** | **5** | **2** |

The two PDFium builds are identical to each other to the label — which is exactly what
Concern A reports, and it is a real result: **the WASM build faithfully reproduces native
PDFium, including this defect.**

On the largest bills the defect is not marginal. `118-hr-4366/5`: production recovers 652
headings; PDFium's glyph path invents 99 and loses 98, about **15 % of the heading tree**.
pdfminer invents 0 and loses 0.

**Mechanism, diagnosed and robust.** PDFium loses the word space at GPO small-caps
boundaries, producing `FAMILYHOUSING`, `NAVYAND`, `ARMYNATIONAL`, `AMERICANBATTLE`. The
layer inserts a space when the x-gap exceeds `_SPACE_FACTOR × size`; at those boundaries the
gap is ~4.3 pt against a threshold of exactly 3.50, and the backends resolve the small-cap
size differently (PDFium 11.2 pt, pdfminer 10.5 pt). The sensitivity sweep shows this is
**not** an artifact of that constant: pdfminer leads at every setting of every parameter,
and its own B2 is flat at 0.5826 across 0.15/0.20/0.30 while PDFium's moves.

**Why nothing caught this earlier.** The exploratory calibration gate compared production's
and the layer's **anchor counts, node counts and conservation numbers** — 165/165, 339/339,
197/197 — and passed. Counts are not what differ; labels are. A gate that compares totals
cannot see a renamed heading.

**Product consequence.** The heading tree is the financial data contract: it is what puts an
amount under the right department, agency and account. A malformed account label does not
merely look wrong, it misfiles the money beneath it.

**What this does and does not change.**

- It does **not** touch Concern A's result. PDFium-WASM does reproduce the harness incumbent
  exactly, on 43 accepted pairs and 4 declined.
- It **does** change what that result licenses. "Safe to swap the backend" is not "safe to
  move to the glyph architecture": a browser build carrying PDFium would regress against
  current production on heading labels, and Concern A was never pointed at that comparison.
- It is **fixable in principle** — the adapter's word-space rule could key on the larger of
  the neighbouring glyph sizes, or use PDFium's own space glyphs — but **nobody has written
  or tested that fix**, so it is not evidence available to a decision today.

---

# Concern C — security / egress

Two claims, kept apart because they support different sentences:

| Test | Claim it supports |
|---|---|
| Browser policy | "our app does not transmit through these mechanisms" |
| Environment isolation | "the process cannot reach the network at all" |

**Threat model.** This establishes strong controls for *Threat A* — DeltaTrack accidentally
or deliberately including ordinary application networking. It does **not** establish
anything about *Threat B*, arbitrary code executing in the browser: the two mechanisms
below that sit outside CSP are a standing demonstration that no page-level policy makes
exfiltration impossible.

## C.1 Per-vector egress under the corrected policy

<!-- C_EGRESS -->

Policy under test: `default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'`

Of **35 frozen mechanisms**, 29 transmitted in the no-policy control and are eligible for scoring. **27 blocked**, **0 bypass the policy**, **2 are outside what CSP governs** (webrtc, windowopen). 6 never transmitted in the control and are not scored (sw, track, svguse, link-dns-prefetch, link-preconnect, webtransport).

| vector | control | policy result |
|---|---|---|
| `fetch` | CONTROL TRANSMITTED | blocked |
| `xhr` | CONTROL TRANSMITTED | blocked |
| `beacon` | CONTROL TRANSMITTED | blocked |
| `img` | CONTROL TRANSMITTED | blocked |
| `script` | CONTROL TRANSMITTED | blocked |
| `css` | CONTROL TRANSMITTED | blocked |
| `cssimport` | CONTROL TRANSMITTED | blocked |
| `webfont` | CONTROL TRANSMITTED | blocked |
| `eventsource` | CONTROL TRANSMITTED | blocked |
| `iframe` | CONTROL TRANSMITTED | blocked |
| `dynimport` | CONTROL TRANSMITTED | blocked |
| `form` | CONTROL TRANSMITTED | blocked |
| `sw` | CONTROL UNSUPPORTED / VOID | not scored |
| `workerfetch` | CONTROL TRANSMITTED | blocked |
| `ws` | CONTROL TRANSMITTED | blocked |
| `webrtc` | CONTROL TRANSMITTED | outside CSP |
| `ping` | CONTROL TRANSMITTED | blocked |
| `speculation` | CONTROL TRANSMITTED | blocked |
| `object` | CONTROL TRANSMITTED | blocked |
| `embed` | CONTROL TRANSMITTED | blocked |
| `video` | CONTROL TRANSMITTED | blocked |
| `track` | CONTROL UNSUPPORTED / VOID | not scored |
| `svgimage` | CONTROL TRANSMITTED | blocked |
| `svguse` | CONTROL UNSUPPORTED / VOID | not scored |
| `cssbg` | CONTROL TRANSMITTED | blocked |
| `keepalive` | CONTROL TRANSMITTED | blocked |
| `importscripts` | CONTROL TRANSMITTED | blocked |
| `srcdoc` | CONTROL TRANSMITTED | blocked |
| `windowopen` | CONTROL TRANSMITTED | outside CSP |
| `metarefresh` | CONTROL TRANSMITTED | blocked |
| `link-prefetch` | CONTROL TRANSMITTED | blocked |
| `link-preload` | CONTROL TRANSMITTED | blocked |
| `link-dns-prefetch` | CONTROL UNSUPPORTED / VOID | not scored |
| `link-preconnect` | CONTROL UNSUPPORTED / VOID | not scored |
| `webtransport` | CONTROL UNSUPPORTED / VOID | not scored |

| validity condition | holds |
|---|---|
| 1_per_vector_control_assigned | yes |
| 2_known_bad_caught | yes |
| 3_all_cases_completed | yes |
| 3b_vector_count_matches | yes |
| 4_network_layer_observation | yes |

<!-- /C_EGRESS -->

**The per-vector control status is the change that matters.** Six mechanisms never
transmitted even with no policy at all. Under the exploratory rule — "the control must leak
on ≥ 12 of 35" — every one of them would have been credited as *blocked by policy*. They
are now recorded as unsupported and score nothing in either direction.

**A false negative this harness produced, and how it was caught.** The first run of this
probe scored WebRTC as **blocked** while six STUN binding requests sat in the policy run's
own log: `serve.py` labels a datagram `[stun]` when it carries the STUN magic cookie and
`[udp]` otherwise, and the detector matched only `[udp]`. That would have published "WebRTC
is closed" and silently contradicted a correct exploratory finding. It was caught because
the two runs disagreed and the disagreement was treated as the finding rather than
explained away — the comforting reading was the wrong one.

## C.2 Environment-level isolation

<!-- C_ISOLATION -->

| check | result |
|---|---|
| observer_liveness (unsandboxed beacon ARRIVED) | **PASS** |
| known_bad_inside_sandbox (beacon did NOT arrive) | **PASS** |
| external_host_unresolvable_inside_sandbox | **PASS** |
| comparison_succeeded_with_network_denied | **PASS** |
| output_identical_to_unsandboxed | **PASS** |

Verdict: **PASS**. Linux container: NOT RUN -- docker daemon unavailable at execution time.

<!-- /C_ISOLATION -->

Both controls ran in the same window, and neither alone would have been sufficient: the
known-bad beacon inside the sandbox is what attributes the silence to the sandbox, and the
unsandboxed liveness beacon is what distinguishes a working sandbox from a dead listener.

---

# Concern D — performance

<!-- D_PERF -->

> **THIS RUN IS VOID.** load average at start >= 1.0: load average 5.27 against a ceiling of 1.0. The numbers are published as void rather than withheld, and no gate verdict below counts. The exploratory gate-9 figure that failed to reproduce was measured under exactly this condition, undeclared.

Document: `tests/corpus/119-hr-1/1_reported-in-house.pdf`. Estimator: minimum of trials of 5.

| backend | min | median | max | spread | cpu/wall at min | D1 | D2 |
|---|---|---|---|---|---|---|---|
| pdfium-native | 6.32 s | 6.33 s | 6.45 s | 0.14 s | 1.0 | VOID -- pass | VOID -- pass |
| pdfium-wasm | 5.40 s | 5.41 s | 5.44 s | 0.04 s | 1.03 | VOID -- pass | VOID -- pass |
| pdfminer | 17.31 s | 19.85 s | 20.62 s | 3.31 s | 0.99 | VOID -- pass | VOID -- pass |

<!-- /D_PERF -->

**Void twice over, and the second reason matters more than the first.** The load-average
condition failed (5.27 against a ceiling of 1.0), which the harness detected and declared
itself. Separately, gate D-1 was frozen as *in-browser* and this probe times native
extraction instead — an oversight logged in [`DEVIATIONS.md`](results/DEVIATIONS.md).

So these numbers **cannot resolve the exploratory gate-9 UNRESOLVED verdict in either
direction**. Native pdfminer at 17.3 s says nothing about Pyodide pdfminer, which is
interpreted Python compiled to WASM and is where the exploratory 37.9 s / 69.2 s figures
came from. The one thing worth carrying is the relative ordering, which is stable across
both runs and does not depend on the ceiling: **PDFium-WASM ≈ PDFium-native, pdfminer ~3×
slower natively and 8–10× slower in-browser.**

`cpu/wall ≈ 1.00` for all three, so none was CPU-starved; the machine was busy but each
process held a core. That is the diagnosis the exploratory run could not make.


---

# Concern E — bundle size and architecture

The axis the exploratory audit identified as unmeasured and most likely to decide the
question. Its stated expectation was that **"pdfminer adds no binary at all, which is the
axis on which it could still win despite being ~8× slower."**

<!-- E_BUNDLE -->

Unit: over-the-wire bytes: gzip for raw wasm/js, published wheel size for wheels (already ZIP).

Shared Pyodide + DeltaTrack baseline: **6.43 MB** over the wire (13.84 MB raw).

| artifact | incremental backend cost | full artifact |
|---|---|---|
| pdfium-wasm | **2.19 MB** | 8.62 MB |
| pdfminer (core only) | **6.66 MB** | 13.08 MB |
| pdfminer (as micropip resolves it, with cryptography) | **9.05 MB** | 15.48 MB |

`pdfminer (core only)` is **3.03×** PDFium-WASM's incremental cost.

`pdfminer (as micropip resolves it, with cryptography)` is **4.13×** PDFium-WASM's incremental cost.

<!-- /E_BUNDLE -->

**That expectation is measured and false.** pdfminer.six's published wheel is 6.59 MB
because it bundles CJK CMap resources, and micropip resolves a further 2.20 MB wasm
`cryptography` wheel. PDFium-WASM's 4.63 MB binary gzips to 2.13 MB. The axis the audit
thought might rescue pdfminer runs the other way, and it is not close.

**What this does not measure:** a built single-file artifact, first/repeat load, Pyodide
init, comparison latency, peak memory, or the JS↔Python transfer volume. No bundler exists
to build that artifact, and writing one here would have measured the bundler.

---

# Concern F — `@embedpdf/pdfium` release readiness

Full memo: [`RELEASE-READINESS.md`](RELEASE-READINESS.md). It can gate adoption and cannot
rank a backend.

Verdict against the pre-committed requirement: **the vendoring branch is satisfiable today;
the reproduction branch is not.** npm publishes no `gitHead` for the version we ran and the
declared source path has moved, so there is no published mapping from tarball to source
commit. Vendored third-party in the shipped `.wasm` is zlib, libpng, OpenJPEG and FreeType.


---

# P3 — non-corpus robustness and safe failure

Renamed from the exploratory "Tier B", because eleven of its twelve fixtures are published
GPO Tier A prints and it was never a pre-publication test.

**Gate S-1 — no fixture may land in ANSWERS ANCHORLESS — FAILS.**

| fixture class | outcome (identical on both backends) |
|---|---|
| Committee report `CRPT-118srpt198` | **DECLINES** — correct, it is not a bill |
| Committee print / markup `CPRT-119HPRT63305` | **DECLINES** — correct |
| 12 real GPO bill prints | **ANSWERS** — correct |
| Synthetic image-only PDF | **ANSWERS ANCHORLESS** |
| Synthetic non-GPO producer PDF | **ANSWERS ANCHORLESS** |

Confirmed at the production entry point rather than at a probe's approximation of it: two
**genuinely different** scanned pages — page 3 and page 21 of one bill, rasterized so no text
layer survives — compare as **0 changes with an empty summary**. The same two pages with
their text layers intact correctly yield 3.

The guard catches the unnumbered-but-text-bearing enrolled layout it was written for. It
does not catch a document with no text layer at all: the pipeline extracts 7 characters,
finds no anchors, and answers anyway. **A staffer comparing two scanned drafts would be told
nothing changed.** ADR 0003 flagged image-only draft PDFs as the untested hard case; this
tests it and finds the failure mode is silent rather than loud.

**It discriminates between no candidates** — pdfium-wasm and pdfminer behave identically — so
it belongs to the pipeline rather than to the bake-off. It is nonetheless the most actionable
product finding in this run.



---

# B8 — the gold sample: built and frozen, **not adjudicated**

The image-adjudicated gold sample was constructed to protocol and **its adjudication was not
performed in this run**. Reported as not done rather than partially done: a prefix of the
seeded shuffle would be a valid random subsample but a thin one, and B8 is corroboration
that by protocol may never decide a ranking.

**99 of 100 items across 98 distinct pages.** Only `financial/table_like` fell short, at 3
of 4, and that cell is genuinely rare — its whole frame is 3 lines carrying three or more
dollar amounts.

| Artifact | Contents | Committed |
|---|---|---|
| `results/gold_key.json` | frame sizes, selection indices, contributing backends and what each said, per-stratum accounting. **Not to be opened until `gold_adjudicated.json` is committed** | yes |
| `results/gold_blind.json` | document, page, image path, printed-line locator, question. No backend name, no candidate text, no XML value, no stratum label | yes |
| `results/gold_pages/` | one CoreGraphics render per page (pypdf split + `qlmanage`) | **no** — 29 MB of deterministic output; regenerate with `gold_build.py --render-only`, which reads the frozen JSON and cannot perturb the sample |

**Why it was not adjudicated:** the sample spans **98 distinct pages for 99 items**, so
adjudication is essentially one page image per item rather than the clustering the design
assumed. That is a cost this run could not absorb after A, B, C, D, E, F, P3, the sensitivity
sweep and the production-comparison probe.

**Two defects found while building it, both fixed, and the second is the instructive one.**

1. *Stratum starvation.* Assignment is first-match and the first build ordered common
   categories before rare ones. Nearly every GPO page carries the rotated gutter watermark
   and most lines end in a hyphen, so those absorbed almost everything. Reordered rare-first.
2. *A predicate that could not fire.* `long_block` — "an amount deep inside a long
   appropriations block" — tested `distance-since-last-heading > 40` where the distance was
   computed **within a page**. GPO pages hold ~25 printed lines, so the test was
   **structurally incapable of matching** and the cell drew a frame of **0** on two
   successive builds. Counting the distance in document order across page boundaries gives
   it a frame of **3,961**. This is the same failure mode this run kept finding elsewhere,
   in the sampler this time.

Neither defective build was committed.

**To adjudicate it later:** run `gold_build.py --render-only`, read `gold_blind.json` and the
images *only*, write `gold_adjudicated.json`, **commit that**, and only then join against
`gold_key.json`. The commit order is the only evidence the adjudication was blind.

---

# Applying the frozen decision rules

**Rule 1 — does either candidate have a clear, practically meaningful, independently
validated accuracy advantage on replication *and* holdout?**

**No, because the conjunction fails.** pdfminer has a demonstrated structural advantage on
the **replication** corpus: it leads B2 on the only stratum where B2 can move (+0.0320, CI
excluding zero), it leads every metric at every setting of every parameter, and it
reproduces production's heading extraction almost exactly through the glyph layer where
PDFium does not (5 spurious labels against 302). But the **holdout cannot corroborate any of
it** — B2 is void there because 37 of 44 holdout documents carry no headings at all.

So the honest statement is narrower than a lead and wider than a tie: **pdfminer has a
structural advantage that is well evidenced on the replication corpus and untested on unseen
data.** On text recovery the two are indistinguishable in the shipping mode on **both**
populations.

**Rule 2 — where accuracy is indistinguishable, tie-breakers apply.** On text, they do, and
they favour PDFium-WASM decisively: a **3.03–4.13× smaller** artifact over the wire and
roughly **3× faster** native extraction (8–10× in-browser, from the exploratory data).

**Rule 3 — PDFium-WASM's exact parity is migration safety, not correctness.** Held to, and
sharpened: its parity is with the *harness incumbent*, and the same output regresses against
*production* on heading labels.

**Rule 4 — pdfminer's exploratory metrics were evidence worth testing, not proof.** Tested.
The text half dissolved into the soft-hyphen repair delta. The structural half survived, and
strengthened once measured against production rather than against the XML.

**Rule 5 — security conclusions name their policy and environment.** Done in Concern C.

## The tradeoff, stated rather than resolved

| | PDFium-WASM | pdfminer.six |
|---|---|---|
| Reproduces the harness incumbent | **exact** — 43/43 accepted, 4/4 declined | amounts yes; change segmentation agrees on only 22/43, full text on 15/43 |
| Heading labels vs **production** | 302 spurious / 280 missed over 33 docs | **5 spurious / 2 missed** |
| Text recovery (shipping mode) | **indistinguishable** | **indistinguishable** |
| Artifact over the wire | **2.19 MB** incremental | 6.66–9.05 MB incremental |
| Speed | **~3× faster** natively | 8–10× slower in-browser (exploratory) |
| Supply chain | single-maintainer fork, no tarball→commit mapping | PyPI, long established |

**Neither dominates, and the deciding axis is now a different one than the audit expected.**
The exploratory audit thought bundle size might rescue pdfminer; it does the opposite. This
run's own finding is that PDFium's glyph path misfiles ~15 % of the heading tree on large
appropriations bills relative to production — and the heading tree is the financial data
contract.

## The step this run has earned

**Fix the adapter's word-space rule and re-run, before choosing.** The defect is one rule:
a space is inserted when the x-gap exceeds `_SPACE_FACTOR × size`, evaluated against the
*following* glyph's size, and at a small-caps boundary that lands ~0.8 pt from the threshold.
Keying it on the larger of the neighbouring sizes, or on PDFium's own space glyphs, is a
small change to `reconstruct.py`.

If it removes PDFium's 302 spurious labels, the two candidates become indistinguishable on
every independent metric and the decision falls cleanly to the tie-breakers, where
PDFium-WASM wins on size, speed and exact migration parity. **That is a cheap experiment with
a decisive outcome, and this run did not perform it** — writing the fix after seeing which
backend it helps is exactly the degree of freedom the preregistration exists to prevent, so
it belongs to a separately pre-registered run.

---

# What this run did not settle

<!-- NOT_SETTLED -->

Named so the next reader does not have to rediscover them.

| Not settled | Why |
|---|---|
| **Genuine pre-publication material** — chair's marks, discussion drafts, real committee drafts | Unobtainable without a congressional contact. The closest proxy this run reached is `CPRT-119HPRT63305`, a full-committee markup print, and the pipeline **declines** it |
| **Conference-report layouts** | No `CRPT` package from 2015 onward carries "conference report" in its title across 800 records; the class is close to extinct. Logged in [`DEVIATIONS.md`](results/DEVIATIONS.md) |
| **Windows** | Everything here is macOS 15 / arm64 |
| **PDF.js's true capability** | The operator-list adapter was not built, so its exploratory score belongs to `getTextContent()`, not to the library. It is measured in Concern E only |
| **Structural accuracy on unseen data** | B2 is void on the holdout: 7 of 44 holdout documents carry any heading at all. The holdout confirms text recovery and is silent on structure |
| **Structural accuracy against a sound reference** | On P1 the only documents where the backends' heading recovery differs are the ones whose XML reference is known-defective (DeltaTrack#11). Fixing #11, not changing the metric, is what would settle this |
| **The image-only failure mode's blast radius** | Gate S-1 fails: two different scanned pages compare as "0 changes". This run establishes the failure, not how often staffers would hit it |
| **A built single-file artifact** | Concern E weighs real component bytes; nobody has written the bundler, so first/repeat load, Pyodide init, peak memory and the JS↔Python transfer volume remain unmeasured |
| **Reproducible WASM provenance** | npm publishes no `gitHead` for the version we ran and the declared source path has moved, so tarball-to-commit cannot be mapped. The containerized build exists and nobody here has run it |
| **Human adjudication** | The gold sample is image-adjudicated at best, and its status is recorded in [`results/`](results/) rather than claimed |

<!-- /NOT_SETTLED -->
