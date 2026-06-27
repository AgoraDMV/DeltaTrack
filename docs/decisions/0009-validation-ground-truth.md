 # 9. Validate the parser against independently-authored committee reports

- Status: Accepted
- Date: 2026-06-27

## Context

The core of the tool is reading dollar amounts out of a bill correctly: a wrong
amount is a wrong diff, and a staffer would act on it ([0001](0001-structured-money-diff.md)).
So the hard question is not "does the parser run" but "how do we *know* it reads the
amounts correctly?"

The obvious way — write tests that assert "account X should be $Y" — has a trap. The
person writing those expected values reads the same bill the parser reads, with the
same assumptions. If the parser misreads a bill because the author misunderstood how
that bill is laid out, the hand-written test will encode the same misunderstanding and
pass. Tests built from the same source as the code confirm the author's assumptions;
they do not catch the author's blind spots. We needed a yardstick the parser's author
did not create.

The Congress publishes a **committee report** alongside each appropriations bill. It is
written by committee staff, for a different purpose (explaining the committee's funding
recommendations), separately from the bill's legal text. It states account amounts.
Because it is authored independently of the bill, agreement between the parser's
output and the report is real outside evidence that the parser read the bill right —
not a restatement of our own assumptions.

This explains something about the codebase that otherwise looks odd: DeltaTrack parses
and fetches committee reports even though no user-facing feature consumes them. That is
not an abandoned product feature. It is test infrastructure.

## Decision

We will validate the parser by comparing the amounts it extracts from a bill against
amounts **independently authored in published committee reports** (Senate
Appropriations `CRPT-…` documents). These cover eleven of the twelve regular
appropriations subcommittees; the twelfth, Legislative Branch, is covered by a second
independent source — a separately maintained appropriations spreadsheet — checked
structurally (the right amount in the right place). Together the two sources reach all
twelve. The living figures, coverage, and the case-by-case remainder live in
[docs/parser-validation.md](../parser-validation.md), which is generated from the
validation suite; this record is the *why*, not the numbers.

Two further commitments make the check trustworthy rather than self-serving:

- **Guard against overfitting.** We validate against at least one year we did not tune
  on (the FY2024 CJS bill alongside the FY2025 set), so a high match rate cannot just
  be thresholds fitted to the sample we happened to look at.
- **Keep the misses visible and hand-traced.** Every account the parser does not match
  is listed and explained, not suppressed. Each known miss is a legitimate difference
  between how the report and the bill state a figure — an indefinite "such sums"
  account with no fixed number in the bill, a report total the bill itemizes into
  parts, or a typo in the report itself — never the parser misreading the bill. We do
  not tune the parser to chase those numbers, because a match has to mean genuine
  agreement, not a figure massaged until it lines up.

Committee-report handling is **validation infrastructure, not a product
feature**. DeltaTrack has no externally-facing use case for committee reports; the
code exists to hold the diff engine honest. 

This independent check is the top layer of a suite, not a replacement for it. We rely
on hand-written tests too — "frozen" expectations that lock in known-good behavior on
specific bills, and broad property checks that confirm nothing is dropped or
duplicated (see [TESTING.md](../../TESTING.md)). What this decision adds is the one
thing those layers structurally cannot give.

Alternatives:

- **Rely on the in-house test suite alone (hand-written fixtures and property
  checks).** Rejected as the source of correctness *evidence*, though the suite is
  kept and depended on for what it does well. Frozen fixtures are written by someone
  reading the same bill the parser reads, so a shared misreading passes silently (the
  circularity above); they lock in behavior but cannot prove that behavior was right
  to begin with. Property checks confirm nothing was lost, not that any amount is
  correct. The independent source supplies the missing piece and sits on top of these
  layers rather than displacing them.

## Consequences

- The headline accuracy figure means something to an outside reader precisely because
  the source is independent. That is what lets `parser-validation.md` state a plain
  accuracy claim to a non-technical audience rather than "trust us."
- The committee-report fetch/parse code must be understood and maintained as a test
  harness. It should not be deleted as an unused feature.
- Reproducibility depends on the report sources being vendored and CI-gated, so the
  check runs the same for everyone and does not silently skip.
- Coverage is bounded by what the reports provide, and its depth varies on purpose.
  The eleven committee-report subcommittees are checked at amount-recall depth (the
  right amount under the right agency) on a single Senate-reported bill each; only
  Legislative Branch is checked structurally and on the House side. Some sources are
  also awkward (House committee reports print their account tables as images, and one
  subcommittee's bill was never reported in the target year, forcing an earlier-year
  substitute), so gaps are driven by source availability and are documented in the doc
  rather than hidden.
- The remainder list is reviewed by hand and will shift as new bills and years are
  added; a new legitimate report/bill discrepancy is expected, not a regression.
- Extending Legislative Branch to *also* rest on a committee report — so all twelve
  subcommittees are validated against reports uniformly, with the spreadsheet kept as
  an additional structural cross-check on Leg Branch — is planned but not yet built
  (tracked in [DeltaTrack#99](https://github.com/AgoraDMV/DeltaTrack/issues/99)).
- This pairs with the deterministic-engine decision ([0008](0008-deterministic-engine.md)):
  a fixed input has exactly one correct output, which is what makes validating it
  against an external source meaningful in the first place.
