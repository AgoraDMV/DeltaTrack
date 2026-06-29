# 13. Bill identity is the slug; version is a per-bill ordinal, not a universal one

- Status: Accepted
- Date: 2026-06-29

## Context

We store every bill the same way on disk, and the CLI has addressed bills with the
same shape since the beginning:

```
bills/
  118-hr-4366/                       <- the bill (folder)
    1_reported-in-house.xml
    1_reported-in-house.pdf
    2_engrossed-in-house.xml
    ...
    6_enrolled-bill.xml
```

- **A bill is a folder**, named `{congress}-{type}-{number}` (e.g. `118-hr-4366`).
- **A version is a file** inside it, named `{n}_{label}.{ext}` where `n` is the
  1-indexed legislative order and `label` is the sanitized stage
  (`engrossed-in-house`, `enrolled-bill`, ...). XML and PDF coexist.

The load-bearing fact that was never written down: **a version's number and its meaning
are per-bill, not universal.** Version `3` is `placed-on-calendar-senate` in 118-hr-4366
but `referred-in-senate` in 114-hr-2029. The ordinal is only meaningful scoped under a
specific bill, and the readable label is how a user learns what that ordinal means.
Inspecting a bill's folder to see its version names is therefore part of the workflow,
not friction to design away.

This came to a head reviewing the bill-index work (PR #24), which introduced a slug
**`{congress}-{type}-{number}[:{version}]`** with a `:version` suffix
(`parse_bill_id` parses it; `make_bill_id` never emits it; the index keys are always
version-less; `download-all --file` parses then ignores it). A separate module,
`shared/version_stems.py`, additionally documented an intended migration of *filenames*
toward the slug form `119-hr-1:2`, retiring the readable `n_label` names.

Both of those treat **version as part of a universal bill identity**. That is the wrong
model. It produced parsed-but-unused code, a documented migration that would have
*destroyed* the readable labels users rely on, and recurring confusion that read like a
half-finished feature. The root cause was a missing, explicit data model — not several
independent bugs.

## Decision

We will model bill identity and version as two distinct things, matching the on-disk
layout we already use:

- **Bill identity is the slug `{congress}-{type}-{number}`.** This is the folder name
  and the `bill_index` key. Full stop. There is no version in the identity.
- **A version is a per-bill ordinal `n`**, addressed as a *separate token* next to the
  bill, never fused into the slug. Its meaning is per-bill and is carried by the
  readable `{n}_{label}` filename. Readable labels are intentional and load-bearing;
  we do not replace them with codes or slugs.
- **`:version` is dropped from the slug spec.** It has no storage role (the index keys
  bills) and the CLI addresses version positionally, so a fused suffix is only a source
  of confusion. `parse_bill_id` should stop treating `:version` as identity.
- **Version is addressed the same way everywhere: *bill, then n*.** This already matches
  `fetch_bills download --version N`; `diff_bill compare` gains the matching
  `compare <slug> <n_old> <n_new>` form (see #152).
- **`shared/version_stems.py` is the resolver**, not a transitional shim: it maps a
  `slug` + ordinal `n` to the readable version file. Its docstring is corrected
  accordingly; there is no migration of filenames to a slug form.
- **A congress grouping level** (`bills/{congress}/...`) is an allowed future parent
  folder. It groups bills; it does not change bill identity.

Alternatives considered:

- **Keep `:version` as a narrow single-token pointer** (e.g. `118-hr-4366:3`). Rejected:
  fusing version into the identity string visually implies versions are universal/
  cross-bill, which is the exact misconception this record corrects, and it buys nothing
  over `<slug> <n> <n>`.
- **Migrate filenames to the slug form** (the old `version_stems` direction). Rejected:
  it discards the per-bill readable labels that let a user know what a version *is*.

## Consequences

- The data model is now explicit and matches the storage we already had, so bill-level
  identity is consistent across the folder layout, `bill_index`, and both CLIs.
- `:version` parsing is removed from the identity path; `download-all --file` no longer
  pretends to honor a version suffix it ignored.
- `diff_bill compare` becomes version-addressable: `compare 118-hr-4366 3 4`, with file
  paths still accepted for backward compatibility, and a bare slug listing the bill's
  local versions so per-bill meanings are one command away (tracked in #152).
- `version_stems` stays and is reframed as the resolver; the misleading "retire these"
  docstring is corrected.
- Open follow-up: if a congress grouping level is ever adopted, resolvers and the
  default `bills/` root must account for the extra parent path.
