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


_RAY_STEP_DEG = 0.5
_RAY_PROBE_PX = 260  # tramo, desde la burbuja, donde se busca la línea de trazo y punto
_RAY_MIN_SHARE = 0.30
_RAY_MIN_LENGTH_PX = 300
_CENTRE_PROBE_MIN_SHARE = 0.12  # hacia el centro basta menos tinta: los arcos y textos tapan buena parte de la línea
_RAY_MAX_CENTER_MISS_PX = 60  # los ejes radiales pasan por un mismo punto: el centro de la parte circular


def _ray_points(bubble: Bubble, angle: np.ndarray, distance: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return bubble.x + np.cos(angle)[:, None] * distance[None, :], bubble.y + np.sin(angle)[:, None] * distance[None, :]


def _trace_ray(ink: np.ndarray, bubble: Bubble, angle: float) -> float:
    """Hasta dónde llega, desde el borde de la burbuja, la línea de trazo y punto que sale en `angle`."""
    h, w = ink.shape
    end = bubble.r
    for distance in np.arange(bubble.r + 3, 4000, _TRACE_STEP_PX):
        window = np.arange(distance, distance + _TRACE_WINDOW_PX, 2.0)
        xs, ys = bubble.x + math.cos(angle) * window, bubble.y + math.sin(angle) * window
        if not ((xs > 1) & (xs < w - 2) & (ys > 1) & (ys < h - 2)).all() or _ink_share(ink, xs, ys) < _TRACE_MIN_SHARE:
            break
        end = distance + _TRACE_WINDOW_PX / 2
    return end


_ALIGNED_DEG = 3.0  # un eje así de cerca de horizontal o vertical es de la cuadrícula, no radial


def _is_aligned(angle: float) -> bool:
    degrees = math.degrees(angle) % 90
    return min(degrees, 90 - degrees) <= _ALIGNED_DEG


def radial_axes(loose: list[Bubble], ink: np.ndarray) -> tuple[list[Bubble], list[Segment], list[Bubble]]:
    """Confirma las burbujas sueltas por la línea de trazo y punto que sale de ellas.

    Devuelve (burbujas de ejes radiales, sus ejes, burbujas de la cuadrícula). Un círculo del que no sale un eje largo
    no es una burbuja (es un inodoro, una mesa...) y se descarta. Los ejes radiales se llevan hasta el punto donde
    todos se cruzan (el centro de la parte circular). Una burbuja con eje horizontal o vertical es de la cuadrícula
    (las de abajo): su eje ya existe, solo falta dibujar su círculo.
    """
    angles = np.deg2rad(np.arange(0.0, 360.0, _RAY_STEP_DEG))
    radial: list[tuple[Bubble, float, float]] = []  # (burbuja, ángulo, largo)
    aligned: list[Bubble] = []
    for bubble in loose:
        distance = np.arange(bubble.r + 4, bubble.r + 4 + _RAY_PROBE_PX, 2.0)
        xs, ys = _ray_points(bubble, angles, distance)
        shares = np.array([_ink_share(ink, xs[k], ys[k]) for k in range(len(angles))])
        best = int(np.argmax(shares))
        if shares[best] < _RAY_MIN_SHARE:
            continue
        # el ángulo exacto: el del grupo de ángulos casi tan buenos que queda más cerca del mejor
        good = np.nonzero(shares >= shares[best] - 0.05)[0]
        angle = float(angles[good[np.argmin(np.abs(good - best))]])
        length = _trace_ray(ink, bubble, angle)
        if length < _RAY_MIN_LENGTH_PX:
            continue
        if _is_aligned(angle):
            aligned.append(Bubble(bubble.x, bubble.y, bubble.r, "vertical" if abs(math.sin(angle)) > 0.7 else "horizontal", bubble.ring))
        else:
            radial.append((bubble, angle, length))
    if len(radial) < 2:
        return [], [], aligned
    # el centro común, ignorando las rectas que no pasan por él (una burbuja puede "ver" la línea de un arco, no la suya)
    inliers = list(radial)
    while True:
        centre = _common_point([(b.x, b.y, a) for b, a, _ in inliers])
        misses = [abs((centre[0] - b.x) * -math.sin(a) + (centre[1] - b.y) * math.cos(a)) for b, a, _ in inliers]
        worst = int(np.argmax(misses))
        if misses[worst] <= _RAY_MAX_CENTER_MISS_PX or len(inliers) <= 2:
            break
        inliers.pop(worst)
    confirmed: list[Bubble] = []
    segments: list[Segment] = []
    for bubble, angle, length in radial:
        miss = abs((centre[0] - bubble.x) * -math.sin(angle) + (centre[1] - bubble.y) * math.cos(angle))
        if miss > _RAY_MAX_CENTER_MISS_PX:
            # su línea propia no apunta al centro: se prueba directamente hacia el centro
            angle = math.atan2(centre[1] - bubble.y, centre[0] - bubble.x)
            distance = np.arange(bubble.r + 4, min(bubble.r + 4 + _RAY_PROBE_PX, math.hypot(centre[0] - bubble.x, centre[1] - bubble.y)), 2.0)
            xs, ys = bubble.x + math.cos(angle) * distance, bubble.y + math.sin(angle) * distance
            if len(distance) < 5 or _ink_share(ink, xs, ys) < _CENTRE_PROBE_MIN_SHARE:
                continue
        start = (bubble.x + math.cos(angle) * (bubble.r + 1), bubble.y + math.sin(angle) * (bubble.r + 1))
        towards = (centre[0] - bubble.x) * math.cos(angle) + (centre[1] - bubble.y) * math.sin(angle) > 0
        end = centre if towards else (bubble.x + math.cos(angle) * length, bubble.y + math.sin(angle) * length)
        confirmed.append(bubble)
        segments.append((start, end))
    logger.info("Ejes radiales: %d burbujas sueltas, %d radiales, %d de la cuadrícula; centro (%d, %d).", len(loose), len(confirmed), len(aligned), *centre)
    return confirmed, segments, aligned


def _common_point(rays: list[tuple[float, float, float]]) -> tuple[float, float]:
    """Punto más cercano a todas las rectas (x, y, ángulo): donde se cruzan los ejes radiales (mínimos cuadrados)."""
    a = np.zeros((2, 2))
    b = np.zeros(2)
    for x, y, angle in rays:
        n = np.array([-math.sin(angle), math.cos(angle)])  # normal a la recta
        a += np.outer(n, n)
        b += np.outer(n, n) @ np.array([x, y])
    solution = np.linalg.solve(a + 1e-9 * np.eye(2), b)
    return float(solution[0]), float(solution[1])


_ROW_PX = 40  # burbujas con casi la misma y (o x) forman una fila (o columna)


def _is_axis_aligned(segment: Segment) -> bool:
    (x1, y1), (x2, y2) = segment
    return min(abs(x2 - x1), abs(y2 - y1)) <= 0.05 * max(abs(x2 - x1), abs(y2 - y1), 1e-9)


def _rows(bubbles: list[Bubble], direction: str) -> list[float]:
    """Posición (y para los ejes verticales, x para los horizontales) de cada fila o columna con 2 o más burbujas."""
    key = (lambda b: b.y) if direction == "vertical" else (lambda b: b.x)
    values = sorted(key(b) for b in bubbles if b.direction == direction)
    groups: list[list[float]] = []
    for v in values:
        if groups and v - groups[-1][0] <= _ROW_PX:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [float(np.median(g)) for g in groups if len(g) >= 2]


def complete_bubbles(axes: list[Segment], bubbles: list[Bubble], radius: float) -> tuple[list[Segment], list[Bubble]]:
    """Pone el círculo que le falta a un eje que llega a la fila (o columna) de burbujas y no tiene la suya.

    Hay burbujas de aro tan borroso que no se detectan, pero su eje sí. Si el eje termina junto a la fila de burbujas
    de sus compañeras, se dibuja su círculo alineado con ellas y se recorta el eje hasta el borde del círculo.
    """
    result = list(axes)
    added: list[Bubble] = []
    band = _KEEP_BAND_RADII * radius + 8
    for direction in ("vertical", "horizontal"):
        vertical = direction == "vertical"
        for row in _rows(bubbles, direction):
            for index, segment in enumerate(result):
                if not _is_axis_aligned(segment) or _is_horizontal(segment) == vertical:
                    continue  # un eje vertical se completa con la fila de arriba o de abajo; uno horizontal, con la columna
                coordinate = _coordinate(segment)
                ends = sorted(segment, key=lambda p: abs((p[1] if vertical else p[0]) - row))
                near = ends[0]
                if abs((near[1] if vertical else near[0]) - row) > band:
                    continue
                if any(abs((b.x if vertical else b.y) - coordinate) <= 1.8 * radius and abs((b.y if vertical else b.x) - row) <= band
                       for b in bubbles + added if b.direction == direction):
                    continue  # ese eje ya tiene su burbuja
                centre = Bubble(coordinate, row, radius, direction) if vertical else Bubble(row, coordinate, radius, direction)
                added.append(centre)
                far = ends[1]
                inward = 1.0 if (far[1] if vertical else far[0]) > row else -1.0
                trimmed = (coordinate, row + inward * (radius + 1)) if vertical else (row + inward * (radius + 1), coordinate)
                result[index] = (trimmed, far)
    if added:
        logger.info("Burbujas que faltaban en su fila o columna: %d.", len(added))
    return result, added
