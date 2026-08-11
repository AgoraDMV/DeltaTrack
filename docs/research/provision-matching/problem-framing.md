# Naming the problem: matching provisions across versions of a structured document

Companion to `spike.md`. That doc measured *what works on our corpus*; this
one names the *problem class* and surveys the methodologies other fields already use for
it, then maps each back to our measured findings. Purpose: give us the vocabulary and the
menu of methods, so #170/#171 draw on a known literature instead of reinventing it.

## The one-sentence name

We are doing **entity resolution over an ordered, hierarchical document whose natural key
is unstable** — deciding which provision in version A is "the same provision" as one in
version B, when the obvious identifier (the section number) is *not* a reliable identity.

That sentence is three named problems stacked, each with its own literature:

1. **Hierarchical change detection / tree-to-tree correction** — the diff itself (find the
   minimum-cost edit script between two trees, including *moves*). Fields: XML change
   detection, AST/source-code differencing.
2. **Entity resolution / record linkage** — the *matching* step inside the diff (which old
   node corresponds to which new node). Fields: record linkage, deduplication.
3. **Natural-key instability / temporal entity resolution** — the specific reason our
   matching is hard: the section number is a natural key that gets *reused* for different
   content and *reassigned* (renumbered) for the same content across versions.

Our spike finding — "structure resolves 2 of 6 hard cases; the rest are a text dead zone"
— is *explained* by this framing: structural signals resolve identity when the natural key
is unstable **but the structure is stable**; when both the key and the structure are
ambiguous (a headerless section whose content was swapped in place), you fall back to pure
record linkage on text, where the state of the art is *not* raw word-ratio.

---

## Field 1 — Hierarchical change detection (the diff)

The canonical statement: given two trees, find the **minimum-cost edit script** (insert,
delete, update, **move**) transforming one into the other. Two model choices that matter
for us:

- **Ordered vs unordered trees.** Ordered = sibling order is significant; unordered = only
  ancestor/descendant relationships are. Appropriations bills are **ordered** (section
  sequence is meaningful, and renumbering is exactly a reorder), so we want ordered-tree
  diffing with *sequence alignment* over siblings — which is precisely why the spike said
  sibling position, if used, must be **LCS alignment, never absolute index**. [X-Diff /
  survey]
- **Move as a first-class action.** Line-based diff cannot express "this block moved";
  tree differs make move an explicit edit. This is exactly our `reconcile_moves`, and it is
  the single feature that separates structural diff from `difflib`.

Representative algorithms and what we borrow:

| algorithm | core idea | maps to us |
|---|---|---|
| **X-Diff** (Wang, DeWitt) | unordered XML diff; hashes subtrees; integrates structure with tree-correction | subtree signatures = a way to detect *unchanged* subtrees cheaply |
| **XyDiff** (Cobéna) | signature (hash) + weight (subtree size) per node; match biggest identical subtrees first, propagate down | "match the confident anchors first, then resolve the rest" — our unique-`match_path` fast path |
| **X-tree Diff+** | O(n) improvement, better edit-script quality | scalability reference |
| **GumTree** (Falleri et al., ASE'14) | **two phases: (1) top-down match of identical/isomorphic subtrees = anchors; (2) bottom-up match of *containers* by Dice similarity of their already-matched descendants; then derive move/update actions** | **This is the template for a tree-native rewrite of our matcher.** Our `match_nodes` is a degenerate GumTree: phase-1 anchors = unique `match_path` equality; we lack phase-2 container matching (matching a parent because its *children* matched) and treat collisions with greedy text similarity instead. |

**Takeaway:** GumTree's phase 2 is the piece we don't have and could most benefit from —
*match a container because its descendants matched, and match ambiguous leaves because
their container matched.* That bidirectional propagation is the structural signal the spike
found we're leaving on the table, and it degrades gracefully (it uses whatever structure is
present, which suits PDF's variable depth).

---

## Field 2 — Entity resolution / record linkage (the matching step)

Inside the diff, "which old node = which new node" is a bipartite matching / record-linkage
problem. The canonical framework is **Fellegi-Sunter**: for each candidate pair, combine
*multiple* field-level agreement/disagreement signals into a single match weight (a
log-likelihood ratio), and threshold *that*, rather than thresholding one field. Four ideas
map directly onto our findings:

1. **Blocking.** Never compare all pairs; partition into "blocks" of plausibly-matching
   records and only compare within a block. **Our `match_path` grouping and the
   division/collision sub-grouping ARE blocking.** The literature's warning is exactly our
   risk: *block on a stable key, because a bad blocking key silently drops true matches.*
   Which leads to —
2. **Multi-signal weighting instead of a single threshold.** Fellegi-Sunter combines all
   fields; the strong field (rare agreement) dominates. Our spike's structural classifier
   (account-path OR specific-header OR high text) is an *informal, hand-tuned* Fellegi-Sunter
   score. The principled version: score each pair on `{path-agreement, header-agreement,
   level-agreement, body-similarity}` with weights **calibrated on the #8 labels**, and
   threshold the combined score. This is the natural home for the #8 answer key.
3. **Rare-token / TF-IDF weighting** ("Soft TF-IDF" for entity resolution). Down-weight
   agreement on *common* tokens, up-weight agreement on *rare* ones. **This is the textbook
   name for our #171 "boilerplate-discounted similarity."** "None of the funds made available
   by this Act" is a high-document-frequency phrase that should count for almost nothing;
   two provisions agreeing on a rare statutory citation should count for a lot. The spike's
   dead-zone pairs (`contested-1/2/3`) share *only* boilerplate; a TF-IDF-weighted similarity
   would push them apart while keeping genuine edits (which share rare, specific content, like
   `Sec. 8144`'s stub→expansion) together. **This is the method the spike deferred to #171.**
4. **Greedy vs optimal assignment.** Our `_similarity_pair` and `reconcile_moves` are
   *greedy* (highest similarity first, claim-and-move-on). The optimal alternative is the
   **Hungarian algorithm** (minimum-cost bipartite assignment). Worth knowing but *not* our
   main lever: the literature reports greedy reaching ~93% of Hungarian with good inputs, and
   greedy is O(n) vs O(n³). Reserve Hungarian for small collision blocks where a globally
   consistent assignment matters; it will not fix the dead zone (that's a signal problem, not
   an assignment problem).

### The specific twist: natural-key instability

The reason our matching is hard has a name in temporal entity resolution: the **instability
problem** / **natural-key instability**. A natural key (here, the section number) is not a
stable identity because:

- it gets **reused** for unrelated content (two `Sec. 10012` in 119-hr-1; `Sec. 232`
  carrying a different provision across versions — our `contested-1/2/3` and the `anchor-diff`
  splits), and
- the same content gets **reassigned** a new key (renumbering: `Sec. 237 → 234`,
  `10012 → 10013` — our moves).

The standard remedy is *don't treat the natural key as identity* — use a **surrogate key**
and resolve identity from evidence at read-time. Our operational version of that: treat
`match_path` strictly as a **blocking key**, never as proof of identity, and let the
combined multi-signal score decide. This is exactly what the spike's "structural keep-
override, but never a pure path-equality keep" recommendation implements. (It is also why a
naive "same path → same provision" would be wrong, and why "different path → not the same"
would miss renumbers.)

---

## Field 3 — Schema matching / ontology alignment (combine name + structure)

Schema matching solves a close cousin: align elements of two schemas using *both* their
names and their structural position. Three canonical systems, one lesson each:

- **Cupid** (Madhavan, Bernstein) — explicitly **combines linguistic similarity (element
  names) with structural similarity (tree position)** into one weighted score. This is our
  recommendation in miniature: header (name) + account-path/level (structure) + body (name-ish).
- **COMA** (Do, Rahm) — **meta-matching**: run several weak matchers and *combine* their
  results, configurably. Argues you get robustness by *combining* matchers rather than
  hunting for one perfect signal — directly supports the spike's "no single signal wins;
  layer account-path, scoped-header, and text" conclusion.
- **Similarity Flooding** (Melnik, Garcia-Molina, Rahm) — **propagate** similarity through
  the graph to a fixed point: *if two nodes' neighbors are similar, they become more
  similar.* This is the same propagation idea as GumTree phase 2, from the matching side: a
  provision under a matched agency, next to matched siblings, is more likely the match. A
  candidate upgrade for our collision resolution.

---

## Field 4 — Domain-specific: legislative informatics

- **Akoma Ntoso** (OASIS LegalDocML) — the international XML standard for legislation.
  Relevant for two things: (1) it has an explicit vocabulary for what we detect —
  **active vs passive modifications** (a change one document makes to another, vs a change
  proposed within a document) and rich **point-in-time versioning** metadata; (2) its
  versioning model is the "surrogate key" answer to instability — stable element identity
  (`eId`/`wId`) carried across versions so provisions are tracked by a persistent id, not by
  their current number. We don't get those ids from GPO XML (that's our whole problem), but
  it names the target state and is a vocabulary worth adopting in the data model.
- Practical toolage (LexML Brazil, Laws.Africa, LEOS) works the same seam; none publishes a
  provision-matching algorithm we can lift directly, but they confirm the framing: identity
  is tracked by persistent element id where available, and reconstructed by matching where
  not.

---

## What the literature tells us to do (beyond the spike)

The spike's recommendations are consistent with the literature; the literature adds three
things and reframes one:

1. **Reframe the matcher as multi-signal entity resolution, not threshold tuning.** Replace
   the single body-similarity threshold with a **combined match score** over
   `{path-agreement, level, header-agreement, body-similarity}`, weights calibrated on the
   #8 labels (Fellegi-Sunter / Cupid / COMA). The #8 answer key stops being a pass/fail gate
   and becomes the *training/calibration set* it was implicitly built to be. This subsumes
   the spike's account-path and scoped-header rules as two terms in one scorer.
2. **Name and adopt the #171 fix: rare-token (TF-IDF / Soft-TF-IDF) similarity.** The
   dead-zone cases (`contested-1/2/3`) are the textbook failure of unweighted string
   similarity on boilerplate-heavy text. This is not a hack to invent; it is the standard
   record-linkage method, and it is the principled path to the four pairs structure can't
   resolve — *without* the floor-raise the spike measured as harmful.
3. **Consider GumTree-style container propagation** (phase 2 / Similarity Flooding) as the
   tree-native successor to `match_nodes`: match a parent because its children matched, and
   an ambiguous child because its parent matched. It degrades gracefully with available
   depth (good for PDF/ADR 0012) and is the structural signal we're currently not using.
4. **Reframe `match_path` as a blocking key, not an identity.** Treat the section number as
   an *unstable natural key* per the temporal-ER literature: use it to form candidate blocks,
   never to assert identity. This is already implicit in the spike; making it explicit in the
   data model (and, longer term, carrying a persistent provision id à la Akoma Ntoso `eId`)
   is the durable fix to instability.

**Net:** #170 is the "structural signals" slice of a **multi-signal entity-resolution
matcher over an ordered tree with an unstable natural key**. #171 is the "rare-token text
similarity" slice. Both are terms in one Fellegi-Sunter/COMA-style combined scorer; framing
them that way lets the #8 labels calibrate the weights instead of us hand-tuning thresholds
pair by pair.

---

## Sources

Hierarchical / tree diff:
- Falleri et al., *Fine-grained and Accurate Source Code Differencing* (GumTree), ASE 2014 — https://hal.science/hal-01054552/document ; scalable follow-up, ICSE 2024 — https://dl.acm.org/doi/10.1145/3597503.3639148
- Wang, DeWitt et al., *X-Diff: An Effective Change Detection Algorithm for XML Documents* — https://research.cs.wisc.edu/niagara/papers/xdiff.pdf
- *Change Detection in XML Trees: a Survey* — https://www.researchgate.net/publication/245636600
- *X-tree Diff+* — https://dl.ifip.org/db/conf/euc/euc2006/LeeK06.pdf

Entity resolution / record linkage:
- Binette & Steorts, *(Almost) All of Entity Resolution* — https://arxiv.org/pdf/2008.04443
- *Soft TF-IDF for entity resolution* — https://medium.com/enigma-engineering/improving-entity-resolution-with-soft-tf-idf-algorithm-42e323565e60
- Term weighting / TF-IDF & cosine similarity primer — https://burtmonroe.github.io/TextAsDataCourse/Tutorials/TADA-CosineSimTutorial.nb.html
- Instability problem (transient resolved ids) — https://www.bencode.io/posts/entity/ ; temporal conflicts — https://www.tigergraph.com/blog/why-temporal-conflicts-in-entity-resolution-cause-chaos/ ; natural vs surrogate keys — https://motherduck.com/glossary/natural-key/
- Hungarian vs greedy assignment (field-matching implementations & comparison) — https://github.com/setuc/Matching-Algorithms

Schema matching:
- Melnik, Garcia-Molina, Rahm, *Similarity Flooding* — http://ilpubs.stanford.edu:8090/730/1/2002-1.pdf
- Madhavan, Bernstein, Rahm, *Generic Schema Matching with Cupid* — https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/tr-2001-58.pdf

Legislative informatics:
- *Akoma Ntoso v1.0* (OASIS LegalDocML) — https://docs.oasis-open.org/legaldocml/akn-core/v1.0/akn-core-v1.0-part1-vocabulary.html ; overview — https://en.wikipedia.org/wiki/Akoma_Ntoso
