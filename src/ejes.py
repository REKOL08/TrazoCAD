"""Ejes de la cuadrícula validados con sus burbujas.

El trazado de líneas encuentra "ejes" de más (cotas largas, líneas dentro de los cuartos, la línea de corte A-A')
y se salta alguno. Con las burbujas de los ejes (src/burbujas.py) se arregla: cada burbuja tiene su eje, recto y
saliendo de su círculo; las líneas largas que no llevan burbuja se descartan.
"""

from __future__ import annotations

import logging
import math

import numpy as np

from .burbujas import Bubble
from .line_detector import Segment

logger = logging.getLogger("planos2dwg")

_MATCH_PX = 16  # un eje detectado a esta distancia de la burbuja es el de esa burbuja
_SNAP_PX = 14  # cuánto se corrige la posición de la línea mirando la tinta
_SNAP_REACH_RADII = 6.0  # tramo de línea, desde la burbuja, donde se mide la tinta para centrarla
_TRACE_STEP_PX = 4
_TRACE_WINDOW_PX = 160  # un eje de trazo y punto tiene ~50% de tinta: se mira en ventanas de este largo
_TRACE_MIN_SHARE = 0.18
_MIN_TRACE_PX = 200
_KEEP_BAND_RADII = 3.5  # un eje sin burbuja se conserva si termina dentro de esta franja de la fila o columna de burbujas


def _is_horizontal(segment: Segment) -> bool:
    (x1, y1), (x2, y2) = segment
    return abs(x2 - x1) >= abs(y2 - y1)


def _coordinate(segment: Segment) -> float:
    """Posición de la recta: su y si es horizontal, su x si es vertical."""
    (x1, y1), (x2, y2) = segment
    return (y1 + y2) / 2 if _is_horizontal(segment) else (x1 + x2) / 2


def _same_line(a: Segment, b: Segment, tolerance: float) -> bool:
    return _is_horizontal(a) == _is_horizontal(b) and abs(_coordinate(a) - _coordinate(b)) <= tolerance


def _ink_share(ink: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> float:
    h, w = ink.shape
    xi, yi = np.clip(np.round(xs).astype(int), 1, w - 2), np.clip(np.round(ys).astype(int), 1, h - 2)
    hit = ink[yi, xi] | ink[yi - 1, xi] | ink[yi + 1, xi] | ink[yi, xi - 1] | ink[yi, xi + 1]
    return float(hit.mean())


def _sign(bubble: Bubble, box: tuple[float, float, float, float]) -> float:
    """Hacia dónde sale el eje de la burbuja: hacia el centro del contenido del plano."""
    centre = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    if bubble.direction == "horizontal":
        return 1.0 if bubble.x < centre[0] else -1.0
    return 1.0 if bubble.y < centre[1] else -1.0


def _line_point(bubble: Bubble, offset: float, along: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Puntos de la recta del eje: `along` es la distancia desde el centro de la burbuja (con signo)."""
    if bubble.direction == "horizontal":
        return bubble.x + along, np.full_like(along, bubble.y + offset)
    return np.full_like(along, bubble.x + offset), bubble.y + along


def _centred_offset(ink: np.ndarray, bubble: Bubble, sign: float) -> float:
    """Corrimiento lateral que mejor centra la línea del eje sobre la tinta, cerca de la burbuja."""
    along = sign * np.arange(bubble.r + 3, bubble.r * _SNAP_REACH_RADII, 2.0)
    best, best_share = 0.0, -1.0
    for offset in range(-_SNAP_PX, _SNAP_PX + 1):
        xs, ys = _line_point(bubble, float(offset), along)
        share = _ink_share(ink, xs, ys) - 0.002 * abs(offset)  # a igual tinta, la más cercana a la burbuja
        if share > best_share:
            best, best_share = float(offset), share
    return best


def _trace_end(ink: np.ndarray, bubble: Bubble, offset: float, sign: float) -> float:
    """Distancia (con signo) desde la burbuja hasta donde termina la línea de trazo y punto."""
    limit = ink.shape[1] if bubble.direction == "horizontal" else ink.shape[0]
    steps = np.arange(bubble.r + 3, limit, _TRACE_STEP_PX)
    end = bubble.r
    for distance in steps:
        window = sign * np.arange(distance, distance + _TRACE_WINDOW_PX, 2.0)
        xs, ys = _line_point(bubble, offset, window)
        inside = (xs > 1) & (xs < ink.shape[1] - 2) & (ys > 1) & (ys < ink.shape[0] - 2)
        if not inside.all() or _ink_share(ink, xs, ys) < _TRACE_MIN_SHARE:
            break
        end = distance + _TRACE_WINDOW_PX / 2
    return sign * end


def _unmatched_in_band(
    axes: list[Segment], used: set[int], bubbles: list[Bubble]
) -> list[Segment]:
    """Ejes detectados sin burbuja encontrada que terminan en la franja de una fila o columna de burbujas.

    Hay burbujas con el aro tan tenue que no se detectan; su eje existe y termina junto a las demás. Un eje que
    no llega a esa franja (una cota larga, una línea dentro de un cuarto) sigue descartado.
    """
    kept: list[Segment] = []
    for direction in ("horizontal", "vertical"):
        row = [b for b in bubbles if b.direction == direction]
        if len(row) < 2:
            continue
        horizontal = direction == "horizontal"
        line = float(np.median([b.x if horizontal else b.y for b in row]))
        band = _KEEP_BAND_RADII * float(np.median([b.r for b in row])) + 8
        for i, segment in enumerate(axes):
            if i in used or _is_horizontal(segment) != horizontal:
                continue
            ends = [p[0] if horizontal else p[1] for p in segment]
            if min(abs(e - line) for e in ends) > band:
                continue
            # los demás trozos sin burbuja de la misma recta (el trazado a veces parte un eje en dos) se unen a este
            pieces = [axes[k] for k in range(len(axes)) if k not in used and _same_line(axes[k], segment, 6)]
            values = [p[0] if horizontal else p[1] for piece in pieces for p in piece]
            coordinate = _coordinate(segment)
            low, high = min(values), max(values)
            kept.append(((low, coordinate), (high, coordinate)) if horizontal else ((coordinate, low), (coordinate, high)))
    unique: list[Segment] = []
    for segment in kept:
        if not any(_same_line(segment, other, 6) for other in unique):
            unique.append(segment)
    return unique


def refine_axes(
    axes: list[Segment],
    bubbles: list[Bubble],
    ink: np.ndarray,
    content_box: tuple[float, float, float, float],
) -> list[Segment]:
    """Un eje recto por burbuja; los ejes detectados sin burbuja se descartan (salvo en la franja de burbujas)."""
    if len(bubbles) < 3:
        return axes
    result: list[Segment] = []
    used: set[int] = set()
    for bubble in bubbles:
        sign = _sign(bubble, content_box)
        offset = _centred_offset(ink, bubble, sign)
        horizontal = bubble.direction == "horizontal"
        target = bubble.y + offset if horizontal else bubble.x + offset
        # el eje detectado más cercano a esa línea: sirve para saber hasta dónde llega
        candidates = [
            (abs(_coordinate(segment) - target), i)
            for i, segment in enumerate(axes)
            if _is_horizontal(segment) == horizontal and abs(_coordinate(segment) - target) < _MATCH_PX
        ]
        if candidates:
            _, i = min(candidates)
            used.add(i)
            far = max(axes[i], key=lambda p: sign * (p[0] if horizontal else p[1]))
            extent = (far[0] - bubble.x) if horizontal else (far[1] - bubble.y)
        else:
            extent = _trace_end(ink, bubble, offset, sign)
        if abs(extent) < _MIN_TRACE_PX:
            continue
        xs, ys = _line_point(bubble, offset, np.array([sign * (bubble.r + 1), sign * abs(extent)]))
        result.append(((float(xs[0]), float(ys[0])), (float(xs[1]), float(ys[1]))))
    # un eje sin burbuja que cae sobre uno con burbuja (a menos de 24 px) es el mismo: se descarta
    extra = [seg for seg in _unmatched_in_band(axes, used, bubbles) if not any(_same_line(seg, r, 24) for r in result)]
    logger.info("Ejes: %d con burbuja y %d alineados con ellas (de %d detectados; el resto se descarta).", len(result), len(extra), len(axes))
    return result + extra
