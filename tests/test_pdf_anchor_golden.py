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
