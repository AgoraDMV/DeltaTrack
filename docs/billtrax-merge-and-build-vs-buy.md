# Decision memo: BillTrax merge and the build-vs-buy question

**Date:** 2026-05-22
**Status:** Open. Needs a demand answer before more engineering.
**Trigger:** Is this project redundant given BillTrax already ships diffing and a deployed UI and diff code.

## The question that actually matters

After working through it, the decision is not "complex diff vs. simple diff." It collapsed to a single question, and it is not a technical one:

> **Do appropriations staffers need structured, queryable, change-tracked dollar data that they cannot get from reading the documents?**

- **If yes:** the work has merit. You need an extraction engine (this repo) surfaced in a UI (BillTrax). Diffing is a feature of that, not the goal.
- **If no:** kill the custom build, point people at an off-the-shelf PDF compare tool plus the raw bills.

Everything else below is the reasoning that gets you to that question.

## How we got here

### 1. The two projects solve adjacent but different problems

| | BillTrax | This project |
|---|---|---|
| Core | Next.js web app that structures appropriations data into searchable signals; auth, SQLite, deployed UI | Extraction + structural-diff engine that turns bills into a tree of accounts with dollar amounts |
| Diff | Word diff in the bill detail view (text-level) | Account-level structural diff: "Account X $4.2M -> $5.1M, +21%", cross-version, amount reconciliation |
| PDF | Upload is a stub, no file processing yet | PDF extraction built (pypdfium2), incl. watermarked Senate bills and PDF-only pre-introduction drafts |
| Validation | Not mentioned | External ground-truth validation across 12+ jurisdictions |

### 2. A word diff cannot do the structural job

A word diff answers "what text changed." It cannot answer "what money moved," because that needs three things it has no model for:

1. **Aggregation and deltas.** Rolling up to "DOJ total: $35.2B -> $37.1B (+5.4%)" requires amounts parsed into a structure and summed by account/agency.
2. **Cross-version alignment.** Appropriations bills get renumbered and reordered constantly. A word diff shows a sea of red/green when an account merely moved position. Structural matching (`match_path`) aligns the same account across versions so you see the real change, not positional noise.
3. **PDF-only drafts.** The highest-value moment is comparing a pre-introduction draft against prior enacted law. Those are PDF-only.

### 3. The simple approach should be *bought* or *downloaded*, not built

If the goal is only "show me what changed," off-the-shelf PDF comparison already does it better than any hand-rolled word diff and at zero maintenance cost (Draftable, Acrobat Compare, diffpdf, free/opensource options, etc.).

So the build-vs-buy verdict on the text layer is clean: **buy.** Which is exactly why the only thing worth building is the structured money layer.

### 4. The honest threats to the "yes" case
- **Trust.** A structured diff that silently drops a line item (recall caps around ~94% on some jurisdictions) is more dangerous than a dumb word diff that never lies. The validation harness exists to manage this; it is not gold-plating, it is what earns the right to present a rolled-up number as trustworthy. But it also means the engine must degrade visibly, not silently.
- **Maintenance.** Parsers break when formats shift. 
- **The official tables already exist.** Appropriations Committees publish **comparative statements** with prior-year vs. proposed amounts by account. That is the official, hand-made version of our structured diff. The engine has to beat "official tables + free PDF compare" for the common case. Where it clearly wins is the cases those do not cover: pre-introduction draft PDFs before any official table exists, arbitrary version-to-version comparisons, and machine-queryable rollups across bills and years.

### 5. IT feasibility colors the "buy" path too

The target audience is non-technical staffers under strict IT, with cloud rejected. Most good PDF compare tools are cloud or paid desktop; diffpdf is free and local but rough; Acrobat they may already have. So "just buy a PDF compare tool" carries the same install/IT friction that has dogged this project's own delivery channel. Confirm before assuming the buy path is frictionless.

## Recommendation

1. **Stop building parser features until the demand question is answered.** The unanswered question is "does anyone need the extraction once a PDF compare tool exists." That is cheap to test.
2. **Validate with actual staffers.** Concretely: what do they do today to understand how the money changed between versions? Do they use the comparative statements? Where do those fall short? Would queryable, draft-stage, cross-version rollups change their workflow?
3. **If demand confirms, merge as layers, not as competitors:**
   - Text/visual diff: buy or embed a PDF compare tool. Do not port this repo's text renderer.
   - Money diff: contribute this repo's extraction + structural-diff engine as the capability BillTrax cannot otherwise have.
   - The bought text diff doubles as the honest fallback for sections the parser does not structure, which also contains the trust risk.
4. **If demand does not confirm:** the structured layer has no buyer, and a PDF compare tool plus the published documents is the whole solution. Retire the custom build.

## One-line summary

Do staffers need something more than a basic PDF diff tool? If not, they can use commercially available/opensource PDF differ that already exists. 
