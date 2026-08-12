"""Neutral identity contract: literal source-glyph membership, and the discordance rules.

SUPERSEDES the projection half of `neutral_geometry.py`. A19 claimed projection was "by
GLYPH MEMBERSHIP" and that membership "needs no tolerance". Neither was true of the code:
`project_by_glyphs` received only BASELINES and assigned each to the nearest neutral line
with NO maximum distance, so a glyph at y = -5000 was still forced onto a neutral line.
That is baseline inference, not membership. This module makes the word literal.

THE NEUTRAL GLYPH ID
--------------------
    gid = (document_sha256, page_number, source_char_index)

`source_char_index` is the index `i` in `FPDFText_CountChars(text_page)` order -- the
engine's own text-page character index, which both adapters already iterate
(`for i in range(max(n, 0))`) and which **neither currently stores**: both `continue` past
characters they reject, so a list position is not the index. Recording `i` is pure
provenance: it changes no extraction decision on either arm, and it is the only exact
identity both arms can name for the same mark on the page.

ELIGIBILITY IS GEOMETRIC, NOT LEXICAL
-------------------------------------
A source glyph is neutral-eligible iff it has a VALID INK BOX -- present, finite, and
positive area -- and is upright. Newlines, generated spaces and control entries carry no
ink and are excluded by that rule alone. `x08` demonstrates this on development documents
rather than assuming it.

IDENTITY NORMALISATION IS NOT ARCHITECTURE-OUTPUT NORMALISATION
---------------------------------------------------------------
This is the distinction A22 exists to freeze, and the one the first cut of this module
erased. Model G answers *which physical line each source glyph belongs to*. That question
has one right answer and both arms must be held to it. It must NOT be allowed to answer
the different question of *how many lines the architecture emitted, and which glyphs it
grouped together* -- because that grouping IS an architecture output, and it is one of the
two things the seam can change.

Concretely: H welding two physical lines into one emitted line, while X emits two, leaves
both arms' PROJECTED TEXT identical on both neutral lines -- partition hands each line back
exactly its own glyphs. Comparing only projected text therefore reports `SAME` for a
reconstruction disagreement that A17.4 existed to observe. The repair is not to weaken the
projection; it is to compare a second, independent quantity: the RECONSTRUCTION SIGNATURE.

    TEXT_DISCORDANCE          what characters the arm produced for this line's glyphs
    SEGMENTATION_DISCORDANCE  how the arm grouped this line's glyphs into emitted lines

The two are deliberately orthogonal. A word-space difference (`FAMILYHOUSING` vs
`FAMILY HOUSING`) moves the text and must NOT move the signature -- inserted characters
carry no gid and never enter it. A merge or split moves the signature and need not move
the text. Keeping them separate is what lets M3 score word boundaries without a
segmentation difference fabricating a boundary error.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import NamedTuple

BASELINE_TOL_FACTOR = 0.5


@dataclass(frozen=True)
class SourceGlyph:
    """One below-seam ink mark, with the identity both arms can name."""

    gid: int  # source char index within the page
    baseline: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 0.0)


SPACE = 0x20


def eligible(gid: int | None, box: tuple | None, upright: bool, codepoint: int | None) -> bool:
    """Neutral-eligible iff it is a real ink mark.

    A24.2 WITHDRAWS A19/A21's absolute phrase "NO codepoint is consulted". `x12` falsified
    the assumption that sentence rested on -- that a positive-area PDFium character box
    identifies a physical ink mark. It does not: PDFium reports a box for a content-stream
    U+0020 about 3.6 pt wide and 0.014 pt tall, against 7.9 pt for a capital, so "positive
    area" admits it by a hair and every real word space entered the supposedly ink-only
    skeleton.

    THE NARROW REPLACEMENT INVARIANT:

        neutral-eligible iff  a source character exists
                          AND codepoint != U+0020
                          AND the box is valid, finite and positive-area
                          AND the character is upright

    WHY THIS ONE LEXICAL EXCEPTION IS LEGITIMATE, and does not reopen the principle it
    narrows:

      * U+0020 is a BELOW-SEAM SOURCE FACT, available before either architecture runs;
      * X-2 already froze the architectural judgment that a space "carries no ink" -- this
        rule adopts a decision the protocol had already made, it does not invent one;
      * it reads no H or X output, so it cannot favour either arm;
      * `x12` measured that PDFium's char-box API simply does not encode the ink/non-ink
        distinction by area, so geometry alone cannot express the intended rule.

    NOT A WHITESPACE BLACKLIST. Only U+0020 is excluded, and only because X-2 froze it and
    x12 measured it. Newlines, generated spaces and control entries are still excluded by
    geometry alone. If another non-ink category appears, it is reported, not quietly added.
    """
    if gid is None or box is None or codepoint == SPACE:
        return False
    x0, y0, x1, y1 = box
    # FINITE is checked explicitly, not assumed. The invariant has always said "valid,
    # FINITE and positive-area", but the code only rejected None -- and NaN defeats a
    # positive-area test silently, because every comparison with NaN is False, while an
    # infinite coordinate would pass `(x1 - x0) > 0` and then poison the median ink height
    # that sets the clustering tolerance for the whole page. `math.isfinite` rejects NaN,
    # +inf and -inf together, and it must run BEFORE any arithmetic is trusted.
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x0, y0, x1, y1)):
        return False
    return upright and (x1 - x0) > 0 and (y1 - y0) > 0


@dataclass(frozen=True)
class NeutralLine:
    page: int
    ordinal: int
    baseline: float
    x0: float
    y0: float
    x1: float
    y1: float
    gids: frozenset[int]
    # A38.2 -- the A30.3 nearest-glyph CANDIDATES: (ngid, unrounded source x0) per member.
    #
    # `gids` alone cannot serve A30.3: the resolver compares an adjudicated PDF x against each
    # neutral glyph's own x0, and the line's aggregate x0 is only the leftmost. Ordered by
    # ngid for SERIALIZATION determinism ONLY -- A30.1 forbids ordering occurrences by ngid,
    # which disagreed with printed order on 10 of 33,602 emitted lines.
    candidates: tuple[tuple[int, float], ...] = ()

    @property
    def key(self) -> tuple[int, int]:
        return (self.page, self.ordinal)


def cluster(glyphs: list[SourceGlyph], page: int) -> list[NeutralLine]:
    """Cluster eligible source glyphs into neutral lines, carrying their GIDS.

    Same geometric rule A19 froze -- tolerance 0.5 x median ink height, descending baseline,
    anchored on the cluster's first glyph -- but each line now OWNS an explicit gid set, so
    membership is a fact rather than something inferred later.

    A38.2: each line also owns its `(ngid, x0)` candidates, from the SAME eligible source
    glyphs that formed it -- so `gids` and `candidates` cannot disagree by construction. The
    x0 is NOT rounded: the line's aggregate bbox is rounded for reporting, but the identity
    resolver compares candidate x0 against a converted pixel coordinate, and rounding there
    would move a nearest-glyph decision.
    """
    if not glyphs:
        return []
    tol = BASELINE_TOL_FACTOR * (statistics.median([g.height for g in glyphs]) or 1.0)
    rows: list[list[SourceGlyph]] = []
    anchor: float | None = None
    for g in sorted(glyphs, key=lambda g: (-g.baseline, g.x0, g.gid)):
        if anchor is None or abs(g.baseline - anchor) > tol:
            rows.append([g])
            anchor = g.baseline
        else:
            rows[-1].append(g)
    return [
        NeutralLine(
            page=page,
            ordinal=i,
            baseline=round(statistics.median([g.baseline for g in row]), 4),
            x0=round(min(g.x0 for g in row), 4),
            y0=round(min(g.y0 for g in row), 4),
            x1=round(max(g.x1 for g in row), 4),
            y1=round(max(g.y1 for g in row), 4),
            gids=frozenset(g.gid for g in row),
            candidates=tuple(sorted(((g.gid, g.x0) for g in row), key=lambda c: c[0])),
        )
        for i, row in enumerate(rows)
    ]


def build_owner(lines: list[NeutralLine]) -> dict[int, tuple[int, int]]:
    """gid -> owning neutral-line key, for every eligible glyph on the page.

    The signature needs to name the OTHER neutral lines an emitted line reaches into, and
    naming them by key rather than by index keeps the representation stable if the caller
    ever passes a subset of lines.
    """
    return {g: ln.key for ln in lines for g in ln.gids}


# --------------------------------------------------------------- architecture output


class Cell(NamedTuple):
    """One character in an emitted printed line, with PROVENANCE and IDENTITY separated.

    A24.2 proved these are two different concepts that a single `gid` was overloading:

        ngid   NEUTRAL INK IDENTITY -- which physical mark owns a place in the skeleton.
               `None` for anything that is not neutral ink.
        sci    SOURCE PROVENANCE -- which PDFium text-page character produced this output.
               `None` only when the architecture INVENTED the character.

    A content-stream space has real provenance and NO physical ink identity. Collapsing the
    two made that state unrepresentable, which is why spaces were entering the skeleton.

        ordinary ink              ngid=123  sci=123  char='A'  generated=False
        content-stream U+0020     ngid=None sci=124  char=' '  generated=False
        PDFium-generated U+0020   ngid=None sci=125  char=' '  generated=True
        X-inserted space          ngid=None sci=None char=' '  generated=False

    Only `ngid` may reach the neutral skeleton, `common`, the reconstruction signature or a
    loss diagnostic. `sci` and `char` are the architecture's own output and stay visible to
    projected text and therefore to M2/M3.
    """

    ngid: int | None
    char: str
    sci: int | None = None
    generated: bool = False


@dataclass
class EmittedLine:
    """ONE reconstructed printed line, as the architecture actually emits it.

    This is deliberately NOT a free-floating "fragment". In both arms the emitted printed
    line is one element of `Page.print_lines` -- a single non-chrome baseline cluster, with
    its GPO margin number already stripped. `Page.lines` (the `_merge_print_lines` output)
    is a LATER, deterministic soft-hyphen recombination shared by both arms, and is not the
    unit: it spans several physical lines by design, so scoring it would manufacture a
    cross-line merge on every hyphenated line in BOTH arms at once.

    `lid` is the architecture's own emitted-line identity, `(page_number, index within
    Page.print_lines)`. It exists so that "these two glyphs were emitted on the same line"
    is a recorded fact rather than something re-derived from geometry.

    Each cell is a `Cell`, which keeps NEUTRAL INK IDENTITY (`ngid`) separate from SOURCE
    PROVENANCE (`sci`). A cell with `ngid is None` is not neutral ink -- an inserted word
    space, an engine-generated space, or a content-stream space that has real provenance but
    no physical ink identity. All three are carried, never normalised away, and none of them
    can enter the reconstruction signature.

    A bare `(ngid, char)` pair is accepted and widened to a `Cell`, so the synthetic fixtures
    stay readable; anything constructed that way has no provenance, which is exactly right
    for a fixture that is not describing a real extraction.
    """

    cells: list[Cell] = field(default_factory=list)
    lid: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        self.cells = [c if isinstance(c, Cell) else Cell(*c) for c in self.cells]

    @property
    def gids(self) -> set[int]:
        """NEUTRAL INK identities only. Never provenance."""
        return {c.ngid for c in self.cells if c.ngid is not None}

    def text(self) -> str:
        return "".join(c.char for c in self.cells)


def contribution(emitted: list[EmittedLine], line: NeutralLine) -> str:
    """MODEL G -- the architecture's text for exactly the glyphs this neutral line owns.

    Set membership on gids. No tolerance, no nearest-anything, no text similarity.

    Spacing is PRESERVED, which is the whole point: a NON-NEUTRAL character (`ngid is None`)
    is kept when it sits BETWEEN two retained ink glyphs of this line. So the same ink set
    yields "FAMILYHOUSING" from an architecture that welded and "FAMILY HOUSING" from one
    that did not -- the neutral skeleton supplies identity and never supplies spacing.

    THE ATTACHMENT RULE, frozen by A24.2 and unchanged in substance by it:

        a non-neutral character contributes to neutral line N iff, in the architecture's own
        emitted order, it lies BETWEEN two ink glyphs that N owns, with no ink glyph of
        another neutral line intervening.

    A24.2 makes this rule carry more traffic than before -- a content-stream space now has
    `ngid is None` like an inserted one -- and it needed no change to do so, which is the
    point: the rule was already about ATTACHMENT, not about identity. Its consequences,
    each tested rather than argued:

      * leading and trailing spaces are dropped (nothing owned precedes / follows them);
      * a space between ink of two DIFFERENT neutral lines is dropped from both, since a
        foreign ink glyph clears the pending buffer. It belongs to neither exclusively and
        no tie-break is invented;
      * consecutive spaces are kept or dropped together;
      * a content-stream space, a generated space and an X-inserted space are treated
        identically here, because at this point they differ only in provenance -- which is
        recorded on the cell and never consulted for attachment.

    Emitted lines are concatenated in the order of their FIRST owned gid, so ordering is a
    function of source identity rather than of emission order: reversing the list cannot
    change the result.

    THEY ARE JOINED BY "\\n", NOT BY "". This corrects A21, which joined by "" and thereby
    manufactured a WELD out of a SPLIT. When an arm emits one neutral line as two printed
    lines, its output really does carry a line break between those characters -- production
    joins printed lines with "\\n" (`Page.text`) -- so "" asserts an adjacency the arm never
    produced. The consequence was not cosmetic: a heading split at a word boundary would
    have projected as `FAMILYHOUSING`, scored a fabricated M3 weld against an oracle reading
    `FAMILY HOUSING`, and counted as `X_REGRESSES` -- a veto term in Rule 1.

    "\\n" needs no new machinery downstream: `m3_boundaries.decompose` tests `ch.isspace()`,
    so a line break is already read as a word boundary, and M2's frozen normalisation
    already collapses whitespace runs. A split at a word boundary therefore costs nothing,
    while a split MID-word still registers as a real boundary defect, which is correct --
    the arm did break the word across two printed lines.
    """
    owned: list[tuple[list[Cell], int]] = []
    for frag in emitted:
        kept: list[Cell] = []
        pending: list[Cell] = []
        seen_owned = False
        for cell in frag.cells:
            gid = cell.ngid
            if gid is None:
                (pending if seen_owned else []).append(cell)
                continue
            if gid in line.gids:
                if seen_owned:
                    kept.extend(pending)
                pending = []
                kept.append(cell)
                seen_owned = True
            else:
                pending = []  # an inserted char adjacent to a foreign glyph is not ours
        if kept:
            first = min(c.ngid for c in kept if c.ngid is not None)
            owned.append((kept, first))
    owned.sort(key=lambda kv: kv[1])
    return "\n".join("".join(c.char for c in cells) for cells, _ in owned)


def emitted_gids(emitted: list[EmittedLine]) -> set[int]:
    """Every NEUTRAL INK glyph this architecture emitted anywhere on the page.

    Neutral identities only. A24.2: a content-stream space has provenance but no ink
    identity, so it can never enter `common`, a signature, or a loss diagnostic.
    """
    return {g for f in emitted for g in f.gids}


def reconstruction_signature(
    emitted: list[EmittedLine],
    line: NeutralLine,
    owner: dict[int, tuple[int, int]],
    common: set[int],
) -> tuple:
    """How this architecture GROUPED the JOINTLY OBSERVED glyphs of this neutral line.

    One element per emitted line carrying at least one jointly observed gid of this neutral
    line, ordered by its first such gid:

        (this line's COMMON gids the emitted line carries,
         other neutral lines it reaches THROUGH COMMON gids)

    `common` is the page-wide set of gids BOTH arms emitted. Restricting to it is what
    separates grouping from coverage, and it is the whole of this repair.

    WHY THE RESTRICTION IS NECESSARY. Without it the signature reads the exact emitted gid
    subset, so PURE CHARACTER LOSS moves it: H emitting {0,1,2} as one line and X emitting
    {0,2} as one line gave `((0,1,2),())` vs `((0,2),())` -- unequal -- and reported a
    SEGMENTATION difference where both arms produced ONE line with identical grouping
    topology and X had simply dropped a glyph. Coverage was masquerading as topology.

    WHY IT MUST ALSO GOVERN `others`. Suppose H emits one line carrying N1's glyphs plus a
    glyph of N2 that X never emits. Reading `others` over ALL gids would name N2 for H and
    nothing for X, manufacturing a cross-line merge out of a coverage difference. Reading
    it over `common` cannot: a glyph only one arm emitted is not evidence about how the two
    arms GROUP anything, and it is already visible as loss and as a text difference.

    WHY TOPOLOGY STILL SURVIVES A COVERAGE DEFECT. The restriction removes gids, never
    grouping. If H merges N0+N1 while ALSO losing a glyph of N1, the surviving jointly
    observed glyphs of N1 are still carried by an emitted line that also carries N0's, so
    `others` still names N0 for H and not for X. Merge detection is untouched -- tested.

    Deliberately absent, each for a reason:

      * text and inserted characters -- a word-space difference must not register as a
        segmentation difference, or M3 would see a boundary error that does not exist;
      * REPEATED gids -- `EmittedLine.gids` is a set, so duplication cannot move the
        signature. (Measured: it never did. Duplication was already classified correctly
        before this repair, and only loss was mis-classified.);
      * emitted-line ids -- two arms numbering their lines differently is not a disagreement
        about grouping, and including lids would make every comparison trivially unequal;
      * glyphs off the neutral skeleton -- a coverage fact, counted separately.

    VACUOUS CASE, stated rather than hidden. When no gid of this line is jointly observed --
    one arm emitted nothing for it -- the signature is `()` for both arms and segmentation is
    concordant. That is correct: with no shared evidence there is no grouping to disagree
    about. The case is carried in full by text/coverage discordance, so it never leaves the
    D-frame; only its ATTRIBUTION between the two components changes.
    """
    parts: list[tuple[tuple[int, ...], tuple[tuple[int, int], ...], int]] = []
    for frag in emitted:
        shared = frag.gids & common
        owned = sorted(shared & line.gids)
        if not owned:
            continue
        others = sorted({owner[g] for g in shared if g in owner and owner[g] != line.key})
        parts.append((tuple(owned), tuple(others), owned[0]))
    parts.sort(key=lambda t: t[2])
    return tuple((o, ot) for o, ot, _ in parts)


def line_state(
    h_emitted: list[EmittedLine],
    x_emitted: list[EmittedLine],
    line: NeutralLine,
    owner: dict[int, tuple[int, int]],
    common: set[int] | None = None,
) -> dict:
    """The frozen per-neutral-line comparison object.

    Carries BOTH comparable quantities -- projected text and reconstruction signature --
    plus the coarse presence label and the diagnostics. The label is for reading; the two
    quantities are what the discordance predicates consume.

    `common` is the page-wide jointly emitted gid set. It is a property of the PAGE, not of
    the line, so the harness computes it once per page and passes it in; it is derived here
    when omitted so a caller comparing a single line cannot accidentally get it wrong.
    """
    h_own = [f for f in h_emitted if f.gids & line.gids]
    x_own = [f for f in x_emitted if f.gids & line.gids]
    if common is None:
        common = emitted_gids(h_emitted) & emitted_gids(x_emitted)
    h_text, x_text = contribution(h_emitted, line), contribution(x_emitted, line)
    h_sig = reconstruction_signature(h_emitted, line, owner, common)
    x_sig = reconstruction_signature(x_emitted, line, owner, common)

    if not h_own and not x_own:
        state = "BOTH_ABSENT"
    elif not h_own:
        state = "H_ABSENT"
    elif not x_own:
        state = "X_ABSENT"
    else:
        state = "SAME" if h_text == x_text else "TEXT_DIFFERS"

    h_gids = {g for f in h_emitted for g in f.gids} & line.gids
    x_gids = {g for f in x_emitted for g in f.gids} & line.gids
    h_seq = [c.ngid for f in h_own for c in f.cells if c.ngid in line.gids]
    x_seq = [c.ngid for f in x_own for c in f.cells if c.ngid in line.gids]
    return {
        "line": line.key,
        "state": state,
        "h_text": h_text,
        "x_text": x_text,
        "h_signature": h_sig,
        "x_signature": x_sig,
        "common_gids": sorted(line.gids & common),
        "diagnostics": {
            "H_EMITTED_LINE_COUNT": len(h_own),
            "X_EMITTED_LINE_COUNT": len(x_own),
            "H_SOURCE_GLYPH_LOSS": sorted(line.gids - h_gids),
            "X_SOURCE_GLYPH_LOSS": sorted(line.gids - x_gids),
            "SHARED_SOURCE_GLYPH_LOSS": sorted(line.gids - h_gids - x_gids),
            "H_SOURCE_GLYPH_DUPLICATION": len(h_seq) != len(set(h_seq)),
            "X_SOURCE_GLYPH_DUPLICATION": len(x_seq) != len(set(x_seq)),
            "H_CROSS_LINE_MERGE": any(f.gids - line.gids for f in h_own),
            "X_CROSS_LINE_MERGE": any(f.gids - line.gids for f in x_own),
            # segmentation is only DEFINED where the two arms share evidence about this
            # line. Recorded so a zero M0b can never be read as "the arms agreed" when it
            # actually means "there was nothing to compare".
            "SEGMENTATION_DEFINED": bool(line.gids & common),
        },
    }


# ------------------------------------------------------------------ discordance rules
#
# Every predicate below is an INEQUALITY BETWEEN THE TWO ARMS' OWN VALUES. That is what
# makes symmetry structural rather than tested-and-hoped-for: `a != b` is `b != a` for any
# a and b, so D(H,X) == D(X,H) holds by construction and the tests confirm the construction
# rather than establish the property. One-arm "badness" flags are deliberately NOT used:
# if both arms merge N0 and N1 the same way there is no H/X discordance to adjudicate, and
# a rule reading `H_CROSS_LINE_MERGE or X_CROSS_LINE_MERGE` would wrongly include it.


def text_discordance(state: dict) -> bool:
    """Did the arms produce different CHARACTERS for this neutral line's glyphs?

    Absence is a text difference, not a separate case: an arm that emits nothing for the
    line contributes "", so H_ABSENT and X_ABSENT fall out of the same comparison and keep
    their mirror symmetry for free.
    """
    return state["h_text"] != state["x_text"]


def segmentation_discordance(state: dict) -> bool:
    """Did the arms GROUP this neutral line's glyphs into emitted lines differently?"""
    return state["h_signature"] != state["x_signature"]


def line_discordance(state: dict) -> bool:
    """D-frame membership contributed by one neutral line: the union of the two.

    NOTE the case this deliberately excludes. When NEITHER arm emits the line -- a running
    head, a page number, a `VerDate` stamp, all correctly dropped as chrome by both -- both
    texts are "" and both signatures are (), so nothing fires. The previous rule
    (`state != "SAME"`) put every such line in the D-frame, scoring agreement as
    discordance and flooding a census frame with page furniture. PRE-REGISTRATION 5.8 is
    explicit that the D-frame "cannot see a failure both architectures share. That is
    exactly why the C-frame exists", so a shared drop belongs to RQ2, not here. It stays
    visible as the BOTH_ABSENT count.
    """
    return text_discordance(state) or segmentation_discordance(state)


def anchor_discordance(h_anchors, x_anchors) -> bool:
    """Do the arms emit different anchor sets for this region?

    Region-level, as PRE-REGISTRATION 5.8 fixes it ("every region where their emitted
    anchor sets differ"). An anchor is placed in a region by IDENTITY, not by position: the
    neutral line owning the first gid of the emitted line the anchor was read from decides
    its region. Sets, so ordering cannot create a spurious difference.
    """
    return set(h_anchors) != set(x_anchors)


def region_discordance(states: list[dict], h_anchors=(), x_anchors=()) -> bool:
    """A neutral region enters the D-frame iff any of the three discordances fires."""
    return any(line_discordance(s) for s in states) or anchor_discordance(h_anchors, x_anchors)


def in_risk_set(state: dict) -> bool:
    """Is this neutral line a unit on which the two arms could have differed at all?

    THE COMPARATIVE RISK SET: neutral lines emitted by AT LEAST ONE architecture. A line
    neither arm emitted is not an aligned printed line, and there is nothing about it to
    compare.

    "At least one", never "both": an arm emitting a line the other dropped is one of the
    strongest discordances there is, and a both-arms denominator would delete the
    numerator's own members from the population it is a fraction of.
    """
    return state["state"] != "BOTH_ABSENT"


def m0(states: list[dict]) -> dict:
    """M0's components. Raw counts preserved; no weighted composite is invented.

    DENOMINATOR: the comparative risk set -- neutral lines emitted by at least one arm.

    WHY BOTH_ABSENT IS OUT. PRE-REGISTRATION 6 defines M0 as the fraction of aligned
    printed lines "whose text differs BETWEEN H AND X". A line neither arm emitted is not a
    comparative observation on which they agreed; it is a unit not at risk. Counting it as
    an agreement makes the reported rate depend on how much page furniture a document
    carries -- running heads, page numbers, VerDate stamps -- which is a property of GPO's
    LAYOUT, not of the seam. That is a nuisance variable in the denominator, and it is worse
    than dilution: committee reports and bills carry different chrome densities, so a
    P-head/P-robust difference in M0 could be pure furniture.

    The question "discordance per physical ink line on the page" is a real question, but it
    is an ABSOLUTE coverage question -- did the arms emit the page's content at all -- and
    that is RQ2's, answered by the C-frame against an adjudicated oracle. M0 is RQ1's
    comparative resolution statement and may not silently answer a different one.

    NOTE THE DIRECTION, so the choice cannot be read as chosen for the number: removing
    BOTH_ABSENT SHRINKS the denominator and therefore RAISES every reported discordance
    rate. On development material the shift is about +7 % relative. RQ1 seeks an equivalence
    statement, so this change makes the study's own claim HARDER to support, not easier.

    `both_absent` is preserved as a raw count and is NOT discarded -- see `in_risk_set`.

    `M0b_only` is the number the segmentation repair exists to produce: neutral lines where
    the arms agree on every character but disagree on how they cut the page into lines.

    `M0b_defined` / `M0b_rate_on_defined` are reported beside the headline because
    segmentation is only DEFINED where the arms share evidence about a line. A zero M0b on
    the risk set must never be readable as "the arms grouped identically" when it could mean
    "one arm emitted nothing to group".
    """
    risk = [s for s in states if in_risk_set(s)]
    n = len(risk)
    text = [s for s in risk if text_discordance(s)]
    seg = [s for s in risk if segmentation_discordance(s)]
    any_d = [s for s in risk if line_discordance(s)]
    seg_only = [s for s in seg if not text_discordance(s)]
    text_only = [s for s in text if not segmentation_discordance(s)]
    defined = [s for s in risk if s["diagnostics"]["SEGMENTATION_DEFINED"]]
    return {
        "neutral_lines_in_scope": len(states),
        "risk_set": n,
        "M0a_text": len(text),
        "M0b_segmentation": len(seg),
        "M0_any": len(any_d),
        "M0b_only_segmentation": len(seg_only),
        "M0a_only_text": len(text_only),
        "both_absent": sum(1 for s in states if s["state"] == "BOTH_ABSENT"),
        "M0b_defined": len(defined),
        "M0a_text_rate": round(len(text) / n, 6) if n else None,
        "M0b_segmentation_rate": round(len(seg) / n, 6) if n else None,
        "M0_any_rate": round(len(any_d) / n, 6) if n else None,
        "M0b_rate_on_defined": round(len(seg) / len(defined), 6) if defined else None,
        # the superseded denominator, kept so the two estimands stay comparable in the
        # record rather than the change being invisible after the fact
        "M0_any_rate_ALL_LINES_superseded": round(len(any_d) / len(states), 6) if states else None,
    }
