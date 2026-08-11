"""Drift guard: content-skip allowlist entries must key on live manifest fixtures (#281).

The content-skip ceiling (#220) allowlists individual corpus-gate cases in
``ALLOWED_CORPUS_SKIPS`` (tests/conftest.py). Each key is a full pytest node id whose
parametrize id — e.g. ``[119-hr-1/1_reported-in-house.xml]`` — is generated from the
committed manifest (tests/corpus_manifest.toml, via ``_xml_id``/``_corpus_id`` =
``<bill>/<stage>.<fmt>``). The same fact ("this fixture version cannot be asserted on")
is therefore spelled out in two files that must agree, and they can drift apart
silently: a fixture that leaves the manifest, or a version renamed, strands an
allowlist entry that quietly widens what the ceiling permits until the case it named
reappears under a new id.

``test_allowlisted_skips_name_real_corpus_gate_modules`` (test_corpus_manifest.py) only
checks the MODULE prefix of each key — by its own docstring it cannot see a
parametrize-id change or a fixture that left the manifest. This guard closes exactly
that gap: every allowlist key that carries a manifest-shaped fixture id must reference a
fixture the manifest still declares, or the entry is flagged as stale by name.

``ALLOWED_CI_SLOW_SKIPS`` (#288) has the same drift channel, closed here for #331, with
two twists. Its fixture-keyed entry uses the corpus-expanding gates' idiom — an
EXTENSIONLESS ``<bill>/<stage>`` stage reference (``test_xml_amounts_appear_in_pdf``
reads both formats of a stage, so its parametrize id carries no suffix, e.g.
``[113-hr-3547/4_engrossed-amendment-senate]``). A stage reference is not a single
manifest key: the manifest declares ``<bill>/<stage>.<fmt>``, and a stage committed in
only one format (113-hr-3547 v1 is pdf-only) yields no CI case for a gate that needs
both. The reference is therefore resolved PER-FORMAT against the formats the module's
cases actually need (``_CORPUS_EXPANDING_MODULES``) — the same resolution
``is_watched_case`` applies when deciding which cases CI can collect. And the
anti-vacuity floor cannot demand that every entry be fixture-shaped: most CI-slow
entries are plain ``::test_name`` keys (fixture-absence and environment-gated floors)
with no manifest coupling, legitimately. The floor is therefore per-allowlist and
asserts a POSITIVE COUNT of validated entries.

Scope: only entries whose parametrize id is a manifest fixture reference — either
``<bill>/<stage>.<fmt>`` or the extensionless ``<bill>/<stage>`` stage form — are
manifest-validated. Gate cases that are not parametrized over a manifest fixture — the
class-based ``test_diff_validation`` gates, the plain ``skipif`` functions in
``test_financial_callout_whole_item``, the unparametrized CI-slow floors — have no
manifest coupling to drift, so they are left to the module-prefix guard and the runtime
ceiling.

Same rationale as the ceiling's own regression tests: a drift guard that has never been
shown to fire cannot distinguish "nothing drifted" from "the check is broken", so the
guard is a directly-unit-testable function proven to fire on a stranded entry.
"""

from tests import conftest


def manifest_fixture_ids() -> set[str]:
    """Every fixture the manifest declares, as ``<bill>/<stage>.<fmt>`` — the exact form
    the corpus gates use as their parametrize id (``_xml_id``/``_corpus_id``), so it is
    directly comparable to the fixture id embedded in an allowlist key."""
    return {
        f"{bill['id']}/{ver['stage']}.{fmt}"
        for bill in conftest._manifest_bills()
        for ver in bill["versions"]
        for fmt in ver["formats"]
    }


def allowlist_fixture_id(nodeid: str) -> str | None:
    """The manifest reference an allowlist key carries, or ``None`` if it keys on no
    manifest fixture.

    Returns the parametrize id inside the trailing ``[...]`` when that id is
    fixture-shaped: either a single-format ``<dir>/<name>.xml`` / ``.pdf`` (matching
    ``_xml_id``/``_corpus_id`` = ``<bill>/<stage>.<fmt>``), or the corpus-expanding
    gates' EXTENSIONLESS ``<bill>/<stage>`` stage reference (#331). The stage form is
    not itself a manifest key — ``stale_allowlist_entries`` resolves it per-format
    via ``_resolved_fixture_ids``. A key with no bracket, a bill-only id, a ``->``
    pair id, or a non-fixture param yields ``None`` — it has no manifest coupling
    for this guard to validate."""
    if "[" not in nodeid or not nodeid.endswith("]"):
        return None
    param = nodeid[nodeid.index("[") + 1 : -1]
    if "/" not in param:
        return None
    if param.endswith((".xml", ".pdf")):
        return param
    if "->" not in param and conftest._BILL_STEM.fullmatch(param):
        return param
    return None


def _resolved_fixture_ids(nodeid: str, ref: str) -> tuple[str, ...]:
    """The manifest fixture ids a reference resolves to, per format.

    A single-format ``<bill>/<stage>.<fmt>`` reference resolves to itself. An
    extensionless ``<bill>/<stage>`` reference resolves to one id per format the
    module's cases read, mirroring ``is_watched_case``: the corpus-expanding modules
    declare their formats in ``_CORPUS_EXPANDING_MODULES`` (the amount-recall gate
    reads the xml AND the pdf of a stage), and a stage manifested in only one of
    them yields no CI case — so the reference is stale the moment ANY needed format
    leaves the manifest, not only when the stage disappears entirely. The id shape
    is generated only by the expanding modules; anywhere else it gets the
    fail-closed reading (both formats required)."""
    if ref.endswith((".xml", ".pdf")):
        return (ref,)
    module = nodeid.split("::", 1)[0]
    formats = conftest._CORPUS_EXPANDING_MODULES.get(module, ("xml", "pdf"))
    return tuple(f"{ref}.{fmt}" for fmt in formats)


def stale_allowlist_entries(allowlist: dict[str, str], manifest_ids: set[str]) -> dict[str, str]:
    """Allowlist entries whose referenced fixture(s) are absent from the manifest.

    Maps each stale node id to the manifest reference it carries (a fixture id or,
    for the corpus-expanding gates' extensionless form, the stage reference). An
    entry is stale when any fixture id its reference resolves to — one per format
    the module's cases need — is no longer declared. Empty on a manifest and
    allowlist that agree — the clean-tree case."""
    stale = {}
    for nodeid in allowlist:
        ref = allowlist_fixture_id(nodeid)
        if ref is not None and any(f not in manifest_ids for f in _resolved_fixture_ids(nodeid, ref)):
            stale[nodeid] = ref
    return stale


def test_allowlist_keys_reference_only_live_manifest_fixtures() -> None:
    """The drift guard, run against the real allowlist: every ``ALLOWED_CORPUS_SKIPS``
    key that names a manifest fixture references one the manifest still declares. This is
    the gate that reddens the fast CI run when an allowlist entry and the manifest drift
    apart — the failure mode #281 exists to catch."""
    stale = stale_allowlist_entries(dict(conftest.ALLOWED_CORPUS_SKIPS), manifest_fixture_ids())
    assert stale == {}, (
        f"{len(stale)} content-skip allowlist entry(ies) key on a fixture absent from "
        f"tests/corpus_manifest.toml (stale — the ceiling now silently permits them): "
        f"{stale}. Remove the entry, or restore the fixture to the manifest."
    )


def test_ci_slow_allowlist_keys_reference_only_live_manifest_fixtures() -> None:
    """The #331 guard, run against the real CI-slow allowlist: every
    ``ALLOWED_CI_SLOW_SKIPS`` key that names a manifest fixture — today one entry, the
    amount-recall case keyed on the extensionless stage
    ``113-hr-3547/4_engrossed-amendment-senate`` — resolves to fixtures the manifest
    still declares in every format the case reads. Before #331 a stale entry here went
    undetected where the same entry in ``ALLOWED_CORPUS_SKIPS`` was flagged."""
    stale = stale_allowlist_entries(dict(conftest.ALLOWED_CI_SLOW_SKIPS), manifest_fixture_ids())
    assert stale == {}, (
        f"{len(stale)} CI-slow allowlist entry(ies) key on a fixture absent from "
        f"tests/corpus_manifest.toml (stale — the ceiling now silently permits them): "
        f"{stale}. Remove the entry, or restore the fixture to the manifest."
    )


def test_each_allowlist_drift_guard_validates_a_positive_count_of_entries() -> None:
    """Per-allowlist anti-vacuity floor (#331): each guard run must VALIDATE at least
    one entry against the manifest, or "no stale entries" is indistinguishable from
    "nothing was checked".

    A positive count of VALIDATED entries — not "all entries are fixture-shaped".
    ``ALLOWED_CI_SLOW_SKIPS`` legitimately carries plain ``::test_name`` keys with no
    manifest coupling (fixture-absence and environment-gated floors), and those must
    stay allowed, so the all-fixture-shaped floor #281 used for the corpus allowlist
    cannot be reused as-is."""
    for name, allowlist in (
        ("ALLOWED_CORPUS_SKIPS", conftest.ALLOWED_CORPUS_SKIPS),
        ("ALLOWED_CI_SLOW_SKIPS", conftest.ALLOWED_CI_SLOW_SKIPS),
    ):
        validated = [nodeid for nodeid in allowlist if allowlist_fixture_id(nodeid) is not None]
        assert validated, (
            f"{name}: none of its {len(allowlist)} entries keys on a manifest fixture, "
            "so its drift guard passes vacuously."
        )


def test_guard_flags_a_fixture_absent_from_the_manifest() -> None:
    """A synthetic entry keyed on a never-manifested fixture is flagged, by name and with
    the offending fixture id — the stranded-entry case, demonstrated to fire."""
    nodeid = "tests/test_corpus_properties.py::test_x[999-hr-9999/1_nonexistent.xml]"
    stale = stale_allowlist_entries({nodeid: "made up"}, manifest_fixture_ids())
    assert stale == {nodeid: "999-hr-9999/1_nonexistent.xml"}


def test_guard_flags_a_real_entry_when_its_fixture_leaves_the_manifest() -> None:
    """The issue's live worked example: take a REAL allowlist entry and drop its fixture
    from the manifest (a version renamed, or a fixture removed under #126 curation). The
    guard flags that exact entry — proving it fires on genuine drift of a live entry, not
    only on a hand-built fake."""
    real_nodeid = next(iter(conftest.ALLOWED_CORPUS_SKIPS))
    fixture = allowlist_fixture_id(real_nodeid)
    assert fixture is not None, "precondition: the sampled entry keys on a fixture"
    manifest_missing_that_fixture = manifest_fixture_ids() - {fixture}
    stale = stale_allowlist_entries(dict(conftest.ALLOWED_CORPUS_SKIPS), manifest_missing_that_fixture)
    assert stale.get(real_nodeid) == fixture


def test_guard_ignores_entries_with_no_manifest_fixture_key() -> None:
    """Entries that key on no manifest fixture — a class-based diff gate, a plain
    ``skipif`` callout function — carry no manifest coupling and must NOT be flagged
    (the false-positive direction: this guard governs manifest drift only)."""
    non_fixture = {
        "tests/test_diff_validation.py::TestControlledDiff::test_added_section": "r",
        "tests/test_financial_callout_whole_item.py::test_sec_20004_callout_nets_to_zero": "r",
    }
    assert stale_allowlist_entries(non_fixture, manifest_fixture_ids()) == {}


def test_allowlist_fixture_id_extracts_only_fixture_shaped_params() -> None:
    """The extractor unit: a manifest-shaped parametrize id is returned; a bare test id,
    or a non-fixture param, yields None."""
    assert (
        allowlist_fixture_id("tests/m.py::test_x[119-hr-1/1_reported-in-house.xml]")
        == "119-hr-1/1_reported-in-house.xml"
    )
    assert allowlist_fixture_id("tests/m.py::test_x[113-hr-3547/4_engrossed-amendment-senate.pdf]") == (
        "113-hr-3547/4_engrossed-amendment-senate.pdf"
    )
    assert allowlist_fixture_id("tests/m.py::TestX::test_y") is None
    assert allowlist_fixture_id("tests/m.py::test_x[serial]") is None


def test_allowlist_fixture_id_extracts_extensionless_stage_refs() -> None:
    """The #331 extractor extension: the corpus-expanding gates' EXTENSIONLESS
    ``<bill>/<stage>`` parametrize id is returned as a stage reference; a bill-only
    id, a ``->`` pair id, and a non-fixture param still yield None."""
    assert (
        allowlist_fixture_id("tests/m.py::test_x[113-hr-3547/4_engrossed-amendment-senate]")
        == "113-hr-3547/4_engrossed-amendment-senate"
    )
    assert allowlist_fixture_id("tests/m.py::test_x[115-hr-5895]") is None
    assert allowlist_fixture_id("tests/m.py::test_x[113-hr-3547/1_introduced-in-house->2_engrossed-in-house]") is None


def test_guard_flags_a_stale_extensionless_stage_entry() -> None:
    """#331's missing case, proven to fire: inject an entry keyed on the extensionless
    ``<bill>/<stage>`` form whose stage is NOT manifested in every format the case
    reads. 114-hr-2029 v4 is manifested pdf-only, and the amount-recall gate reads
    the xml AND the pdf of a stage, so CI can never collect that case — the entry is
    stale and must be named. (A naive second ``stale_allowlist_entries`` call without
    per-format resolution validated 0 of the allowlist's 4 entries and read
    permanently green — the vacuous decoration this guard exists to prevent.)

    The example used to be 113-hr-3547 v1, which gained its xml when the corpus moved to
    per-version format parity. Then 114-hr-2029 v4, whose xml was withheld while #434 (the
    multi-<legis-body> text drop) was open. #434 landed and that xml is now committed, so
    the corpus holds no single-format stage at all — per-version parity means it may never
    hold one again. Taking the prior note's own instruction, the manifest id set is now
    SYNTHETIC rather than a real stage hunted for: the pdf of a stage is declared and its
    xml is not, which is the condition under test.

    Only the id set is synthetic. ``stale_allowlist_entries`` and its per-format
    resolution are the real ones, so what this proves is unchanged — and it no longer
    depends on the corpus permanently keeping a fixture in one format, which is what made
    the previous two examples expire."""
    stage = "114-hr-2029/4_reported-in-senate"
    nodeid = f"tests/test_pdf_xml_amount_recall.py::test_xml_amounts_appear_in_pdf[{stage}]"
    allowlist = dict(conftest.ALLOWED_CI_SLOW_SKIPS)
    allowlist[nodeid] = "injected stale entry"
    # The real manifest with this stage's xml withdrawn, so every OTHER allowlist entry
    # still resolves and only the injected one is stale. Built by subtraction rather than
    # from scratch: a hand-built id set would make every other entry look stale too, and
    # the assertion would then pass on a set that proves nothing about per-format
    # resolution.
    pdf_only_manifest = manifest_fixture_ids() - {f"{stage}.xml"}
    assert f"{stage}.pdf" in pdf_only_manifest, "the pdf must remain declared for this to be a per-FORMAT case"
    stale = stale_allowlist_entries(allowlist, pdf_only_manifest)
    assert stale == {nodeid: stage}


def test_guard_passes_a_live_extensionless_stage_entry() -> None:
    """The complement: the real CI-slow entry keys on 113-hr-3547 v4, manifested in
    BOTH formats, so the case is collectible and the entry must NOT be flagged —
    per-format resolution does not turn a live stage reference into a false
    positive."""
    nodeid = (
        "tests/test_pdf_xml_amount_recall.py::test_xml_amounts_appear_in_pdf[113-hr-3547/4_engrossed-amendment-senate]"
    )
    assert nodeid in conftest.ALLOWED_CI_SLOW_SKIPS, "precondition: the live entry exists"
    manifest = manifest_fixture_ids()
    assert {
        "113-hr-3547/4_engrossed-amendment-senate.xml",
        "113-hr-3547/4_engrossed-amendment-senate.pdf",
    } <= manifest, "precondition: v4 is manifested in both formats"
    assert stale_allowlist_entries({nodeid: "reason"}, manifest) == {}
