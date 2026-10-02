"""Reconstrucción limpia de muros y ejes a partir de un plano escaneado.

Un dibujante dibuja un muro como dos líneas paralelas a distancia constante y
un eje como una línea larga de trazo y punto. Aquí se detectan segmentos
largos (LSD de OpenCV), se emparejan los paralelos cercanos (= caras de un
muro), se fusionan los tramos colineales, se enderezan a horizontal/vertical
y se prolongan hasta cruzarse en esquinas y encuentros. Los ejes son líneas
largas, discontinuas, que no pertenecen a ningún muro.

Limitaciones honestas: solo muros rectos (los arcos no se detectan como muro),
y los vanos de puertas pueden quedar abiertos o cerrados según el escaneo.
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from .line_detector import Segment, merge_collinear_segments

logger = logging.getLogger("planos2dwg")

_MM_PER_INCH = 25.4
_REFERENCE_DPI = 300
_BACKGROUND_KERNEL_AT_REF_DPI = 51

_WALL_MIN_LENGTH_MM = 4.0
_WALL_THICKNESS_MM = (0.8, 2.2)
_STROKE_EDGE_MM = 0.55
_PAIR_ANGLE_DEG = 2.5
_PAIR_MIN_OVERLAP = 0.6
_SNAP_ANGLE_DEG = 1.5
_CORNER_REACH_MM = 2.5

_AXIS_MIN_PIECE_MM = 3.0
_AXIS_GAP_MM = 14.0
_AXIS_MIN_SPAN_MM = 40.0
_AXIS_MIN_PIECES = 3
_AXIS_MAX_COVERAGE = 0.92
_AXIS_OFFSET_MM = 0.6


def _odd(value: float) -> int:
    number = max(3, int(round(value)))
    return number if number % 2 == 1 else number + 1


def _lsd_segments(image: np.ndarray, dpi: int) -> np.ndarray:
    """Segmentos (n, 4) = x1, y1, x2, y2 detectados sobre la imagen sin fondo."""
    scale = dpi / _REFERENCE_DPI
    background = cv2.medianBlur(image, _odd(_BACKGROUND_KERNEL_AT_REF_DPI * scale))
    normalized = cv2.divide(image, background, scale=255)
    lines = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(normalized)[0]
    if lines is None:
        return np.zeros((0, 4), dtype=np.float64)
    return lines[:, 0, :].astype(np.float64)


def _paired_indices(segments: np.ndarray, px_per_mm: float) -> set[int]:
    """Índices de los segmentos que tienen un paralelo cercano (cara de muro)."""
    count = len(segments)
    if count < 2:
        return set()

    angle = np.arctan2(segments[:, 3] - segments[:, 1], segments[:, 2] - segments[:, 0]) % math.pi
    ux, uy = np.cos(angle), np.sin(angle)
    nx, ny = -uy, ux
    mid_x = (segments[:, 0] + segments[:, 2]) / 2
    mid_y = (segments[:, 1] + segments[:, 3]) / 2
    along_a = segments[:, 0] * ux + segments[:, 1] * uy
    along_b = segments[:, 2] * ux + segments[:, 3] * uy
    low, high = np.minimum(along_a, along_b), np.maximum(along_a, along_b)
    length = high - low

    min_gap = _WALL_THICKNESS_MM[0] * px_per_mm
    max_gap = _WALL_THICKNESS_MM[1] * px_per_mm
    angle_tol = math.radians(_PAIR_ANGLE_DEG)

    paired: set[int] = set()
    for i in range(count - 1):
        rest = slice(i + 1, count)
        delta = np.abs(angle[i] - angle[rest])
        delta = np.minimum(delta, math.pi - delta)
        gap = np.abs((mid_x[rest] - mid_x[i]) * nx[i] + (mid_y[rest] - mid_y[i]) * ny[i])

        # proyección del resto sobre la dirección de i
        a = segments[rest, 0] * ux[i] + segments[rest, 1] * uy[i]
        b = segments[rest, 2] * ux[i] + segments[rest, 3] * uy[i]
        other_low, other_high = np.minimum(a, b), np.maximum(a, b)
        overlap = np.minimum(high[i], other_high) - np.maximum(low[i], other_low)
        shortest = np.minimum(length[i], other_high - other_low)

        match = (
            (delta <= angle_tol)
            & (gap >= min_gap)
            & (gap <= max_gap)
            & (overlap >= _PAIR_MIN_OVERLAP * shortest)
            & (overlap >= 0.8 * _WALL_MIN_LENGTH_MM * px_per_mm)
        )
        for offset in np.nonzero(match)[0]:
            paired.add(i)
            paired.add(i + 1 + int(offset))
    return paired


def _snap_axis_aligned(segments: list[Segment]) -> list[Segment]:
    """Endereza a horizontal/vertical exacto los segmentos casi alineados."""
    tolerance = math.tan(math.radians(_SNAP_ANGLE_DEG))
    snapped: list[Segment] = []
    for (x1, y1), (x2, y2) in segments:
        dx, dy = x2 - x1, y2 - y1
        if abs(dy) <= tolerance * abs(dx):
            y = (y1 + y2) / 2
            snapped.append(((x1, y), (x2, y)))
        elif abs(dx) <= tolerance * abs(dy):
            x = (x1 + x2) / 2
            snapped.append(((x, y1), (x, y2)))
        else:
            snapped.append(((x1, y1), (x2, y2)))
    return snapped


def _line_intersection(a: Segment, b: Segment) -> tuple[float, float] | None:
    (x1, y1), (x2, y2) = a
    (x3, y3), (x4, y4) = b
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def _extend_to_corners(segments: list[Segment], reach_px: float) -> list[Segment]:
    """Prolonga cada extremo hasta cruzar un muro perpendicular cercano."""
    result = [list(map(list, s)) for s in segments]
    for i, segment in enumerate(segments):
        for end in (0, 1):
            tip = segment[end]
            best: tuple[float, tuple[float, float]] | None = None
            for j, other in enumerate(segments):
                if i == j:
                    continue
                direction_a = (segment[1][0] - segment[0][0], segment[1][1] - segment[0][1])
                direction_b = (other[1][0] - other[0][0], other[1][1] - other[0][1])
                cross = abs(direction_a[0] * direction_b[1] - direction_a[1] * direction_b[0])
                norms = math.hypot(*direction_a) * math.hypot(*direction_b)
                if norms == 0 or cross / norms < 0.5:
                    continue
                point = _line_intersection(segment, other)
                if point is None:
                    continue
                distance = math.dist(tip, point)
                if distance > reach_px:
                    continue
                other_len = math.dist(other[0], other[1])
                along = (
                    (point[0] - other[0][0]) * (other[1][0] - other[0][0])
                    + (point[1] - other[0][1]) * (other[1][1] - other[0][1])
                ) / (other_len**2)
                margin = reach_px / other_len
                if along < -margin or along > 1 + margin:
                    continue
                if best is None or distance < best[0]:
                    best = (distance, point)
            if best is not None:
                result[i][end] = [best[1][0], best[1][1]]
    return [((p[0][0], p[0][1]), (p[1][0], p[1][1])) for p in result]


def detect_walls_and_axes(
    image: np.ndarray,
    dpi: int,
    ignore_bottom_fraction: float = 0.0,
) -> tuple[list[Segment], list[Segment]]:
    """Devuelve (caras de muro, ejes) como segmentos en píxeles.

    `ignore_bottom_fraction` descarta la franja inferior de la imagen (por
    ejemplo el rótulo del plano) para que no se confunda con muros.
    """
    px_per_mm = dpi / _MM_PER_INCH
    segments = _lsd_segments(image, dpi)
    if len(segments) == 0:
        return [], []

    if ignore_bottom_fraction > 0:
        limit = image.shape[0] * (1 - ignore_bottom_fraction)
        centres_y = (segments[:, 1] + segments[:, 3]) / 2
        segments = segments[centres_y < limit]

    lengths = np.hypot(segments[:, 2] - segments[:, 0], segments[:, 3] - segments[:, 1])
    segments = segments[lengths >= _AXIS_MIN_PIECE_MM * px_per_mm]

    # LSD devuelve los dos bordes de cada trazo grueso: se fusionan en una
    # sola línea central antes de buscar pares de caras de muro.
    raw: list[Segment] = [
        ((float(s[0]), float(s[1])), (float(s[2]), float(s[3]))) for s in segments
    ]
    strokes = merge_collinear_segments(
        raw, dpi=dpi, offset_tolerance_px=_STROKE_EDGE_MM * px_per_mm
    )
    stroke_array = np.array([[a[0], a[1], b[0], b[1]] for a, b in strokes], dtype=np.float64)
    stroke_lengths = np.hypot(
        stroke_array[:, 2] - stroke_array[:, 0], stroke_array[:, 3] - stroke_array[:, 1]
    )

    candidate_ids = np.nonzero(stroke_lengths >= _WALL_MIN_LENGTH_MM * px_per_mm)[0]
    local_paired = _paired_indices(stroke_array[candidate_ids], px_per_mm)
    paired_ids = {int(candidate_ids[k]) for k in local_paired}

    wall_raw = [strokes[k] for k in sorted(paired_ids)]
    walls = merge_collinear_segments(wall_raw, dpi=dpi)
    walls = _snap_axis_aligned(walls)
    walls = _extend_to_corners(walls, _CORNER_REACH_MM * px_per_mm)

    axis_pieces = [stroke for k, stroke in enumerate(strokes) if k not in paired_ids]
    axes = _axes_from_pieces(axis_pieces, dpi, px_per_mm)

    logger.info("Muros: %d caras (de %d segmentos). Ejes: %d.", len(walls), len(wall_raw), len(axes))
    return walls, axes


def _axes_from_pieces(pieces: list[Segment], dpi: int, px_per_mm: float) -> list[Segment]:
    """Agrupa trozos colineales discontinuos y conserva los que parecen un eje."""
    if not pieces:
        return []

    gap = _AXIS_GAP_MM * px_per_mm
    grouped = merge_collinear_segments(pieces, dpi=dpi, gap_tolerance_px=gap)

    axes: list[Segment] = []
    for merged in grouped:
        (mx1, my1), (mx2, my2) = merged
        span = math.hypot(mx2 - mx1, my2 - my1)
        if span < _AXIS_MIN_SPAN_MM * px_per_mm:
            continue
        direction = ((mx2 - mx1) / span, (my2 - my1) / span)
        intervals: list[tuple[float, float]] = []
        for (x1, y1), (x2, y2) in pieces:
            off1 = abs((x1 - mx1) * -direction[1] + (y1 - my1) * direction[0])
            off2 = abs((x2 - mx1) * -direction[1] + (y2 - my1) * direction[0])
            t1 = (x1 - mx1) * direction[0] + (y1 - my1) * direction[1]
            t2 = (x2 - mx1) * direction[0] + (y2 - my1) * direction[1]
            if max(off1, off2) <= _AXIS_OFFSET_MM * px_per_mm and min(t1, t2) >= -2 and max(t1, t2) <= span + 2:
                intervals.append((min(t1, t2), max(t1, t2)))
        dashes = _union_intervals(sorted(intervals), gap=0.3 * px_per_mm)
        if len(dashes) < _AXIS_MIN_PIECES:
            continue
        covered = sum(end - start for start, end in dashes)
        if covered / span > _AXIS_MAX_COVERAGE:
            continue
        axes.append(merged)
    return _snap_axis_aligned(axes)


def _union_intervals(intervals: list[tuple[float, float]], gap: float) -> list[tuple[float, float]]:
    """Une intervalos ordenados que se tocan o están a menos de `gap`."""
    merged: list[tuple[float, float]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1] + gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
