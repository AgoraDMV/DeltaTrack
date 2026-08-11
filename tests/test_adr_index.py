"""The decision-record indexes are generated from docs/decisions/, and cannot drift (#481).

Nothing loads ``docs/decisions/``, so before #481 a decision was reachable only if a code
comment happened to name it and the reader happened to follow the pointer. That matters
more since #478 told contributors to escalate a long rationale out of a comment and into
an ADR: escalation assumes the destination is reachable, and if it is not, the convention
converts a rationale that was verbose but present into one that is absent.

AGENTS.md is loaded every session, so the index lives there. It works because the titles
are already claims rather than topic labels ("11. Process user-provided bill content only
on the user's machine") -- a reader who sees only the title has received the decision,
which is most of what a discoverability mechanism has to deliver.

An index maintained by hand is the shape that goes stale by default. That is not a
hypothesis here: the ``Records`` table in ``docs/decisions/README.md`` had already drifted
from the file it names, describing 0004 as "Fetch discovery and text..." where the record
itself says "Fetch BILL discovery and text...". One word, invisible to review, and the
same drift in a title that states a decision would misreport what was decided. The
enumerated CI module list in CONTRIBUTING went stale three times for the same reason, and
#483 relabelled that history.

So both indexes are derived here rather than trusted. The two select different sets --
AGENTS.md carries the ``Accepted`` records, since it presents itself as the architecture
in force, and the README table carries every record with its status -- so ``Status`` is
checked too. A missing, repeated or unrecognised status would drop a record out of the
accepted set, and a silently shorter index reads exactly like a correct one, so an
unknown value fails the run rather than being skipped.

That rule is close to vacuous against the corpus as it stands: every live record is
``Accepted``, so the filter currently drops nothing and the check would pass
unimplemented. It is therefore also exercised against ADR text written into a temporary
directory and read back through this same parser, so the failures are observed rather
than assumed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DECISIONS_DIR = REPO_ROOT / "docs" / "decisions"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
DECISIONS_README = DECISIONS_DIR / "README.md"

# `# 12. Recover PDF heading levels...` -> ("12", "Recover PDF heading levels...").
# Anchored at the start of the line with no leading whitespace on purpose: that is the
# 0009 defect, and a tolerant pattern would silently accept it again.
_HEADING_RE = re.compile(r"^# (\d+)\. (.+)$")

# `- Status: Accepted` -> ("Status", "Accepted").
_FIELD_RE = re.compile(r"^- ([A-Za-z][A-Za-z ]*?):\s*(.*)$")

_AGENTS_SECTION = "## Architecture decisions"

STATUSES = ("Proposed", "Accepted", "Superseded", "Deprecated", "Rejected")
OPERATIVE = "Accepted"


@dataclass
class Record:
    """One decision record, as its own header declares it."""

    number: int
    title: str
    filename: str
    status: str


def parse_record(path: Path, problems: list[str]) -> Record | None:
    """One record's heading and status, appending any violation to `problems`."""
    text = path.read_text()
    heading = next((line for line in text.splitlines() if line.lstrip().startswith("#")), "")
    match = _HEADING_RE.match(heading)
    if not match:
        problems.append(f"{path.name}: first heading is not `# N. Title` with no leading whitespace: {heading!r}")
        return None
    number, title = int(match.group(1)), match.group(2)
    if number != int(path.name[:4]):
        problems.append(f"{path.name}: heading declares itself {number}")

    # Read `- Status:` from the header block only, meaning the lines above the first `## `
    # section, so a status quoted in prose cannot pose as one.
    statuses: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            break
        field = _FIELD_RE.match(line)
        if field and field.group(1).strip() == "Status":
            statuses.append(field.group(2).strip())

    if not statuses:
        problems.append(f"{number:04d}: no `- Status:` header line")
    elif len(statuses) > 1:
        problems.append(f"{number:04d}: {len(statuses)} `- Status:` lines: {statuses}")
    elif statuses[0] not in STATUSES:
        problems.append(f"{number:04d}: status {statuses[0]!r} is not one of {STATUSES}")

    status = statuses[0] if len(statuses) == 1 else ""
    return Record(number=number, title=title, filename=path.name, status=status)


def load_records(directory: Path) -> tuple[list[Record], list[str]]:
    """Every record in `directory`, in number order, with everything wrong with them."""
    problems: list[str] = []
    records = [record for path in sorted(directory.glob("0*.md")) if (record := parse_record(path, problems))]

    declared_by: dict[int, str] = {}
    for record in records:
        if record.number in declared_by:
            problems.append(
                f"{record.number:04d} is declared by two records, {declared_by[record.number]} and "
                f"{record.filename}; a number names one record, and both indexes are keyed by it"
            )
        else:
            declared_by[record.number] = record.filename
    return records, problems


def render_agents_index(records: list[Record]) -> str:
    """The AGENTS.md index block: the accepted decisions, and only those."""
    return "\n".join(
        f"- [{record.number}. {record.title}](docs/decisions/{record.filename})"
        for record in records
        if record.status == OPERATIVE
    )


def render_readme_table(records: list[Record]) -> str:
    """The `Records` table rows: every record, current or not, with its status."""
    return "\n".join(
        f"| [{record.filename[:4]}]({record.filename}) | {record.status} | {record.title} |" for record in records
    )


def _agents_index_block() -> str:
    """The bullet list under the Architecture decisions heading, verbatim."""
    body = AGENTS_MD.read_text().split(_AGENTS_SECTION, 1)
    assert len(body) == 2, f"AGENTS.md has no `{_AGENTS_SECTION}` section"
    lines = [line for line in body[1].splitlines() if line.startswith("- [")]
    return "\n".join(lines)


def _readme_table_block() -> str:
    """The `| [NNNN](file.md) | Status | Title |` rows of the Records table, verbatim."""
    rows = [line for line in DECISIONS_README.read_text().splitlines() if re.match(r"^\| \[\d{4}\]\(", line)]
    return "\n".join(rows)


def test_record_headings_and_statuses_are_well_formed() -> None:
    """Every record's heading, number and status parse to a known shape."""
    _records, problems = load_records(DECISIONS_DIR)
    assert not problems, "Decision records carry malformed headers:\n  " + "\n  ".join(problems)


def test_agents_md_lists_the_accepted_records() -> None:
    """AGENTS.md carries the Accepted records, with the titles the records themselves carry."""
    records, _problems = load_records(DECISIONS_DIR)
    expected = render_agents_index(records)
    assert _agents_index_block() == expected, (
        "The ADR index in AGENTS.md has drifted from docs/decisions/. It is generated, "
        "not hand-maintained, and holds the accepted decisions only: replace the bullet "
        f"list under '{_AGENTS_SECTION}' with exactly this:\n\n{expected}\n"
    )


def test_decisions_readme_table_lists_every_record() -> None:
    """The Records table says what the records say, superseded and rejected ones included."""
    records, _problems = load_records(DECISIONS_DIR)
    expected = render_readme_table(records)
    assert _readme_table_block() == expected, (
        "The Records table in docs/decisions/README.md has drifted from the records it "
        f"names. Replace its rows with exactly this:\n\n{expected}\n"
    )


# --------------------------------------------------------------------------------------
# The rules above, exercised on ADR text rather than on assumptions about it.
#
# Every live record is Accepted, so against the real corpus the status filter drops
# nothing and would pass unimplemented. These write records into a temporary directory and
# read them back through `load_records`, the same parser the real ones go through.
# --------------------------------------------------------------------------------------


def write_record(
    directory: Path, number: int, *, status: str = "Accepted", header: str = "", body: str = "", slug: str = "record"
) -> Path:
    """A minimal well-formed record. `slug` varies only the filename, so two files can
    declare one number."""
    path = directory / f"{number:04d}-{slug}.md"
    lines = [f"# {number}. Decide the thing", "", f"- Status: {status}", "- Date: 2026-01-01"]
    if header:
        lines.extend(header.splitlines())
    lines.extend(["", "## Context", "", body or "Why."])
    path.write_text("\n".join(lines) + "\n")
    return path


def problems_for(directory: Path) -> list[str]:
    """Everything the parser finds wrong with a directory of records."""
    return load_records(directory)[1]


def test_a_well_formed_record_raises_nothing(tmp_path: Path) -> None:
    """The fixture itself is clean, so a failure below is the injected fault and not it."""
    write_record(tmp_path, 1)
    assert problems_for(tmp_path) == []


def test_a_malformed_heading_fails(tmp_path: Path) -> None:
    """A heading the number and title cannot be read out of, here the 0009 defect.

    Indented, so Markdown renders it as a code block rather than a heading, and the
    record would otherwise reach both indexes with nothing to label it by. Syntax only:
    this says nothing about whether the title states a decision or names a topic, which
    the parser has no way to tell apart.
    """
    (tmp_path / "0001-record.md").write_text("  # 1. Decide the thing\n\n- Status: Accepted\n\n## Context\n\nWhy.\n")
    assert any("is not `# N. Title`" in problem for problem in problems_for(tmp_path))


def test_a_heading_number_disagreeing_with_the_filename_fails(tmp_path: Path) -> None:
    """Both indexes link by filename and label by heading, so the two must name one record."""
    (tmp_path / "0001-record.md").write_text("# 2. Decide the thing\n\n- Status: Accepted\n\n## Context\n\nWhy.\n")
    assert any("heading declares itself 2" in problem for problem in problems_for(tmp_path))


def test_a_missing_status_fails(tmp_path: Path) -> None:
    """No status at all is caught, rather than read as absent-and-therefore-not-accepted."""
    (tmp_path / "0001-record.md").write_text("# 1. Decide the thing\n\n- Date: 2026-01-01\n\n## Context\n\nWhy.\n")
    assert any("no `- Status:`" in problem for problem in problems_for(tmp_path))


def test_an_unknown_status_fails(tmp_path: Path) -> None:
    """A status outside the closed set fails loudly instead of dropping out of the index."""
    write_record(tmp_path, 1, status="Accepted (but not yet implemented)")
    assert any("is not one of" in problem for problem in problems_for(tmp_path))


def test_a_repeated_status_fails(tmp_path: Path) -> None:
    """Two status lines mean two answers, and the file cannot be read as either."""
    write_record(tmp_path, 1, header="- Status: Superseded")
    assert any("`- Status:` lines" in problem for problem in problems_for(tmp_path))


def test_a_status_line_in_the_body_is_not_a_header(tmp_path: Path) -> None:
    """The header block ends at the first section, so a status in prose cannot pose as one.

    The body line here is a `- Status:` line in its own right, not one quoted inside a
    sentence: an example written out in a record that documents the statuses would parse
    as a second header field, and the record would be rejected for declaring two.
    """
    write_record(tmp_path, 1, body="- Status: Rejected\n\nis what a record reads once we decide against it.")
    assert problems_for(tmp_path) == []


def test_two_records_declaring_one_number_fails(tmp_path: Path) -> None:
    """Otherwise one of them is simply absent from an index that reads complete."""
    write_record(tmp_path, 1, slug="first")
    write_record(tmp_path, 1, slug="second")
    problems = problems_for(tmp_path)
    assert any("declared by two records" in problem for problem in problems)
    assert any("0001-first.md" in problem and "0001-second.md" in problem for problem in problems)


def test_the_indexes_select_different_record_sets(tmp_path: Path) -> None:
    """AGENTS.md carries what is current; the README table carries the history too."""
    write_record(tmp_path, 1, status="Superseded")
    write_record(tmp_path, 2, status="Proposed")
    write_record(tmp_path, 3)
    records, _problems = load_records(tmp_path)

    agents = render_agents_index(records)
    assert "0003-record.md" in agents
    assert "0001-record.md" not in agents, "a superseded record is being presented as current"
    assert "0002-record.md" not in agents, "a proposed record is being presented as current"

    assert render_readme_table(records).splitlines() == [
        "| [0001](0001-record.md) | Superseded | Decide the thing |",
        "| [0002](0002-record.md) | Proposed | Decide the thing |",
        "| [0003](0003-record.md) | Accepted | Decide the thing |",
    ]
