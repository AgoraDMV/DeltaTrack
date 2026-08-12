"""Pure encodings of frozen methodology rules. NOT a harness component.

Each function here is a frozen rule written down executably so it can be tested before any
result-bearing component consumes it. Nothing here reads a PDF, an architecture output, an
oracle, or the holdout; nothing here makes a decision. `x15_methodology_contracts.py` is the
test.

    A28.1   adequacy occurrence counting -- the union of A27.1 source-position keys
    A28.2   the 4.5 adequacy state machine
    A28.3   canonical PRE-BLINDING stimulus identity, and the blind id derived from it
    A28.4   frozen renderer scale
    A27.7   domain-separated deterministic ranking
"""

from __future__ import annotations

import hashlib
import json
import math

# ----------------------------------------------------------------- A27.7 determinism

SELECTION_SEED = 20260807


def canonical(obj) -> str:
    """One canonical serialization for every identity tuple. Tested, not assumed.

    `sort_keys` + no whitespace + explicit list/tuple coercion, so the same logical identity
    can never hash two ways because a caller passed a tuple where another passed a list.
    """

    def norm(o):
        if isinstance(o, (list, tuple)):
            return [norm(x) for x in o]
        if isinstance(o, dict):
            return {str(k): norm(v) for k, v in o.items()}
        return o

    return json.dumps(norm(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def rank_key(namespace: str, item_identity) -> str:
    """A27.7: deterministic rank of one item within one purpose. No RNG, no input order."""
    return hashlib.sha256(f"{namespace}|{SELECTION_SEED}|{canonical(item_identity)}".encode()).hexdigest()


def select(namespace: str, identities: list, k: int) -> list:
    """The first `k` identities by domain-separated rank. Order-independent and reproducible."""
    return [i for _r, i in sorted((rank_key(namespace, i), i) for i in identities)][:k]


def order(namespace: str, identities: list) -> list:
    """Full deterministic ordering, used for blind presentation order."""
    return [i for _r, i in sorted((rank_key(namespace, i), i) for i in identities)]


# ------------------------------------------------- A28.3 canonical stimulus identity


def base_stimulus_identity(document_sha256: str, page_number: int, region_ordinal: int):
    return ("region", document_sha256, page_number, region_ordinal)


def control_stimulus_identity(
    control_kind: str, source_fixture_sha256: str, page_number: int, region_ordinal: int, control_variant: str
):
    return ("control", control_kind, source_fixture_sha256, page_number, region_ordinal, control_variant)


def r1_repeat_identity(base_identity):
    return ("r1-repeat", list(base_identity))


def blind_id(final_stimulus_identity) -> str:
    """The adjudicator-facing ALIAS, derived AFTER all selection is settled.

    It exists only so the adjudicator cannot infer provenance. It must never determine
    membership, repeat selection, audit selection or presentation order -- those all rank
    canonical identities. `x15` proves that by re-deriving every selection under a different
    blind-id scheme and requiring identical results.
    """
    return hashlib.sha256(f"blind-id|{SELECTION_SEED}|{canonical(final_stimulus_identity)}".encode()).hexdigest()[:16]


class BlindIdCollision(Exception):
    """A30.5 -- two distinct realized stimuli were assigned the same adjudicator-facing id."""


class DuplicateStimulusIdentity(Exception):
    """A30.5 -- the realized stimulus set contains the same canonical identity twice."""


def assert_realized_blind_ids_unique(final_identities) -> dict:
    """A30.5 -- blind ids must be unique over the COMPLETE REALIZED stimulus set.

    Called before any oracle artifact is committed and before adjudication begins; returns
    `blind id -> canonical identity` when clean and RAISES otherwise.

    WHY A SYNTHETIC UNIQUENESS CHECK WAS NOT ENOUGH. x15 shows the scheme separates a
    handful of constructed identities. That is a property of those identities, not a proof
    about the set the study will actually build, which is not known until selection,
    controls and repeats have all been resolved. The invariant has to be asserted on the
    realized set or it is not asserted at all.

    WHY A COLLISION IS A BUILD FAILURE AND NOTHING ELSE. Overwriting loses a stimulus;
    merging fuses two adjudications; last-write-wins silently picks one. Salting or
    re-rolling the alias after seeing the stimulus set would let the set choose the scheme,
    which is exactly the influence A28.3 removed when it stopped blind ids from steering
    sampling. So this refuses deterministically and requires review.
    """
    mapping: dict[str, str] = {}
    seen: set[str] = set()
    for ident in final_identities:
        form = canonical(ident)
        if form in seen:
            raise DuplicateStimulusIdentity(f"identity appears twice in the realized set: {form}")
        seen.add(form)
        bid = blind_id(ident)
        if bid in mapping:
            raise BlindIdCollision(f"blind id {bid} claimed by both {mapping[bid]} and {form}")
        mapping[bid] = form
    return mapping


# ------------------------------------------------------------- A28.4 renderer scale

PRIMARY_DPI = 300
R1_REPEAT_DPI = 330  # 300 x 1.10, fixed pre-execution; higher so the repeat is not less legible


def required_dpi(is_r1_repeat: bool) -> int:
    return R1_REPEAT_DPI if is_r1_repeat else PRIMARY_DPI


# --------------------------------------------------- A28.1 / A28.2 section 4.5 adequacy

ADEQUACY_KINDS = frozenset({"account", "agency", "grouping"})
# A28.1 restricts adequacy to the P-head population. A30.4 makes that restriction
# EXECUTABLE here rather than an obligation on callers -- see `filter_keys`.
P_HEAD = "P-head"


def adequacy_occurrences(h_keys, x_keys) -> int:
    """|H_keys union X_keys| over A27.1 source-position occurrence keys.

    Symmetric: neither arm's failure can remove a key the other emitted. Counts one physical
    occurrence once even when both arms emit it, because the key is a source position rather
    than an arm's output. No text similarity and no oracle result enters this.

    Callers pass keys already restricted by `filter_keys`, which since A30.4 applies BOTH
    the P-head population restriction and the account / agency / grouping kind restriction
    itself rather than trusting the caller to have done it.

    Each key is an A30.1 occurrence identity, whose fourth component is the absolute
    `start_ngid` -- so two occurrences beginning on one physical line stay distinct, and a
    missing earlier occurrence cannot renumber a later one.
    """
    return len(set(h_keys) | set(x_keys))


def filter_keys(keyed) -> set:
    """Keep only P-head account/agency/grouping occurrences (A28.1, executable by A30.4).

    Input is `(key, kind, population)`.

    KIND. The design pilot's "heading occurrences emitted" quantity used exactly those three
    classes; the later oracle codebook is broader, and widening the adequacy denominator to
    title/division/section would silently make the holdout look more adequate than the
    frozen quantity it is compared against.

    POPULATION. A28.1 restricts adequacy to P-head, but until A30.4 this function filtered
    on kind alone and its docstring made the population restriction an obligation on the
    CALLER. A caller obligation is not a gate: it cannot fail, and nothing in the harness
    would have reported a P-robust document silently inflating the adequacy count -- the
    number would simply have been larger, and larger reads as *more* adequate. Applying both
    restrictions here makes the frozen clause falsifiable, and x15 proves it by adding
    arbitrarily many P-robust adequacy-kind keys and requiring the count not to move.
    """
    return {key for key, kind, population in keyed if population == P_HEAD and kind in ADEQUACY_KINDS}


# ------------------------------------------------------- A36.7 the M5 role coarsening

M5_LEAF = "LEAF"
M5_CONTAINER = "CONTAINER"
M5_UNSCORABLE = "UNSCORABLE"

# The adjudicator records the FINE section 5.3 role; M5 alone coarsens it. HARNESS-PLAN 3's
# "coarse leaf/container role" described this SCORING map, not what the adjudicator writes down
# -- asking only leaf-vs-container would discard information 5.3 requires and could not be
# recovered later.
ORACLE_ROLE_TO_M5 = {
    "account": M5_LEAF,
    "section": M5_LEAF,
    "agency": M5_CONTAINER,
    "grouping": M5_CONTAINER,
    "title": M5_CONTAINER,
    "division": M5_CONTAINER,
    "other": M5_UNSCORABLE,
}

# Production's emitted anchor kinds. COMPLETE against `AnchorKind`, which x21 asserts against
# the production Literal rather than trusting this comment -- a kind added to production later
# must FAIL a control instead of arriving silently as an unmapped role.
#
# `division` is an oracle role and an `Anchor` FIELD, never an emitted KIND, which is why it
# appears in the oracle map only.
EMITTED_KIND_TO_M5 = {
    "account": M5_LEAF,
    "section": M5_LEAF,
    "major": M5_CONTAINER,
    "agency": M5_CONTAINER,
    "grouping": M5_CONTAINER,
    "title": M5_CONTAINER,
    "subsection": M5_UNSCORABLE,
    "preamble": M5_UNSCORABLE,
}


class UnknownRole(Exception):
    """A36.7 -- a role outside the frozen map. Refuses; never silently UNSCORABLE.

    Mapping an unknown role to UNSCORABLE would quietly SHRINK the M5 denominator, and a
    smaller denominator reads as a cleaner result rather than as a defect.
    """


def m5_oracle_role(role: str) -> str:
    if role not in ORACLE_ROLE_TO_M5:
        raise UnknownRole(f"oracle role not in the frozen A36.7 map: {role!r}")
    return ORACLE_ROLE_TO_M5[role]


def m5_emitted_kind(kind: str) -> str:
    if kind not in EMITTED_KIND_TO_M5:
        raise UnknownRole(f"emitted kind not in the frozen A36.7 map: {kind!r}")
    return EMITTED_KIND_TO_M5[kind]


def m5_scorable(oracle_role: str, emitted_kind: str) -> bool:
    """A36.7 -- in the M5 denominator only when BOTH sides coarsen to LEAF or CONTAINER."""
    return M5_UNSCORABLE not in (m5_oracle_role(oracle_role), m5_emitted_kind(emitted_kind))


def m5_agreement(oracle_role: str, emitted_kind: str):
    """Do the two sides agree after coarsening? `None` when the pair is out of scope.

    `None` rather than False: an excluded pair is not a disagreement, and counting it as one
    would penalise the architecture for a role M5 was never licensed to score.
    """
    if not m5_scorable(oracle_role, emitted_kind):
        return None
    return m5_oracle_role(oracle_role) == m5_emitted_kind(emitted_kind)


# ------------------------------ A37 the supplementary document bootstrap (NON-GATING)

#: A27.6's decision-blocking conditions, written down so "the bootstrap is not one of them"
#: is a CHECKABLE statement rather than a promise in prose. Cross-engine (x09) is absent on
#: purpose: it qualifies reporting and never blocks a decision.
GATE_VECTOR = (
    "R1",
    "N-A",
    "N-B",
    "N-C",
    "S1",
    "confirmatory X2-a",
    "confirmatory X2-b",
    "M9 evaluability",
    "4.5 adequacy",
)

BOOTSTRAP_NAMESPACE = "bootstrap-document"
BOOTSTRAP_RESAMPLES = 10_000

#: A37.3 -- THE canonical identity of the section 8 event. One constant, so callers cannot
#: invent competing labels for the same statistic and get different draw sequences.
#:
#: The population component is NOT decoration. Section 4.4.1 splits P-head from P-robust and
#: states that NO heading metric is claimed on P-robust; the section 8 event is heading-level,
#: so this statistic is P-head only. Encoding that here means a P-robust variant cannot
#: silently reuse this draw sequence.
SECTION8_DOCUMENT_DISCORDANCE = ("section8", "document-heading-discordance", P_HEAD)

EMPTY_DOCUMENT_SET = "EMPTY_DOCUMENT_SET"
DUPLICATE_DOCUMENT_IDENTITY = "DUPLICATE_DOCUMENT_IDENTITY"
NON_BOOLEAN_EVENT = "NON_BOOLEAN_EVENT"
ZERO_EVENTS_BOOTSTRAP_REFUSED = "ZERO_EVENTS_BOOTSTRAP_REFUSED"


class BootstrapInputError(Exception):
    """A37.2 -- the document vector is not a valid set of independent units. Refuses."""

    def __init__(self, reason: str, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason} {detail!r}")


def bootstrap_draw_index(statistic_id, replicate: int, draw: int, n: int) -> int:
    """A37.4 -- which document the `draw`-th pick of `replicate` takes, from `n` documents.

    Hash-derived rather than drawn from a PRNG. A seeded PRNG would freeze the interval only
    for one library's generator and one consumption order; this depends on nothing but the
    committed identity of the statistic and the two ordinals, so any implementation in any
    language reproduces the same resample. There is no RNG object and no input-order
    dependence to leak in.
    """
    digest = hashlib.sha256(
        f"{BOOTSTRAP_NAMESPACE}|{SELECTION_SEED}|{canonical(statistic_id)}|{replicate}|{draw}".encode()
    ).digest()
    return int.from_bytes(digest[:8], "big") % n


def canonical_document_vector(records) -> list:
    """A37.2 -- validate and CANONICALLY SORT one record per independent document.

    `records` is `[(document_identity, event_boolean), ...]`.

    A duplicate identity REFUSES rather than being weighted twice: the document is the
    independent unit (8.3, red-team #7), so a repeated document is either a caller error or a
    headings-as-rows table being passed in, and silently double-weighting it would inflate
    whatever it carries. That refusal is what makes a heading-level table unpassable here.

    Sorting is LOAD-BEARING, not tidiness: the draw is an INDEX, so without a canonical order
    the caller's listing order silently selects different documents and two runs over the same
    set print different intervals. That is the defect withdrawn A29 measured.
    """
    rows = list(records)
    if not rows:
        raise BootstrapInputError(EMPTY_DOCUMENT_SET, {"n": 0})
    seen = set()
    for identity, event in rows:
        # `isinstance(1, bool)` is False, so a bare 0/1 is correctly refused here even though
        # bool subclasses int. An int event would silently work in `sum()` and never be seen.
        if not isinstance(event, bool):
            raise BootstrapInputError(NON_BOOLEAN_EVENT, {"document": identity, "event": repr(event)})
        form = canonical(identity)
        if form in seen:
            raise BootstrapInputError(DUPLICATE_DOCUMENT_IDENTITY, {"document": form})
        seen.add(form)
    return sorted(rows, key=lambda row: canonical(row[0]))


def bootstrap_resample(statistic_id, vector: list, replicate: int) -> list:
    """One replicate: `n` draws WITH REPLACEMENT over documents, the resampling unit (A27.5).

    `vector` must already be canonical -- see `canonical_document_vector`.
    """
    n = len(vector)
    return [vector[bootstrap_draw_index(statistic_id, replicate, d, n)] for d in range(n)]


def percentile_indices(b: int = BOOTSTRAP_RESAMPLES) -> tuple[int, int]:
    """A37.6 -- the frozen ORDER-STATISTIC indices. B = 10_000 gives exactly (249, 9749).

    Stated normatively rather than left to a library: NumPy's default `percentile` linearly
    INTERPOLATES between neighbours, which would emit an endpoint that is not an observed
    replicate value and would drift if the backend changed. Both endpoints here are always
    values the bootstrap actually produced.
    """
    return math.floor(0.025 * (b - 1)), math.floor(0.975 * (b - 1))


def zero_event_upper_bound(n: int) -> float:
    """8.3 / A27.5 -- the frozen zero-event Clopper-Pearson closed form `1 - 0.05**(1/N)`.

    Only the ZERO-EVENT form lives here, because it is a closed form the protocol froze
    verbatim. The general Clopper-Pearson bound remains `score_metrics`' obligation (A27.5)
    and is deliberately not implemented in this pure-contract module.
    """
    if n < 1:
        raise BootstrapInputError(EMPTY_DOCUMENT_SET, {"n": n})
    return 1 - 0.05 ** (1 / n)


def section8_document_bootstrap(records) -> dict:
    """A37 -- SUPPLEMENTARY ONLY. A 95 % percentile interval over 10,000 document resamples.

    **This value is reporting, never evidence.** It is not an input to Rule 0, Rule 1, Rule 3,
    any adequacy gate, or any architecture-selection outcome -- `GATE_VECTOR` states the
    decision-blocking conditions so that claim is checkable. A27.5 already fixed the inference:
    the primary bound is the exact one-sided 95 % Clopper-Pearson bound on the document unit.

    The event count is DERIVED from the records. There is no `events=` parameter, because a
    caller-supplied count can contradict the vector it claims to summarise and nothing would
    detect the disagreement.

    Refuses at zero events rather than returning a degenerate `[0.0, 0.0]`, which 8.1 measured
    and section 8 forbids.
    """
    vector = canonical_document_vector(records)
    n = len(vector)
    events = sum(1 for _identity, event in vector if event)

    if events == 0:
        return {
            "reported": False,
            "reason": ZERO_EVENTS_BOOTSTRAP_REFUSED,
            "n_documents": n,
            "events": 0,
            # the branch still yields the licensed number rather than only an absence
            "clopper_pearson_upper_bound": zero_event_upper_bound(n),
            "gating": False,
        }

    rates = sorted(
        sum(1 for _identity, event in bootstrap_resample(SECTION8_DOCUMENT_DISCORDANCE, vector, r) if event) / n
        for r in range(BOOTSTRAP_RESAMPLES)
    )
    lo_i, hi_i = percentile_indices(BOOTSTRAP_RESAMPLES)
    return {
        "reported": True,
        "statistic": list(SECTION8_DOCUMENT_DISCORDANCE),
        "resamples": BOOTSTRAP_RESAMPLES,
        "namespace": BOOTSTRAP_NAMESPACE,
        "seed": SELECTION_SEED,
        "unit": "document",
        "n_documents": n,
        "events": events,
        "observed_rate": events / n,
        "endpoint_indices": [lo_i, hi_i],
        "interval": [rates[lo_i], rates[hi_i]],
        "gating": False,
    }


# ------------------------------- A39.1 Rule 0's margin-line clause, and A39.2 page sampling

RULE0_NO_MARGIN_LINE_LOSS = "NO_MARGIN_LINE_LOSS"


def margin_line_loss(h_recovered: int, x_recovered: int) -> dict:
    """A39.1 -- which architecture, if either, LOSES margin-numbered lines on this document.

    The quantity is `count of Page.lines where line_number is not None`, and NOT `_coverage`'s
    numerator. Section 6's M9 row lists three SEPARATE quantities -- band, coverage >= 0.85,
    and "how many margin-numbered lines are recovered" -- so the third cannot be the second's
    numerator without the row naming one quantity twice.

    ANY strictly positive deficit counts. There is no tolerance, no minimum count, no
    percentage and no severity threshold, because the frozen text says "loses", not "loses
    more than N". Inventing one here would be choosing the sensitivity of a decision rule.
    """
    if h_recovered < x_recovered:
        return {"loser": "H", "fires": True, "h": h_recovered, "x": x_recovered, "deficit": x_recovered - h_recovered}
    if x_recovered < h_recovered:
        return {"loser": "X", "fires": True, "h": h_recovered, "x": x_recovered, "deficit": h_recovered - x_recovered}
    return {"loser": None, "fires": False, "h": h_recovered, "x": x_recovered, "deficit": 0}


# A39.2 owns the SAMPLE. It deliberately does NOT own the gate: the matching rule, the
# `max(pdfium, pymupdf)` denominator and both thresholds belong to `x09_skeleton_cross_engine`
# and are called from there. A duplicate `cross_engine_qualification` lived here briefly and
# drifted immediately -- the confirmatory producer built against it scored `matched / pdfium`,
# which made PyMuPDF over-segmentation invisible. One executable owner, or the two disagree.
CROSS_ENGINE_NAMESPACE = "cross-engine-page"
CROSS_ENGINE_FRACTION = 0.10


def cross_engine_pages(document_sha256: str, page_numbers) -> list[int]:
    """A39.2 -- the frozen 10 % cross-engine page sample for ONE document.

    `k = max(1, ceil(0.10 * page_count))`. The `max(1, ...)` is LOAD-BEARING rather than
    defensive: the frozen consequence is per-document, so a document with no sampled page
    could never acquire the PDFIUM-CONDITIONED FRAME qualification the rule attaches to it,
    and a short document would silently escape the control entirely.

    Ranked by the A27.7 domain-separated hash over `(document_sha256, page_number)`. No RNG and
    no caller-order dependence: the returned pages are the same for any input permutation.
    """
    pages = sorted(set(page_numbers))
    if not pages:
        return []
    k = max(1, math.ceil(CROSS_ENGINE_FRACTION * len(pages)))
    identities = [(document_sha256, p) for p in pages]
    chosen = select(CROSS_ENGINE_NAMESPACE, identities, k)
    return sorted(p for _sha, p in chosen)


def adequacy(strata_filled: int, occurrences: int) -> str:
    """A28.2 -- the 4.5 rows as an ORDERED, EXHAUSTIVE state machine. No threshold changed.

    The frozen table left `>= 7 strata` with 300-799 occurrences matching no row, and
    `5-6 strata` with `< 300` matching two rows with no precedence. Ordering the failure
    condition first resolves the overlap conservatively and makes the space total.
    """
    if strata_filled < 5 or occurrences < 300:
        return "INADEQUATE"
    if strata_filled >= 7 and occurrences >= 800:
        return "GENERALISABLE"
    return "LIMITED"
