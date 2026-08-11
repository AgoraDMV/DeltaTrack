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
