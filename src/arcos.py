"""Detección de arcos y círculos a partir de los trocitos de línea de LSD.

Una curva escaneada se descompone en muchos segmentos cortos, todos
tangentes a una misma circunferencia. Con RANSAC se buscan circunferencias
que tengan muchos segmentos tangentes, se refinan por mínimos cuadrados y
se recorta cada una al tramo realmente dibujado. Así un muro curvo o la
puerta batiente salen como un único ARC en vez de decenas de rectas.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger("planos2dwg")

_MM_PER_INCH = 25.4

_MIN_CHORD_MM = 1.5
_MAX_CHORD_MM = 12.0
_MIN_RADIUS_MM = 3.0
_MAX_RADIUS_MM = 250.0
_RADIAL_TOL_MM = 0.30
_TANGENT_TOL_DEG = 8.0
_MIN_TOTAL_LENGTH_MM = 25.0
_MIN_SPAN_DEG = 15.0
_SPLIT_GAP_DEG = 20.0
_MIN_ARC_LENGTH_MM = 6.0
_MIN_COVERAGE = 0.45
_BIG_RADIUS_MM = 68.0
_BIG_RADIUS_MIN_SPAN_DEG = 35.0
_MEDIUM_RADIUS_MM = 25.0
_MEDIUM_RADIUS_MIN_SPAN_DEG = 25.0
_MERGE_CENTRE_MM = 0.7
_MERGE_RADIUS_MM = 0.5
_ITERATIONS = 1500
_MAX_MISSES = 1
_MAX_ARCS = 60


@dataclass
class Arc:
    """Arco en píxeles de imagen; ángulos en grados, antihorarios, con Y hacia arriba."""

    cx: float
    cy: float
    radius: float
    start_deg: float
    end_deg: float

    @property
    def is_circle(self) -> bool:
        return abs((self.end_deg - self.start_deg) % 360) < 1e-6


def _fit_circle(points: np.ndarray) -> tuple[float, float, float] | None:
    """Ajuste algebraico (Kåsa) de una circunferencia a (n, 2) puntos."""
    if len(points) < 3:
        return None
    design = np.column_stack([points[:, 0], points[:, 1], np.ones(len(points))])
    target = points[:, 0] ** 2 + points[:, 1] ** 2
    solution, *_ = np.linalg.lstsq(design, target, rcond=None)
    cx, cy = solution[0] / 2, solution[1] / 2
    squared = solution[2] + cx**2 + cy**2
    if squared <= 0:
        return None
    return float(cx), float(cy), float(math.sqrt(squared))


def _angle_y_up(x: np.ndarray, y: np.ndarray, cx: float, cy: float) -> np.ndarray:
    return np.degrees(np.arctan2(-(y - cy), x - cx)) % 360.0


def detect_arcs(segments: np.ndarray, dpi: int) -> tuple[list[Arc], np.ndarray]:
    """Devuelve (arcos, máscara de segmentos usados) para `segments` (n, 4)."""
    count = len(segments)
    used = np.zeros(count, dtype=bool)
    if count < 6:
        return [], used

    px_per_mm = dpi / _MM_PER_INCH
    dx = segments[:, 2] - segments[:, 0]
    dy = segments[:, 3] - segments[:, 1]
    length = np.hypot(dx, dy)
    pool = (length >= _MIN_CHORD_MM * px_per_mm) & (length <= _MAX_CHORD_MM * px_per_mm)
    if pool.sum() < 6:
        return [], used

    ux = np.where(length > 0, dx / np.maximum(length, 1e-9), 0.0)
    uy = np.where(length > 0, dy / np.maximum(length, 1e-9), 0.0)
    mid_x = (segments[:, 0] + segments[:, 2]) / 2
    mid_y = (segments[:, 1] + segments[:, 3]) / 2
    tolerance = _RADIAL_TOL_MM * px_per_mm
    tangent_cos = math.cos(math.radians(_TANGENT_TOL_DEG))
    min_total = _MIN_TOTAL_LENGTH_MM * px_per_mm
    r_min, r_max = _MIN_RADIUS_MM * px_per_mm, _MAX_RADIUS_MM * px_per_mm
    rng = np.random.default_rng(12345)

    def inliers_of(cx: float, cy: float, radius: float, candidates: np.ndarray) -> np.ndarray:
        distance = np.hypot(mid_x - cx, mid_y - cy)
        safe = np.maximum(distance, 1e-9)
        tangent = np.abs(ux * (-(mid_y - cy) / safe) + uy * ((mid_x - cx) / safe))
        end_a = np.hypot(segments[:, 0] - cx, segments[:, 1] - cy)
        end_b = np.hypot(segments[:, 2] - cx, segments[:, 3] - cy)
        # los extremos de cada trocito están sobre la curva; su punto medio no
        # (queda dentro por la flecha de la cuerda), por eso solo se miran los extremos
        return (
            candidates
            & (tangent >= tangent_cos)
            & (np.abs(end_a - radius) <= tolerance * 1.5)
            & (np.abs(end_b - radius) <= tolerance * 1.5)
        )

    raw_arcs: list[Arc] = []
    available = pool.copy()
    misses = 0
    for _ in range(2 * _MAX_ARCS):
        if len(raw_arcs) >= _MAX_ARCS:
            break
        ids = np.nonzero(available)[0]
        if len(ids) < 6:
            break
        best_score, best_circle = 0.0, None
        local_mid = np.column_stack([mid_x[ids], mid_y[ids]])
        for _iteration in range(_ITERATIONS):
            first = int(rng.integers(len(ids)))
            near = np.hypot(local_mid[:, 0] - local_mid[first, 0], local_mid[:, 1] - local_mid[first, 1])
            neighbours = np.nonzero((near > 4) & (near < 30 * px_per_mm))[0]
            if len(neighbours) == 0:
                continue
            second = int(rng.choice(neighbours))
            i, j = ids[first], ids[second]
            n_i, n_j = (-uy[i], ux[i]), (-uy[j], ux[j])
            det = -n_i[0] * n_j[1] + n_j[0] * n_i[1]
            if abs(det) < 0.05:
                continue
            rhs_x, rhs_y = mid_x[j] - mid_x[i], mid_y[j] - mid_y[i]
            s = (-rhs_x * n_j[1] + n_j[0] * rhs_y) / det
            u = (n_i[0] * rhs_y - n_i[1] * rhs_x) / det
            if not (r_min <= abs(s) <= r_max) or abs(abs(u) - abs(s)) > 0.1 * abs(s) + 2 * tolerance:
                continue
            cx, cy = mid_x[i] + s * n_i[0], mid_y[i] + s * n_i[1]
            ends = np.hypot(
                np.array([segments[i, 0], segments[i, 2], segments[j, 0], segments[j, 2]]) - cx,
                np.array([segments[i, 1], segments[i, 3], segments[j, 1], segments[j, 3]]) - cy,
            )
            radius = float(ends.mean())
            if ends.max() - ends.min() > 2 * tolerance:
                continue
            mask = inliers_of(cx, cy, radius, available)
            score = float(length[mask].sum())
            if score > best_score:
                best_score, best_circle = score, (cx, cy, radius)
        if best_circle is None or best_score < min_total:
            # un mal sorteo no debe cortar la búsqueda: se acepta que fallen varios
            # intentos seguidos antes de dar por terminados los arcos
            misses += 1
            if misses >= _MAX_MISSES:
                break
            continue
        misses = 0

        mask = inliers_of(*best_circle, available)
        points = np.vstack([segments[mask][:, [0, 1]], segments[mask][:, [2, 3]]])
        fitted = _fit_circle(points)
        if fitted is not None and r_min <= fitted[2] <= r_max:
            best_circle = fitted
            mask = inliers_of(*best_circle, available)
        if float(length[mask].sum()) < min_total:
            available[np.nonzero(mask)[0]] = False
            continue

        arcs_before = len(raw_arcs)
        cx, cy, radius = best_circle
        angles = np.sort(
            np.concatenate(
                [
                    _angle_y_up(segments[mask][:, 0], segments[mask][:, 1], cx, cy),
                    _angle_y_up(segments[mask][:, 2], segments[mask][:, 3], cx, cy),
                ]
            )
        )
        gaps = np.diff(np.concatenate([angles, [angles[0] + 360.0]]))
        breaks = np.nonzero(gaps > _SPLIT_GAP_DEG)[0]
        mid_angle = _angle_y_up(mid_x[mask], mid_y[mask], cx, cy)
        mask_length = length[mask]
        if len(breaks) == 0:
            if mask_length.sum() / (2 * math.pi * radius) >= _MIN_COVERAGE:
                raw_arcs.append(Arc(cx, cy, radius, 0.0, 360.0))
        else:
            for position, brk in enumerate(breaks):
                start = angles[(brk + 1) % len(angles)]
                end = angles[breaks[(position + 1) % len(breaks)]]
                span = (end - start) % 360.0
                arc_length = math.radians(span) * radius
                if span < _MIN_SPAN_DEG or arc_length < _MIN_ARC_LENGTH_MM * px_per_mm:
                    continue
                if not _plausible(radius, span, px_per_mm):
                    continue
                inside = ((mid_angle - start) % 360.0) <= span
                # un arco real está cubierto por trocitos a lo largo de toda su
                # longitud; una recta casi plana tomada por curva apenas tiene apoyo
                if mask_length[inside].sum() / arc_length >= _MIN_COVERAGE:
                    raw_arcs.append(Arc(cx, cy, radius, float(start), float(end)))

        # solo los segmentos de un arco ACEPTADO dejan de ser candidatos a muro: un
        # candidato descartado (recta casi plana) no debe quitarle paredes al plano
        if len(raw_arcs) > arcs_before:
            used |= mask
        available &= ~mask

    arcs = _merge_concentric(raw_arcs, px_per_mm)
    logger.info("Arcos: %d (de %d candidatos, %d segmentos usados).", len(arcs), len(raw_arcs), int(used.sum()))
    return arcs, used


def _plausible(radius_px: float, span_deg: float, px_per_mm: float) -> bool:
    """Un radio grande con un tramo corto es casi una recta, no una curva.

    Las rectas largas (ejes, cotas) caben en una circunferencia enorme con
    muy poca curvatura; las curvas reales de radio grande abarcan un tramo
    amplio. Se exige más tramo cuanto mayor es el radio.
    """
    if radius_px > _BIG_RADIUS_MM * px_per_mm:
        return span_deg >= _BIG_RADIUS_MIN_SPAN_DEG
    if radius_px > _MEDIUM_RADIUS_MM * px_per_mm:
        return span_deg >= _MEDIUM_RADIUS_MIN_SPAN_DEG
    return True


def _merge_concentric(arcs: list[Arc], px_per_mm: float) -> list[Arc]:
    """Une arcos casi idénticos (mismo centro y radio) en uno solo."""
    centre_tol = _MERGE_CENTRE_MM * px_per_mm
    radius_tol = _MERGE_RADIUS_MM * px_per_mm
    merged: list[Arc] = []
    for arc in arcs:
        for index, other in enumerate(merged):
            if (
                math.hypot(arc.cx - other.cx, arc.cy - other.cy) <= centre_tol
                and abs(arc.radius - other.radius) <= radius_tol
                and _spans_overlap(arc, other)
            ):
                merged[index] = Arc(
                    (arc.cx + other.cx) / 2,
                    (arc.cy + other.cy) / 2,
                    (arc.radius + other.radius) / 2,
                    _span_union(arc, other)[0],
                    _span_union(arc, other)[1],
                )
                break
        else:
            merged.append(arc)
    return merged


def _spans(arc: Arc) -> list[tuple[float, float]]:
    start, end = arc.start_deg % 360.0, arc.end_deg % 360.0
    if arc.is_circle:
        return [(0.0, 360.0)]
    return [(start, end)] if start <= end else [(start, 360.0), (0.0, end)]


def _spans_overlap(a: Arc, b: Arc) -> bool:
    return any(s1 <= e2 and s2 <= e1 for s1, e1 in _spans(a) for s2, e2 in _spans(b))


def _span_union(a: Arc, b: Arc) -> tuple[float, float]:
    if a.is_circle or b.is_circle:
        return 0.0, 360.0
    start_a, end_a = a.start_deg % 360.0, a.end_deg % 360.0
    start_b, end_b = b.start_deg % 360.0, b.end_deg % 360.0
    span_a, span_b = (end_a - start_a) % 360.0, (end_b - start_b) % 360.0
    candidates = [(start_a, (start_a + span_a) % 360.0), (start_b, (start_b + span_b) % 360.0)]
    # el origen de la unión es el inicio que deja al otro arco por delante
    offset_b = (start_b - start_a) % 360.0
    if offset_b <= span_a:
        total = max(span_a, offset_b + span_b)
        return start_a, (start_a + min(total, 360.0)) % 360.0
    offset_a = (start_a - start_b) % 360.0
    if offset_a <= span_b:
        total = max(span_b, offset_a + span_a)
        return start_b, (start_b + min(total, 360.0)) % 360.0
    return candidates[0]
