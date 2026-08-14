# PDF ↔ ADR 0020 convergence — first research phase

**Status: research only.** Nothing under `src/` changed. No behaviour moved. This record
answers "what should the PDF side emit so that PDF↔PDF comparison can use as much of the
common ADR 0020 architecture as is justified", and stops there.

Every number below is produced by a committed reproducer in `probes/`, over the committed
corpus, and every count that describes *production behaviour* is computed over the 17
adjacent PDF pairs `compare.pdf` will actually diff — not the 23 `diff_pdfs` will accept.
Six pairs differ, all with an enrolled (unnumbered) side that production declines. Results
are snapshots under `results/`, not maintained invariants.

```
uv run python docs/research/pdf-matching-convergence/probes/pdf_stage_census.py
uv run python docs/research/pdf-matching-convergence/probes/pdf_observation_census.py
uv run python docs/research/pdf-matching-convergence/probes/pdf_threshold_sensitivity.py
uv run python docs/research/pdf-matching-convergence/probes/pdf_tiebreak_equivalence.py
```

---

## Rulings

| # | Question | Ruling |
|---|---|---|
| 1 | Begin PDF stage extraction now | **Was STOP — no preservation oracle existed.** A ±0.05 change to either PDF matching cutoff passed the entire suite, confirmed by mutating production (§6.2.1). **Slice 0 has since been built and falsified (§6.3, §6.5), so this blocker is retired** and slice 1 may begin. |
| 2 | Can `_Block` become an ADR 0019 observation | **CHANGE.** Yes in substance. The blocker is that the block former lives inside the differ, so "parser revision" would include the matcher. The emission rule itself is fine — the 190 dropped blocks are correctly dropped (§4.2a, corrected against an earlier draft); what is missing is any statement or test of the rule. §4 |
| 3 | Is PDF emission deterministic (ADR 0019 open question 2) | **APPROVE.** 53/53 documents re-emit identical line, anchor and block sequences. §4.1 |
| 4 | Share `ObservationRef` / `Candidate` / `CandidateSet` / `CorrespondenceEvidence` / `Correspondence` | **APPROVE**, conditional on ruling 2. §5 |
| 5 | Share the assignment *implementation* | **RESEARCH FIRST.** The two greedy loops are provably the same shape (§5.3), but sharing means reshaping the XML side, which this thread must not do. |
| 6 | Share the classification implementation | **CHANGE — do not.** `moved` does not mean the same thing on the two pipelines, and three different PDF sites produce it. §3.4 |
| 7 | Adopt XML's `match_path` / `division_key` / node granularity for PDF | **STOP — source conflict.** §7.1, §7.2 |
| 8 | Is PDF's convergence point after Observation production | **APPROVE.** Yes. An earlier draft claimed round-1 sequence alignment could not become a `CandidateSet` behaviour-preservingly; that was wrong — candidate recall is measured against adjudicated correspondences, not the retriever's own output. Corrected in §9. |
| 9 | Blockers, restated after two corrections | The blocking finding is **only** ruling 1. Slices 1–5 and 7 are behaviour-preserving wraps; slice 6 stays research-gated on what PDF `moved` means. |

---

## 1. The current PDF pipeline, from source

```
PDF bytes
│
├─ parsers/pdf_text.extract_clean_pages                                    EXTRACTION
│     per page:  textpage.get_text_range()  ──────────────► raw text
│                _page_glyph_sizes: char boxes + text-matrix scale
│                     → baseline clustering → visual lines
│                     → {margin line number: (glyph_size, LineGeom)}
│                normalize_raw → strip_page_chrome
│                _parse_print_lines   → print_lines   (printed layout verbatim)
│                _merge_print_lines   → lines + merge_ranges  (soft hyphens rejoined)
│                _attach_geometry     → glyph_size, geom on each merged line
│     → list[Page]
│
├─ compare/pdf._is_unnumbered_layout ──► DECLINE                    ADMISSIBILITY
│     <50 % numbered lines over ≥50 lines ⇒ UnsupportedLayoutError
│     (6 of 23 committed adjacent pairs)
│
└─ diff_pdf.diff_pdfs
   │
   ├─ _flatten(pages) ─────────────────────────────────────► list[_IndexedLine]
   │     _rejoin_cross_page_hyphens                          (text, page, line)
   │
   ├─ parsers/pdf_anchors.extract_anchors(pages) ──────────► list[Anchor]
   │     _anchors_from_page      TITLE / SEC. / run-in subsection   (per page)
   │     derive_size_bands + _coverage ≥ 0.85:
   │        _account_anchors_by_size    account / grouping / agency
   │        _major_anchors_by_size      major
   │     sort by (page, line);  _assign_divisions → division  (DISPLAY ONLY)
   │
   ├─ _group_into_blocks(indexed, anchors) ────────────────► list[_Block]     ◄── observation
   │     anchors whose (page,line) no longer resolves are SKIPPED               production,
   │     front matter → synthesized "preamble" Anchor                           living in
   │     block = indexed[pos : next_pos], then _strip_heading_lines             the differ
   │     EMPTY BLOCKS DROPPED   (190 corpus-wide)
   │
   ├─ _block_key(b) = f"{anchor.text or '(preamble)'}::{block.text[:80].strip()}"
   ├─ difflib.SequenceMatcher(a=keys_v1, b=keys_v2, autojunk=False).get_opcodes()
   │        equal   → zip → _emit_pair                                        RETRIEVAL
   │        replace → zip BY POSITION k; surplus → added/removed              (+ assignment,
   │        delete  → _hunk_for_removed                                        fused)
   │        insert  → _hunk_for_added
   │
   ├─ _emit_pair(a, b)
   │        a.text == b.text:
   │             anchors differ → _hunk_for_paired_blocks(similarity=1.0)  → moved
   │             else           → EMIT NOTHING                                (unchanged is
   │                                                                           not a record)
   │        else sim = text_similarity_at_least(a.text, b.text, 0.4)
   │             sim < SIMILARITY_THRESHOLD → removed + added                  ASSIGNMENT
   │             else                       → _hunk_for_paired_blocks(sim)
   │
   ├─ _hunk_for_paired_blocks(a, b, sim)
   │        both anchors AND anchor texts differ AND sim ≥ MOVE_THRESHOLD  → moved
   │        else                                                           → modified
   │        amount_pairs = match_amounts(a.text, b.text)                       CLASSIFICATION
   │        has_amendment_annotations                                          thresholding a
   │                                                                           correspondence
   │                                                                           score
   └─ _reconcile_moves(hunks, MOVE_THRESHOLD)                              RETRIEVAL round 2
            over the EMITTED HUNK LIST, after every hunk is classified        + ASSIGNMENT,
            move_candidates(removed_texts, added_texts, 0.6)                   running AFTER
            sort desc by (sim, ri, ai); greedy exclusive claim                 classification
            moved hunk emitted at the REMOVED hunk's position
   → PdfDiff(hunks, v1_anchors + front matter, v2_anchors + front matter)

formatters/canonical.pdf_diff_to_canonical                                 PROJECTION
      breadcrumb_for(anchor, all_anchors) → path
      _pdf_move → renumbered | relocated  (+ body_unchanged)
      _pdf_span → char offsets;  _pdf_tree_payload → build_pdf_tree + own_amounts
→ view_from_canonical → format_diff_html      (shared with XML, ADR 0007)
```

Two structural facts fall out of the map and matter more than any individual rule.

**Observation production lives in the differ.** `_flatten`, `_rejoin_cross_page_hyphens`,
`_group_into_blocks` and `_strip_heading_lines` are all in `diff_pdf.py`. What a PDF
observation *is* is therefore defined by the module that matches them.

**`_reconcile_moves` is the pre-#591 XML shape.** ADR 0020 names `reconcile_moves` as "a
second retrieval pass, unnamed as such, running after classification". The XML side moved
its round 2 before classification in #591. The PDF side did not: `_reconcile_moves` reads
`h.change_type`, which is set at hunk construction, so retrieval genuinely runs on
classified output.

---

## 2. Every matching decision, and the stage that owns it

"Stage in code" is where the decision physically lives today; "ADR 0020 stage" is where the
record puts it.

| # | Site | Decides | In code | ADR 0020 stage |
|---|---|---|---|---|
| 1 | `compare/pdf._is_unnumbered_layout` | whether to compare at all | pre-extraction | **not a matching stage** — source admissibility, and the natural home of `bill_diff`'s resolver |
| 2 | `extract_anchors` (size bands, `_COVERAGE_MIN`, dangle guard, catchline shape) | what landmarks exist | extraction | **observation production** |
| 3 | `_group_into_blocks` anchor skip | which anchors delimit a block | extraction | **observation production** |
| 4 | `_group_into_blocks` empty-block filter | which blocks exist at all | extraction | **retrieval bound wearing extraction's clothes** — §4.2 |
| 5 | `_strip_heading_lines` | what a block's *text* is | extraction | **observation production** — legitimately, but it defines every similarity number downstream |
| 6 | `_block_key` | the unit two sides are aligned on | fused | **RETRIEVAL** — this key is what can ever be compared |
| 7 | `SequenceMatcher.get_opcodes` | which blocks are considered counterparts | fused | **RETRIEVAL** |
| 8 | `replace` positional `zip` by index `k` | which block pairs with which inside a replace run | fused | **RETRIEVAL** — it decides what is *considered*; `_emit_pair` can still refuse the correspondence (corrected, §9) |
| 9 | `replace` surplus → added/removed | 1:0 / 0:1 | fused | retrieval emits no candidate; **ASSIGNMENT** settles them unmatched |
| 10 | `_emit_pair` identical texts → emit nothing | suppress unchanged | fused | **CLASSIFICATION** + an output policy XML does not share (§7.3) |
| 11 | `_emit_pair` identical texts + anchors differ → `moved(sim=1.0)` | moved | fused | **CLASSIFICATION** — and the `1.0` is synthesised, not measured |
| 12 | `_emit_pair` `sim < SIMILARITY_THRESHOLD` → split | revokes a correspondence | fused | **ASSIGNMENT** |
| 13 | `_hunk_for_paired_blocks` `sim ≥ MOVE_THRESHOLD` → moved | moved vs modified | fused | **classification applying a threshold to a correspondence score — the violation ADR 0020 names by name** |
| 14 | `_reconcile_moves` `move_candidates(…, 0.6)` | which unmatched pairs are worth evaluating | fused, post-classification | **RETRIEVAL round 2** |
| 15 | `_reconcile_moves` sort `(sim, ri, ai)` desc + greedy claim | which pairs correspond | fused | **ASSIGNMENT round 2** |
| 16 | `_reconcile_moves` `threshold` re-applied to the same score | correspondence | fused | **ASSIGNMENT** |
| 17 | `_reconcile_moves` emits the move at the removed hunk's index | record order | fused | **classification output policy** — and it differs from XML's, which appends moves |
| 18 | `canonical._pdf_move` renumbered vs relocated | presentation of a settled move | projection | **CLASSIFICATION** — legitimate; reads anchor-text equality, applies no threshold |
| 19 | `canonical._pdf_hunk_to_canonical` `anchor_resolution` | degraded flag | projection | presentation |
| 20 | `_extract_amount_pairs` / `match_amounts` | money | on the hunk | **money extraction, parallel to classification** — already where ADR 0020 puts it |
| 21 | `formatters/_text.word_diff` | inline diff vs stacked paragraphs | renderer | **presentation** — already separated (`LEGIBILITY_THRESHOLD`), and PDF already benefits |

Rows 12, 13, 15 and 16 are the four places one word-overlap ratio decides four different
questions. Row 13 is not an inference: ADR 0020's own "Alternatives rejected" section says
"What it may not do is threshold a correspondence score, which `diff_bill.diff_bills` and
`diff_pdf._hunk_for_paired_blocks` both do today." The XML half of that sentence has since
been addressed; the PDF half has not.

---

## 3. Measured decision volumes

17 production-accepted adjacent pairs, 3,526 old-side and 8,636 new-side blocks.
`probes/pdf_stage_census.py` reconstructs the pipeline stage by stage and **asserts its
hunks are element-for-element identical to `diff_pdfs`'** on every pair before recording a
number, so these describe the shipping pipeline rather than a drifted copy.

### 3.1 Retrieval — what block-key alignment offered

| | count |
|---|---|
| `equal` opcode pairs | 2,981 |
| `replace` opcode positional pairs | 420 |
| `replace` surplus → removed / added | 115 / 3,618 |
| `delete` / `insert` blocks | 10 / 1,617 |

### 3.2 Assignment — the split-vs-pair cutoff

| | count |
|---|---|
| aligned pairs with identical text, suppressed | 2,437 |
| aligned pairs kept as one correspondence | 739 |
| **aligned pairs split into removed + addition** (`sim < 0.4`) | **224** |
| **…of those, carrying dollar amounts on BOTH sides** | **23** |

That last row is the PDF analogue of the measurement ADR 0020 built its money argument on.
The record reports 27 of 327 for XML and says: "That is the measured population in which a
correspondence decision can propagate into materially different financial output — not a
count of confirmed errors, since none of the 27 has been adjudicated." The same wording
applies here. **Neither the 224 nor the 23 has been adjudicated**; what is established is
that the mechanism exists on the PDF path at a comparable rate, so #368 is not an XML-only
defect.

### 3.3 Assignment — round 2

| | count |
|---|---|
| pairs the retriever evaluates (removed × added) | **190,055** |
| …on the single largest pair (118-hr-4366 v4→v5) | 125,685 |
| candidates surfacing at ≥ 0.6 | 194 |
| correspondences selected | 145 |
| candidates lost to greedy exclusivity | 49 |
| removals contested by more than one candidate | 16 |
| additions contested by more than one candidate | 17 |
| candidate score ties | 23 |

Competition is real, not theoretical: a quarter of surfaced candidates lose, and 23 ties
are broken by `(ri, ai)` position alone. ADR 0020's argument that "retrieval must be
allowed to bound — `move_candidates` already faces roughly 78,000 candidate pairs on one
large bill" is if anything understated on the PDF side.

### 3.4 `moved` has three producers, and they do not mean the same thing

| producer | rule | count |
|---|---|---|
| `_reconcile_moves` | assigned in round 2 | **145** |
| `_hunk_for_paired_blocks` | aligned pair, anchors differ, `sim ≥ 0.6` | **19** |
| `_emit_pair` | aligned pair, texts identical, anchors differ (`sim` forced to `1.0`) | **1** |

On the XML side `moved` is pure provenance — `_moved_record` fires when
`item.round == MOVE_ROUND`, and nothing about the two nodes distinguishes it. On the PDF
side, 20 of 165 moves are *not* provenance: they are pairs that survived round-1 alignment
and were then relabelled by a threshold. **Adopting XML's "moved = round 2" rule for PDF
would silently reclassify those 20 as `modified`.**

They exist because `_block_key` carries the body preview as well as the anchor text, so a
renumbered section can still align at the same position — where XML's `match_path` *is* the
label, so a renumber always breaks the group and always falls to round 2. The PDF rule is
the compensation for a more forgiving retriever. That is a real semantic difference between
the pipelines, not an accident to be tidied.

### 3.5 Boundary sensitivity

Of the 739 kept pairs, **18** sit within ±0.05 of `MOVE_THRESHOLD` and **5** within ±0.05
of `SIMILARITY_THRESHOLD`. That is the population any retune moves.

---

## 4. What a PDF Observation is

### 4.1 Emission is deterministic — ADR 0019 open question 2, answered for PDF

ADR 0019 records: "Whether the PDF pipeline's emission order is deterministic. The ordinal
generalizes to PDF where `element_id` could not, which is one reason it was chosen — but
determinism has been measured on the XML pipeline only."

Measured now. `probes/pdf_observation_census.py` extracts each of the 53 committed PDFs
**twice, both times for real** (never from the cache — the question is whether extraction
repeats itself), and compares the complete emitted sequences element by element:

| sequence | deterministic |
|---|---|
| `_IndexedLine` stream | **53 / 53** |
| `Anchor` stream | **53 / 53** |
| `_Block` stream | **53 / 53** |

Comparison is over the ordered sequence, not a digest of the node set, so a reordering that
preserved the set would fail — which is the one fault an ordinal-based identity exists to
catch.

**Residual, stated rather than glossed:** this is *in-process* repetition on one machine and
one pypdfium2 build. It does not establish cross-process, cross-platform or cross-version
stability, and `_page_glyph_sizes` reads floating-point char boxes and text matrices through
FFI, which is where a platform difference would enter. Committing a PDF observation ordinal
into a stored artifact needs the cross-process check first.

### 4.2 `_Block` is the right observation, and the emitted sequence is not

`_Block` is already the unit the matcher compares, already carries provenance the canonical
output consumes (page/line range), and already survives to the report. Nothing else in the
PDF path is a provision. Four things stop it being an ADR 0019 observation as emitted.

**(a) The sequence is filtered — but the filter is correct, and an earlier draft of this
section was wrong about it.** `_group_into_blocks` drops empty blocks: **190 corpus-wide**,
up to 58 in one document. The census confirms the code's own account of why they are empty —
`blocks_dropped_empty` equals `anchor_coord_collisions` exactly, document for document, so
every dropped block is the SEC-inline run-in subsection collision (DeltaTrack#96 Seam #2),
where a section anchor and a subsection anchor share one `(page, line)` and the subsection
owns the whole line.

This record previously concluded that "an empty block is a retrieval bound, not an absent
observation", and that the fix was to emit it and let retrieval decline it. **A second review
rejected that, and the rejection is right.** ADR 0019 says the ordinal indexes the parser's
*complete emitted sequence*. It does not say every intermediate object constructed while
deriving that sequence must itself become an observation. Which objects the parser emits is
the question, and the earlier draft assumed the pre-filter list was the answer — begging it.

The falsification question the review posed is the right one: *what stored judgment or
matcher-relevant legislative unit becomes impossible to address if the zero-content artifact
is not emitted?* Measured over all 53 committed PDFs
(`probes/pdf_dropped_block_addressability.py`), for all **190** dropped blocks:

| | |
|---|---|
| anchor kind | `section`, 190 of 190 |
| still present in the anchor stream `PdfDiff` carries | **190 / 190** |
| still a node in the canonical structure tree (`build_pdf_tree`) | **190 / 190** |
| still resolves a breadcrumb naming itself | **190 / 190** |

Nothing becomes unaddressable. The colliding section survives as an anchor, as a tree node,
and as a breadcrumb; `canonical._pdf_tree_payload` already gives it a zero-length own-span so
its money cannot double-count. Emitting it *again* as an empty observation would duplicate a
representation that already exists and would make parser identity reflect implementation
scaffolding rather than parsed legislative units.

**Conclusion, corrected: the complete emitted sequence is the post-filter block sequence.**
The filter is part of deciding what the parser emits, not a retrieval bound smuggled into
extraction. Slice 2 changes accordingly (§8) — it must *pin* the emission rule and prove the
ordinal indexes it, not lift the filter out.

The ADR 0019 hazard is therefore narrower than claimed, and still real: whatever the emission
rule is, the ordinal must index **that** sequence, and today nothing states or tests the rule
at all. Gate 5 (§6.4) is what closes it.

**(b) There is no identity to record.** A block's identity today is its position in the
post-filter list. `Anchor` carries `(page, line, kind, text, division)` but no id, and ADR
0019 already notes PDF "does not have [`element_id`] at all". `(page, line)` is *nearly*
unique — the 190 collisions above are the exception — so it is traceability metadata, not a
key.

**(c) The parser revision would have to hash the differ. — RESOLVED, in two steps.** ADR
0019 requires a revision "derived from the parser implementation, [changing] whenever code
capable of changing the emitted observations changes". When this was written that meant
`pdf_text.py` + `pdf_anchors.py` + the pypdfium2 build **+ `diff_pdf.py`**, because
`_group_into_blocks` and `_strip_heading_lines` lived there — so editing the matcher would
change observation identity and quarantine every stored artifact on a matching change that
touched no observation.

Slice 1 moved block formation to `parsers/pdf_blocks.py`, which removed `diff_pdf` from the
closure. It did **not** finish the job: `_is_strippable_heading_line` called
`extract_amounts` from `diff_bill`, and that call is result-bearing — an uppercase heading
with no recognised amount may be stripped, one carrying an amount must be retained. So a
change to the money regexes could still alter emitted observations without touching any file
the declared revision covered. The dependency-repair commit moved that primitive to the
source-neutral `deltatrack/amounts.py`.

**The dependency closure is now measured, not asserted.** Walking module-level imports from
`parsers.pdf_blocks`:

| | modules in the observation-production closure |
|---|---|
| before the repair | `bill_tree`, **`diff_bill`**, **`matching`**, `parsers.pdf_anchors`, `parsers.pdf_blocks`, `parsers.pdf_text`, **`similarity`**, `version_stems` |
| after | `amounts`, `parsers.pdf_anchors`, `parsers.pdf_blocks`, `parsers.pdf_text` |

`similarity` and `matching` — which carry the matching thresholds — were inside PDF
observation production and are now out.

**A PDF parser revision must therefore hash:** `parsers/pdf_text.py` +
`parsers/pdf_anchors.py` + `parsers/pdf_blocks.py` + `deltatrack/amounts.py` + the pypdfium2
distribution version. **Slice 3 implements it** as `pdf_observations.pdf_parser_revision()`,
deriving that closure by walking imports from `parsers.pdf_blocks` rather than listing
filenames, so a new parser dependency joins it without an edit.

**This is a second identity, not a widening of the first — an earlier draft of this section
had that wrong.** It claimed `tests/pdf_corpus._extractor_fingerprint` was "the working half
of the mechanism" and that slice 3 should widen it to cover `pdf_anchors`, `pdf_blocks` and
`amounts`. That conflates two questions with different subjects:

| | `_extractor_fingerprint` | `pdf_parser_revision()` |
|---|---|---|
| answers | may this cached `Page` list be served? | which parse was this stored judgment about? |
| subject | the payload `cached_pages()` stores | the emitted observation sequence |
| closure | `pdf_text` + pypdfium2 | `pdf_text` + `pdf_anchors` + `pdf_blocks` + `amounts` + pypdfium2 |

A cached `Page` is produced by `pdf_text` alone, so no edit to `pdf_anchors`, `pdf_blocks` or
`amounts` can make one stale. Widening the cache key to cover them would buy nothing and cost
a full corpus re-extraction on every downstream parser edit. The fingerprint is therefore left
exactly as it is, and the flagged gap is closed by adding the second identity rather than by
enlarging the first.

**(d) The observation's text is already a transformation.** `_Block.text` is
post-`_strip_heading_lines`, so it is not the printed text and `page_range` bounds the
stripped body. Legitimate — a parser transforms — but it means an observation must carry
both, or provenance into the full-bill view degrades.

### 4.3 The model — proposed, then built

The sketch this section originally carried listed six fields:

```python
@dataclass(frozen=True)
class PdfObservation:
    ref:           ObservationRef      # (side, ordinal) over the COMPLETE block sequence
    anchor:        Anchor | None       # kind, canonical text, page, line, division
    text:          str                 # the body the matcher compares (post-strip)
    page_range:    PageLineRange | None
    line_span:     tuple[int, int]     # [start, end) into the flattened _IndexedLine stream
    printed_lines: tuple[_IndexedLine, ...]   # pre-strip, for provenance
```

**Slice 3 built two**, and the difference is worth recording because a sketch is a hypothesis:

```python
@dataclass(frozen=True)
class PdfObservation:
    ref:   ObservationRef   # (side, ordinal) over the complete emitted block sequence
    block: _Block           # the parsed thing it addresses
```

- `anchor`, `text` and `page_range` are already `_Block` members. Restating them on the
  observation would create a second representation free to drift from the first, and buys
  nothing that `observation.block.text` does not.
- `line_span` and `printed_lines` are **not** projections of a `_Block`: `_group_into_blocks`
  retains neither the flattened-stream position nor the pre-strip lines. Producing them is a
  change to what the parser derives, which a behaviour-preserving slice may not make, and
  neither has a consumer. They stay available to a later slice that has one. Nothing is lost
  meanwhile — `page_range` and the anchor's `(page, line)` already resolve an observation back
  into the printed bill.

That leaves the same two fields `diff_bill.Observation` carries, which is the intended
convergence: an address plus the parsed thing, with the source-specific half being the only
difference between the two pipelines.

Mapped onto the ask's checklist:

| ADR 0019 / ask field | PDF answer |
|---|---|
| source identity | SHA-256 of the PDF bytes. Constant per side within one comparison, so — exactly as `matching.ObservationRef` argues for XML — it is a property of the comparison, not of each reference. |
| parser/extractor revision | `pdf_observations.pdf_parser_revision()`: SHA-256 over the transitive `deltatrack` import closure of `parsers.pdf_blocks` — `pdf_text`, `pdf_anchors`, `pdf_blocks`, `amounts`, plus the package initializers that run during those imports — and the pypdfium2 distribution version. Its precondition, that block formation leave `diff_pdf`, was met by slices 1 and 1a. |
| complete-sequence ordinal | index into `_group_into_blocks`' output, **post-filter** (§4.2a, corrected). Anchors that resolve to no surviving line stay skipped — that is genuine extraction, and those anchors address nothing. |
| text / body | `_Block.text`, via `observation.block` |
| structural path or inferred hierarchy | `breadcrumb_for(anchor, all_anchors)`. Detection-path dependent by design: a low-coverage bill has no account level, so the chain is shallower. **Not currently used in matching at all.** |
| anchor / heading information | `Anchor.kind` + `Anchor.text` |
| page/range provenance | `_Block.page_range`, plus the anchor's own `(page, line)` |
| other source-specific metadata | `Anchor.division` (display-only, §7.2); glyph size and `LineGeom`, which are consumed by anchor detection and never reach matching |

**The complete emitted sequence is the post-filter block sequence.** Not the anchor stream
(anchors that resolve to no line address nothing; a front-matter anchor is synthesised
during blocking), and not the line stream (a line is not a provision, and there are ~100k
of them).

---

## 5. Common vs source-specific

### 5.1 Shareable as-is — **APPROVE**

`matching.py` imports nothing from `deltatrack`, and its own docstring says why: "It is the
mechanism behind ADR 0020's requirement that the contracts survive an unsettled PDF
observation representation." That constraint pays off here.

| contract | verdict |
|---|---|
| `ObservationRef` | **APPROVE**, conditional on §4.2a. `(side, ordinal)` names nothing XML-specific. |
| `RetrieverInvocation`, `Proposal`, `Candidate`, `CandidateSet` | **APPROVE.** PDF round 2 maps onto them exactly as `retrieve_move_candidates` does; PDF round 1 is source-specific in its *policy* but produces the same shape. |
| `CorrespondenceEvidence` | **APPROVE the type, not the signal set.** PDF's signals are `word_overlap`, `anchor_text_equal`, and probably `alignment_op`. ADR 0020 explicitly permits header-equality booleans. |
| `Correspondence`, `CorrespondenceSet` | **APPROVE**, with §5.2. |
| canonical projection | **already shared at the contract**, two producers. ADR 0007 governs downstream. Do not merge the producers. |

### 5.2 One thing PDF must start doing — settle unchanged pairs

`CorrespondenceSet` requires every observation to sit in at most one correspondence. PDF
satisfies *exclusivity* but not *totality*: 2,437 identical aligned pairs produce no hunk at
all, so both observations are in no correspondence. XML settles those as 1:1 and classifies
them `unchanged`, and `xml_diff_to_canonical` drops them at projection.

The fix is straightforward and must be done carefully: settle them internally, classify
`unchanged`, drop before building `PdfHunk`s. **Not** by letting them reach `PdfDiff.hunks`
— `PdfDiff.summary` is `Counter(h.change_type)` and flows straight into canonical
`"summary"`, so an `unchanged` key would be a canonical byte change.

### 5.3 The assignment implementations are the same shape — **RESEARCH FIRST**

XML `_greedy_move_links` sorts `(word_overlap, ri_of[old], ai_of[new])` descending, then
claims greedily. PDF `_reconcile_moves` sorts `(sim, absolute_removed_index,
absolute_added_index)` descending, then claims greedily. `removed_idx`/`added_idx` are built
by ascending enumeration, so local→absolute is monotonic and **the two orderings are
identical**, not merely similar. Both call the same `move_candidates`.

One difference is apparent but not real. XML normalizes text (`_normalize_text`) before
scoring; PDF passes raw block text. Measured rather than argued, over all 9,976 committed
blocks: the strings differ in 8,045 cases, and `raw.split() == normalized.split()` in
**9,976 of 9,976** — the word sequences `text_similarity` actually consumes are identical.
The normalization cannot reach this measure.

**The tiebreak is the part that could still have differed, and it does not.** An earlier
revision of this section argued the two orderings were identical from the fact that
`removed_idx`/`added_idx` ascend, so local→absolute is monotonic. That answers the wrong
question. PDF's tiebreak is a position in the **emitted hunk list**, which interleaves hunks
from five producers; XML's is a position in the unmatched-**observation** stream. #590
measured that substituting ADR 0019 ordinals for XML's `(ri, ai)` moves the selected
correspondence on 3 of 27 pairs — so on XML the legacy key is policy, and the same could
have been true here.

Measured on PDF: selecting under `(sim, old_block_ordinal, new_block_ordinal)` instead of
`(sim, removed_hunk_index, added_hunk_index)` yields the **identical 145 links, symmetric
difference 0**, across all 23 score ties. And it is structural rather than a corpus
coincidence: on all 23 non-empty side-sequences the hunk-list order is already the
block-ordinal order, because the hunk list is emitted by a monotonic walk over the two
aligned block sequences. The two keys induce the same total order by construction.

So PDF and XML differ here in a way worth recording: **the legacy positional tiebreak is
policy on XML and inert on PDF.** XML's pairing stream comes from iterating `match_path`
groups, which is not document order; PDF's comes from a document-order alignment walk. A
shared assignment implementation therefore has one less way to silently change PDF results
than it has to change XML's.

Sharing is genuinely available. It is still **RESEARCH FIRST**, because sharing means making
`_greedy_move_links` generic over the population type, which is a change to the XML side —
and this thread must not make one to accommodate a hypothetical PDF need. Record the
finding; propose the change from the XML thread when a second consumer actually exists.

### 5.4 Not shareable — **CHANGE, do not**

**Classification.** XML emits `NodeDiff` (display paths, `element_id`, `text_diff`); PDF
emits `PdfHunk` (anchors, page ranges, `amount_pairs`). And `moved` differs semantically
(§3.4). Share the *boundary rule* — classification changes no partners — and the invariant
tests that carry it. Not the code.

**Retrieval round 1.** XML groups by `match_path`; PDF aligns two key sequences with
`SequenceMatcher`. These are not the same operation and §9 argues the difference is real.

### 5.5 Signal classification (the ask's Section B)

| signal | classify as | note |
|---|---|---|
| anchor text equality | **correspondence evidence** (boolean) | read in three places today, two of which decide |
| anchor kind | **observation metadata**; candidate retrieval policy | not consulted by matching at all today |
| body preview (first 80 chars) | **retrieval policy** | half of `_block_key` |
| block position in the aligned sequence | **retrieval policy** *and*, inside `replace`, **assignment** | one mechanism doing two jobs; must be split |
| word-overlap ratio | **retrieval bound** (round 2), **evidence signal**, **assignment threshold** | today it is also a classification threshold — the violation |
| inferred hierarchy (breadcrumb) | **observation metadata** today; candidate evidence | unused by matching; the natural home of #170's structural term |
| page proximity, geometry | **not used** — would be a new retrieval score | do NOT introduce during extraction |
| glyph size / `LineGeom` | **observation metadata** | consumed by anchor detection only |
| division label | **observation metadata, display-only** | §7.2 |
| page/line range | **provenance** | survives to canonical `location` |
| amounts | **money extraction**, parallel to classification | already correctly placed |

---

## 6. Preservation oracles — and the measured false-green

### 6.1 Inventory

| oracle | covers | can detect | stays green through |
|---|---|---|---|
| `test_canonical_baseline.py` | **XML only** | any canonical byte change on 27 XML pairs | **everything on the PDF path.** Its own docstring: "a PDF baseline is owed before any PDF-side stage extraction happens." |
| `test_committed_examples.py` | **one** PDF pair (118-hr-8752 v1→v2), byte-identical HTML re-render | a rendering or matching change on that pair | any change that leaves that pair's output alone — see §6.2 |
| `test_pdf_diff_recall.py` | 13 hand-authored cases on the same pair | wrong location, wrong `change_type`, prose not surfacing, missing annotation flag | the other 16 pairs; any change preserving type and location; **the split population — no case exercises a below-0.4 split** |
| `test_pipeline_parity.py` | 4 bills, v1→v2, **total-count bands** | a collapse or a large regression | anything inside the band (117-hr-4502's is 90 wide) |
| `test_pdf_corpus_smoke.py` | 23 pairs, structural invariants | malformed hunks, out-of-document ranges, overlapping ranges | **every matching-policy change** — the invariants hold at any threshold. Also runs 6 pairs production declines. |
| `test_pdf_injection_recall.py` | synthetic sentinels injected into a real v1 | text lost between diff and render | correspondence errors that still surface the text |
| `test_pdf_anchor_golden.py` | anchor goldens `(kind, text, page, line)` | observation-production drift | matching changes; and it carries no source digest or parser revision (ADR 0019 open question 5) |
| `test_pdf_extraction_golden.py` | extraction goldens | extractor drift | everything downstream |
| `test_canonical_tree.py`, `test_corpus_tree_properties.py` | tree + amount conservation | double-counted or lost amounts | correspondence errors that conserve amounts |
| `test_pdf_xml_amount_recall.py` | PDF vs XML amounts | money extraction gaps | correspondence errors |
| `test_diff_pdf.py` | ~40 unit cases on hand-built `Page` objects | the specific rules each names | anything not named; and being self-supplied input, it cannot catch a mismatch with what pypdfium2 really produces |

### 6.2 The negative control — and it fails

`probes/pdf_threshold_sensitivity.py` perturbs each cutoff by ±0.05 and asks which pairs
change output. It re-asserts the replica equals `diff_pdfs` at the baseline on every pair
first, so a perturbed run means something. (It uses a replica rather than monkeypatching for
a reason worth keeping: `diff_pdf` binds both constants into its own namespace at import,
and `_reconcile_moves` takes `MOVE_THRESHOLD` as a **default argument**, bound at
definition. A monkeypatching probe would report "no change" for every perturbation and read
as reassurance.)

| perturbation | accepted pairs whose output changes |
|---|---|
| `SIMILARITY_THRESHOLD` 0.4 → 0.45 | 2 / 17 |
| `SIMILARITY_THRESHOLD` 0.4 → 0.35 | 4 / 17 |
| `MOVE_THRESHOLD` 0.6 → 0.65 | 2 / 17 |
| `MOVE_THRESHOLD` 0.6 → 0.55 | 1 / 17 |

Now intersect with what the gates cover:

| pair | gate | responds to |
|---|---|---|
| **118-hr-8752 v1→v2** | the committed PDF example (byte-identical) **+** the 13-case fixture **+** a parity band | **NOTHING** — byte-identical under all four |
| 117-hr-4502 v1→v2 | parity band (1430, 1520) | **NOTHING** |
| 115-hr-5895 v1→v2 | parity band (310, 345) | **NOTHING** |
| 118-hr-8774 v1→v2 | parity band (31, 36) | similarity −0.05 only, moving the total 33 → **32** — inside the band |

The pairs that *do* respond — 118-hr-4366 v3→v4 and v4→v5, 115-hr-5895 v3→v4 — are covered
by no output-preserving gate at all. On 118-hr-4366 v4→v5 a ±0.05 move on `MOVE_THRESHOLD`
swings `moved` between 61 and 66 and `removed` between 71 and 76, and nothing reddens.

### 6.2.1 Confirmed by mutating production and running the real suite

The measurement above is a replica's. A second review objected, correctly, that "the entire
test suite passes" is stronger than a replica can support — a claim that outran its run. So
it was run properly (`probes/mutate_production_and_run_suite.py`).

Each cutoff is rebound **inside `diff_pdf`**, not in `deltatrack.similarity`. That is
deliberate: `similarity` serves both pipelines, so editing it there would redden the XML
canonical baseline, and the red would say nothing about PDF. Rebinding after `diff_pdf`'s
import block also lands *before* `_reconcile_moves` is defined, so its
`threshold: float = MOVE_THRESHOLD` default argument picks the new value up — the probe
prints the live values each run to prove the injection reached both sites.

| run | live `(similarity, move, _reconcile_moves default)` | result |
|---|---|---|
| baseline | `0.4  0.6  (0.6,)` | **3227 passed** |
| `SIMILARITY_THRESHOLD` → 0.45 | `0.45  0.6  (0.6,)` | **3227 passed — green** |
| `SIMILARITY_THRESHOLD` → 0.35 | `0.35  0.6  (0.6,)` | **3227 passed — green** |
| `MOVE_THRESHOLD` → 0.65 | `0.4  0.65  (0.65,)` | **3227 passed — green** |
| `MOVE_THRESHOLD` → 0.55 | `0.4  0.55  (0.55,)` | **3227 passed — green** |

> **Four production mutations, each changing real corpus output, and the suite stayed green
> on all four. Not one test in 3227 detected any of them.**

**One test is deselected, and the reason is itself a finding.** `tests/test_engine_installs.py`
builds a wheel and asserts the engine resolves from the installed environment; the
`PYTHONPATH` this harness needs (the worktree has no `uv sync`) lets the checkout answer
instead, so it fails identically with and without a mutation. It is a packaging gate and
cannot detect a matching cutoff. Worth noting that it caught its own fallback correctly —
which is more than the PDF gates managed.

This is the blocking finding. ADR 0020's implementation rule — "Introduce the contracts
behaviour-preservingly before changing matching policy, with canonical JSON byte-identical
across the corpus on both pipelines as the acceptance criterion. That is enforcement, not
convention: a matching-policy change necessarily breaks a byte-identical gate" — is
currently **false for PDF**, and now measured at the artifact rather than argued. The
enforcement it relies on does not exist, and a PDF extraction slice claiming behaviour
preservation today would be citing gates shown incapable of failing.

### 6.3 The gates, as built

**Slice 0 is implemented.** This section described what to build; it now describes what
exists. Falsification results are in §6.5.

**Gate 1 — `tests/test_pdf_canonical_baseline.py`.** SHA-256 over `compare.pdf.compare_pdfs`'
sorted-key JSON, through the public producer rather than a chain reassembled in the test,
with counts beside each digest so a failure reads as a diagnosis. Opt-in regeneration
(`UPDATE_PDF_BASELINE=1`), all-or-nothing writes, a key-set drift guard.

Two PDF-specific design points the XML baseline does not face, and the second changed during
implementation. It is built through `compare_pdfs`, not a reassembled chain. And it pins
**all 23 adjacent pairs, including the 6 production declines**, rather than only the 17
accepted ones as this section originally proposed. Pinning only the accepted set would make
the covered population depend on a production decision nothing checks: a regression in
`_MIN_NUMBERED_RATIO` or `_MIN_LINES_FOR_GUARD` would silently move which pairs are covered
while every remaining digest still matched. The declines are recorded as
`{"declined": true}` with their user-facing message, and the population is derived by
*attempting* the comparison and catching `UnsupportedLayoutError` — public surface only, so
the gate cannot drift from the predicate it describes, and no new private reach-around joins
the tangle #62 tracks.

**Gate 2 — `tests/test_pdf_matching_boundary.py`.** The split rule and the move rule,
transcribed independently and checked against production over the corpus, following
`tests/test_assignment_classification_boundary.py`'s constraint: "It exists to disagree with
production… this must never be replaced by a call to [the production helper], and production
must never import it."

The transcription checks three invariants over emitted hunks rather than re-deriving the
whole opcode walk: every surviving pair clears the split cutoff; every `moved` hunk clears
the move cutoff; and no `modified` hunk satisfies the transcribed moved rule. The third is
the sharp one — a `modified` hunk whose anchors differ and whose bodies clear the move cutoff
is precisely what `_hunk_for_paired_blocks` should have labelled `moved`.

**Gate 4 — the split population**, in the same module. A real below-cutoff split on
118-hr-4366 v4→v5, asserted as a floor rather than an exact count (an exact count would turn
a legitimate retune into a fixture edit), plus a synthetic pair either side of the cutoff so
the rule is pinned off-corpus too.

**Gates 5–7 — the three controls of §6.4**, in
`tests/test_pdf_observation_emission.py` (gate 5) and `tests/test_pdf_matching_boundary.py`
(gates 6 and 7).

**Gate 3 — every gate carries its own falsification, permanently.** Not a one-off probe: each
rule is paired with a test applying a NAMED mutation and asserting the result changes, so if
a future refactor makes a mutation stop mattering, the mutation test says so. §6.5 records
the whole-suite falsification against the four production mutations.

### 6.4 Three more controls, each with its falsifying mutation named

A second independent review of this same question (a differently-trained model, given the
same brief and the same repository) proposed a control set built the right way round: each
control states the concrete mutation that must turn it red. Three of its cases cover
decision sites gates 1–4 reach only incidentally, and they are adopted here. Cross-model
review is the repository's own practice for consequential calls, and the value showed up
exactly where a single reviewer is weakest — in the controls for one's own conclusions.

**Gate 5 — the ordinal addresses the complete population.** **Mutation: assign ordinals after
filtering. Required: red.** This is the control §4.2a's finding needs and gates 1–4 do not
supply — a canonical digest is blind to a renumbering that happens to preserve the output,
which is precisely how the filtered-view hazard would survive slice 2.

Built as `tests/test_pdf_observation_emission.py`, and the shape changed once §4.2a was
corrected. The review that proposed it assumed the pre-filter sequence was the emitted one,
so its fixture asserted that an excluded observation keeps its ordinal. That is the wrong
rule for PDF: the post-filter sequence *is* what the parser emits (§4.2a). What the module
therefore pins is the emission rule itself — the sequence is exactly the blocks
`_group_into_blocks` returns, in order, complete, non-overlapping and stable across
re-derivation — together with the measurement that justifies it, that all 190 dropped blocks
stay addressable three independent ways. The mutation survives intact in the corrected form:
indexing a plausible filtered view (the section-anchored observations) is shown to address a
*different* observation at the same ordinal.

**Gate 6 — the positional `replace` rule is pinned.** Construct a `replace` region where
global best-similarity pairing would cross (`old1↔new2`, `old2↔new1`) but legacy behaviour
pairs positionally (`old1↔new1`, `old2↔new2`). **Mutation: replace the positional rule with
global best-similarity assignment. Required: red.** This is the sharpest available test of
§9's claim about the `replace` zip, and the specific guard against a future "reuse the XML
assignment helper" changing PDF policy at the one site where the two genuinely disagree.

Built, and the fixture had to be tuned against real scores rather than designed ones. The
first attempt was symmetric — all four cross-similarities tied at 0.9429 — so positional and
crossed scored identically and it discriminated nothing. The committed version carries an
8-word shared head, giving positional 0.596 against crossed 0.913: clear enough above the 0.4
split cutoff that production *keeps* the positional pair (so round 2 never runs and the gate
tests the positional rule rather than the split rule), and far enough below the crossed score
that global-best assignment visibly crosses. Both preconditions are asserted in the test, so
the fixture cannot rot into a tautology.

**Gate 7 — greedy competition is pinned, four ways.** Two removals against two additions with
competing scores. **Mutations, one at a time: remove exclusivity; change settlement ordering;
let each candidate independently pick its best partner; change tie handling. Required: at
least one changes the frozen link set.** §3.3 measures that competition is live (16 contested
removals, 17 contested additions, 23 ties) but nothing currently pins how it resolves.

Note what §5.3's tiebreak measurement does and does not do for gate 7. It shows the *legacy
positional key* is inert on PDF, so that particular substitution needs no guard. It says
nothing about the other three mutations, and exclusivity in particular is unpinned: 49 of 194
candidates lose to it.

Built, and two of the four mutations were wrong on the first attempt in ways worth recording,
because each is a shape in which the gate would have passed while testing nothing.

*Collapsing all four scores onto one value does not isolate the tiebreak.* With every
candidate tied, exclusivity still admits two disjoint pairs and an ascending sort selects the
same set, so the experiment reports "no change" for a rule that does matter. The tie has to
be placed on the **contested partner** — tie `X→P` against `Y→P` only — and the mutation must
flip **only the index component** of the sort key, not sort everything ascending: on this
fixture the remaining scores reorder to compensate and the selected set comes out identical
either way.

*The tie mutation cannot be compared against production's untied selection.* It perturbs the
scores as well as the rule, so the correct control is production's rule applied to the tied
fixture. Compared against the untied selection the two coincide here, which would have
reported a failure that meant nothing.

The committed fixture asserts four **distinct** scores as a precondition, so a future drift
into a tie cannot silently merge the ordering and tie-handling mutations into one experiment
while both still pass.

**A rule for running all seven.** Once a gate is frozen and its preservation artifact is in
place, do not modify the apparatus in response to a surprising result. If a new
implementation disagrees with frozen legacy evidence, record the disagreement, identify which
invariant failed, and decide whether the implementation or the methodology is wrong — do not
quietly move a threshold, a fixture or an expected output to make the migration green. This
is the confirmatory-execution discipline the PDF backend bake-off already runs under
(`docs/research/pdf-backend-bakeoff/PRE-REGISTRATION-CONFIRMATORY.md`); it applies here for
the same reason, and it is the second reviewer's contribution.

---

### 6.5 Slice 0 falsified — the same four mutations, before and after

The four production mutations of §6.2.1, re-run against the suite with the gates in place.
Same harness, same PDF-only rebinding, same live-value proof each run.

| production mutation | before slice 0 | after slice 0 | gates that fired |
|---|---|---|---|
| `SIMILARITY_THRESHOLD` → 0.45 | 3227 passed | **2 failed** | canonical baseline ×2 |
| `SIMILARITY_THRESHOLD` → 0.35 | 3227 passed | **8 failed** | canonical baseline ×4, transcribed split rule ×4 |
| `MOVE_THRESHOLD` → 0.65 | 3227 passed | **2 failed** | canonical baseline ×2 |
| `MOVE_THRESHOLD` → 0.55 | 3227 passed | **2 failed** | canonical baseline ×1, transcribed move rule ×1 |

Clean baseline with the gates in place: **3527 passed**, and the tree restored clean after
every run.

Three things worth reading off this beyond "it goes red now".

**The failures land on exactly the pairs the replica predicted.** §6.2's replica said
`similarity −0.05` moves 4 of 17 pairs and named them; the gate fails on 115-hr-5895 v3→v4,
118-hr-4366 v3→v4 and v4→v5, and 118-hr-8774 v1→v2 — the same four. `similarity +0.05` and
`move +0.05` were predicted to move 2, and fail on 2. That is the replica and production
agreeing on a population neither was fitted to, which is the corroboration §6.2.1 could not
supply on its own.

**Both gate families fire, and on different mutations.** The canonical baseline catches every
mutation that moves a committed pair. The transcribed oracle catches two it would not have
caught alone — and the move-rule failure is the sharp direction by design: under
`MOVE_THRESHOLD` → 0.55, production labels a pair `modified` that the independently written
rule says is `moved`. A gate that only re-asked production what the rule is could not see
that.

**The counts are not symmetric, and that is informative.** `similarity −0.05` produces four
times the failures of `similarity +0.05`, because lowering the split cutoff keeps pairs
together that were previously split, which moves both the digests *and* the transcribed
invariant. Raising it only moves digests.

### 6.6 A source conflict found while building the gates

**Production's admissibility decision has no public accessor.** `compare.pdf` refuses an
unnumbered layout via `_is_unnumbered_layout`, which is private, so a gate that wants to
restrict itself to the pairs a user can actually reach has three options and no good one:
reach into the private predicate (another cross-module private import, which is the tangle
[#62](https://github.com/AgoraDMV/DeltaTrack/issues/62) tracks), call `compare_pdfs` and
catch `UnsupportedLayoutError` (correct, but pays for a full comparison), or invent a proxy.

This is not hypothetical: the boundary module's first version invented a proxy —
`len(cached_pages(...)) > 1` — and it was wrong **in both directions**. It let all six
declined pairs through, because an enrolled print has plenty of pages and what it lacks is
line numbers, and it dropped one legitimate pair whose old side is a one-page shell bill. The
docstring asserted it excluded the declines, so the module carried a false claim about its
own coverage. Caught by checking the proxy against the real predicate rather than by any
test, which is itself the point: nothing would have failed.

Resolved per gate rather than papered over. Gate 1 needs the full comparison anyway, so it
attempts it and catches the refusal — public surface only, and it pins the decline as
behaviour. The boundary module dropped the filter entirely, because the rules it transcribes
are invariants of `diff_pdfs`, and admissibility is decided a layer above; a refused pair
still exercises them. The division is now explicit: **gate 1 covers what a user can reach,
the boundary module covers what the differ must always do.**

The underlying seam stands as a finding for the eventual `bill_diff` resolver (§7.5): source
admissibility is product-facing behaviour with no public way to ask about it.

## 7. Where forcing XML/PDF symmetry would be wrong

### 7.1 `match_path` has no PDF counterpart — **STOP**

XML retrieval groups by `match_path`, an exact structural key: two nodes with the same path
are candidates, two with different paths are never scored. The PDF equivalent would be the
breadcrumb — which is *detection-path dependent*. `_breadcrumb_core`'s own docstring:
"Breadcrumb DEPTH is detection-path dependent: major/agency/grouping parents exist only on
the size path, so a low-coverage/no-band bill has no account level at all… Consumers must
not assume a major, agency or account segment is always present."

So a PDF path key would change *depth* between two versions of the same bill purely because
one version's glyph-size coverage crossed `_COVERAGE_MIN` (0.85). Grouping on it would
partition the two sides differently for a reason that has nothing to do with the
legislation. `_block_key` avoids this by using only the anchor's own text plus body content.
That is not a shortcut; it is the correct choice given the signal.

### 7.2 XML has a division matching key; PDF deliberately does not — **RESEARCH FIRST**

`Anchor.division` is documented as "A DISPLAY field only — it is prepended as the leftmost
breadcrumb segment but never enters block matching (mirroring the XML `division_label`,
which sits in display_path, not match_path…)".

The mirror is exact for `division_label` — and incomplete, because XML separately carries
`division_key`, and `_match_collision_group` sub-groups collisions by it (#468, which fixed
nodes "silently pairing across divisions"). PDF has no equivalent, so nothing prevents the
same pairing on the PDF side.

The census gives this teeth: `_block_key` produces **525 duplicate keys across 796 blocks**,
concentrated exactly where divisions are (119-hr-1: 149 duplicates in 1,303 blocks;
114-hr-2029 reported-in-senate: 82 duplicates across 160 of 338 blocks — 47 % of the
document). Duplicate keys are where a cross-division mispairing would live.

**This is a research question, not a finding.** Duplicate keys are a necessary, not
sufficient, condition: `SequenceMatcher` is order-aware, so a duplicate key does not by
itself produce a wrong alignment. Whether any cross-division mispairing actually occurs
needs measuring — and it must be measured before anyone "adds division to `_block_key` for
symmetry with XML", which would be a matching-policy change dressed as an architectural one.

### 7.3 `unchanged` is not a PDF record

XML emits an `unchanged` `NodeDiff` per matched node and drops it at projection. PDF emits
nothing (2,437 suppressions). §5.2 covers the mechanics; the point here is that the
difference is in *output policy*, not in correspondence, and unifying it would move
canonical bytes.

### 7.4 Move record order differs

XML classification sorts on round, so moves append at the end. PDF emits the move at the
removed hunk's original index. Both are "classification output policy" (ADR 0020's phrase);
neither is more correct; changing either moves every `c-XXXX` canonical id after it.

### 7.5 The admissibility guard is not a matching stage

`_is_unnumbered_layout` is source resolution, and it is where the eventual
`bill_diff <v1> <v2>` command's "no common supported source" failure belongs. Its residual
is already documented in `compare/pdf.py`: a document under 50 lines is exempt and will
still diff to one anchorless block. Worth carrying into the resolver design; out of scope
for matching.

---

## 8. Recommended migration sequence

Each slice is behaviour-preserving, independently falsifiable, and small enough that its
gate can be shown to fire before it lands. Slice 0 is not optional — §6.2 is the reason.

| slice | change | acceptance |
|---|---|---|
| **0** | **DONE.** Gates 1–7 built (§6.3, §6.4); no production change. | Falsified against the four production mutations — §6.5. |
| **1** | **DONE** (`63d569e`). Moved `_flatten`, `_rejoin_cross_page_hyphens`, `_group_into_blocks`, `_strip_heading_lines` and their types from `diff_pdf` to `parsers/pdf_blocks.py`, unchanged. | Gate 1 byte-identical; 9/9 moved definitions byte-identical to source; no `parsers/* -> diff_pdf`. |
| **1a** | **DONE** (`d6d515b`). Dependency repair the slice 1 review exposed: move `DOLLAR_RE`, `AMENDMENT_RE`, `extract_amounts` to the source-neutral `deltatrack/amounts.py`, so observation production no longer reaches a differ (§4.2c). | Gate 1 byte-identical; closure measured 8 modules -> 4; new conservation invariant red under a broken money detector (`a54bf61`). |
| **2** | **ALREADY DONE by slice 0's gate 5.** `tests/test_pdf_observation_emission.py` states the emission rule (the post-filter block sequence) and pins completeness, order, non-overlap, stability and the ordinal hazard. No further production work; slice 2 is a plan-state closure, not an implementation slice. | Gate 5 red under "assign ordinals after filtering"; and, since 1a, red under a broken money detector. |
| **3** | **DONE** (`142f7cd`). `PdfObservation` + `PdfObservationRegistry` + `pdf_parser_revision()` in `deltatrack/pdf_observations.py`. Nothing consumes them; no stored artifact records a PDF ordinal. | Gate 1 byte-identical (356 passed / 1 skipped, unchanged). Revision moves on any of the four parser modules and on the engine version, and does not move on `diff_pdf` / `similarity` / `matching` / `diff_bill`; the exclusion is proved non-vacuous by injecting a matcher import into `pdf_blocks` (§8.1). Registry totality, contiguity and round-trip over 23 corpus pairs, red under both a filtered and a re-sorted sequence. |
| **4** | **DONE** (`5dac421`). `pdf_unmatched_population` → `retrieve_pdf_move_candidates` → `pdf_move_evidence` → `assign_pdf_moves`, plus `settle_pdf_correspondences` and `classify_pdf`, with round 2 moved **before** classification. `_emit_pair` now appends provisional pairings instead of classified hunks. This is the PDF #591. | Gate 1 byte-identical; a whole-output comparison against an independently transcribed pre-slice-4 pipeline agrees on all 23 adjacent pairs, including the six the baseline cannot cover. Four fault injections, two of which were informative no-ops (§8.3). |
| **5** | **DONE** (`9eebcc5`, evidence-floor repair `61cc3fa`). `_pdf_similarity_signals` → `pdf_similarity_correspondence_evidence` → `pdf_pairing_survives_similarity_rule` → `apply_pdf_similarity_revocation`, mirroring `diff_bill`. `_align_blocks` is retrieval only; `_AlignedPairing` loses its similarity field. | Gate 1 byte-identical; gate 4 unchanged. Threshold sweep at 0.2/0.3/0.4/0.6/0.9 → 192/214/230/257/402, plus a corpus-wide exact-overlap invariant (§8.4, §8.5). The first version shipped a censored evidence floor that the original 0.0/0.4/0.99 sweep could not see — §8.5. |
| **6** | Move the moved-vs-modified decision out of classification. Because 20 of 165 PDF moves are *not* round-2 provenance (§3.4), this needs assignment to record *why* a pair corresponds, not a classification threshold. **Design work, not extraction.** | Requires §10 Q2 answered first. |
| **7** | Wrap round-1 (`_block_key` + `SequenceMatcher` + the positional `replace` zip) as a source-specific **retriever** emitting a `CandidateSet`, preserving its exact candidate population. No longer architecture-blocked (§9, corrected). | Gate 1 byte-identical; gate 6's crossing fixture red under global best-similarity assignment. |

Slices 1–5 are wrap-and-extract with a byte-identical gate. Slice 6 changes semantics and
owes precision/recall evidence under ADR 0020's second implementation rule. Slice 7 is
bounded by §9's limitation rather than blocked by it.

**State: slices 0, 1, 1a, 2, 3, 4 and 5 complete. Slice 7 is next.**

Slice 7 before slice 6, on the reviewer's recommendation: slice 7 is still behaviour-preserving
extraction, slice 6 is the semantic moved-vs-modified decision, and completing round-1
`CandidateSet` retrieval first removes that unfinished variable before the policy call. Slice 7
must use develop's *current* B2 staging as its reference — `CandidateSet` admission is now
load-bearing before evidence there.

### 8.1 Slice 3's controls, and the faults that proved each one fires

A revision mechanism is two claims in opposite directions, and the exclusion half is an
absence assertion — the shape that passes vacuously. Each control below was therefore run
against a deliberately broken implementation, restoring the source afterwards.

| fault injected | what should go red | result |
|---|---|---|
| registry numbers only anchored blocks (a filtered view) | totality | red — `new: registry holds 0 of 1 blocks` |
| registry reverses each side (a re-sorted view) | address round-trip | red on 6/6 selected pairs — `block 0 addressed as ordinal 195`. Contiguity still passed, which is the point: only the round-trip assertion separates the two. |
| closure walk stops at the entry module | inclusion, and the exclusion's own control | red ×5 — the closure floor, the three transitive members (`amounts`, `pdf_anchors`, `pdf_text`), and the matcher-import control |
| closure walked from `diff_pdf` instead of `pdf_blocks` | exclusion | red ×6 — the exclusion list and all four matching-only mutation cases |

The third and fourth are the pair that matters. Without the third, every "X is not in the
closure" assertion would be satisfied perfectly by a walker that finds nothing; without the
fourth, the exclusion would never have been shown capable of failing at all.

Two things slice 3 deliberately did **not** do, recorded so they are not read as oversights.
`tests/pdf_corpus._extractor_fingerprint` is untouched (§4.2c: it identifies a different
payload). And no cross-process determinism study was launched: the property that would need
it — a stored PDF ordinal — is not introduced here. The *revision* is cross-process stable and
tested under two hash seeds, because a stored artifact will record it and a per-process value
would be unverifiable by construction.

### 8.2 Two guard defects the slice 3 review found, and how they were closed

Both were in the *guards*, not in the production implementation, which the review approved
unchanged. Recorded because each is a defect class that recurs.

**The revision controls mutated the checkout.** The four faults above were run by hand against
production and restored, which is fine for a one-off. The committed tests did the same thing,
and the suite runs `-n auto`: two workers interleaving save/write/restore on one file can leave
a worker asserting against another's mutation, restore over one, or leave the tree dirty. The
green full run reported at handoff did not retire that — worker scheduling decides. Each
mutating test now copies `src/deltatrack` into its own `tmp_path` and monkeypatches
`pdf_observations._PACKAGE_ROOT` at the copy, so the **real** closure walk and digest run
against a tree the test owns. Because that is a copy of the thing under test, it proves it is
still the same thing before use: byte-identical tree, closure resolving only inside the copy,
and the copy's revision equal to the checkout's. An autouse fixture digests the real package
before and after every test in the module and fails the test that wrote into it; demonstrated
to fire by a throwaway test that appended to `amounts.py` without restoring.

**The `amounts.py` vocabulary exemption was too wide.** Allowlisting the module whole exempted
it from the ADR 0018 structural-vocabulary scan, and `amounts.py` is the one allowlisted module
a structural parser consumes result-bearingly (`_is_strippable_heading_line`). So a genre
trigger added there would make the emitted observation sequence depend on appropriations
English while the gate stayed green — ADR 0019's revision would move, recording the change
without objecting to it. The exemption is now narrowed to the
`(increased|reduced|decreased) by $X` amendment annotation it was granted for, with the
remainder required to be empty and the guard falsified by running the real rule over the real
source plus `necessary expenses`.

### 8.3 Slice 4's controls, and two faults that turned out to be no-ops

| fault injected | what should go red | result |
|---|---|---|
| staged assigner sorts ascending instead of descending | move selection | red — 3 pairs in the new oracle, the same 3 in gate 1 |
| population re-sorted by ordinal instead of stream order | the ``(ri, ai)`` order | **no-op** — see below |
| population drops text-free unmatched blocks | population membership | **no-op** — no committed pair produces one |
| population drops the first unmatched old block | population membership | red — 17 pairs in the projection test, 6 in the output oracle, and the round-2 floor (166 moves → 20) |

**The two no-ops are findings, not failed controls.** Re-sorting by ordinal changes nothing
because the population is *already* in ordinal order: `SequenceMatcher` yields opcodes in
ascending `(i1, j1)`, and each opcode walks its blocks in ascending index, so the pairing
stream visits each side's blocks in ordinal order and filtering preserves that. This
structurally re-confirms §5.3's finding that PDF's legacy positional tiebreak is inert against
block ordinals — the two orders cannot disagree, where XML's demonstrably can (#590 measured 3
corpus pairs moving). The second no-op restates what `_reconcile_moves`' own docstring already
said: `_strip_heading_lines` never empties a body, so no PDF pair reaches the text-free state
#357 exists for on the XML side.

**The last fault is what shows the two preservation tests fail apart**, which is why both
exist: the projection test caught it on 17 pairs and the whole-output oracle on 6. An output
comparison alone would have accepted a population derived differently whenever the selected
links happened to coincide.

One structural note for slice 5. `_reconcile_moves` is retained, unchanged and off the
production path, as the preservation oracle; `test_pdf_matching_boundary` exercises round-2
competition and its four named mutations *through it*. It must not be rewired to delegate to
the new stages — that would turn the gate from an oracle into a helper, unable to detect the
one failure the extraction can have. `test_the_production_path_does_not_run_the_legacy_reconciler`
monkeypatches it to raise and runs a real comparison, so "off the path" stays executable.

### 8.4 Slice 5's control, and why gate 4 could not be it

Gate 4 pins the split *rule* against an independently transcribed oracle, over the corpus and
at two synthetic points either side of the cutoff. It establishes **what the rule is**. It
cannot establish **which code applies it**, because it runs `diff_pdfs` end to end with the
production constant — one number reaching one behaviour, with no way to separate a rule reading
its parameter from a rule reading `SIMILARITY_THRESHOLD` directly.

So slice 5 adds the control gate 4 structurally cannot give: move the threshold at the stage
boundary and watch the split population respond, corpus-wide.

| threshold | revoked pairings |
|---|---|
| 0.0 | 0 |
| 0.4 (production) | 230 |
| 0.99 | 813 |

Aggregated over the corpus rather than one pair, deliberately: a single pair can have every
non-identical pairing already below production's cutoff, in which case raising the threshold
changes nothing there and the control reports a false alarm. That happened on the first draft.

Three fault injections, each caught by a different control:

| fault injected | what went red |
|---|---|
| the rule reads `SIMILARITY_THRESHOLD` instead of its parameter | the threshold sweep **only** — baseline and gate 4 stayed green |
| the identical-text short-circuit removed, ratio computed instead | the monkeypatched short-circuit test **only** — the verdict is unchanged, so no output gate can see it |
| the two replacement records emitted addition-first | 11 baseline pairs, 14 oracle pairs, and the unit case |

The first two are the argument for this module existing: both are invisible to every gate that
compares output, because neither changes any output. The third confirms the "adjacent and in
place" ordering is load-bearing rather than incidental.

### 8.5 The hidden evidence floor, and the sweep that could not see it

**The first version of slice 5 shipped a false green, and the sweep above was part of why.**
`_pdf_similarity_signals` computed non-identical evidence with
`text_similarity_at_least(..., SIMILARITY_THRESHOLD)`, which returns `0.0` rather than the true
ratio below its bound. That put a correspondence cutoff inside the *evidence*, so the
assignment threshold was not the sole authority ADR 0020 requires it to be:

| | |
|---|---|
| true overlap | 0.30 |
| recorded `word_overlap` | **0.0** |
| revocation at threshold 0.20 | **revoked** — but 0.30 ≥ 0.20 says keep |

The original sweep ran 0.0 / 0.4 / 0.99 and passed throughout, because **a censored `0.0`
fails a `>= 0.0` test exactly as a true `0.0` does**. Using 0.0 as the only sub-production
point made that endpoint accidentally compatible with the very floor it should have exposed.

**The gate was removed rather than made honest-but-censored, and the cost was measured before
the choice rather than after.** Exact similarity for every non-identical aligned pair costs
**+0.9%** on a full-corpus `diff_pdfs` sweep (5.552s → 5.600s over 23 pairs), inside the 3.2%
run-to-run spread, with byte-identical output. The gate saved little because the identical-text
short-circuit already removes the large majority of pairs before it — that is the population
XML's equivalent gate is actually paying for. Corroborated independently and long before this
slice: gate 4's transcribed oracle has always used exact `text_similarity` and has always
agreed with production at 0.4.

The alternative the review left open — keep the gate, record the censored fact honestly, and
have assignment fail closed below the floor — was rejected as more machinery for a 0.9% saving:
a third signal, a floor parameter and an undecidable branch, to preserve an optimization that
measurement says is not there.

`SIMILARITY_THRESHOLD` now has exactly one executable use in `diff_pdf`: the
`apply_pdf_similarity_revocation` call in `diff_pdfs`.

The revised controls catch both failure modes, proved by reintroducing the censoring:

| control | caught the censoring |
|---|---|
| sweep at 0.2 / 0.3 / 0.4 / 0.6 / 0.9, all-distinct and increasing | yes — 0.2, 0.3 and 0.4 all collapse to 230 under the floor |
| the 0.30 fixture, asserting the recorded value *and* both verdicts | yes |
| corpus-wide `word_overlap == text_similarity` for every non-identical pair | yes |
| PDF canonical baseline | **no** — the defect changes no output |

Measured sweep: 0.2 → 192, 0.3 → 214, 0.4 → 230, 0.6 → 257, 0.9 → 402.

### 8.6 230 versus §3.2's 224, reconciled

Partitioned by the committed canonical baseline's `declined` flag, which is where production's
admissibility verdict is already recorded:

| population | pairs | revocations at 0.4 |
|---|---|---|
| production-accepted | 17 | **224** |
| production-declined | 6 | 6 |
| total | 23 | **230** |

The 224 lands exactly on §3.2's figure, so the two numbers describe the same rule over
different populations and nothing further is outstanding. Pinned by
`test_the_revocation_population_splits_as_224_accepted_plus_6_declined` rather than left as a
plausible account.

---

## 9. Round-1 retrieval: a limitation, not a blocker

**This section previously claimed a source conflict. A second review falsified that claim,
and the correction is adopted.** What was argued: that PDF round-1 retrieval could not
become a `CandidateSet` behaviour-preservingly, because emitting only the aligned pairs
would make candidate recall "1.0 by construction". That reasoning is wrong, and the error is
worth naming because it is the kind that survives review by sounding rigorous.

**Candidate recall is measured against adjudicated true correspondences, not against the
retriever's own output.** ADR 0020 is explicit that the denominator is the population the
retriever *never formed* — "pairs the path grouping never forms produce no event to trace,
and those are the population candidate recall is about". So a true counterpart that
`SequenceMatcher` passed over, because a duplicate `_block_key` (§7.2) drew the alignment
elsewhere, is a candidate-recall **miss** and is measurable as one. Recall is not 1.0 by
construction; it is exactly the quantity materialising the candidate set exists to expose.

So the behaviour-preserving representation does exist:

```text
PDF observations
      ↓
alignment retriever  (_block_key + SequenceMatcher)
      ↓  proposals carry: alignment op, sequence position, key provenance
CandidateSet
      ↓
correspondence evidence  (word_overlap, anchor_text_equal)
      ↓
assignment  (the existing revocation rule, unchanged)
```

**The positional `replace` zip is retrieval, not assignment**, and §2 row 8 is corrected
accordingly. It decides which pair is *considered*; `_emit_pair`'s similarity rule can still
refuse the correspondence afterwards. That is precisely ADR 0020's line — retrieval controls
consideration, assignment controls correspondence — so the legacy round-1 rule reads as "an
aligned or positionally-proposed candidate survives unless the similarity revocation rejects
it". Behaviour-preserving, and it names each half correctly.

**What genuinely survives is a limitation, and it is worth stating.** The round-1 candidate
set is **exclusive by construction**: the aligner emits at most one candidate per
observation, so assignment has nothing to choose *between* and its only power is revocation.
The extraction therefore buys observability of round-1 recall, but not of round-1
competition, because there is none to observe. That is a real bound on what slice 7 delivers
— not a reason to defer it. Widening retrieval over the 525 duplicate keys, so that
assignment has a genuine choice, is a **matching-policy experiment for later**, owing
precision and recall evidence under ADR 0020's second implementation rule. It is not a
prerequisite for the architectural extraction.

Slice 7 is therefore unblocked and can run as a behaviour-preserving wrap, with gate 6's
crossing fixture (§6.4) pinning the positional rule against exactly the substitution a future
shared assignment implementation might make.

---

## 10. Blockers and open questions

**Blockers — implementation cannot start**

1. ~~**No PDF preservation oracle** (§6.2).~~ **RETIRED — slice 0 is built and falsified**
   (§6.3, §6.5). This was the only hard blocker after the two corrections below, so with it
   closed, slice 1 may begin.
2. ~~**Block formation lives in `diff_pdf`** (§4.2c), so no ADR 0019 parser revision is
   derivable for PDF.~~ **RETIRED — slice 1 (`63d569e`) moved it, and the dependency repair
   (`d6d515b`) finished the job** by moving the amount primitive out of `diff_bill` too. The
   closure is now measured at four modules, differ-free (§4.2c).
3. ~~**The emission rule is nowhere stated or tested** (§4.2a).~~ **RETIRED — gate 5 owns
   it.** `tests/test_pdf_observation_emission.py` states the rule and pins completeness,
   order, non-overlap, stability and the ordinal hazard, so slice 2 needs no production work.
   The 190 dropped blocks are correctly dropped; the sequence was never wrongly filtered.

**No hard blocker remains. Slice 4 is next.**

**Retired by measurement or correction, recorded so they are not re-raised**

- *PDF emission determinism as a hard blocker* — 53/53 in-process (§4.1). Only the
  cross-process/platform half survives, as Q3.
- *Empty blocks must become observations* — falsified: 190/190 stay addressable three ways
  (§4.2a).
- *Round-1 alignment cannot become a `CandidateSet` behaviour-preservingly* — false; it can,
  and slice 7 is unblocked (§9).
- *Does `_group_into_blocks` filter for matching reasons?* — answered: it drops 190 blocks,
  all the DeltaTrack#96 coordinate collision, and correctly.
- *Is PDF's legacy positional tiebreak policy, as XML's is?* — answered: no, and structurally
  so (§5.3).

**Research questions — answer before the slice that depends on them**

- **Q1.** Does the round-1 alignment ever pair blocks across divisions? Necessary condition
  measured (525 duplicate keys); the mispairing itself is not. Blocks §7.2 and any proposal
  to add division to `_block_key`. → slice 7.
- **Q2.** What should a PDF `moved` mean? 20 of 165 are threshold verdicts on round-1 pairs,
  not provenance (§3.4). Either assignment records a reason, or PDF and XML keep two
  definitions of one canonical `change_type`. → slice 6.
- **Q3.** Is PDF emission deterministic **across processes and platforms**? §4.1 establishes
  in-process only; the glyph-size sidecar reads FFI floats. → before any stored PDF ordinal.
  This is the surviving half of what a second review called its only hard ADR-level blocker;
  the in-process half is measured and closed. **Slice 3 does not trigger it**: the registry is
  run-local and writes nothing, so no artifact yet depends on reproducing an ordinal in another
  process. The revision half *is* cross-process tested (§8.1) — the question that survives is
  about the ordinal, not the digest.
- **Q4.** Are any of the 23 both-sided-money splits wrong? Unadjudicated, like XML's 27. This
  is the ground-truth work, not the refactor's. → informs whether slice 5 should be followed
  by a policy change.
- **Q5.** What should round-1 PDF retrieval be (§9)? Needs a candidate-recall measurement
  over a wider candidate set. → slice 7.

**Cheap, unblocking, and worth doing regardless**

- `test_pdf_corpus_smoke.py` runs 6 pairs production declines. Either restrict it to the
  accepted population or assert the decline explicitly — right now it certifies a path no
  user reaches.
- ADR 0019 open question 2 can be closed for the in-process case, citing §4.1.

---

## 11. Recommendation on what the eventual common engine shares

**Contracts: yes. Retrieval: no. Assignment: eventually. Classification: no.**

| layer | share | why |
|---|---|---|
| `ObservationRef`, `Candidate`, `CandidateSet`, `CorrespondenceEvidence`, `Correspondence`, `CorrespondenceSet` | **Yes** | Already source-neutral by construction and by an enforced import ban. Nothing in `matching.py` needs to change to admit PDF. |
| Retrieval | **No** | XML groups by an exact structural key; PDF aligns two sequences. §7.1 shows the XML key has no sound PDF analogue. ADR 0020 already permits source-specific retrieval. |
| Correspondence evidence *signals* | **Partly** | `word_overlap` is common. `anchor_text_equal` is PDF's; `path_equal` is XML's. Share the vocabulary mechanism, not the vocabulary. |
| Assignment | **Eventually — the greedy competition only** | §5.3 shows the two loops are the same shape and the apparent normalization difference is measurably inert. Blocked on a second consumer existing, not on doubt. The round-1 rules stay separate: XML's collision resolution and PDF's positional `replace` zip are different problems. |
| Classification | **No** | Different record types, and `moved` means different things (§3.4). Share the boundary rule and its tests. |
| Canonical projection | **Already shared at the contract** | Two producers, one schema, one renderer (ADR 0007). Leave it. |

Restated as the ask framed it: **common contracts, source-specific retrieval, partly shared
evidence, eventually-shared round-2 assignment, separate classification, common
canonicalization.** That is close to the shape the ask anticipated — but the two places it
differs are the load-bearing ones. Retrieval is not merely "source-specific in policy"; on
PDF it is a different *kind* of operation (§9). And classification cannot be shared, because
`moved` is not one concept across the two pipelines.

**On the risk of accidentally building a second independent matcher:** the present danger is
the opposite one. Nothing is being built. What exists is a fused PDF matcher with no
preservation gate, and the cheapest way to end up with two permanently independent engines
is to extract PDF stages against tests that cannot fail — because then no later unification
can ever be shown to preserve anything. Slice 0 is the anti-divergence measure.

---

## Relationship to other records

- **[ADR 0020](../../decisions/0020-matching-stages.md)** — the model. It explicitly defers
  "whether XML and PDF share one assignment implementation"; §11 is evidence toward that
  decision, not the decision.
- **[ADR 0019](../../decisions/0019-observation-identity.md)** — §4.1 answers its open
  question 2 for the in-process case; §4.2 shows what PDF must change to satisfy invariant 2.
- **[ADR 0006](../../decisions/0006-canonical-diff-contract.md)** — unchanged. Every slice
  in §8 is byte-identical against it.
- **[ADR 0007](../../decisions/0007-single-renderer.md)** — why the canonical projection is
  already the convergence point, and why the two producers need not merge.
- **[ADR 0012](../../decisions/0012-pdf-heading-levels.md)**, **[ADR 0018](../../decisions/0018-text-triggers-are-financial-only.md)**
  — constrain what any new PDF signal may read. A structural evidence term may read format,
  never appropriations vocabulary.
- **[ADR 0021](../../decisions/0021-naming-authority-and-boundaries.md)** — governs the
  names proposed in §4.3 and §8.
- **#368** — §3.2 measures its PDF population for the first time.
- **#62** — slice 1 relieves part of the `diff_pdf` ↔ `diff_bill` ↔ `formatters` tangle.
- **#299** — §6.3's gate 3 is exactly the "prove a test can fail" problem it tracks.
