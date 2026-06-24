"""
A cache for bill metadata intended to accumulate information about large volumes of bills.

The guiding idea behind the cache is that each bill has an identifying slug of the form:

{congress}-{type}-{number}[:{version}]

e.g. `119-hr-1` for the 1st House Resolution bill of the 119th Congress.

Aside from a uniquely identifying slug, each bill can have arbitrary metadata.
The index automatically syncs with a CSV file. It can be used to prevent duplicate downloads
and to accumulate bill metadata from different sources.

Usage:
index = BillIndex(csv_path)
records: list[dict] = index.bills
bill_ids: list[str] = [record["id"] for record in records]
latest_hr_bills = index.fetch_all(119, "hr")
for senate, bill_type, bill_number, doc_version in map(parse_bill_id, bill_ids):
    ...
"""

from __future__ import annotations

import csv
import json
from collections import namedtuple
from pathlib import Path
from typing import Any, Iterable, Literal, Tuple

from shared.bill_types import BILL_TYPES

BillRecord = dict[str, Any]
InsertMode = Literal["merge", "skip"]


def make_bill_id(congress: int | str, bill_type: str, number: int | str) -> str:
    """Build a bill id slug from a congress number, bill type, and bill number."""
    return f"{congress}-{bill_type}-{number}"


BillIdentifier = namedtuple("BillIdentifier", ["congress", "bill_type", "number", "version"])


def parse_bill_id(slug: str) -> BillIdentifier:
    """Parse `congress-type-number[:version]` into a typed identifier."""
    id_version = slug.split(":")
    id, version = id_version[0], None if len(id_version) == 1 else id_version[1]
    congress, bill_type, number = id.split("-")
    if bill_type not in BILL_TYPES:
        raise ValueError(f"Unknown bill type '{bill_type}' in slug: {slug}")

    return BillIdentifier(congress=congress, bill_type=bill_type, number=number, version=version)


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

        with self.csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames:
                self._columns = list(reader.fieldnames)
                if "id" not in self._columns:
                    raise ValueError("CSV file is missing required column: 'id'")
            for row in reader:
                bill = {key: _decode_value(key, row.get(key, "")) for key in self._columns}
                self._records.append(bill)
                self._bills_by_id[bill["id"]] = bill

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
    if value is None or value == "":
        return ""

    try:
        return int(value)
    except ValueError:
        pass

    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1].replace('""', '"')

    return value
