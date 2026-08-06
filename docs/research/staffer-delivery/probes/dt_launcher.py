"""Spike-only entry point for the packaged-executable experiment (Options F/H).

NOT production code. Exists to answer three questions about packaging the engine
with PyInstaller: does pypdfium2's native binary get collected, how large is the
artifact, and how long does a cold start take before the first byte of real work.

Usage (packaged):  DeltaTrack <old.xml> <new.xml> [-o report.html]
                   DeltaTrack --selftest        # timing probe, no arguments needed
"""

from __future__ import annotations

import sys
import time

_T_PROCESS_START = time.time()


def _probe_pdfium(argv: list[str]) -> str:
    """Exercise the bundled PDFium binary for real; return a one-line status.

    Opens a PDF and extracts text from page 1. If a path is supplied after
    ``--pdf`` that file is used, otherwise a one-page PDF is synthesized in memory
    so the probe needs no fixture. Either way the native library is loaded and
    called, so "OK" cannot be returned by a build that dropped the binary.
    """
    try:
        import pypdfium2 as pdfium
    except Exception as e:  # noqa: BLE001
        return f"IMPORT FAILED: {type(e).__name__}: {e}"

    try:
        if "--pdf" in argv:
            doc = pdfium.PdfDocument(argv[argv.index("--pdf") + 1])
        else:
            doc = pdfium.PdfDocument.new()
            doc.new_page(200, 200)
        n_pages = len(doc)
        text = doc[0].get_textpage().get_text_range()
        doc.close()
        ver = f"pypdfium2 {pdfium.version.PYPDFIUM_INFO}, libpdfium {pdfium.version.PDFIUM_INFO}"
        return f"OK {ver} | {n_pages} page(s), {len(text)} chars extracted"
    except Exception as e:  # noqa: BLE001
        return f"NATIVE CALL FAILED: {type(e).__name__}: {e}"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # Import INSIDE main so the cost lands after process start and is measurable.
    t_imp = time.perf_counter()
    from deltatrack.compare.xml import compare_xml_html

    import_ms = (time.perf_counter() - t_imp) * 1000

    # Prove the native PDF engine survived packaging -- this is the dependency most
    # likely to be silently dropped, and a "works on XML" test would never notice.
    #
    # An attribute probe is NOT sufficient: it can fail for a wrong attribute name
    # while the library is present and fully working, which reads as "packaging
    # dropped the binary" and is the opposite of true. So this actually opens a PDF
    # and extracts text -- the .dylib/.dll is exercised or the check does not pass.
    pdfium_status = _probe_pdfium(argv)

    if "--selftest" in argv:
        print(f"pypdfium2:        {pdfium_status}")
        print(f"engine import:    {import_ms:.0f} ms")
        print(f"cold start->here: {(time.time() - _T_PROCESS_START) * 1000:.0f} ms")
        print(f"frozen:           {getattr(sys, 'frozen', False)}")
        print(f"python:           {sys.version.split()[0]}")
        # EXIT NON-ZERO when the native probe failed. Printing a failure string and
        # returning 0 lets an automated run read a dropped or broken PDFium binary as a
        # successful experiment, which is the exact failure this self-test exists to
        # catch. The status string is for a human; the exit code is for the harness.
        if not pdfium_status.startswith("OK "):
            print("SELFTEST FAILED: the bundled PDFium binary is missing or unusable.", file=sys.stderr)
            return 1
        return 0

    if len(argv) < 2:
        print(__doc__)
        return 2

    from pathlib import Path

    old, new = Path(argv[0]), Path(argv[1])
    out = Path(argv[argv.index("-o") + 1]) if "-o" in argv else Path("deltatrack-report.html")

    t = time.perf_counter()
    html = compare_xml_html(old.read_bytes(), new.read_bytes(), start_label=old.stem, end_label=new.stem)
    diff_ms = (time.perf_counter() - t) * 1000

    out.write_text(html, encoding="utf-8")
    print(f"pypdfium2:     {pdfium_status}")
    print(f"engine import: {import_ms:.0f} ms")
    print(f"diff+render:   {diff_ms:.0f} ms")
    print(f"total elapsed: {(time.time() - _T_PROCESS_START) * 1000:.0f} ms")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
