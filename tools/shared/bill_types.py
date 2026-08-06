"""Bill type definitions."""

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

def resolve_bill_types(bill_types: list[str] | None = None) -> list[str]:
    "Allow for 'all' keyword to include all bill types. Default to all types if no type are specified."
    return list(BILL_TYPES) if bill_types is None or "all" in bill_types else bill_types
