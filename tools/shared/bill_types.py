"""Bill type definitions."""

from typing import TypeAlias

# (human-readable label, congress.gov URL slug)
BILL_TYPES = {
    "hr": ("H.R.", "house-bill"),
    "s": ("S.", "senate-bill"),
    "hjres": ("H.J.Res.", "house-joint-resolution"),
    "sjres": ("S.J.Res.", "senate-joint-resolution"),
    "hres": ("H.Res.", "house-resolution"),
    "sres": ("S.Res.", "senate-resolution"),
    "hconres": ("H.Con.Res.", "house-concurrent-resolution"),
    "sconres": ("S.Con.Res.", "senate-concurrent-resolution"),
}

BillType: TypeAlias = str


def resolve_bill_types(bill_types: list[str] | None) -> list[BillType]:
    """Resolve bill-type tokens into canonical lowercase keys."""
    normalized = [bill_type.lower() for bill_type in (bill_types or [])]
    if not normalized or "all" in normalized:
        return list(BILL_TYPES)
    for bill_type in normalized:
        if bill_type not in BILL_TYPES:
            raise ValueError(
                f"Unknown bill type '{bill_type}'. Bill type must be one of: {list(BILL_TYPES)}"
            )
    return normalized
