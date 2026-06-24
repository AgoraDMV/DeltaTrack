"""Parse version-prefixed bill filename stems (e.g. ``1_reported-in-house``).

Transitional: the on-disk convention is ``<n>_<label>.{xml,pdf}``. If downloaded
filenames move to the slug convention (``119-hr-1:2``), prefer
``bill_index.parse_bill_id`` and retire these helpers.
"""

from __future__ import annotations


def version_number_from_stem(stem: str) -> int | None:
    """Leading ``<n>_`` version number from a filename stem, else None."""
    prefix = stem.split("_", 1)[0]
    return int(prefix) if prefix.isdigit() else None


def label_from_stem(stem: str) -> str:
    """Human-readable label after a numeric ``<n>_`` prefix; stem unchanged otherwise."""
    parts = stem.split("_", 1)
    return parts[1] if len(parts) == 2 and parts[0].isdigit() else stem
