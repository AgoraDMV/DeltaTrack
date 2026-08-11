"""In-memory two-version comparison: bytes in, canonical diff and HTML report out.

This is the product surface as ADR 0005 draws it — the engine a caller hands two
document versions to, with no persistence and no acquisition. `pdf.py` and `xml.py`
each wrap the parse → diff → render pipeline for one input format.

Both modules used to live under `server/`, which read as though they belonged to the
web app. They never did: neither imports FastAPI, and the `diff_bill.py` and
`diff_pdf.py` CLIs both reach into them for their HTML output. Filed here, the CLIs
depend on the engine instead of on a delivery channel (#367, and one of the
reach-arounds tracked in #62).
"""
