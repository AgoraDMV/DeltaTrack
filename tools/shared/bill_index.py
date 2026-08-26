"""
A cache for bill metadata intended to accumulate information about large volumes of bills.

The guiding idea behind the cache is that each bill has an identifying slug of the form:

{congress}-{type}-{number}

e.g. `119-hr-1` for the 1st House Resolution bill of the 119th Congress.

Version is deliberately not part of the slug. A version is a per-bill ordinal addressed
as a separate token next to the bill, so its number and meaning are only defined under
one bill (ADR 0013). `version_stems.py` resolves a slug + ordinal to a file.

Aside from a uniquely identifying slug, each bill can have arbitrary metadata.
The index automatically syncs with a CSV file. It can be used to prevent duplicate downloads
and to accumulate bill metadata from different sources.

Usage:
index = BillIndex(csv_path)
records: list[dict] = index.bills
bill_ids: list[str] = [record["id"] for record in records]
latest_hr_bills = index.fetch_all(119, "hr")
for congress, bill_type, bill_number in map(parse_bill_id, bill_ids):
    ...
"""

from __future__ import annotations

import csv
from collections import namedtuple
from pathlib import Path
from typing import Any, Iterable, Literal, Tuple

from shared.bill_types import BILL_TYPES

BillRecord = dict[str, Any]
InsertMode = Literal["merge", "skip"]


def make_bill_id(congress: int | str, bill_type: str, number: int | str) -> str:
    """Build a bill id slug from a congress number, bill type, and bill number."""
    return f"{congress}-{bill_type}-{number}"


BillIdentifier = namedtuple("BillIdentifier", ["congress", "bill_type", "number"])


def _is_ascii_digits(part: str) -> bool:
    return part.isascii() and part.isdigit()


def parse_bill_id(slug: str) -> BillIdentifier:
    """Parse `congress-type-number` into a typed identifier.

    Raises ValueError on anything else, including the retired `:version` suffix. No
    bill type contains a hyphen, so a well-formed slug always splits into exactly three
    parts. Callers that need to accept legacy or hand-written input do that at their own
    boundary, where they can say what compatibility they are providing -- see
    `fetch_bills download-all --file`.

    Congress and number are checked for digits rather than only counting the parts: a
    `:version` suffix rides along on the number (`118-sconres-12:2` splits into three
    parts under a valid type), so a part count alone would readmit the exact form
    ADR 0013 retired. The digit check is ASCII-only: `str.isdigit` alone also accepts
    Arabic-Indic digits and superscripts, which no govinfo URL will ever resolve.
    """
    shape = "{congress}-{type}-{number}"
    parts = slug.split("-")
    if len(parts) != 3:
        raise ValueError(f"Expected a bill slug of the form '{shape}', got: {slug}")

    congress, bill_type, number = parts
    if bill_type not in BILL_TYPES:
        raise ValueError(f"Unknown bill type '{bill_type}' in slug: {slug}")
    if not _is_ascii_digits(congress) or not _is_ascii_digits(number):
        raise ValueError(f"Expected a bill slug of the form '{shape}', got: {slug}")

    return BillIdentifier(congress=congress, bill_type=bill_type, number=number)


class BillIndex:
    """
    An in-memory + CSV-backed bill metadata index.

    BillIndex is used as a metadata cache for congress bills from various sources.
    It normalizes on bill slugs of the form congress-bill_type-number as unique identifiers. E.g. 119-hr-1.
    Aside from normalized bill slugs, BillIndex allows arbitrary bill metadata.
    """

    def __init__(self, csv_path: str | Path = "bills.csv"):
        self.csv_path = Path(csv_path)
        self._records: list[BillRecord] = []
        self._bills_by_id: dict[str, BillRecord] = {}
        self._columns: list[str] = []
        self.load()

    @property
    def bills(self) -> list[BillRecord]:
        return self._records

    @property
    def columns(self) -> list[str]:
        return self._columns

    def has(self, bill_id: str) -> bool:
        return bill_id in self._bills_by_id

    def get(self, bill_id: str) -> BillRecord | None:
        return self._bills_by_id.get(bill_id)

    def __getitem__(self, bill_id: str) -> BillRecord:
        """Enable subscript support: bill_index[bill_id]"""
        return self._bills_by_id[bill_id]

    def find_new_and_existing_bills(
        self, candidates: Iterable[BillRecord]
    ) -> Tuple[list[BillRecord], list[BillRecord]]:
        """Splits a list of bill records into records that are or are not in the index based on record slugs/ids."""
        new_records = [record for record in candidates if record["id"] not in self._bills_by_id]
        existing_records = [record for record in candidates if record["id"] in self._bills_by_id]
        return (new_records, existing_records)

    def find_new_and_existing_bill_ids(self, candidate_ids: Iterable[str]) -> Tuple[list[str], list[str]]:
        """Split candidate bill ids into ids that are new vs already indexed."""
        new_ids = [bill_id for bill_id in candidate_ids if bill_id not in self._bills_by_id]
        existing_ids = [bill_id for bill_id in candidate_ids if bill_id in self._bills_by_id]
        return (new_ids, existing_ids)

    def fetch_all(self, congress: int, type: str | int | None, number: int | None) -> list[BillRecord]:
        """Return bills matching the passed slug prefix parts."""
        parts = [str(congress)]
        if type is not None:
            parts.append(str(type))
            if number is not None:
                parts.append(str(number))
        prefix = "-".join(parts)
        return [bill for bill in self._records if str(bill.get("id", "")).startswith(prefix)]

    def add_bills(
        self,
        records: Iterable[BillRecord],
        *,
        mode: InsertMode = "merge",
        save: bool = True,
    ) -> dict:
        """Insert many records using append or merge behavior.

        - ``skip``: skip over records that are indexed already, keeping the old data.
        - ``merge``: if a record exists, combine the new data with the old data. otherwise, add a new record.
        """
        if mode not in {"skip", "merge"}:
            raise ValueError("mode must be 'append' or 'merge'")

        if not records:
            return self._records

        records = list(records)
        self._validate_records(records)

        if not self._records:
            self._columns = list(records[0].keys())
            self._records = [self._normalize_record(record) for record in records]
            self._bills_by_id = {record["id"]: record for record in self._records}
            if save:
                self.save()
            return self._records

        columns_before = list(self._columns)
        self._expand_columns([column for record in records for column in record])
        columns_changed = self._columns != columns_before

        new_records, existing_records = self.find_new_and_existing_bills(records)

        merged_existing = False
        if mode == "merge" and existing_records:
            for record in existing_records:
                self.get(record["id"]).update(record)
            merged_existing = True

        normalized: list[BillRecord] = []
        if new_records:
            normalized = [self._normalize_record(record) for record in new_records]
            self._records.extend(normalized)
            for record in normalized:
                self._bills_by_id[record["id"]] = record

        if records:
            self._reorder_columns(records[0].keys())

        if save:
            if merged_existing or columns_changed:
                self.save()
            elif normalized:
                self.append_to_csv(normalized)

        return self._records

    def load(self) -> None:
        """Load CSV into memory. Missing files result in an empty index."""
        self._records = []
        self._bills_by_id = {}
        self._columns = []

        if not self.csv_path.exists():
            return

        # utf-8-sig, not utf-8: the index may be hand-authored (README documents
        # --file), and Excel and Google Sheets both prefix a BOM. Read as utf-8 that
        # BOM binds to the first header name, so 'id' arrives as '﻿id' and the
        # check below rejects a file that plainly has an id column. utf-8-sig strips a
        # BOM when present and is a no-op otherwise. The write paths stay utf-8 so we
        # never emit one ourselves.
        try:
            with self.csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames:
                    self._columns = list(reader.fieldnames)
                    if "id" not in self._columns:
                        raise ValueError("CSV file is missing required column: 'id'")
                for row in reader:
                    bill = {key: _decode_value(key, row.get(key, "")) for key in self._columns}
                    self._records.append(bill)
                    self._bills_by_id[bill["id"]] = bill
        except UnicodeDecodeError as exc:
            # Same origin as the BOM case, different symptom: a spreadsheet export in
            # the system codepage rather than UTF-8. The bare error names a byte offset
            # and no file, so say which file and what to do about it.
            raise ValueError(
                f"CSV file is not valid UTF-8: {self.csv_path}. "
                "Re-save it as UTF-8 (in Excel: 'CSV UTF-8 (Comma delimited)')."
            ) from exc

    def save(self) -> None:
        """Persist in-memory records to CSV."""
        self._ensure_csv_with_header(truncate=True)
        self.append_to_csv(self._records)

    def append_to_csv(self, records: Iterable[BillRecord]) -> None:
        """Persist in-memory records to CSV."""
        self._ensure_csv_with_header()
        with self.csv_path.open("a", encoding="utf-8", newline="") as fh:
            for record in records:
                fh.write(_format_csv_row(self._columns, record) + "\n")

    def _ensure_csv_with_header(self, *, truncate: bool = False) -> None:
        """Create CSV if needed and ensure header exists."""
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = truncate or not self.csv_path.exists() or self.csv_path.stat().st_size == 0
        if not needs_header:
            return
        mode = "w" if truncate else "a"
        with self.csv_path.open(mode, encoding="utf-8", newline="") as fh:
            fh.write(",".join(self._columns) + "\n")

    def _expand_columns(self, incoming_columns: Iterable[str]) -> None:
        """Append new columns to the index and backfill existing records."""
        for column in incoming_columns:
            if column in self._columns:
                continue
            self._columns.append(column)
            for record in self._records:
                record[column] = ""

    def rename_columns(self, renames: dict[str, str], *, save: bool = True) -> bool:
        """Rename columns in place, preserving values. Returns True if any columns changed."""
        migrated = False
        for old_name, new_name in renames.items():
            if old_name not in self._columns:
                continue

            if new_name not in self._columns:
                self._columns.append(new_name)

            for record in self._records:
                old_value = record.pop(old_name, "")
                if record.get(new_name) in ("", None) and old_value not in ("", None):
                    record[new_name] = old_value

            self._columns = [column for column in self._columns if column != old_name]
            migrated = True

        if migrated and save:
            self.save()

        return migrated

    def _reorder_columns(self, preferred: Iterable[str]) -> None:
        """Reorder columns to match a preferred sequence; unknown columns trail."""
        preferred_columns = [column for column in preferred if column in self._columns]
        trailing_columns = [column for column in self._columns if column not in preferred_columns]
        self._columns = preferred_columns + trailing_columns

    def _normalize_record(self, record: BillRecord) -> BillRecord:
        """Ensure a record contains every index column."""
        return {column: record.get(column, "") for column in self._columns}

    def _validate_records(self, incoming: list[BillRecord]):
        for record in incoming:
            if not record.get("id"):
                raise ValueError(f"Bill record is missing an id: {record}")


def _format_csv_cell(value: Any) -> str:
    """Format one CSV cell, quoting values that contain commas, quotes, or newlines."""
    if value is None:
        text = ""
    else:
        text = str(value)

    if "," in text or '"' in text or "\n" in text or "\r" in text:
        return '"' + text.replace('"', '""') + '"'
    return text


def _format_csv_row(columns: list[str], record: BillRecord) -> str:
    """Format one CSV row."""
    return ",".join(_format_csv_cell(record.get(column, "")) for column in columns)


def _decode_value(column: str, value: str | None) -> Any:
    """Decode one CSV cell back into a record value.

    ``csv.DictReader`` has already removed CSV quoting by the time this runs, so the
    text arriving here is the stored text, and unquoting it again can only damage it.
    A second unquoting branch used to live here (``json.loads``, falling back to
    stripping the outer quotes and collapsing ``""``), which is why text that itself
    began and ended with a straight quote lost those quotes, and why the two branches
    disagreed about backslash escapes (#256).

    It was never the inverse of anything this module wrote: ``_format_csv_cell`` has
    emitted plain CSV quoting in every revision of this file and has never JSON-encoded
    a cell, so no on-disk index has ever needed JSON decoding. Removing it changes how
    a stored value reads only in the case it was corrupting.

    It no longer coerces digits to ``int`` either (#256). A CSV cell is text, and the
    reader guessed a type from the value's *shape* while ignoring which column it was
    reading, so any text that happened to be all digits came back as a number: a title
    of ``2024``, or worse, an ``id`` of ``12345``, which then crashed the
    ``--file <csv>`` download path on ``.strip()``.

    The alternative -- declaring a type per column -- was considered and rejected. This
    index is documented to carry *arbitrary* metadata, so a type registry would need
    every producer to register its columns and would still need a rule for the ones that
    did not. Returning text is also what the file actually holds. Callers that want a
    number convert at the point of use; nothing in the project reads the writer's
    counting columns (``actionCount``, ``daysActive``, ``historySize`` and peers) back
    out, so no caller loses anything here.
    """
    if value is None or value == "":
        return ""

    return value
