# Harness validation, before any score exists

Everything here happened **before the first confirmatory score was produced**, so none of it
is a deviation — [`DEVIATIONS.md`](DEVIATIONS.md) opens at the first score. It is recorded
because a reviewer needs to know that the controls were exercised, what they caught, and
which of these corrections were made by me rather than forced by the data.

Calibration document: `tests/corpus/118-hr-4366/1_reported-in-house.pdf`, base backend
`pdfium-wasm`, strict mode. It is a P1 document, so **these numbers are calibration, not
results**, and they are not carried into any published table.

## What the B0 controls caught, in order

### 1. The heading detector was inverted, and three controls were silently no-ops

`_heading_rows` looked for a size step **up** against the page's dominant size. GPO sets the
body face at 14 pt and an account heading as 14 pt initials with an **11.2 pt** small-caps
body — the heading glyphs are *smaller* than the body, not larger. The predicate matched
nothing, so S2, S4 and S5 returned their input unchanged and every one of their deltas was
exactly `+0.0000`.

**Under the frozen rule that would have voided B2, B5 and B6 on a harness bug.** A void
verdict and a blind metric are indistinguishable from the output alone, which is the whole
reason the controls exist — here they caught the control itself.

Corrected to the measured signature: two distinct sizes within one printed line at a ratio
between 0.70 and 0.90 (measured: exactly 0.800), excluding chrome. On the calibration page
those are the only non-chrome multi-size rows.

### 2. S5's line lookup found nothing

It located a victim line through `Line.geom.baseline`, but `geom` is `None` on ordinary
print lines, so the band list was always empty. Rewritten to match the row by its own
printed margin number.

### 3. S2 does not move B2, and that is a finding rather than a fault

Collapsing the small-caps size band moves B2 by **+0.0029**, far below its 0.020 threshold.
The product's anchor detector evidently leans on the heading's *text* far more than on its
*size band*.

That is worth knowing, so S2 stays in the run as a diagnostic. But a metric must be
controlled against the fault it *names*, not against one mechanism that could cause it, so
**S2b** was added: delete 20 % of heading lines outright, which is the direct injection of
"this backend did not recover the heading label". S2b decides B2's void verdict; S2 is
reported alongside it.

### 4. S4 was revised twice, and I am recording that I stopped

| S4 design | B5 delta | B2 delta | Why rejected |
|---|---|---|---|
| shift heading lines down one line-height | +0.4612 | +0.4425 | drops glyphs into the next line's cluster and garbles both lines; B1 also fell 0.108. It corrupted the document, not its structure |
| swap each heading with the row below | +0.3527 | +0.0525 | the row below is usually a body line of the heading's *own* block, so the heading lands mid-sentence and stops being detected |
| **rotate each heading into the next heading's slot** (kept) | **+0.8649** | +0.2763 | every heading keeps its glyphs and still lands where a heading was; B1 moves 0.0002 |

Revising a control after seeing it fail its own separability check is a degree of freedom,
and it is named here rather than left for a reviewer to infer. **The stopping rule was
declared before the third run and held: S4 was not revised again, and its separability
verdict is reported as measured.**

### 5. A control was perturbing the population it controls

B3a's page set is the union of pages any backend could number. Sabotage variants were in
that union, and S4 moves heading glyphs *between pages*, so it added pages and moved the
untouched base backend's B3a from **1.0000 to 0.9891** with nothing about that backend
having changed. The union is now over the real backends only.

## Control status at calibration

| Control | Decides | Δ | Threshold | Verdict |
|---|---|---|---|---|
| S1 | B1 | +0.2473 | 0.010 | fires |
| S2b | B2 | +0.0475 | 0.020 | fires |
| S3 | B3a | +0.0517 | 0.005 | fires |
| S4 | B5 | +0.8649 | 0.010 | fires |
| S5 | B6 | +0.2667 | 0.020 | fires |

| Separability | Own metric | B2 | Verdict |
|---|---|---|---|
| S4 (B5 vs B2) | +0.8649 | +0.2763 | **NOT SEPARABLE** at calibration |
| S5 (B6 vs B2) | +0.2667 | +0.0044 | separable |

**Reading the S4 result.** It does not mean B5 is redundant. It means *this pipeline cannot
move a heading without also changing whether the heading is detected*: `extract_anchors`
classifies partly by context, so a heading in a foreign context can fall out of the
account/agency/grouping kinds B2 counts. That is a real coupling in the product, and the
population run decides the verdict — this is one document.

## Holdout selection: generated twice

The first run walked `b.iter("committee")` for committee referral codes, which matches
nothing in BILLSTATUS. **0 of 108,121 bills were flagged appropriations**, stratum 4
reported 0 candidates, and the adequacy rule downgraded the run to *sampled-classes-only* —
a result indistinguishable from real scarcity. Corrected to `committees/item`, the accessor
`tools/fetch_govinfo.py` already had, and regenerated in full, because filling stratum 4
removes its picks from the pools of the strata that follow it.

**Nothing was scored from the first output and it was never committed.** The membership now
in git is the only one that has ever been there, and it fills **8 of 8 strata**.
