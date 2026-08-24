"""One bill pair, both surfaces, one document (#693).

Nothing ran a single input through the command line *and* the HTTP endpoint and
compared what came back. ``tests/test_pipeline_parity.py`` compares the XML and PDF
*pipelines*; ``tests/test_surface_boundary.py`` enforces import direction. Neither
looks across the two surfaces, which is why ``./diff_bill.py compare --format json``
could return the engine's internal diff dictionary while
``POST /api/compare?output=json`` returned the canonical contract, two documents
sharing two of eight top-level keys, with the whole suite green.

The gate is byte-identity rather than "both look canonical", because a shape check
passes on two documents that are wrong in the same way. The schema test covers the
direction byte-identity cannot: both surfaces drifting together, away from
``schema/canonical-diff.schema.json``.

Real bill XML, so ``@pytest.mark.slow`` (see AGENTS.md). The fixture pair is
committed and manifested, so these fail closed rather than skipping.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from deltatrack.diff_bill import build_parser, cmd_compare
from tests.corpus_paths import FIXTURES_DIR

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "canonical-diff.schema.json"

BILL_DIR = FIXTURES_DIR / "118-hr-8752"
V1 = BILL_DIR / "1_reported-in-house.xml"
V2 = BILL_DIR / "2_engrossed-in-house.xml"


def _cli_json(tmp_dir: Path, old: Path, new: Path) -> str:
    """``./diff_bill.py compare --format json``, driven through its real argument parser."""
    out = tmp_dir / "cli.json"
    cmd_compare(build_parser().parse_args(["compare", str(old), str(new), "--format", "json", "-o", str(out)]))
    return out.read_text()


def _endpoint_json(old: Path, new: Path) -> dict:
    """``POST /api/compare?format=xml&output=json``, driven through the real route."""
    from fastapi.testclient import TestClient

    from web.app import app

    with open(old, "rb") as start, open(new, "rb") as end:
        response = TestClient(app).post(
            "/api/compare?format=xml&output=json",
            files={
                "start_file": (old.name, start, "application/octet-stream"),
                "end_file": (new.name, end, "application/octet-stream"),
            },
        )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def unprefixed_pair(tmp_path_factory) -> tuple[Path, Path]:
    """The fixture pair copied under stems carrying no ``<n>_`` legislative ordinal.

    The two surfaces derive a version's identity from the filename by different
    algorithms: ``version_stems.label_from_stem`` strips a numeric prefix and
    ``version_number_from_stem`` reads the ordinal off it, while
    ``web/app.py::_label_from_filename`` strips only the path and the extension and
    has no ordinal to read at all. On ``1_reported-in-house.xml`` they therefore
    disagree, and that disagreement is #692 (one bill pair, three different version
    headings), a property of the two label algorithms rather than of the diff.

    Removing the prefix removes that variable, so the parity gate below measures the
    document rather than re-measuring #692. What the corpus filenames *do* change is
    asserted separately, so the exclusion stays one named key wide.
    """
    tmp = tmp_path_factory.mktemp("unprefixed")
    old, new = tmp / "reported-in-house.xml", tmp / "engrossed-in-house.xml"
    shutil.copyfile(V1, old)
    shutil.copyfile(V2, new)
    return old, new


@pytest.mark.slow
def test_the_command_and_the_endpoint_return_the_same_document(tmp_path, unprefixed_pair):
    """Same two files in, byte-identical canonical JSON out.

    This is the gate #693 is verified by, and reverting the routing in
    ``cmd_compare`` is the mutation that turns it red: the internal diff dictionary
    shares two top-level keys with the canonical document and none of its change
    fields.
    """
    old, new = unprefixed_pair
    cli_text = _cli_json(tmp_path, old, new)
    endpoint = _endpoint_json(old, new)

    assert json.loads(cli_text) == endpoint
    assert cli_text == json.dumps(endpoint, indent=2), "same document, different serialization"


@pytest.mark.slow
def test_only_the_version_identity_depends_on_the_filename(tmp_path):
    """On the committed corpus stems, ``versions`` is the only key that may differ.

    The mutation this catches and the test above cannot: making any *other* canonical
    field depend on the filename stem. That gate matters here specifically, because
    version identity is re-derived from a filename in six places (#692) and the pair
    above is chosen to make two of them agree.

    Deliberately not an inequality assertion on ``versions``: when #692 lands and the
    two algorithms converge, this test should stay green rather than pin the defect.
    """
    cli = json.loads(_cli_json(tmp_path, V1, V2))
    endpoint = _endpoint_json(V1, V2)

    assert set(cli) == set(endpoint)
    assert {k: v for k, v in cli.items() if k != "versions"} == {k: v for k, v in endpoint.items() if k != "versions"}


@pytest.mark.slow
def test_the_command_output_validates_against_the_published_schema(tmp_path, unprefixed_pair):
    """Byte-identity says the two agree; this says what they agree on is the contract."""
    jsonschema = pytest.importorskip("jsonschema")

    old, new = unprefixed_pair
    jsonschema.validate(json.loads(_cli_json(tmp_path, old, new)), json.loads(SCHEMA.read_text()))
