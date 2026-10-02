"""Detección de ventanas: un hueco en un muro con líneas finas dentro.

Una ventana se dibuja interrumpiendo las dos caras del muro en el mismo tramo
y poniendo en el hueco varias líneas finas (el vidrio y el alféizar). Se
buscan, entre las caras de cada muro, interrupciones alineadas en las dos
caras y se comprueba en la tinta que dentro del hueco haya al menos dos de
las tres líneas (cara, centro, cara).

Limitación honesta: si el plano dibuja las líneas de la ventana sobre las
mismas líneas de las caras, el muro se ve continuo en el escaneo y no hay
hueco que detectar; en esos casos la ventana no se encuentra.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np

from .line_detector import Segment
from .muros import _face_pairs

logger = logging.getLogger("planos2dwg")

_GAP_IN_WALL_THICKNESS = (3.0, 20.0)
_THICKNESS_WINDOW = (0.6, 1.6)
_MIN_FACE_IN_WALL_THICKNESS = 2.5
_PARALLEL_SIN = math.sin(math.radians(2.5))
_LINE_COVERAGE = 0.6
_MIN_LINES = 2
_OVERLAP = 0.7


@dataclass(frozen=True)
class Window:
    """Hueco de ventana: las líneas que lo cruzan (cara, centro, cara) y sus dos jambas."""

    lines: list[Segment]


def _unit(segment: Segment) -> tuple[float, float]:
    (x1, y1), (x2, y2) = segment
    length = math.hypot(x2 - x1, y2 - y1)
    return (x2 - x1) / length, (y2 - y1) / length


def _interval(segment: Segment, u: tuple[float, float], origin: tuple[float, float]) -> tuple[float, float]:
    a = (segment[0][0] - origin[0]) * u[0] + (segment[0][1] - origin[1]) * u[1]
    b = (segment[1][0] - origin[0]) * u[0] + (segment[1][1] - origin[1]) * u[1]
    return min(a, b), max(a, b)


def _gaps(
    faces: list[Segment],
    index: int,
    u: tuple[float, float],
    origin: tuple[float, float],
    skip: int,
    thickness: float,
) -> list[tuple[float, float]]:
    """Huecos entre la cara `index` y otros tramos de su misma recta."""
    normal = (-u[1], u[0])
    a0, a1 = _interval(faces[index], u, origin)
    low_gap, high_gap = (thickness * g for g in _GAP_IN_WALL_THICKNESS)
    found = []
    for k, other in enumerate(faces):
        if k in (index, skip):
            continue
        uk = _unit(other)
        if abs(u[0] * uk[1] - u[1] * uk[0]) > _PARALLEL_SIN:
            continue
        perpendicular = abs((other[0][0] - origin[0]) * normal[0] + (other[0][1] - origin[1]) * normal[1])
        if perpendicular > 3.0:
            continue
        b0, b1 = _interval(other, u, origin)
        for lo, hi in ((a1, b0), (b1, a0)):
            if low_gap <= hi - lo <= high_gap:
                found.append((lo, hi))
    return found


def _line_coverage(ink: np.ndarray, start: tuple[float, float], end: tuple[float, float]) -> float:
    xs = np.linspace(start[0], end[0], 40)
    ys = np.linspace(start[1], end[1], 40)
    hits = 0
    for x, y in zip(xs, ys):
        ix, iy = int(round(x)), int(round(y))
        window = ink[max(iy - 1, 0) : iy + 2, max(ix - 1, 0) : ix + 2]
        hits += bool(window.size and (window > 0).any())
    return hits / len(xs)


def detect_windows(
    walls: list[Segment], ink: np.ndarray, dpi: int, wall_thickness_px: float
) -> list[Window]:
    """Devuelve las ventanas: huecos alineados en las dos caras de un muro con líneas dentro."""
    thickness = wall_thickness_px
    faces = [w for w in walls if math.dist(*w) >= _MIN_FACE_IN_WALL_THICKNESS * thickness]
    if len(faces) < 3:
        return []
    array = np.array([[a[0], a[1], b[0], b[1]] for a, b in faces], dtype=np.float64)
    px_per_mm = dpi / 25.4
    pairs = [
        (i, j, gap)
        for i, j, gap in _face_pairs(array, px_per_mm)
        if _THICKNESS_WINDOW[0] * thickness <= gap <= _THICKNESS_WINDOW[1] * thickness
    ]

    windows: list[Window] = []
    seen: set[tuple[int, int, int, int]] = set()
    for i, j, gap in pairs:
        u = _unit(faces[i])
        origin = faces[i][0]
        normal = (-u[1], u[0])
        side = (faces[j][0][0] - origin[0]) * normal[0] + (faces[j][0][1] - origin[1]) * normal[1]
        offset = math.copysign(gap, side if side else 1.0)
        for lo1, hi1 in _gaps(faces, i, u, origin, j, thickness):
            for lo2, hi2 in _gaps(faces, j, u, origin, i, thickness):
                lo, hi = max(lo1, lo2), min(hi1, hi2)
                if hi - lo < _OVERLAP * min(hi1 - lo1, hi2 - lo2) or hi - lo < _GAP_IN_WALL_THICKNESS[0] * thickness:
                    continue
                lines: list[Segment] = []
                coverage = []
                for fraction in (0.0, 0.5, 1.0):
                    start = (origin[0] + u[0] * lo + normal[0] * offset * fraction, origin[1] + u[1] * lo + normal[1] * offset * fraction)
                    end = (origin[0] + u[0] * hi + normal[0] * offset * fraction, origin[1] + u[1] * hi + normal[1] * offset * fraction)
                    lines.append((start, end))
                    inner_start = (start[0] + u[0] * 0.1 * thickness, start[1] + u[1] * 0.1 * thickness)
                    inner_end = (end[0] - u[0] * 0.1 * thickness, end[1] - u[1] * 0.1 * thickness)
                    coverage.append(_line_coverage(ink, inner_start, inner_end))
                if sum(c >= _LINE_COVERAGE for c in coverage) < _MIN_LINES:
                    continue
                key = tuple(int(round(v / 6)) for v in (*lines[0][0], *lines[-1][1]))
                if key in seen:
                    continue
                seen.add(key)
                # jambas: líneas que cierran el hueco de una cara a la otra
                jamb_a = (lines[0][0], lines[-1][0])
                jamb_b = (lines[0][1], lines[-1][1])
                windows.append(Window(lines=lines + [jamb_a, jamb_b]))

    logger.info("Ventanas: %d.", len(windows))
    return windows
