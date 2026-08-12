"""A33 -- region crop and the pixel/PDF coordinate transform. NOT a harness component.

Pure encodings of the A33 rulings, written executably so they can be tested before
`build_oracle.py` exists. Nothing here opens a PDF, scores anything, or decides an outcome.
`x20_oracle_crop_coordinates.py` is the test.

    A33.1  the region bbox is the MINIMAL union of COMMITTED neutral-line bboxes, zero padding
    A33.2  the committed frame is authoritative -- geometry is never re-derived from the PDF
    A33.3  the pixel<->PDF transform is the renderer's actual mapping, measured not assumed
    A33.4  a rotated page is REFUSED -- ratified, and it aborts rather than skipping
    A34    the device-rectangle epsilon: MuPDF rounds out only past 0.001 px, at BOTH edges.
           A33 originally spelled the transform epsilon-free; A34 corrects that forward, and
           `x20` falsifies the constant against the renderer with the boundary bracketed.

WHY THE TRANSFORM IS NOT WHAT A30.3 SKETCHED. A30.3 described the inversion as a linear map
across the bbox:

    pdf_x = bbox_x0 + (start_x_px / image_width) * (bbox_x1 - bbox_x0)

`x20` measures that MuPDF does something different and simpler: the pixmap's device origin is
`floor(bbox_x0 * DPI/72)`, so image column 0 is NOT `bbox_x0`, and each pixel is exactly
`72/DPI` points -- never `(bbox_x1-bbox_x0)/image_width`, which differs because the integer
pixmap is the rounded-out bounding box of the transformed clip. Both errors are small per pixel
and both accumulate across a region-width image. The mapping below is the renderer's, and it
needs no metadata beyond `bbox_x0` and the frozen DPI.
"""

from __future__ import annotations

import math

# abort classes -- each refuses; none is representable in a rendered stimulus
MISSING_LINE_BBOX = "MISSING_LINE_BBOX"
NON_FINITE_LINE_BBOX = "NON_FINITE_LINE_BBOX"
NON_POSITIVE_LINE_BBOX = "NON_POSITIVE_LINE_BBOX"
NON_POSITIVE_REGION_BBOX = "NON_POSITIVE_REGION_BBOX"
REGION_HAS_NO_LINES = "REGION_HAS_NO_LINES"
REGION_BBOX_OUTSIDE_PAGE = "REGION_BBOX_OUTSIDE_PAGE"
NONZERO_PAGE_ROTATION = "NONZERO_PAGE_ROTATION"


class OracleGeometryError(Exception):
    """The committed geometry cannot be rendered as frozen. Deterministic, never a value."""

    def __init__(self, reason: str, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason} {detail!r}")


# ------------------------------------------------------------------- A33.1 / A33.2 bbox


def region_bbox(page_frame: dict, region_ordinal: int):
    """The MINIMAL axis-aligned union of the region's COMMITTED neutral-line bboxes.

    ZERO PADDING. A `NeutralLine` bbox is already the min/max over every eligible source-glyph
    box on that physical line, so padding would introduce a free parameter, could expose
    neighbouring content outside the frozen region, and would no longer be the unique
    least-expansive rectangle implementing "region bbox from neutral geometry".

    A33.2 -- this reads ONLY the committed frame. It never re-clusters, never re-reads the PDF,
    and never consults H text, X text, anchor content or adjudicated content. The PDF supplies
    pixels; the frame supplies which rectangle to render.
    """
    region = next((r for r in page_frame["regions"] if r["region_ordinal"] == region_ordinal), None)
    if region is None or not region["neutral_line_keys"]:
        raise OracleGeometryError(REGION_HAS_NO_LINES, {"region_ordinal": region_ordinal})

    wanted = {tuple(k) for k in region["neutral_line_keys"]}
    boxes = []
    for line in page_frame["neutral_lines"]:
        if tuple(line["key"]) in wanted:
            bbox = line.get("bbox")
            if bbox is None or len(bbox) != 4:
                raise OracleGeometryError(MISSING_LINE_BBOX, {"line": line.get("key")})
            if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in bbox):
                raise OracleGeometryError(NON_FINITE_LINE_BBOX, {"line": line.get("key"), "bbox": bbox})
            # EACH committed line must be positive-area in its own right. Checking only the
            # union would let a degenerate line pass whenever its siblings happen to make the
            # union positive -- the region would render, and the defective committed geometry
            # would never be seen. The bad line is refused, never silently dropped.
            if not (bbox[2] > bbox[0] and bbox[3] > bbox[1]):
                raise OracleGeometryError(NON_POSITIVE_LINE_BBOX, {"line": line.get("key"), "bbox": bbox})
            boxes.append(bbox)
    if len(boxes) != len(wanted):
        raise OracleGeometryError(MISSING_LINE_BBOX, {"expected": len(wanted), "found": len(boxes)})

    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    if not (x1 > x0 and y1 > y0):
        raise OracleGeometryError(NON_POSITIVE_REGION_BBOX, {"bbox": [x0, y0, x1, y1]})
    return (x0, y0, x1, y1)


def validate_region_bbox_for_page(bbox, page_width: float, page_height: float) -> None:
    """A33.1 -- committed geometry that cannot be rendered whole is REFUSED, never repaired.

    The reusable boundary a future `build_oracle` calls before rendering. There is deliberately
    no clip-to-page, no intersection, no padding and no repair: a region extending past the
    page means the committed frame geometry disagrees with the page it claims to describe, and
    silently rendering the surviving part would hand the adjudicator a stimulus that is not the
    region the frame committed to.
    """
    x0, y0, x1, y1 = bbox
    if x0 < 0 or y0 < 0 or x1 > page_width or y1 > page_height:
        raise OracleGeometryError(
            REGION_BBOX_OUTSIDE_PAGE,
            {"bbox": [x0, y0, x1, y1], "page": [page_width, page_height]},
        )


# ------------------------------------------------------------------ A33.3 the transform


def scale(dpi: int) -> float:
    return dpi / 72.0


# MuPDF's own rounding fudge, MEASURED not assumed: sweeping the overhang of the transformed
# right edge, a device rectangle rounds out only once it exceeds an integer by MORE than 0.001
# px (2025.001 -> 2025; 2025.0011 -> 2026). This is `fz_round_rect`'s epsilon, applied
# symmetrically at both edges. It is a RENDERER CONSTANT, not a tolerance: nothing in the
# nearest-x resolver consults it, and it admits no slack in the identity decision.
MUPDF_ROUND_EPS = 0.001


def device_origin_px(bbox_x0: float, dpi: int) -> int:
    """The device x of image column 0.

    MEASURED: MuPDF's pixmap is the rounded-OUT integer bounding box of the transformed clip,
    so its origin is a floor, not `bbox_x0 * s`. The epsilon matters here too, and its absence
    would be a LATENT OFF-BY-ONE in the inversion: without it, a `bbox_x0 * s` sitting just
    below an integer floors one pixel low, which no synthetic phase grid and no development
    region happened to hit.
    """
    return math.floor(bbox_x0 * scale(dpi) + MUPDF_ROUND_EPS)


def expected_image_width(bbox_x0: float, bbox_x1: float, dpi: int) -> int:
    """The width MuPDF returns for this clip: ceil(x1*s) - floor(x0*s).

    A VALIDATION helper only -- `pixel_to_pdf_x` does not use it, so nothing in the inversion
    depends on this function. It applies `MUPDF_ROUND_EPS` at both edges, which is the
    renderer's measured behaviour and which also subsumes the IEEE-double case where `x1 * s`
    is mathematically an integer but evaluates to 463.00000000000006.
    """
    s = scale(dpi)
    return math.ceil(bbox_x1 * s - MUPDF_ROUND_EPS) - math.floor(bbox_x0 * s + MUPDF_ROUND_EPS)


def pixel_to_pdf_x(start_x_px: int, bbox_x0: float, dpi: int) -> float:
    """A33.3 -- the frozen inversion. Needs only `bbox_x0` and the frozen DPI.

    Each pixel is exactly 72/DPI points; the origin is the pixmap's device origin. `image_width`
    is deliberately NOT an input: using it as a scale, as A30.3 sketched, spreads the
    rounded-out integer width across the region and drifts by a pixel or more at the far edge.
    """
    return (device_origin_px(bbox_x0, dpi) + start_x_px) / scale(dpi)


def pdf_x_to_pixel(pdf_x: float, bbox_x0: float, dpi: int) -> int:
    """The forward map an adjudicator's eye approximates: which integer column contains `pdf_x`."""
    return math.floor(pdf_x * scale(dpi)) - device_origin_px(bbox_x0, dpi)


# --------------------------------------------------------------------- A33.4 rotation


def check_rotation(rotation: int) -> None:
    """A33.4, RATIFIED -- a rotated source page is non-executable, and ABORTS.

    `x20` proves the CLIP can be carried exactly onto a rotated page by `page.rotation_matrix`.
    That is not sufficient, and the reason is the part that matters: at 90 and 270 the image's
    horizontal axis is the PDF **y** axis, and at 180 it is the PDF x axis MIRRORED. So
    `start_x_px` -- a horizontal pixel offset the adjudicator marks -- stops corresponding to a
    neutral glyph's `x0`, which is the quantity A30.3's nearest-x resolver compares. Rendering
    the right pixels is not the same as preserving the coordinate semantics.

    IT ABORTS ORACLE CONSTRUCTION. It must NEVER skip the page, skip the region, drop the
    stimulus, or reduce any denominator. Those would each turn an unrepresentable condition
    into a quietly smaller study -- the same silent-reduction failure the frame preconditions
    exist to prevent -- and the loss would be invisible precisely because the affected pages
    are the ones no longer counted. Encountered on confirmatory material, execution stops for
    review; rotation is neither silently supported nor silently removed.
    """
    if rotation:
        raise OracleGeometryError(NONZERO_PAGE_ROTATION, {"rotation": rotation})
