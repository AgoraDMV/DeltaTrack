# How appropriations bills are published: formats, venues, and timing

The stock answer to a question that comes up constantly: *for a given version of an
appropriations bill, what formats exist, where, published by whom, and when?* This
drives why we have both an XML and a PDF input path (see
[ADR 0010](decisions/0010-pdf-pipeline-pre-publication.md)) and when to steer a user
to one over the other.

Scope: the twelve regular appropriations bills in each chamber, drafted by the twelve
House and twelve Senate Appropriations subcommittees. The same pattern holds for
ordinary legislation, but appropriations is where the timing gap bites, because the
high-value diffing happens *before* a bill is formally published.

## The one fact that drives everything

**A bill is authored in XML, but the XML is not public until GPO publishes it —
which happens *after* the committee stages where staffers most need to compare
versions.** At the chair's-mark and markup stages, the only public artifact is a
PDF. The authoritative XML appears one to two days *after* the bill is formally
introduced or reported, as a downstream product of the Government Publishing Office
(GPO), not the committee.

You can see the XML existing privately: the committee-print PDFs posted on
docs.house.gov carry their internal source path in the document title (e.g.
`U:\2026OMNI\MIN41203.xml`). The bill is XML upstream; what the public gets at that
moment is the PDF rendered from it.

## Who publishes what, and where

| Actor | Publishes | Where | Format(s) |
|-------|-----------|-------|-----------|
| House/Senate Appropriations committees | Chair's mark, committee print, markup amendments, committee report | [docs.house.gov](https://docs.house.gov) (Committee Repository), `appropriations.house.gov`, `appropriations.senate.gov` | **PDF** (bill text); the only `.xml` on a Committee Repository event page is the *meeting manifest*, not the bill |
| House Rules Committee | The version made in order for the floor | [rules.house.gov](https://rules.house.gov) | PDF, sometimes XML |
| **GPO** (Government Publishing Office) | Authenticated bill text + status | [govinfo](https://www.govinfo.gov/app/collection/BILLS) (`BILLS` collection), [Bulk Data Repository](https://www.govinfo.gov/bulkdata/BILLS) | **XML**, PDF, TXT, HTML |
| Library of Congress | Mirrors GPO, adds bill metadata | [congress.gov](https://www.congress.gov) | XML (the "Download XML" link), PDF, TXT |

The Senate publishes XML for schedules, votes, nominations, and floor proceedings on
[senate.gov](https://www.senate.gov/general/common/generic/XML_Availability.htm), but
**no bill-text XML**. Senate bill XML exists only downstream via GPO/govinfo. Senate
Appropriations marks are posted as PDF on `appropriations.senate.gov`, same as the
House.

## The lifecycle of a version, by format

Reading top to bottom is the chronology a single bill travels.

| Stage | Public artifact | Where | Public XML? |
|-------|-----------------|-------|-------------|
| Subcommittee mark (chair's mark) | PDF committee print | docs.house.gov / committee site | No |
| Full-committee mark | PDF committee print | docs.house.gov / committee site | No |
| Markup amendments | PDF | docs.house.gov | No |
| **Introduced / reported** (gets an `H.R.`/`S.` number) | XML, PDF, TXT, HTML | **govinfo + congress.gov** | **Yes — ~1–2 days after** |
| Floor version (Rules print) | PDF, sometimes XML | rules.house.gov | Sometimes |
| Engrossed / enrolled / public law | XML, PDF, TXT, HTML | govinfo + congress.gov | Yes |

The "No" rows are the **pre-publication window**. They are exactly the stages an
appropriations staffer cares about most: comparing a chair's mark against last year's
enacted bill or the President's request, and tracking amendments through markup. That
is the access gap the PDF pipeline exists to close.

## When does the XML show up, and how do I know?

- **Trigger.** XML is produced when GPO processes a *formally introduced or reported*
  bill. A pre-introduction committee print does not get bill-text XML; it may get a
  committee-print (`CPRT`) entry, typically PDF.
- **Lag.** Text is usually on govinfo and congress.gov **one to two days** after
  introduction. congress.gov refreshes from govinfo early each morning (~6 a.m. ET);
  a bill introduced today generally appears tomorrow. Delays grow when many bills land
  at once or a bill is very large.
- **How to check.** Look up the bill on congress.gov; the **Text** tab lists each
  version with a **Download XML** link once GPO has it. The
  [Bill Texts Received Today](https://www.congress.gov/bill-texts-received-today) page
  shows the day's arrivals. On govinfo, browse the
  [`BILLS` collection](https://www.govinfo.gov/app/collection/BILLS).

## Coverage by Congress (history)

- **Bill-text XML**: 113th Congress (2013) forward on govinfo. Earlier bills are
  PDF/TXT only.
- **Bill-status XML** (metadata, not text): 108th Congress forward, via the GPO Bulk
  Data Repository.

Today `fetch_bills.py` fetches bill text and committee-bill discovery from the
Congress.gov API v3, while `fetch_bill_archives.py` already loads bill-status metadata
from the govinfo bulk repository. [ADR 0004](decisions/0004-govinfo-bulk-data.md) sets
the planned move of text and discovery to govinfo bulk data as well.

## Practical guidance: prefer XML when it exists

When a published XML version exists for the bill in hand, **use it, and point users
to it.** XML is the better source — it is the authenticated structure the bill was
authored in, so amount and hierarchy extraction is exact rather than reconstructed
from a rendered page (the PDF path is inherently lossier; see
[ADR 0002](decisions/0002-pdfium-single-engine.md) and the validation in
[ADR 0009](decisions/0009-validation-ground-truth.md)). The PDF pipeline is for when
no published XML exists yet — not a parallel choice for bills that have one.

A genuine *discussion draft* (released and never formally introduced) may never get
public XML at all; for those, PDF is the only option there will ever be.

## Sources

- [Congressional Bills — govinfo](https://www.govinfo.gov/help/bills)
- [Bulk Data: Congressional Bills — govinfo](https://www.govinfo.gov/bulkdata/BILLS)
- [Committee Repository help — docs.house.gov](https://docs.house.gov/committee/Help.aspx)
- [Availability of Legislative Measures in the House (the "72-Hour Rule"), CRS RS22015](https://www.congress.gov/crs-product/RS22015)
- [The Committee Markup Process in the House, CRS RL30244](https://www.congress.gov/crs-product/RL30244)
- [XML Sources Available on Senate.gov](https://www.senate.gov/general/common/generic/XML_Availability.htm)
- [Legislative Documents in XML — xml.house.gov](http://xml.house.gov/)
- [Bill Texts Received Today — congress.gov](https://www.congress.gov/bill-texts-received-today)
- [FAQ (text availability timing) — congress.gov](https://www.congress.gov/help/faq)
</content>
</invoke>
