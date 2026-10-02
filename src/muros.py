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

from .arcos import Arc, detect_arcs
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
_CORNER_REACH_MM = 4.0
_CAP_ALIGN_MM = 0.5

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
    return {k for pair in _face_pairs(segments, px_per_mm) for k in pair}


def _face_pairs(segments: np.ndarray, px_per_mm: float) -> list[tuple[int, int]]:
    """Pares (i, j) de segmentos paralelos a distancia de muro y con solape."""
    count = len(segments)
    if count < 2:
        return []

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

    pairs: list[tuple[int, int]] = []
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
            pairs.append((i, i + 1 + int(offset)))
    return pairs


def _merge_stroke_edges(segments: np.ndarray, px_per_mm: float) -> list[Segment]:
    """Funde los dos bordes de cada trazo grueso en una línea central.

    LSD devuelve cada segmento orientado con el lado oscuro siempre del mismo
    lado, así que los dos bordes de un trazo "se miran" (cada uno tiene al otro
    en su lado oscuro), mientras que los bordes enfrentados de dos trazos
    vecinos (el hueco entre las dos caras de un muro) se dan la espalda. Con
    eso se funde cada trazo sin mezclar nunca las dos caras de un muro, que es
    lo que pasaba al fusionar por distancia.
    """
    count = len(segments)
    if count == 0:
        return []

    dx = segments[:, 2] - segments[:, 0]
    dy = segments[:, 3] - segments[:, 1]
    length = np.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    dark_x, dark_y = -uy, ux  # lado oscuro de cada segmento
    mid_x = (segments[:, 0] + segments[:, 2]) / 2
    mid_y = (segments[:, 1] + segments[:, 3]) / 2

    max_width = _STROKE_EDGE_MM * px_per_mm * 1.25
    angle_tol = math.radians(3.0)
    consumed = np.zeros(count, dtype=bool)
    result: list[Segment] = []

    for i in range(count):
        if consumed[i]:
            continue
        rest = np.arange(i + 1, count)
        rest = rest[~consumed[rest]]
        if len(rest) == 0:
            continue

        # a lo largo de la dirección de i
        cross = np.abs(ux[i] * uy[rest] - uy[i] * ux[rest])
        sep_x, sep_y = mid_x[rest] - mid_x[i], mid_y[rest] - mid_y[i]
        toward_j = sep_x * dark_x[i] + sep_y * dark_y[i]  # j en el lado oscuro de i
        toward_i = -(sep_x * dark_x[rest] + sep_y * dark_y[rest])  # i en el lado oscuro de j
        a = (segments[rest, 0] - segments[i, 0]) * ux[i] + (segments[rest, 1] - segments[i, 1]) * uy[i]
        b = (segments[rest, 2] - segments[i, 0]) * ux[i] + (segments[rest, 3] - segments[i, 1]) * uy[i]
        low_j, high_j = np.minimum(a, b), np.maximum(a, b)
        overlap = np.minimum(length[i], high_j) - np.maximum(0.0, low_j)
        shortest = np.minimum(length[i], high_j - low_j)

        ok = (
            (cross <= math.sin(angle_tol))
            & (toward_j > 0.8)
            & (toward_j <= max_width)
            & (toward_i > 0.8)
            & (overlap >= 0.5 * shortest)
        )
        candidates = np.nonzero(ok)[0]
        if len(candidates) == 0:
            continue
        best = rest[candidates[np.argmax(overlap[candidates])]]
        consumed[i] = consumed[best] = True

        # línea central: promedio de los dos bordes, tramo = unión de ambos
        direction = (ux[i], uy[i])
        start_i = (segments[i, 0], segments[i, 1])
        s_values = [
            0.0,
            length[i],
            (segments[best, 0] - start_i[0]) * direction[0] + (segments[best, 1] - start_i[1]) * direction[1],
            (segments[best, 2] - start_i[0]) * direction[0] + (segments[best, 3] - start_i[1]) * direction[1],
        ]
        lo, hi = min(s_values), max(s_values)
        shift_x = (mid_x[best] - mid_x[i]) / 2
        shift_y = (mid_y[best] - mid_y[i]) / 2
        # quitar la componente a lo largo de la línea del desplazamiento
        along = shift_x * direction[0] + shift_y * direction[1]
        shift_x, shift_y = shift_x - along * direction[0], shift_y - along * direction[1]
        result.append(
            (
                (start_i[0] + lo * direction[0] + shift_x, start_i[1] + lo * direction[1] + shift_y),
                (start_i[0] + hi * direction[0] + shift_x, start_i[1] + hi * direction[1] + shift_y),
            )
        )

    for i in range(count):
        if not consumed[i]:
            result.append(((float(segments[i, 0]), float(segments[i, 1])), (float(segments[i, 2]), float(segments[i, 3]))))
    return result


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


def _point_touches(point: tuple[float, float], segments: list[Segment], skip: set[int], tol: float) -> bool:
    for k, (a, b) in enumerate(segments):
        if k in skip:
            continue
        abx, aby = b[0] - a[0], b[1] - a[1]
        denom = abx * abx + aby * aby
        if denom == 0:
            continue
        t = max(0.0, min(1.0, ((point[0] - a[0]) * abx + (point[1] - a[1]) * aby) / denom))
        if math.hypot(point[0] - (a[0] + t * abx), point[1] - (a[1] + t * aby)) <= tol:
            return True
    return False


def _end_caps(walls: list[Segment], px_per_mm: float) -> list[Segment]:
    """Cierra con una línea los extremos libres de cada muro (jambas, cabezas)."""
    if len(walls) < 2:
        return []
    array = np.array([[a[0], a[1], b[0], b[1]] for a, b in walls], dtype=np.float64)
    align_tol = _CAP_ALIGN_MM * px_per_mm
    touch_tol = 2.5 * px_per_mm / 11.8
    caps: dict[tuple[int, int, int, int], Segment] = {}

    for i, j in _face_pairs(array, px_per_mm):
        a, b = walls[i], walls[j]
        length = math.dist(a[0], a[1])
        if length == 0:
            continue
        ux, uy = (a[1][0] - a[0][0]) / length, (a[1][1] - a[0][1]) / length
        along_a = [(p[0] * ux + p[1] * uy) for p in a]
        along_b = [(p[0] * ux + p[1] * uy) for p in b]
        for end_a, end_b in ((int(np.argmin(along_a)), int(np.argmin(along_b))), (int(np.argmax(along_a)), int(np.argmax(along_b)))):
            if abs(along_a[end_a] - along_b[end_b]) > align_tol:
                continue
            tip_a, tip_b = a[end_a], b[end_b]
            if _point_touches(tip_a, walls, {i}, touch_tol) or _point_touches(tip_b, walls, {j}, touch_tol):
                continue
            key = tuple(int(round(v / 3)) for v in (*sorted([tip_a, tip_b])[0], *sorted([tip_a, tip_b])[1]))
            caps[key] = (tip_a, tip_b)
    return list(caps.values())


def detect_walls_and_axes(
    image: np.ndarray,
    dpi: int,
    ignore_bottom_fraction: float = 0.0,
) -> tuple[list[Segment], list[Segment], list[Arc]]:
    """Devuelve (caras de muro, ejes, arcos); segmentos en píxeles.

    `ignore_bottom_fraction` descarta la franja inferior de la imagen (por
    ejemplo el rótulo del plano) para que no se confunda con muros.
    """
    px_per_mm = dpi / _MM_PER_INCH
    segments = _lsd_segments(image, dpi)
    if len(segments) == 0:
        return [], [], []

    if ignore_bottom_fraction > 0:
        limit = image.shape[0] * (1 - ignore_bottom_fraction)
        centres_y = (segments[:, 1] + segments[:, 3]) / 2
        segments = segments[centres_y < limit]

    # las curvas se detectan primero: sus trocitos no deben acabar como rectas
    arcs, arc_used = detect_arcs(segments, dpi)
    segments = segments[~arc_used]

    lengths = np.hypot(segments[:, 2] - segments[:, 0], segments[:, 3] - segments[:, 1])
    segments = segments[lengths >= _AXIS_MIN_PIECE_MM * px_per_mm]

    # LSD devuelve los dos bordes de cada trazo grueso: se funden en una sola
    # línea central antes de buscar pares de caras de muro.
    strokes = merge_collinear_segments(
        _merge_stroke_edges(segments, px_per_mm), dpi=dpi
    )
    if not strokes:
        return [], [], arcs
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
    walls = walls + _end_caps(walls, px_per_mm)

    axis_pieces = [stroke for k, stroke in enumerate(strokes) if k not in paired_ids]
    axes = _axes_from_pieces(axis_pieces, dpi, px_per_mm)

    logger.info(
        "Muros: %d caras (de %d segmentos). Ejes: %d. Arcos: %d.",
        len(walls),
        len(wall_raw),
        len(axes),
        len(arcs),
    )
    return walls, axes, arcs


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
