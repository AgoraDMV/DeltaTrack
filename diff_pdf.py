#!/usr/bin/env python3
"""`./diff_pdf.py` -- the command, wrapping `deltatrack.diff_pdf` (#398).

See `diff_bill.py` beside this file for why the wrapper exists and why `build_parser` is
re-exported rather than only `main`.
"""

try:
    from deltatrack.diff_pdf import build_parser, main
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard, not logic
    if exc.name != "deltatrack":
        raise
    raise SystemExit(
        "diff_pdf.py: DeltaTrack is not installed in this environment.\n"
        "Run `source ./init` from the project folder first (it installs dependencies and "
        "activates the environment), then try again."
    ) from exc

__all__ = ["build_parser", "main"]

if __name__ == "__main__":
    main()
