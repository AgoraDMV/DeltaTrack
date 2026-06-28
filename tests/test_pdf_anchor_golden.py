"""Golden anchor-snapshot guard + precision-harness self-test (DeltaTrack#89).

The golden snapshots pin the full ordered anchor list per fixture bill. They are
the deterministic regression guard the tolerant diff-recall suite can't provide:
they catch BOTH over-emission (spurious accounts) and under-emission (dropped
accounts) when the size-detection swap lands. Regenerate ONLY when a change is
intended, and prove the delta with the set-diff assertion in the swap commit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parsers.pdf_anchors import extract_anchors
from parsers.pdf_text import extract_clean_pages

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / "test_data" / "pdf" / "anchors_golden"

# (golden name, pdf path) — approps (House), non-approps (House), approps (Senate).
FIXTURES = {
    "118-hr-8752": ROOT / "bills" / "118-hr-8752" / "1_reported-in-house.pdf",
    "118-hr-8282": ROOT / "bills" / "118-hr-8282" / "1_introduced-in-house.pdf",
    "118-s-4795": ROOT / "test_data" / "BILLS-118s4795rs.pdf",
}


def _current_anchors(pdf_path: Path) -> list[list]:
    anchors = extract_anchors(extract_clean_pages(pdf_path))
    return [[a.kind, a.text, a.page_number, a.line_number] for a in anchors]


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_anchors_match_golden(name: str):
    pdf_path = FIXTURES[name]
    if not pdf_path.exists():
        pytest.skip(f"{name} PDF not present")
    golden = json.loads((GOLDEN_DIR / f"{name}.json").read_text())
    # JSON has no tuples; compare as lists.
    assert _current_anchors(pdf_path) == golden


def _account_names(pdf_path: Path) -> set[str]:
    anchors = extract_anchors(extract_clean_pages(pdf_path))
    return {a.text for a in anchors if a.kind == "account"}


def _legacy_account_names(name: str) -> set[str]:
    # Frozen pre-swap baseline (never regenerated), so the set-delta stays
    # meaningful after the full golden is regenerated post-swap.
    return set(json.loads((GOLDEN_DIR / f"{name}.legacy-accounts.json").read_text()))


class TestSizeDetectionEndToEnd:
    """The canonical #85/#89 proof: the size path catches FEDERAL PROTECTIVE
    SERVICE, which the legacy 'For necessary expenses' walk misses, with no
    regression to the accounts the legacy path already caught."""

    def test_fps_account_now_detected(self):
        pdf = FIXTURES["118-hr-8752"]
        if not pdf.exists():
            pytest.skip("HR 8752 PDF not present")
        assert "FEDERAL PROTECTIVE SERVICE" in _account_names(pdf)

    def test_no_account_regressions_vs_legacy_baseline(self):
        pdf = FIXTURES["118-hr-8752"]
        if not pdf.exists():
            pytest.skip("HR 8752 PDF not present")
        new = _account_names(pdf)
        legacy = _legacy_account_names("118-hr-8752")
        # The only accounts dropped vs the legacy baseline are parenthetical
        # qualifiers (e.g. "(INCLUDING TRANSFER OF FUNDS)") — legacy false positives
        # the size path correctly excludes. No real account is removed.
        removed = legacy - new
        assert all(t.strip().startswith("(") and t.strip().endswith(")") for t in removed), (
            f"non-qualifier accounts removed vs legacy: {removed}"
        )
        # The intended addition includes FPS.
        assert "FEDERAL PROTECTIVE SERVICE" in (new - legacy)


class TestNonAppropsGeneralization:
    """The whole point of the change: size detection works on general legislation
    that has no 'For necessary expenses' language. Pinned so a future change can't
    silently break the generalization claim."""

    def test_sections_detected(self):
        # new-true-positive (red-first claim): the universal SEC level is found.
        pdf = FIXTURES["118-hr-8282"]
        if not pdf.exists():
            pytest.skip("HR 8282 PDF not present")
        anchors = extract_anchors(extract_clean_pages(pdf))
        assert any(a.kind == "section" for a in anchors)

    def test_zero_false_accounts(self):
        # precision-characterization: a non-appropriations bill has no accounts, so
        # size detection (incl. the run-in-enumerator reject) must emit none.
        pdf = FIXTURES["118-hr-8282"]
        if not pdf.exists():
            pytest.skip("HR 8282 PDF not present")
        anchors = extract_anchors(extract_clean_pages(pdf))
        assert [a.text for a in anchors if a.kind == "account"] == []


class TestSectionCatchlineContinuation:
    """Real-bill repro for the #89 catchline merge: a wrapped SEC. catchline line
    rendered in the heading band must not surface as a false `account`."""

    # (pdf, the false-account text the wrapped catchline used to emit)
    REPROS = {
        ROOT / "bills" / "117-hr-2471" / "1_introduced-in-house.pdf": "AND ASSEMBLY IN HAITI.",
        ROOT / "bills" / "118-hr-2882" / "1_introduced-in-house.pdf": "TRUST FUND.",
    }

    @pytest.mark.parametrize("pdf", sorted(REPROS), ids=lambda p: p.parent.name)
    def test_no_catchline_continuation_account(self, pdf: Path):
        if not pdf.exists():
            pytest.skip(f"{pdf.parent.name} PDF not present")
        assert self.REPROS[pdf] not in _account_names(pdf)


def _xml_agency_vocab(xml_path: Path) -> set[str]:
    """The XML's agency-level vocabulary (normalized), derived from the structure.

    The XML rarely carries agencies as standalone ``appropriations-intermediate``
    nodes; mostly they live as an intermediate segment of an account's
    ``display_path``. The level above the leaf is NOT positional (the department
    may be its own segment, e.g. ``TITLE II > DEPARTMENT OF JUSTICE > Office of
    inspector general > ...``, or folded into the title, e.g. ``TITLE I—DEPARTMENT
    OF COMMERCE > Bureau of the census > ...``), so position can't separate the
    major from the agency. Casing can: GPO renders the major ALL-CAPS and the
    agency in Title-case. So the agency vocab = every Title-cased path segment
    between the title prefix and the leaf, plus any standalone intermediate node.
    Derived, never hardcoded, so it can't drift against a regenerated golden.
    """
    from bill_tree import normalize_bill, normalize_header

    tree = normalize_bill(xml_path)
    vocab: set[str] = set()
    for n in tree.nodes:
        if n.tag == "appropriations-small":
            for seg in n.display_path[1:-1]:  # exclude the title prefix and the leaf
                if any("a" <= ch <= "z" for ch in seg):  # Title-case => agency, not an ALL-CAPS major
                    vocab.add(normalize_header(seg))
        elif n.tag == "appropriations-intermediate" and n.header_text:
            vocab.add(normalize_header(n.header_text))
    return vocab


def _pdf_agency_vocab(pdf_path: Path) -> set[str]:
    from bill_tree import normalize_header

    anchors = extract_anchors(extract_clean_pages(pdf_path))
    return {normalize_header(a.text) for a in anchors if a.kind == "agency"}


class TestCarryoverAgenciesEndToEnd:
    """Slice B of #54 (DeltaTrack#104): the size path recovers the XML agency level.

    The PDF size path emits the carry-over agency (kind ``agency``), rejoining
    names that wrap across heading lines (e.g. ``OFFICE OF THE SECRETARY AND
    EXECUTIVE`` + ``MANAGEMENT``). H.R. 8752 is the CLEAN case — single-line account
    names, unambiguous agency wraps — so it gets exact-set parity. The harder
    behavior (wrapped account names, header-only and prose-leading agencies) is
    gated tolerantly on the Senate CJS bill in TestCarryoverAgencyVocabFloors.
    """

    def test_pdf_agencies_match_xml_path_segments(self):
        # Exact-set parity on the clean bill: every XML agency recovered, none
        # spurious. The central acceptance gate for #104; must pass BEFORE the anchor
        # golden is regenerated so the regeneration can't bake in garbage.
        pdf = FIXTURES["118-hr-8752"]
        xml = ROOT / "bills" / "118-hr-8752" / "1_reported-in-house.xml"
        if not pdf.exists():
            pytest.skip("HR 8752 PDF not present")
        assert _pdf_agency_vocab(pdf) == _xml_agency_vocab(xml)

    def test_zero_false_agencies_on_non_approps(self):
        # Generalization guard (fresh-eyes C5): a non-appropriations bill has no
        # agency level, so the carry-over rule must emit zero agency anchors.
        pdf = FIXTURES["118-hr-8282"]
        if not pdf.exists():
            pytest.skip("HR 8282 PDF not present")
        anchors = extract_anchors(extract_clean_pages(pdf))
        assert [a.text for a in anchors if a.kind == "agency"] == []


class TestCarryoverAgencyVocabFloors:
    """Tolerant agency-vocab floor on the HARD bill (Senate CJS, 118-s-4795).

    Unlike H.R. 8752, s-4795 has variable path depth, account names that wrap
    across heading lines, header-only intermediate agencies, and a prose-leading
    agency. JOIN recovers the recoverable agencies but CANNOT segment a wrapped
    account name from an agency — that is the #54/#108 leveled tree, out of slice
    B's scope. So this is a floor with KNOWN, documented residue, not exact parity:

      - False positives that remain are wrapped account-name fragments and a
        provision header (e.g. 'salaries and expenses, foreign claims', 'major
        research equipment and facilities', 'administrative provision—legal
        services') — indistinguishable from agencies without the tree (#108).
      - Misses are the 3 header-only intermediate agencies (no leaf account beneath
        them) and the 1 prose-leading agency (slice D).

    The dangling-conjunction guard removes the worst mis-joins (runs joining into a
    phrase ending in 'and'/'of'/…), lifting precision from ~0.80 to ~0.87 — so the
    precision floor below is set to REQUIRE that guard. Floors sit under the
    measured values with margin for per-line median wobble; they are regression
    floors, not targets.
    """

    AGENCY_RECALL_FLOOR = 0.85
    AGENCY_PRECISION_FLOOR = 0.82

    def test_s4795_agency_vocab_floors(self):
        pdf = ROOT / "test_data" / "BILLS-118s4795rs.pdf"
        xml = ROOT / "bills" / "118-s-4795" / "1_reported-in-senate.xml"
        if not pdf.exists() or not xml.exists():
            pytest.skip("118-s-4795 pdf/xml pair not present")
        xa = _xml_agency_vocab(xml)
        pa = _pdf_agency_vocab(pdf)
        hit = pa & xa
        recall = len(hit) / len(xa) if xa else 0.0
        precision = len(hit) / len(pa) if pa else 0.0
        assert recall >= self.AGENCY_RECALL_FLOOR, f"agency recall {recall:.3f}"
        assert precision >= self.AGENCY_PRECISION_FLOOR, f"agency precision {precision:.3f}"


class TestCorpusAccountPrecision:
    """Corpus-wide floor on size-detected account vocabulary precision/recall (#89).

    Complements the exact golden snapshots (which pin three bills) with a tolerant
    net over the appropriations corpus, so a future change can't silently flood
    false accounts or drop real ones without tripping a gate. The floors sit below
    today's measured values (see scripts/heading_precision.py for the live numbers).

    Why precision is well under 1.0 even when correct — the residual misses are
    KNOWN and accepted, deferred to #54, NOT bugs to chase here:
      - Provision-group headers (ADMINISTRATIVE PROVISIONS, GENERAL PROVISIONS,
        SPENDING REDUCTION ACCOUNT) — real block headers mislabeled `account`.
      - Wrapped agency-name fragments (e.g. "FAMILY HOUSING CONSTRUCTION, AIR
        FORCE" wrapping onto a line read as "FORCE") — correct labeling needs the
        leveled tree.
      - Real account names whose GPO casing/wording normalizes differently than the
        XML header (counted as a vocab miss though the anchor is right).
    The SEC.-catchline-continuation class is NOT among the accepted residue — it is
    fixed (see TestSectionCatchlineContinuation); a regression there would lower
    these numbers, but the targeted test catches it first.
    """

    # Appropriations bills with a paired XML; (bill id, pdf rel path, xml rel path).
    BILLS = [
        ("114-hr-2029", "bills/114-hr-2029", None),
        ("115-hr-5895", "bills/115-hr-5895", None),
        ("117-hr-4432", "bills/117-hr-4432", None),
        ("117-hr-4502", "bills/117-hr-4502", None),
        ("118-hr-4366", "bills/118-hr-4366", None),
        ("118-hr-4820", "bills/118-hr-4820", None),
        ("118-hr-8752", "bills/118-hr-8752", None),
        ("118-hr-8774", "bills/118-hr-8774", None),
        ("118-s-4795", "test_data/BILLS-118s4795rs.pdf", "bills/118-s-4795/1_reported-in-senate.xml"),
    ]
    # Set below the lowest measured value (118-hr-4820: vrec 0.64 / vprec 0.46) with
    # margin for per-line median wobble; these are regression floors, not targets.
    RECALL_FLOOR = 0.60
    PRECISION_FLOOR = 0.45

    @staticmethod
    def _pair(spec) -> tuple[Path, Path] | None:
        _id, p, x = spec
        if x is not None:
            pdf, xml = ROOT / p, ROOT / x
            return (pdf, xml) if pdf.exists() and xml.exists() else None
        d = ROOT / p
        for pdf in sorted(d.glob("*.pdf")):
            xml = pdf.with_suffix(".xml")
            if xml.exists():
                return pdf, xml
        return None

    @pytest.mark.parametrize("spec", BILLS, ids=[b[0] for b in BILLS])
    def test_account_vocab_floors(self, spec):
        pair = self._pair(spec)
        if pair is None:
            pytest.skip(f"{spec[0]} pdf/xml pair not present")
        from scripts.heading_precision import measure

        m = measure(*pair)
        assert m["vocab_recall"] >= self.RECALL_FLOOR, f"{spec[0]} recall {m['vocab_recall']:.3f}"
        assert m["vocab_precision"] >= self.PRECISION_FLOOR, f"{spec[0]} precision {m['vocab_precision']:.3f}"


class TestPrecisionHarnessOracle:
    """Validate the harness computation (it is the oracle the swap is judged by)."""

    def test_measure_arithmetic_and_stable_xml_counts(self):
        pdf = FIXTURES["118-hr-8752"]
        xml = ROOT / "bills" / "118-hr-8752" / "1_reported-in-house.xml"
        if not pdf.exists():
            pytest.skip("HR 8752 PDF not present")
        from scripts.heading_precision import measure

        m = measure(pdf, xml)
        # XML-side counts are stable (independent of PDF detection method).
        assert m["xml_small"] == 35
        # count_ratio is accounts / (small + intermediate); verify the arithmetic.
        denom = m["xml_small"] + m["xml_intermediate"]
        assert m["count_ratio"] == pytest.approx(m["pdf_accounts"] / denom)
        # near-full margin-number attachment on this clean working-stage bill.
        assert m["coverage"] == pytest.approx(1.0, abs=0.01)
        # vocabulary precision/recall are bounded ratios.
        assert 0.0 <= m["vocab_precision"] <= 1.0
        assert 0.0 <= m["vocab_recall"] <= 1.0
