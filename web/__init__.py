"""DeltaTrack web delivery channel: a FastAPI app plus the static front-end it serves.

A thin layer over the diff engine. It does not reimplement any diffing logic — it
imports the same `compare/` pipeline the CLIs use and returns canonical diff JSON
(see schema/canonical-diff.md) for the browser front-end in `web/webapp/` to render.

Kept out of the product tree because serving the engine over HTTP is one delivery
channel among several still under consideration (#112, ADR 0011), not the engine
itself. Its dependencies are the `web` group in pyproject.toml rather than core
requirements, so installing the engine does not install a web server (#367).
"""
