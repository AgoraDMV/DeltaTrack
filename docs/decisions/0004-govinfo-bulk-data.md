# 4. Fetch bill discovery and text from govinfo bulk data, not the Congress.gov API

- Status: Accepted
- Date: 2026-06-27

## Context

`fetch_bills.py` currently retrieves both the list of bills and their text from the
Congress.gov API v3. That has three frictions:

1. It requires an API key. Without one it falls back to `DEMO_KEY`, capped at 30
   requests/hour. Every clone, every CI run, and every staffer install inherit
   either the key-management step or the cap.
2. Discovery is gated on an appropriations-committee filter and paged at 250
   results, which made the dataset look like a 450k-bill "firehose" that has to be
   filtered down.
3. The committee filter as a discovery *gate* contradicts the project goal that the
   diff works on any bill type, not only appropriations.

GPO's govinfo bulk data is the alternative: static files served from
`govinfo.gov/bulkdata`, no key, no rate limit, covering the 113th Congress forward.

## Decision

Move discovery and text retrieval to govinfo bulk data, and demote the
appropriations-committee filter from a gate to a label.

govinfo exposes bill **text** and bill **metadata** as two separate bulk feeds, and
the design uses each for a different job:

- **Text for diff** comes from the **BILLS** feed, one XML file per version at
  `bulkdata/BILLS/{congress}/{session}/{type}/BILLS-{congress}{type}{number}{ver}.xml`.
  A parity check (`parity_check.py`, comparing byte / canonical-XML / parsed-tree
  equality) found this **byte-for-byte identical** to the Congress.gov "Formatted
  XML" the pipeline downloads today, on all 12 test fixtures. It is the same legacy
  `bill.dtd` format, so `bill_tree.py` needs no changes.
- **Metadata for discovery** comes from the separate **BILLSTATUS** feed
  (`bulkdata/BILLSTATUS/{congress}/{type}/BILLSTATUS-{congress}{type}{number}.xml`),
  which carries title, subjects, and committee / subcommittee codes. It does not
  contain bill text, and the BILLS feed does not contain this metadata, so the two
  are fetched independently.
- **Discovery by bill number** is a direct BILLS URL, no index, works for any bill.
- **Discovery by title** uses a local index built from the BILLSTATUS feed (one
  per-bill-type ZIP, roughly 14 MB for the ~5,600 Senate bills of a Congress), not
  a live paged API.
- **Appropriations becomes a facet, not a gate.** BILLSTATUS carries the committee
  and subcommittee codes (e.g. `ssap01` = Senate Agriculture subcommittee), so
  appropriations can be a label without restricting what the tool will diff.

## Consequences

- No API key and no rate limit. This removes a friction point for an
  install-constrained audience and makes the test corpus fully reproducible from a
  clean clone without credentials.
- `bill_tree.py` is unchanged, so the migration is low-risk on the parsing side.
  The legacy DTD path is deliberate: govinfo's USLM format lives on a separate beta
  subpath and would force a parser rewrite, so we do not use it.
- Coverage floor is the 113th Congress, where govinfo bulk BILLS begins. Older
  bills are out of scope for this path.
- Drafts are still not covered. Pre-introduction draft PDFs have no XML at any
  source, govinfo included, so they remain PDF-only.

## PDF retrieval

The BILLS bulk feed is XML only; it does not serve PDFs. Today `fetch_bills.py`
gets each version's PDF from the Congress.gov API (the API returns a PDF URL in the
version's `formats` list), so the PDF path currently carries the same API key and
rate-limit dependency this decision removes for XML.

The intended post-migration source is govinfo's package content path, which is also
keyless and uses the same package id as the BILLS XML:

`https://www.govinfo.gov/content/pkg/BILLS-{congress}{type}{number}{ver}/pdf/BILLS-{congress}{type}{number}{ver}.pdf`

A keyless download confirms this returns the same artifact: the govinfo PDFs for
`BILLS-118hr4366eh` and `BILLS-118hr4366enr`, fetched with no API key and no auth,
are byte-for-byte identical (matching SHA-256) to the Congress.gov copies. Moving
the PDF fetch here removes the last Congress.gov API dependency from the pipeline.

Caveat: the prototype implemented only XML, not PDF, so this PDF path is verified
but not yet wired into `fetch_bills.py`. **If the PDF migration is deferred, the XML
path moves to govinfo while the PDF path still depends on the Congress.gov API key
and rate limit.** That split is workable but should be a conscious choice, not an
accident. Both are tracked under issue #10.

## Feeds and references

- govinfo bulk data repository: <https://www.govinfo.gov/bulkdata>
- BILLS (bill text, XML): <https://www.govinfo.gov/bulkdata/BILLS>
- BILLSTATUS (bill metadata, XML): <https://www.govinfo.gov/bulkdata/BILLSTATUS>
- Bill PDFs (package content, keyless): `https://www.govinfo.gov/content/pkg/{packageId}/pdf/{packageId}.pdf`
- govinfo developer / API docs: <https://api.govinfo.gov/docs/>

## Notes on implementation (from the prototype)

- **Resolve version codes from the BILLS directory listing** (prefix-match
  `BILLS-118s4690*`), not by translating human version labels. BILLSTATUS says
  "Reported to Senate" where the old fixtures say "reported-in-senate"; the
  directory codes are the stable key.
- **Do not filter by version count.** Appropriations bills often have exactly one
  published version (Senate bills are reported as original bills), so a
  "two or more versions" filter would drop every one. Diffs here are against
  external baselines (budget request, prior year, companion bill), not intra-bill
  versions.
- **Discovery is separate from text retrieval.** The law API was suggested as an
  alternative source but covers only enacted bills, which loses the in-progress
  versions that are the whole point of a diff. It is the wrong source here.

This decision is accepted but not yet implemented. The prototype lives on the
`worktree-govinfo-prototype` branch (`fetch_govinfo.py`, `discover.py`,
`parity_check.py`); the migration is tracked in issue #10.
