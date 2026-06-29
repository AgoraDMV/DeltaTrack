# 13. Bill identity is the slug; version is a per-bill ordinal, not a universal one

- Status: Proposed
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

This convention has worked well, but it lived only in the code and in our habits; we
never wrote it down. The fact that most needs stating: **a version's number and its
meaning are per-bill, not universal.** Version `3` is `placed-on-calendar-senate` in
118-hr-4366 but `referred-in-senate` in 114-hr-2029. The ordinal is only meaningful
scoped under a specific bill, and the readable label is how a user learns what that
ordinal means. Inspecting a bill's folder to see its version names is part of the
workflow, not friction to design away.

Because the model was implicit, work that needed to reference bills and versions had to
infer it. The bill-index work reasonably reached for a single combined slug
`{congress}-{type}-{number}[:{version}]`, and a note in `shared/version_stems.py`
anticipated filenames eventually moving to that combined form (`119-hr-1:2`). Both
readings fold version into a global identity. That is an understandable interpretation in
the absence of a written convention, but it does not match how we actually store and use
bills: it would put version in the identity (where the per-bill ordinal does not belong)
and, taken to its conclusion, would replace the readable `n_label` filenames that carry a
version's per-bill meaning. The gap to close is a missing explicit data model, not the
individual choices made under it.

## Decision

We will state the model we already use, keeping bill identity and version as two
distinct things:

- **Bill identity is the slug `{congress}-{type}-{number}`** — the folder name and the
  `bill_index` key. Version is not part of the identity.
- **A version is a per-bill ordinal `n`**, addressed as a *separate token* next to the
  bill rather than fused into the slug. Its meaning is per-bill and is carried by the
  readable `{n}_{label}` filename. Readable labels are intentional and load-bearing; we
  keep them rather than substituting codes or slugs.
- **The `:version` slug suffix is not part of the convention.** The index keys bills and
  the CLI addresses version positionally, so identity stays version-free;
  `parse_bill_id` should treat only `{congress}-{type}-{number}` as identity.
- **Version is addressed the same way everywhere: *bill, then n*.** This already matches
  `fetch_bills download --version N`; `diff_bill compare` gains the matching
  `compare <slug> <n_old> <n_new>` form (see #152).
- **`shared/version_stems.py` is the resolver** that maps a `slug` + ordinal `n` to the
  readable version file. Its docstring is updated to say so; filenames stay in the
  `n_label` form.
- **A congress grouping level** (`bills/{congress}/...`) is an allowed future parent
  folder. It groups bills; it does not change bill identity.

Alternatives considered:

- **Keep `:version` as a single-token pointer** (e.g. `118-hr-4366:3`). Set aside:
  combining version into the identity string reads as if versions were universal across
  bills, and it offers nothing over `<slug> <n> <n>`.
- **Move filenames to the slug form** (the direction the `version_stems` note
  anticipated). Set aside: it would drop the per-bill readable labels that tell a user
  what a version is.

## Consequences

- The data model is explicit and matches the storage we already had, so bill-level
  identity is consistent across the folder layout, `bill_index`, and both CLIs.
- Identity stays version-free: `parse_bill_id` and `download-all --file` treat the slug
  as `{congress}-{type}-{number}`, with version supplied separately.
- `diff_bill compare` becomes version-addressable: `compare 118-hr-4366 3 4`, with file
  paths still accepted for backward compatibility, and a bare slug listing the bill's
  local versions so per-bill meanings are one command away (tracked in #152).
- `version_stems` is described as the resolver, and its docstring is brought in line.
- Open follow-up: if a congress grouping level is adopted, resolvers and the default
  `bills/` root must account for the extra parent path.
