"""Resolve version-prefixed bill filename stems (e.g. ``1_reported-in-house``).

The on-disk convention is ``<n>_<label>.{xml,pdf}`` inside a ``{congress}-{type}-{number}``
bill folder, where ``<n>`` is the 1-indexed legislative order and ``<label>`` is the
readable stage. A version's number and meaning are **per-bill**, not universal
(ADR 0013), so these helpers resolve a bill slug + ordinal ``n`` to its readable version
file. The readable labels stay; filenames are not migrated to a slug form.
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
