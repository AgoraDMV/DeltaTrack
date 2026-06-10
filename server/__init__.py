"""DeltaTrack web service.

A thin FastAPI layer over the existing diff engine. It does not reimplement any
diffing logic — it imports the same pipeline the CLI and sample generator use
and returns canonical diff JSON (schema v1.2) for a browser front-end to render.
"""
