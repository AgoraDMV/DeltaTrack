# #501 near-full container at the account boundary — NO SEPARATING SIGNAL FOUND

> **Superseded in part.** This round's search conclusion stands: no signal tested here
> separates the class. Its *ruling* does not: it framed the result as "#501 and #524
> cannot be jointly resolved" and omitted the conservative candidate this round's own
> measurements produced. Declining to join the ambiguous case is a third option, and it
> validated. See [`CANDIDATE-4.md`](CANDIDATE-4.md).

Narrow round under `#501`/`#551`, on Candidate 3's one blocking failure: a genuine
container whose printed line leaves no early break, so line fullness cannot see it.

**Result: no source-neutral PDF evidence TESTED IN THIS STUDY separates the class without
collateral damage — and the damage lands on `#524`'s own named headings.** That is the
claim the evidence establishes. It is not a proof that no such evidence exists.

## The population, fixed before any feature was tested

Boundaries where fullness has no margin (`slack < 0`, reaching Candidate 3's
`C5_fullness_join`), excluding those `C1`/`C2` already split, over the combined
development evidence:

| | n |
|---|---|
| no-margin population | **1524** |
| **NEAR_FULL_CONTAINER** (truth SPLIT — the `#501` class) | **2** |
| **GENUINE_WRAP** (truth JOIN) | **1522** |

The two controls are the same heading pair in two bills:

```
118-hr-4366/5_engrossed-amendment-house p234 L4
114-hr-2578/rs                          p121 L5
   NATIONAL OCEANIC AND ATMOSPHERIC ADMINISTRATION   fill 0.972 / 0.973, caps 0.8
   OPERATIONS, RESEARCH, AND FACILITIES              caps 0.5, slack -67.5 / -67.8
```

So the entire class in 3466 boundaries is **one distinct heading**. That bounds what any
result here could have established even had a discriminator appeared.

## Every signal tested

| signal | outcome |
|---|---|
| line fullness | has no margin here by construction — this is the population's definition |
| upper-line fill fraction | containers 0.972–0.973, sitting **inside** the wrap distribution (p95 0.997, max 1.089) |
| caps-per-word (lower) | containers 0.500; **10 wraps** share that exact value |
| median glyph size, font name, font weight, leading, line-number gap, centring | measured dead in earlier rounds; re-checked in this population, unchanged |
| **tracking, raw** (new extraction) | containers 0.0092; **63 wraps** at or below it. Catching both damages 63–67 |
| **tracking, document-normalised** | worse — **70 wraps** damaged. The two controls do not even cluster with each other (ratio 0.130 vs 0.301) |
| lower-line tracking | **141 wraps** damaged |
| **fill ∧ tracking conjunction** | best result: catches 2/2 at **6 wraps** damaged |

Tracking is genuinely new evidence — `LineGeom` keeps only three x-coordinates, so whether
a line was set normal, loose or **condensed** is unrecoverable downstream. Extracted for
364,019 lines over 15,025 pages with a contract check against
`pdf_text._page_glyph_sizes`: **0 divergences**.

And the phenomenon is real. The same text, in the same bill, at two places:

```
114-hr-2578/rs p13  L19  'OPERATIONS, RESEARCH, AND FACILITIES'   tracking +0.095
114-hr-2578/rs p121 L6  'OPERATIONS, RESEARCH, AND FACILITIES'   tracking -0.008
```

At p121 GPO **condensed** the lines; at p13 it let the agency wrap instead. Per-page dumps
confirm the condensation is specific to those two lines (0.009 / −0.008) against every
other line on the page (0.019–0.045). The mechanism is not imagined.

## Why it still fails

The best conjunction (`fill ≥ 0.97` and `tracking ratio ≤ 0.31`) catches both controls and
damages six genuine wraps:

```
[other]      UNITED STATES INTERNATIONAL DEVELOPMENT FINANCE CORPORATION
[#524-NAMED] RAILROAD REHABILITATION AND IMPROVEMENT FINANCING PROGRAM   118-hr-4366/4_eas
[other]      PUBLIC TELECOMMUNICATIONS FACILITIES, PLANNING AND CONSTRUCTION
[other]      DEFENSE URANIUM ENRICHMENT DECONTAMINATION AND DECOMMISSIONING
[#524-NAMED] RAILROAD REHABILITATION AND IMPROVEMENT FINANCING PROGRAM   118-hr-4366/5_eah
[other]      PUBLIC TELECOMMUNICATIONS FACILITIES, PLANNING AND CONSTRUCTION
```

**Two of the six are `RAILROAD REHABILITATION AND IMPROVEMENT FINANCING PROGRAM` — one of
the fourteen headings `#524` names as its acceptance criterion.** Any rule that catches the
NOAA container re-breaks a heading `#524` explicitly requires be recovered. That is a
direct contradiction between the two issues' acceptance conditions, established on real
print rather than argued.

The reason is a single shared mechanism: **GPO condenses a line to manufacture a fit.** It
does that when squeezing a complete container onto one line, and equally when squeezing
more of a wrapped account name onto its first line. The physical act is identical; only
the intention differs, and the intention is not printed. "Near-full and condensed" is not
a container signature — it is a *fit-was-manufactured* signature, and both classes
manufacture fits.

## Negative control — required, and it passes

| | false joins | missed joins | NOAA false joins |
|---|---|---|---|
| discriminator **ON** | 0 | 68 | **0** |
| discriminator **OFF** | 2 | 62 | **2** — both NOAA cases return |

So the discriminator does detect the class, and removing it does bring the false join back.
It is rejected for its collateral damage, not for an inability to fire. The scored trade is
**2 fabrications prevented, 6 correct `#524` fixes destroyed, 2 of them `#524`'s own named
headings.**

## Ruling

**No signal tested in this study separates the class without collateral damage.**

The consequence drawn here — that the two issues cannot both be satisfied — was too
strong, and assumed the only responses were to catch the container or to join it. The
third response, declining the ambiguous boundary, is the one the measurements supported
all along and is now validated in [`CANDIDATE-4.md`](CANDIDATE-4.md).

Candidate 3 stays blocked by the agreed invariant — no novel false join. What a
*discriminating* fix would need is a signal separating "condensed because a container had to fit" from
"condensed because more of a wrapped name had to fit". Nothing in the glyph layer, the
geometry or the type carries that distinction; it is a fact about intent, and the only
sources that record it are the XML twin (absent on draft PDFs, which is where `#524`
matters most) or a document-local recurrence signal (banned, and separately falsified in
the candidate-2 round).

No candidate is frozen and no holdout is drawn.

### Options as recorded at the time (superseded by candidate 4)

Stated as options, not as a proposed round, since further methodology work is not
authorised and none of these is a research question:

1. **Accept the two NOAA fabrications as a tracked `#501` limitation**, gated by a standing
   test that pins their identity so a third instance is noticed. `#501` already records
   exactly this shape as an accepted residue at the major band; this would extend the same
   posture to the account band, with the honest difference that the corpus now contains
   real instances where `#501`'s did not.
2. **Gate on the XML twin** where a bill is dual-published, and decline the join where it
   disagrees. Does nothing for draft PDFs.
3. **Ship nothing**, leaving `#524`'s 654 under-joins in place to avoid 2 over-joins.

Option 3 is the status quo and the measured evidence is heavily against it: Candidate 3
removes 62 of shipped's 64 false joins, cuts missed joins 1296 → 62, and reduces
false-fragment `Renumbered` cards 15 → 4 on the key `#639` pair. The choice between 1 and 3
is a product judgement about which silent error is worse, and it is yours.

## Reproducing

```sh
uv run python docs/research/pdf-heading-identity/nearfull/population.py
uv run python docs/research/pdf-heading-identity/nearfull/tracking.py
```
