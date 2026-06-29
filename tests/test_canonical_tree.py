"""Canonical `tree` field — the structure tree exposed in the contract (#108, step 4A).

Asserts on the CONSUMED output (the canonical JSON + its schema), not an internal
tree dump (feedback_measure_at_consumed_output): the tree validates against the
published schema, its spans slice the right text, money is conserved, and an
account named "Title 17 …" carries level=account (the #155-immune data).
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from bill_tree import normalize_bill
from diff_bill import bill_diff_to_dict, diff_bills, extract_amounts
from diff_pdf import PdfDiff
from formatters.canonical import SCHEMA_VERSION, pdf_diff_to_canonical, xml_diff_to_canonical
from formatters.text_serializer import build_xml_full_text
from parsers.pdf_anchors import Anchor

_V1 = Path("bills/118-hr-8752/1_reported-in-house.xml")
_V2 = Path("bills/118-hr-8752/2_engrossed-in-house.xml")
_OMNIBUS = Path("bills/113-hr-3547/6_enrolled-bill.xml")
_SCHEMA = Path("schema/canonical-diff.schema.json")
_PDF_V1 = Path("bills/118-hr-4366/1_reported-in-house.pdf")
_PDF_V2 = Path("bills/118-hr-4366/2_engrossed-in-house.pdf")

pytestmark = pytest.mark.skipif(not _V1.exists(), reason="bill corpus not present (fetch_bills.py)")


def _canonical(v1_path: Path, v2_path: Path) -> tuple[dict, dict]:
    v1, v2 = normalize_bill(v1_path), normalize_bill(v2_path)
    diff_dict = bill_diff_to_dict(diff_bills(v1, v2), financial=True)
    full_text, spans, _sections, tree = build_xml_full_text(v1, v2)
    canonical = xml_diff_to_canonical(diff_dict, full_text=full_text, full_text_spans=spans, tree=tree)
    return canonical, full_text


def _walk(nodes):
    for n in nodes:
        yield n
        yield from _walk(n["children"])


def test_canonical_carries_tree_at_schema_1_3():
    canonical, _ = _canonical(_V1, _V2)
    assert canonical["schema_version"] == SCHEMA_VERSION == "1.3"
    assert canonical["tree"] is not None
    assert len(canonical["tree"]["v1"]) > 0 and len(canonical["tree"]["v2"]) > 0


def test_canonical_validates_against_published_schema():
    jsonschema = pytest.importorskip("jsonschema")
    canonical, _ = _canonical(_V1, _V2)
    jsonschema.validate(canonical, json.loads(_SCHEMA.read_text()))


def test_tree_requires_full_text_copresence():
    v1, v2 = normalize_bill(_V1), normalize_bill(_V2)
    diff_dict = bill_diff_to_dict(diff_bills(v1, v2), financial=True)
    _ft, spans, _sections, tree = build_xml_full_text(v1, v2)
    # A tree with spans but no full_text would carry dangling offsets: rejected.
    with pytest.raises(ValueError, match="tree requires full_text"):
        xml_diff_to_canonical(diff_dict, full_text=None, full_text_spans=spans, tree=tree)


def test_node_spans_slice_their_own_text():
    canonical, full_text = _canonical(_V1, _V2)
    checked = 0
    for node in _walk(canonical["tree"]["v2"]):
        span = node["full_text_span"]
        if span is None or not node["own_amounts"]:
            continue
        sliced = full_text["v2"][span["start"] : span["end"]]
        assert all(f"${a:,}" in sliced for a in node["own_amounts"]), (
            f"{node['label']}: own_amounts not in its own span"
        )
        checked += 1
    assert checked > 0  # the assertion actually ran on real nodes


def test_tree_conserves_money_against_full_diff_amounts():
    # The union of per-node own_amounts equals the amounts the parser extracted
    # for the bill (the conservation invariant, measured at the contract).
    canonical, _ = _canonical(_V1, _V2)
    import xml.etree.ElementTree as ET

    from bill_tree import extract_text_content, find_bill_body

    tree_amounts: Counter = Counter()
    for node in _walk(canonical["tree"]["v2"]):
        tree_amounts.update(node["own_amounts"])
    raw = Counter(extract_amounts(extract_text_content(find_bill_body(ET.parse(_V2).getroot()))))
    assert sum((tree_amounts - raw).values()) == 0  # no over-count
    assert sum((raw - tree_amounts).values()) == 0  # exact on this clean bill


@pytest.mark.slow
@pytest.mark.skipif(not _OMNIBUS.exists(), reason="omnibus fixture absent")
def test_node_named_title_is_not_elevated_to_title_level():
    # #155: a node named "Title 17 …" must NOT be elevated to a title-level node
    # in the contract. Its level comes from the source tag, not the label text —
    # here the DOE "Title 17" loan-guarantee heading is an appropriations-
    # intermediate, so it types as `agency`, never `title`.
    canonical, _ = _canonical(_OMNIBUS, _OMNIBUS)
    title17 = [n for n in _walk(canonical["tree"]["v2"]) if n["label"].startswith("Title 17")]
    assert title17, "expected the DOE 'Title 17' heading in this bill"
    assert all(n["level"] != "title" for n in title17)
    assert all(n["level"] == "agency" for n in title17)  # tag-derived, not text-derived


# ---- PDF pipeline tree (#108, commit A.2) ----------------------------------
# The XML serializer hands the tree its per-node spans for free; the PDF pipeline
# has no body-span index, so `pdf_diff_to_canonical` derives own_amounts and spans
# from the anchor stream — each anchor owns the block up to the next anchor. These
# assert that partition conserves money (no overcount) and the spans are honest.


def test_pdf_tree_partitions_blocks_between_anchors():
    # A synthetic stream: two accounts under one agency under a title. Each
    # account's $ lands in ITS block (anchor → next anchor), never a sibling's.
    title = Anchor(page_number=1, line_number=1, kind="title", text="TITLE I")
    agency = Anchor(page_number=1, line_number=2, kind="agency", text="AGENCY NAME")
    acct1 = Anchor(page_number=1, line_number=3, kind="account", text="ACCOUNT ONE")
    acct2 = Anchor(page_number=1, line_number=5, kind="account", text="ACCOUNT TWO")
    anchors = (title, agency, acct1, acct2)
    lines = [
        "TITLE I",
        "AGENCY NAME",
        "ACCOUNT ONE",
        "For expenses, $1,000,000.",
        "ACCOUNT TWO",
        "For other purposes, $2,500,000.",
    ]
    text = "\n".join(lines)
    pos, line_start = 0, {}
    for i, ln in enumerate(lines, start=1):
        line_start[i] = pos
        pos += len(ln) + 1  # + newline
    offsets = {(1, n): (line_start[n], line_start[n] + len(lines[n - 1])) for n in (1, 2, 3, 5)}
    diff = PdfDiff(hunks=(), v1_anchors=anchors, v2_anchors=anchors)
    canonical = pdf_diff_to_canonical(
        diff,
        bill_type="hr",
        bill_number=1,
        congress=118,
        full_text={"v1": text, "v2": text},
        line_offsets={"v1": offsets, "v2": offsets},
    )
    by_label = {n["label"]: n for n in _walk(canonical["tree"]["v2"])}
    assert by_label["ACCOUNT ONE"]["own_amounts"] == [1_000_000]
    assert by_label["ACCOUNT TWO"]["own_amounts"] == [2_500_000]
    assert by_label["TITLE I"]["own_amounts"] == []  # interior heading, no body $
    # union conserves with no overcount
    union = Counter()
    for n in _walk(canonical["tree"]["v2"]):
        union.update(n["own_amounts"])
    assert union == Counter([1_000_000, 2_500_000])
    # each span actually contains its own_amounts
    for n in _walk(canonical["tree"]["v2"]):
        if not n["own_amounts"]:
            continue
        span = n["full_text_span"]
        sliced = text[span["start"] : span["end"]]
        assert all(f"${a:,}" in sliced for a in n["own_amounts"])


def test_pdf_tree_drops_to_none_without_full_text():
    # Co-presence: no full_text → no spans to index into → tree is null, not [].
    title = Anchor(page_number=1, line_number=1, kind="title", text="TITLE I")
    diff = PdfDiff(hunks=(), v1_anchors=(title,), v2_anchors=(title,))
    canonical = pdf_diff_to_canonical(diff, bill_type="hr", bill_number=1, congress=118)
    assert canonical["tree"] is None


@pytest.mark.slow
@pytest.mark.skipif(not _PDF_V1.exists() or not _PDF_V2.exists(), reason="sample PDFs absent")
def test_pdf_tree_conserves_money_no_overcount_on_real_bill():
    from server.pdf_compare import compare_pdfs

    canonical = compare_pdfs(_PDF_V1.read_bytes(), _PDF_V2.read_bytes())
    assert canonical["tree"] is not None and canonical["tree"]["v2"]

    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(canonical, json.loads(_SCHEMA.read_text()))

    # No overcount: the per-node own_amounts are a sub-multiset of the amounts the
    # parser extracts from the same full_text (front matter before the first anchor
    # is the only allowed drop — bounded, documented).
    for side in ("v1", "v2"):
        tree_amounts: Counter = Counter()
        for n in _walk(canonical["tree"][side]):
            tree_amounts.update(n["own_amounts"])
        body_amounts = Counter(extract_amounts(canonical["full_text"][side]))
        assert sum((tree_amounts - body_amounts).values()) == 0, f"{side}: overcount"

    checked = 0
    for n in _walk(canonical["tree"]["v2"]):
        span = n["full_text_span"]
        if span is None or not n["own_amounts"]:
            continue
        sliced = canonical["full_text"]["v2"][span["start"] : span["end"]]
        assert all(f"${a:,}" in sliced for a in n["own_amounts"]), n["label"]
        checked += 1
    assert checked > 0
