# 4. Fetch bill discovery and text from govinfo bulk data, not the Congress.gov API

- Status: Accepted
- Date: 2026-06-27

## Context

Bill discovery and text retrieval both ran against the Congress.gov API v3, which
carried three frictions:

1. It requires an API key. Without one it falls back to `DEMO_KEY`, capped at 30
   requests/hour. Every clone, every CI run, and every staffer install inherits
   either the key-management step or the cap.
2. Discovery is gated on an appropriations-committee filter and paged at 250
   results, which made the dataset look like a 450k-bill "firehose" that has to be
   filtered down.
3. The committee filter as a discovery *gate* contradicts the project goal that the
   diff works on any bill type, not only appropriations.

GPO's govinfo bulk data is the alternative: static files served from
`govinfo.gov/bulkdata`, keyless, covering the 113th Congress forward.

## Decision

Discovery and text retrieval come from govinfo, and the appropriations-committee
filter is a label rather than a gate. The Congress.gov API stays available as an
explicit opt-in fallback, which is also the only path to bills below the govinfo
coverage floor.

govinfo exposes bill **text** and bill **metadata** as two separate bulk feeds, and
the design uses each for a different job:

- **Text for diff** comes from GPO's **BILLS** collection, by two routes onto the same
  documents: bulk ingestion reads the BILLS bulk-data feed
  (`bulkdata/BILLS/{congress}/{session}/{type}/BILLS-{congress}-{session}-{type}.zip`),
  and per-bill acquisition fetches the same BILLS packages through the package-content
  path below. A parity check comparing byte, canonical-XML and parsed-tree equality
  found this **byte-for-byte identical** to the Congress.gov "Formatted XML" the
  pipeline previously downloaded, across all twelve fixtures checked. It is the same
  legacy `bill.dtd` format the parser already reads, so no source-specific parsing
  exists.
- **PDFs** come from the **package-content** path, addressed by the same package id
  and equally keyless:
  `https://www.govinfo.gov/content/pkg/{packageId}/pdf/{packageId}.pdf`. That path
  serves each package's XML rendition too, which is the route per-bill acquisition
  takes above; it needs no session in the URL, where the bulk-data path does. The
  govinfo PDFs for `BILLS-118hr4366eh` and `BILLS-118hr4366enr` are byte-for-byte
  identical (matching SHA-256) to the Congress.gov copies, so nothing downstream
  depends on which source served the file.
- **Metadata for discovery** comes from the separate **BILLSTATUS** feed
  (`bulkdata/BILLSTATUS/{congress}/{type}/BILLSTATUS-{congress}{type}{number}.xml`),
  which carries title, subjects, committee / subcommittee codes, and the version
  dates that order a bill's versions. It does not contain bill text, and the BILLS
  feed does not carry this metadata, so the two are fetched independently.
- **Lookup by bill number needs no local index.** The per-bill path reads that bill's
  BILLSTATUS, takes the BILLS package ids from the text versions it declares, and
  retrieves the corresponding package renditions. Bills below the coverage floor use
  the API fallback.
- **Discovery by title** uses a local index built from the BILLSTATUS feed (one
  per-bill-type ZIP, roughly 14 MB for the ~5,600 Senate bills of a Congress), not a
  live paged API.
- **Appropriations is a facet, not a gate.** BILLSTATUS carries the committee and
  subcommittee codes (e.g. `ssap01` = Senate Agriculture subcommittee), so
  appropriations can be a label without restricting what the tool will diff.
- **A version is identified by its package code, never by translating a human
  label.** BILLSTATUS says "Reported to Senate" where older fixtures say
  `reported-in-senate`; the code carried in the package id is the stable key.
- **Version count is not a filter.** Appropriations bills often have exactly one
  published version — Senate bills are reported as original bills — so a "two or more
  versions" rule would drop every one of them. Diffs here are frequently against
  external baselines (budget request, prior year, companion bill) rather than an
  earlier version of the same bill.

Alternatives:

- **Keep the Congress.gov API as the primary source.** Rejected for the three
  frictions above. It is retained as an opt-in fallback rather than removed, because
  it is the only source for bills below the govinfo coverage floor.
- **The law API.** Rejected as a source: it covers only enacted bills, which loses
  the in-progress versions that are the whole point of a diff.
- **govinfo's USLM format.** Rejected: it lives on a separate beta subpath and would
  force a parser rewrite, where the legacy `bill.dtd` the BILLS feed serves is what
  the parser already reads.

## Consequences

- **No Congress.gov API key or API-quota dependency on the default path.** XML and PDF
  acquisition both use keyless govinfo endpoints, so neither inherits Congress.gov key
  management nor the `DEMO_KEY` cap of 30 requests/hour. govinfo publishes no quota for
  these endpoints and none was observed in use, which is weaker than a guarantee that
  it never throttles; what this decision removes is the dependency on a *metered,
  credentialed* API, not the possibility of server-side limits. The effect is one less
  friction point for an install-constrained audience, and a test corpus reproducible
  from a clean clone without credentials. A `CONGRESS_API_KEY` is needed only for the
  API fallback, or for a year-range bulk download, whose appropriations *discovery*
  still uses the committee endpoint even though its text comes from govinfo.
- **Discovery and text retrieval are separable**, which is what lets that split
  exist: either can change source without the other having to follow.
- **Coverage floor is the 113th Congress**, where govinfo bulk BILLS begins. A
  request below it fails fast and names the API fallback rather than returning
  nothing.
- **Drafts are still not covered.** Pre-introduction draft PDFs have no XML at any
  source, govinfo included, so they remain PDF-only
  ([0010](0010-pdf-pipeline-pre-publication.md)).

## Feeds and references

- govinfo bulk data repository: <https://www.govinfo.gov/bulkdata>
- BILLS (bill text, XML): <https://www.govinfo.gov/bulkdata/BILLS>
- BILLSTATUS (bill metadata, XML): <https://www.govinfo.gov/bulkdata/BILLSTATUS>
- Bill PDFs (package content, keyless): `https://www.govinfo.gov/content/pkg/{packageId}/pdf/{packageId}.pdf`
- govinfo developer / API docs: <https://api.govinfo.gov/docs/>
