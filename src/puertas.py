"""Detección de puertas: el arco de giro de la hoja (con la hoja si está dibujada).

Una puerta se dibuja como un cuarto de círculo (la trayectoria de la hoja) con
centro en la bisagra. En un escaneo ese arco es una línea fina, a menudo de
trazos, y los trocitos de curva son demasiado cortos para el detector general
de arcos. Aquí se buscan círculos del tamaño de una puerta con la transformada
de Hough y se aceptan solo los que cumplen tres cosas: hay tinta continua a lo
largo de un tramo de unos 90°, esa tinta está aislada (no hay tinta pegada por
dentro ni por fuera, como pasa en una zona de muros o de texto) y el radio
corresponde a una hoja de puerta según el espesor de muro del plano.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import cv2
import numpy as np

from .arcos import Arc, _fit_circle
from .line_detector import Segment
from .vectorizer import binarize_ink

logger = logging.getLogger("planos2dwg")

_RADIUS_IN_WALL_THICKNESS = (4.0, 11.0)
_SPAN_DEG = (65.0, 115.0)
_MIN_DENSITY = 0.5
_MAX_NEIGHBOUR_INK = 0.12
_MIN_HINGE_INK = 0.12
_LEAF_MIN_COVERAGE = 0.75
_BIN_DEG = 3.0
_MAX_GAP_BINS = 3
_HOUGH_PARAM2 = 25


@dataclass(frozen=True)
class Door:
    """Arco de giro de una puerta y, si está dibujada, su hoja (bisagra -> punta)."""

    arc: Arc
    leaf: Segment | None


def _point(cx: float, cy: float, radius: float, degrees: float) -> tuple[float, float]:
    return cx + radius * math.cos(math.radians(degrees)), cy - radius * math.sin(math.radians(degrees))


def _ink_at(ink: np.ndarray, x: float, y: float) -> bool:
    ix, iy = int(round(x)), int(round(y))
    return 0 <= iy < ink.shape[0] and 0 <= ix < ink.shape[1] and ink[iy, ix] > 0


def _ring_hits(
    ink: np.ndarray, cx: float, cy: float, radii: np.ndarray, angles_deg: np.ndarray
) -> np.ndarray:
    """Matriz (ángulos x radios) de tinta en los puntos de la rejilla polar."""
    rad = np.deg2rad(angles_deg)
    xs = np.rint(cx + radii[None, :] * np.cos(rad)[:, None]).astype(int)
    ys = np.rint(cy - radii[None, :] * np.sin(rad)[:, None]).astype(int)
    inside = (xs >= 0) & (xs < ink.shape[1]) & (ys >= 0) & (ys < ink.shape[0])
    hits = np.zeros(xs.shape, dtype=bool)
    hits[inside] = ink[ys[inside], xs[inside]] > 0
    return hits


def _coverage(ink: np.ndarray, cx: float, cy: float, radius: float, bins: int) -> np.ndarray:
    angles = np.arange(bins) * _BIN_DEG
    return _ring_hits(ink, cx, cy, radius + np.array([-2.0, -1.0, 0.0, 1.0, 2.0]), angles).any(axis=1)


def _ink_around(ink: np.ndarray, cx: float, cy: float, half: int) -> float:
    """Fracción de tinta en un cuadrado de lado 2*half+1 centrado en (cx, cy)."""
    x0, y0 = max(int(cx) - half, 0), max(int(cy) - half, 0)
    window = ink[y0 : int(cy) + half + 1, x0 : int(cx) + half + 1]
    return float((window > 0).mean()) if window.size else 0.0


def _longest_run(covered: np.ndarray) -> tuple[int, int]:
    """Tramo circular continuo más largo, tolerando huecos cortos (trazos)."""
    bins = len(covered)
    doubled = np.concatenate([covered, covered])
    best = (0, -1)
    start = last_true = None
    for index in range(2 * bins):
        if doubled[index]:
            if start is None:
                start = index
            last_true = index
        elif start is not None and index - last_true > _MAX_GAP_BINS:
            if last_true - start + 1 <= bins and last_true - start > best[1] - best[0]:
                best = (start, last_true)
            start = None
    if start is not None and last_true - start + 1 <= bins and last_true - start > best[1] - best[0]:
        best = (start, last_true)
    return best


def _neighbour_ink(
    ink: np.ndarray, cx: float, cy: float, radius: float, angles: list[float], offset: float
) -> float:
    """Fracción de tinta justo por dentro y por fuera del arco (debe ser casi nula)."""
    radii = np.array([radius + sign * (offset + extra) for sign in (-1.0, 1.0) for extra in (-1.0, 0.0, 1.0)])
    hits = _ring_hits(ink, cx, cy, radii, np.array(angles))
    return float(hits.mean()) if hits.size else 0.0


def _leaf_at(ink: np.ndarray, arc: Arc, angle: float) -> bool:
    samples = [
        _ink_at(ink, *_point(arc.cx, arc.cy, arc.radius * fraction, angle))
        or any(
            _ink_at(ink, *_point(arc.cx, arc.cy, arc.radius * fraction, angle + d)) for d in (-2.0, 2.0)
        )
        for fraction in np.linspace(0.15, 0.95, 24)
    ]
    return sum(samples) / len(samples) >= _LEAF_MIN_COVERAGE


def detect_doors(image: np.ndarray, dpi: int, wall_thickness_px: float | None = None) -> list[Door]:
    """Devuelve las puertas encontradas (arco de giro y hoja si se ve)."""
    thickness = wall_thickness_px or (1.0 * dpi / 25.4)
    min_radius = int(_RADIUS_IN_WALL_THICKNESS[0] * thickness)
    max_radius = int(_RADIUS_IN_WALL_THICKNESS[1] * thickness)

    ink = binarize_ink(image, dpi)
    blurred = cv2.GaussianBlur(ink, (0, 0), 1.5 * dpi / 300)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=max(int(0.35 * thickness), 3),
        param1=100,
        param2=_HOUGH_PARAM2,
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if circles is None:
        return []

    bins = int(round(360.0 / _BIN_DEG))
    neighbour_offset = 0.7 * thickness
    radius_limits = (0.9 * min_radius, 1.1 * max_radius)

    def evaluate(cx: float, cy: float, radius: float):
        """Tramo continuo de tinta del círculo si tiene forma de puerta; si no, None."""
        covered = _coverage(ink, cx, cy, radius, bins)
        first, last = _longest_run(covered)
        if last < first:
            return None
        span = (last - first + 1) * _BIN_DEG
        indices = np.arange(first, last + 1) % bins
        density = float(covered[indices].mean())
        if not (_SPAN_DEG[0] <= span <= _SPAN_DEG[1]) or density < _MIN_DENSITY:
            return None
        angles = [float(k) * _BIN_DEG for k in indices]
        if _neighbour_ink(ink, cx, cy, radius, angles, neighbour_offset) > _MAX_NEIGHBOUR_INK:
            return None
        return density, angles

    found: list[tuple[float, Arc]] = []
    hinge_half = max(int(0.6 * thickness), 2)
    for cx, cy, radius in circles[0]:
        # la bisagra está en el muro: su centro cae sobre tinta; un arco de cota, de texto o
        # de mueble tiene el centro en vacío
        if _ink_around(ink, cx, cy, hinge_half) < _MIN_HINGE_INK:
            continue
        circle = (float(cx), float(cy), float(radius))
        refined = None
        # Hough da un círculo aproximado: se reajusta con la tinta que lo respalda hasta que se
        # estabiliza. Sobre una circunferencia completa, un círculo desplazado que la roza parece
        # un arco de 90°; al converger sale la circunferencia entera y deja de cuadrar como puerta.
        for _ in range(5):
            refined = evaluate(*circle)
            if refined is None:
                break
            points = [
                _point(circle[0], circle[1], circle[2] + dr, angle)
                for angle in refined[1]
                for dr in range(-3, 4)
                if _ink_at(ink, *_point(circle[0], circle[1], circle[2] + dr, angle))
            ]
            fitted = _fit_circle(np.array(points)) if len(points) >= 8 else None
            if fitted is None or not (radius_limits[0] <= fitted[2] <= radius_limits[1]):
                refined = None
                break
            moved = math.hypot(fitted[0] - circle[0], fitted[1] - circle[1]) + abs(fitted[2] - circle[2])
            circle = fitted
            if moved < 0.5:
                refined = evaluate(*circle)
                break
        if refined is None or _ink_around(ink, circle[0], circle[1], hinge_half) < _MIN_HINGE_INK:
            continue
        density, angles = refined
        found.append((density, Arc(circle[0], circle[1], circle[2], angles[0], angles[-1])))

    # varios círculos de Hough describen la misma puerta: se queda el de mayor densidad
    doors: list[Door] = []
    taken: list[Arc] = []
    for density, arc in sorted(found, key=lambda item: -item[0]):
        if any(
            math.hypot(arc.cx - other.cx, arc.cy - other.cy) < 1.5 * thickness
            and abs(arc.radius - other.radius) < 1.5 * thickness
            for other in taken
        ):
            continue
        taken.append(arc)
        leaf = None
        for angle in (arc.start_deg, arc.end_deg):
            if _leaf_at(ink, arc, angle):
                tip = _point(arc.cx, arc.cy, arc.radius, angle)
                leaf = ((arc.cx, arc.cy), tip)
                break
        doors.append(Door(arc=arc, leaf=leaf))

    logger.info("Puertas: %d (%d con la hoja dibujada).", len(doors), sum(d.leaf is not None for d in doors))
    return doors
