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
```

---

## Rulings

| # | Question | Ruling |
|---|---|---|
| 1 | Begin PDF stage extraction now | **STOP — no preservation oracle exists.** A ±0.05 change to either PDF matching cutoff passes the entire test suite. Measured, §6. |
| 2 | Can `_Block` become an ADR 0019 observation | **CHANGE.** Yes in substance, no as emitted: the sequence is filtered (190 blocks dropped) and the block former lives inside the differ, so "parser revision" would include the matcher. §4 |
| 3 | Is PDF emission deterministic (ADR 0019 open question 2) | **APPROVE.** 53/53 documents re-emit identical line, anchor and block sequences. §4.1 |
| 4 | Share `ObservationRef` / `Candidate` / `CandidateSet` / `CorrespondenceEvidence` / `Correspondence` | **APPROVE**, conditional on ruling 2. §5 |
| 5 | Share the assignment *implementation* | **RESEARCH FIRST.** The two greedy loops are provably the same shape (§5.3), but sharing means reshaping the XML side, which this thread must not do. |
| 6 | Share the classification implementation | **CHANGE — do not.** `moved` does not mean the same thing on the two pipelines, and three different PDF sites produce it. §3.4 |
| 7 | Adopt XML's `match_path` / `division_key` / node granularity for PDF | **STOP — source conflict.** §7.1, §7.2 |
| 8 | Is PDF's convergence point after Observation production | **CHANGE.** Mostly yes, with one genuine conflict: PDF's first retrieval round is a *sequence alignment*, which has no XML counterpart and cannot be expressed as a candidate set without also deciding what to do about its 525 duplicate keys. §9 |

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
| 8 | `replace` positional `zip` by index `k` | which block pairs with which inside a replace run | fused | **ASSIGNMENT** — competition resolved by position, consulting no evidence |
| 9 | `replace` surplus → added/removed | 1:0 / 0:1 | fused | **ASSIGNMENT** |
| 10 | `_emit_pair` identical texts → emit nothing | suppress unchanged | fused | **CLASSIFICATION** + an output policy XML does not share (§7.4) |
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

**(a) The sequence is filtered.** `_group_into_blocks` drops empty blocks — **190
corpus-wide**, up to 58 in one document. ADR 0019 invariant 2 is exact about this: "An
ordinal always addresses that complete sequence, never a filtered or re-sorted view",
and its consequences section calls indexing a filtered view "a genuine new hazard".
Indexing today's output would be that hazard.

The census confirms the code's own account of *why* they are empty: `blocks_dropped_empty`
equals `anchor_coord_collisions` exactly, document for document — every dropped block is the
SEC-inline run-in subsection collision (DeltaTrack#96 Seam #2), where a section anchor and a
subsection anchor share one `(page, line)`. So the drop is not arbitrary, and it converts
cleanly: **an empty block is a retrieval bound, not an absent observation.** Emitting it and
letting the retriever decline it makes the ordinal complete *and* moves an unrecorded filter
into the stage ADR 0020 says may bound consideration.

**(b) There is no identity to record.** A block's identity today is its position in the
post-filter list. `Anchor` carries `(page, line, kind, text, division)` but no id, and ADR
0019 already notes PDF "does not have [`element_id`] at all". `(page, line)` is *nearly*
unique — the 190 collisions above are the exception — so it is traceability metadata, not a
key.

**(c) The parser revision would have to hash the differ.** ADR 0019 requires a revision
"derived from the parser implementation, [changing] whenever code capable of changing the
emitted observations changes". For PDF that is `pdf_text.py` + `pdf_anchors.py` + the
pypdfium2 build **+ `diff_pdf.py`**, because `_group_into_blocks` and `_strip_heading_lines`
live there. Under that definition, editing the matcher changes observation identity, and
every stored artifact would quarantine on a matching change that touched no observation.
The repository already has the working half of this mechanism —
`tests/pdf_corpus._extractor_fingerprint` hashes `pdf_text.py` plus the pypdfium2 version —
which is why the fix is a move, not an invention.

**(d) The observation's text is already a transformation.** `_Block.text` is
post-`_strip_heading_lines`, so it is not the printed text and `page_range` bounds the
stripped body. Legitimate — a parser transforms — but it means an observation must carry
both, or provenance into the full-bill view degrades.

### 4.3 Proposed model

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

Mapped onto the ask's checklist:

| ADR 0019 / ask field | PDF answer |
|---|---|
| source identity | SHA-256 of the PDF bytes. Constant per side within one comparison, so — exactly as `matching.ObservationRef` argues for XML — it is a property of the comparison, not of each reference. |
| parser/extractor revision | content hash over `parsers/pdf_text.py` + `parsers/pdf_anchors.py` + the future `parsers/pdf_blocks.py` + the pypdfium2 distribution version. **Precondition: block formation must first leave `diff_pdf`.** |
| complete-sequence ordinal | index into `_group_into_blocks`' output **with the empty-block filter removed** (§4.2a). Anchors that resolve to no surviving line stay skipped — that is genuine extraction, and those anchors address nothing. |
| text / body | `_Block.text` |
| structural path or inferred hierarchy | `breadcrumb_for(anchor, all_anchors)`. Detection-path dependent by design: a low-coverage bill has no account level, so the chain is shallower. **Not currently used in matching at all.** |
| anchor / heading information | `Anchor.kind` + `Anchor.text` |
| page/range provenance | `page_range`, plus `line_span` into the flattened stream |
| other source-specific metadata | `Anchor.division` (display-only, §7.2); glyph size and `LineGeom`, which are consumed by anchor detection and never reach matching |

**The complete emitted sequence is the unfiltered block sequence.** Not the anchor stream
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

So sharing is genuinely available. It is still **RESEARCH FIRST**, because sharing means
making `_greedy_move_links` generic over the population type, which is a change to the XML
side — and this thread must not make one to accommodate a hypothetical PDF need. Record the
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

> **A ±0.05 change to either PDF matching cutoff passes the entire test suite.**

This is the blocking finding. ADR 0020's implementation rule — "Introduce the contracts
behaviour-preservingly before changing matching policy, with canonical JSON byte-identical
across the corpus on both pipelines as the acceptance criterion. That is enforcement, not
convention: a matching-policy change necessarily breaks a byte-identical gate" — is
currently **false for PDF**. The enforcement it relies on does not exist, and a PDF
extraction slice claiming behaviour preservation today would be citing gates that provably
cannot fail.

### 6.3 What to build first

**Gate 1 — a PDF canonical baseline** (`tests/test_pdf_canonical_baseline.py`), mirroring the
XML one: SHA-256 over `compare.pdf.compare_pdfs`' sorted-key JSON for all 17 accepted pairs,
plus counts so a failure reads as a diagnosis. Opt-in regeneration, all-or-nothing writes,
a key-set drift guard. Covers the pairs the current gates miss, and by construction responds
to every perturbation in §6.2 that moves any pair.

Two PDF-specific design points the XML baseline does not face. It must key on
**production-accepted pairs**, so the declined enrolled pairs cannot silently enter or leave
the pinned set. And it must be built through `compare_pdfs` — the public producer — not a
chain reassembled in the test, for the reason the XML baseline gives: a gate that
re-implements the composition can stay green while production's composition changes.

**Gate 2 — a transcribed-oracle boundary test**, following
`tests/test_assignment_classification_boundary.py`. That module transcribes the pre-refactor
XML rule and states the constraint that makes it work: "It exists to disagree with
production… this must never be replaced by a call to `pairing_survives_similarity_rule`, and
production must never import it." The PDF equivalent transcribes `_emit_pair`'s split rule
and `_hunk_for_paired_blocks`' moved rule as they stand today, and re-derives the current
change sequence independently.

**Gate 3 — prove both can fail.** ADR 0020 invariant 12 is called out as "a green-by-default
gate of the kind that has passed while checking nothing before (#299, #542)". Before either
gate is trusted, run it under each of the four §6.2 perturbations and record which fire.
That is the same measurement this probe already performs, so the evidence is a re-run rather
than new machinery — and the perturbations are the *known-bad fixtures* the absence
assertion needs.

**Gate 4 — a split-population case.** No committed fixture exercises a below-0.4 split. 224
occur on the corpus, 23 with money on both sides. Add at least one, and prefer a real one
from 118-hr-4366 v4→v5 (11 of the 23) over a synthetic `Page`.

---

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
| **0** | **Build gates 1–4 (§6.3).** No production change. | Each gate is shown to redden under the §6.2 perturbations. **Nothing after this proceeds until slice 0's gates have each produced a real failure.** |
| **1** | Move `_flatten`, `_rejoin_cross_page_hyphens`, `_group_into_blocks`, `_strip_heading_lines` from `diff_pdf` to `parsers/pdf_blocks.py`, unchanged. `diff_pdf` imports them. | Gate 1 byte-identical. Makes a parser revision derivable without hashing the matcher (§4.2c). Also relieves part of #62. |
| **2** | Emit the **complete** block sequence with the empty-block filter lifted into the caller. | Gate 1 byte-identical. The filter becomes an explicit, recorded retrieval bound; the ordinal becomes ADR-0019-legal. |
| **3** | Introduce `PdfObservation` + a `PdfObservationRegistry` mirroring `diff_bill.ObservationRegistry`. Nothing consumes it yet beyond address resolution. | Gate 1 byte-identical; totality and injectivity asserted, as the XML registry does. |
| **4** | Extract **round 2** only: `pdf_unmatched_population` → `retrieve_pdf_move_candidates` → `pdf_move_evidence` → `assign_pdf_moves`, and move it **before** classification. This is the PDF #591. | Gate 1 byte-identical; gate 2 (transcribed oracle) agrees. Sequencing is load-bearing — check the XML equivalent's finding that round 2 depends on round-1 revocation output. |
| **5** | Extract the `_emit_pair` split rule as `pdf_pairing_survives_similarity_rule` + `apply_pdf_similarity_revocation`, mirroring `diff_bill`. | Gate 1 byte-identical; gate 4's split case exercises it. |
| **6** | Move the moved-vs-modified decision out of classification. Because 20 of 165 PDF moves are *not* round-2 provenance (§3.4), this needs assignment to record *why* a pair corresponds, not a classification threshold. **Design work, not extraction.** | Requires §11 Q2 answered first. |
| **7** | Only then: name round-1 retrieval (`_block_key` + `SequenceMatcher`) as a retriever emitting a `CandidateSet`, and the positional `replace` zip as assignment. | See §9 — this is the slice with a real open design question. |

Slices 1–5 are wrap-and-extract with a byte-identical gate. Slice 6 changes semantics and
owes precision/recall evidence under ADR 0020's second implementation rule. Slice 7 is
blocked on §9.

---

## 9. Source conflict with "PDF converges after Observation production"

The assumption mostly holds: slices 1–5 all sit at or after observation production and reuse
common contracts. One part does not.

**PDF round-1 retrieval is a sequence alignment, not a candidate generator.** XML retrieval
is set-shaped: group by key, and every pair within a group is a candidate. PDF retrieval is
`difflib.SequenceMatcher` over two key sequences, which returns a *monotonic, non-crossing*
alignment. Its output is not "these pairs are worth evaluating" — it is one specific
matching, already chosen, with order as an implicit constraint no `CandidateSet` records.

Expressing it as a `CandidateSet` forces a choice that is a policy decision either way:

- Emit only the aligned pairs as candidates. Then the "retriever" has already assigned, and
  the candidate set has recall 1.0 by construction, which is exactly the unmeasurable shape
  ADR 0020 built the boundary to prevent.
- Emit a wider set (say, every pair sharing a `_block_key`, or a window around the aligned
  position) and let assignment choose. That is honest retrieval — and it changes behaviour,
  because the 525 duplicate keys (§7.2) mean the wider set contains pairs the alignment
  currently never forms.

There is no behaviour-preserving third option, which is why slice 7 is last and why this is
the one place the "converge after observations" framing does not simply apply. It is a
genuine design question about what PDF retrieval *should* be, and it should be answered with
candidate-recall measurement rather than by analogy to XML.

The `replace` opcode makes the same point concretely. 420 pairings are formed by positional
`zip` inside a replace run, with 115 old-side and 3,618 new-side surplus becoming removals
and additions. That positional choice consults no evidence at all — it is assignment
performed by `difflib`'s block structure. Naming it as assignment is right; giving it an
evidence-based rule instead is a behaviour change.

---

## 10. Blockers and open questions

**Blockers — implementation cannot start**

1. **No PDF preservation oracle** (§6.2). Slice 0. Everything depends on it.
2. **Block formation lives in `diff_pdf`** (§4.2c), so no ADR 0019 parser revision is
   derivable for PDF. Slice 1.
3. **The emitted block sequence is filtered** (§4.2a), so no ordinal is ADR-0019-legal.
   Slice 2.

**Research questions — answer before the slice that depends on them**

- **Q1.** Does the round-1 alignment ever pair blocks across divisions? Necessary condition
  measured (525 duplicate keys); the mispairing itself is not. Blocks §7.2 and any proposal
  to add division to `_block_key`. → slice 7.
- **Q2.** What should a PDF `moved` mean? 20 of 165 are threshold verdicts on round-1 pairs,
  not provenance (§3.4). Either assignment records a reason, or PDF and XML keep two
  definitions of one canonical `change_type`. → slice 6.
- **Q3.** Is PDF emission deterministic **across processes and platforms**? §4.1 establishes
  in-process only; the glyph-size sidecar reads FFI floats. → before any stored PDF ordinal.
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
