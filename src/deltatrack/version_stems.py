"""Resolve version-prefixed bill filename stems (e.g. ``1_reported-in-house``).

The on-disk convention is ``<n>_<label>.{xml,pdf}`` inside a ``{congress}-{type}-{number}``
bill folder, where ``<n>`` is the 1-indexed legislative order and ``<label>`` is the
readable stage. A version's number and meaning are **per-bill**, not universal
(ADR 0013), so these helpers resolve a bill slug + ordinal ``n`` to its readable version
file. The readable labels stay; filenames are not migrated to a slug form.
"""

from __future__ import annotations

from pathlib import Path


def version_number_from_stem(stem: str) -> int | None:
    """Leading ``<n>_`` version number from a filename stem, else None.

    ``isdecimal`` rather than ``isdigit``: ``"³".isdigit()`` is True while ``int("³")``
    raises, so a file named ``³_x.xml`` made this raise ValueError instead of answering
    None. Reachable from :func:`local_versions`, which reads whatever is on disk.
    """
    prefix = stem.split("_", 1)[0]
    return int(prefix) if prefix.isdecimal() else None


def label_from_stem(stem: str) -> str:
    """Human-readable label after a numeric ``<n>_`` prefix; stem unchanged otherwise.

    Same ``isdecimal`` test as above, so a prefix this module cannot turn into an
    ordinal is not treated as one here either.
    """
    parts = stem.split("_", 1)
    return parts[1] if len(parts) == 2 and parts[0].isdecimal() else stem


def local_versions(bills_dir: Path, slug: str, ext: str = "xml") -> list[tuple[int, str]]:
    """``(ordinal, label)`` for every locally present version of ``slug``, ascending.

    Reads ``{bills_dir}/{slug}/{n}_{label}.{ext}``. The sort key is the one
    ``scripts/serve_compare.py`` already uses to pick versions — ordinal first, stem as
    the tiebreak — so this listing orders identically to the tool a reader may already
    have open, and ``10`` sorts after ``2`` rather than before it.

    Stems carrying no ``{n}_`` prefix are left out: a version with no ordinal cannot be
    addressed by one, and the point of the listing is to be picked from. A bill folder
    that is missing entirely lists nothing rather than raising — "no local versions" is
    the honest answer to "which versions do I have", and the caller says so.
    """
    bill_dir = bills_dir / slug
    if not bill_dir.is_dir():
        return []
    stems = sorted(
        (p.stem for p in bill_dir.glob(f"*.{ext}")),
        key=lambda s: (version_number_from_stem(s) or 0, s),
    )
    return [(number, label_from_stem(s)) for s in stems if (number := version_number_from_stem(s)) is not None]


def resolve_version_file(bills_dir: Path, slug: str, number: int, ext: str = "xml") -> Path | None:
    """The ``{number}_*.{ext}`` file for ``slug``, or None when there is no such version.

    ADR 0013 names this module the resolver from a bill slug plus an ordinal ``n`` to the
    readable version file; that pair is exactly the address ``diff_bill compare <slug>
    <n_old> <n_new>`` takes (#152). Matching on the ``{number}_`` glob rather than on the
    label keeps a label that itself contains digits or underscores out of the decision,
    and keeps ``3`` from reaching ``30_placed-on-calendar-senate``.

    Returns None instead of raising: an out-of-range ordinal is a question about which
    versions exist, and the answer is :func:`local_versions`, which the caller is better
    placed to render than this module is.
    """
    bill_dir = bills_dir / slug
    if not bill_dir.is_dir():
        return None
    matches = sorted(bill_dir.glob(f"{number}_*.{ext}"))
    return matches[0] if matches else None
