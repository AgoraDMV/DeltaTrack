# PDF heading identity — closed, implemented in `pdf_anchors`

Research note for [#524](https://github.com/AgoraDMV/DeltaTrack/issues/524). The study is
closed and its rule ships. This file is the durable summary; the investigative record —
round write-ups, probes, holdout draws and scorers, and the frozen-candidate apparatus —
was working material and was deleted at closure per AGENTS.md, "Research artifacts are
working material". It is recoverable from git history.

## The defect

A GPO account heading wraps across as many printed lines as it needs. The parser took the
heading run's **last printed line** as the account, so a wrapped heading was read as an
agency plus a fragment: it invented an agency the bill does not contain and filed the
appropriation under a non-name (`CORPORATION`, `PROGRAM ACCOUNT`, `FUND`). `#524` lists
fourteen confirmed cases on `118-hr-4820`, each verified against the bill's XML twin.

## The rule that ships

The account is the last **segment** of the heading run, not its last line.
`pdf_anchors._account_boundary_splits` decides each boundary in this order; the ordering is
load-bearing and first match wins:

| | condition | decision |
|---|---|---|
| C1 | upper line ends in a wrap hyphen | continue |
| C2 | caps-per-word(upper) >= 0.5 and caps-per-word(lower) < 0.5 | split — container above an account |
| C3 | geometry absent | split — fail closed |
| C4 | the next word would have fitted | split — the break was deliberate |
| C5 | near-full (>= 0.97) **and** condensed for this document (ratio <= 0.31) | split — the fit was manufactured |
| C5b | tracking absent, or the document median absent or <= 0 | split — fail closed |
| C6 | otherwise | continue |

Two evidence sources feed it, both retained raw in `pdf_text` from the existing glyph walk
at no extra PDFium cost: a per-line **size histogram** (the median collapses it, hiding
caps-and-small-caps) and **tracking**, the mean intra-word inter-glyph gap over glyph size,
which is negative when GPO condensed the line. Neither carries structural semantics.

**The rule is conservative by construction and fails closed.** Where evidence is missing it
declines to join, because a missed join leaves the prior behaviour while a false join
fabricates a heading that was never printed and deletes a real one.

## What the design is bounded by

**The NOAA falsifier.** `NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION` on `114-hr-2578`
fills 97% of the measure, so fullness has no margin left to read — but it is an
independently established container. Merging it deletes a real agency and reparents its
appropriation under `NATIONAL INSTITUTE OF STANDARDS AND TECHNOLOGY`. C5 exists to decline
exactly this: the line was *also* condensed, so its lack of trailing room proves nothing.
This is why no-fabricated-hierarchy outranks recovery.

**The Railroad residue.** `RAILROAD REHABILITATION AND IMPROVEMENT FINANCING PROGRAM` is
**not** recovered, on two bills. Its first line is condensed and near-full, which is the
same signature that protects the NOAA case, so requiring its recovery requires the
fabrication. Recovering all fourteen of `#524`'s cases and never fabricating hierarchy are
not simultaneously satisfiable on observed print. `#524`'s verification section was amended
to record this rather than bending the rule; the conservative under-join is intended
behaviour, not an open defect.

## External validation

Scored against an XML-derived oracle on the development corpus and then on two independent,
pre-registered bill-level holdouts drawn after the specification was frozen. On the second
holdout: **0 false joins, 21 missed joins, zero novel errors** — every error a class the
development corpus had already shown. Both holdouts are spent.

Consequential deltas on the committed corpus, each traced to an oracle-confirmed correction:
`118-s-4795` moves 212 → 208 anchors, with five invented agencies removed and seven account
fragments replaced one-for-one by the complete heading the XML twin carries. Aggregate diff
effect across the 23 canonical pairs: −175 `added` hunks, −8 `moved`, −4 `removed`,
+1 `modified`. The admissibility split does not move (`declined` unchanged on all 23).

## Where the durable claims now live

- **Behaviour** — `tests/test_pdf_account_segmentation.py` owns three semantic invariants
  (wrapped-account recovery, no-fabricated-parent, missing-evidence fail-closed), each with
  a stated mutation that reddens it.
- **Acceptance criteria** — the amended Verification section of `#524`.
- **The operating point** — the four constants and their rationale in `pdf_anchors`, beside
  the code they govern.
- **Structural baselines** — the anchor goldens, `pdf_canonical_baseline.json`, and the
  ADR 0019 `round1_legacy_trace.json`.

`0.5`, `0.97`, `0.31` and the 8-gap median floor are the validated operating point, not
tuning knobs; moving one invalidates the validation above.
