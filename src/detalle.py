"""Líneas de detalle limpias: lo que no es muro, eje, arco, puerta ni texto.

El calco de la tinta hereda cada irregularidad del escaneo (se ve "tembloroso").
Aquí lo que queda del dibujo —cotas, contornos de muebles, rayados— se rehace como
líneas rectas de un solo trazo: se funden los dos bordes de cada trazo en una línea
central, se unen los tramos colineales, se enderezan a horizontal/vertical y se
descartan las que ya están representadas por muros, ejes, arcos, puertas, ventanas,
sanitarios o textos.
"""

from __future__ import annotations

import logging
import math

import numpy as np

from .line_detector import Segment, merge_collinear_segments
from .muros import _lsd_segments, _merge_stroke_edges, _snap_axis_aligned
from .texto import TextItem

logger = logging.getLogger("planos2dwg")

_MM_PER_INCH = 25.4
_MIN_LENGTH_MM = 2.2
_EXPLAINED_TOL_MM = 0.45
_SHARE_EXPLAINED = 0.80


def _distance_to_segments(points: np.ndarray, starts: np.ndarray, ends: np.ndarray) -> np.ndarray:
    """Distancia mínima de cada punto a cualquiera de los segmentos."""
    along = ends - starts
    squared = np.maximum((along**2).sum(axis=1), 1e-9)
    t = np.clip(((points[:, None, :] - starts[None]) * along[None]).sum(axis=2) / squared, 0.0, 1.0)
    nearest = starts[None] + t[..., None] * along[None]
    return np.hypot(*(points[:, None, :] - nearest).transpose(2, 0, 1)).min(axis=1)


def detect_detail_lines(
    image: np.ndarray,
    dpi: int,
    explained: list[Segment],
    texts: list[TextItem],
    ignore_bottom_fraction: float = 0.0,
) -> list[Segment]:
    """Devuelve las líneas de detalle rectas que no están ya dibujadas en otra capa."""
    px_per_mm = dpi / _MM_PER_INCH
    segments = _lsd_segments(image, dpi)
    if len(segments) == 0:
        return []
    if ignore_bottom_fraction > 0:
        limit = image.shape[0] * (1 - ignore_bottom_fraction)
        segments = segments[(segments[:, 1] + segments[:, 3]) / 2 < limit]

    length = np.hypot(segments[:, 2] - segments[:, 0], segments[:, 3] - segments[:, 1])
    segments = segments[length >= 0.6 * px_per_mm]
    fused, _widths = _merge_stroke_edges(segments, px_per_mm)
    merged = merge_collinear_segments(fused, dpi=dpi)
    lines = _snap_axis_aligned([s for s in merged if math.dist(*s) >= _MIN_LENGTH_MM * px_per_mm])

    if explained:
        starts = np.array([a for a, _b in explained], dtype=np.float64)
        ends = np.array([b for _a, b in explained], dtype=np.float64)
        tolerance = _EXPLAINED_TOL_MM * px_per_mm
        kept = []
        for a, b in lines:
            samples = np.array([(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for t in np.linspace(0, 1, 7)])
            if (_distance_to_segments(samples, starts, ends) <= tolerance).mean() < _SHARE_EXPLAINED:
                kept.append((a, b))
        lines = kept

    sure = [t for t in texts if t.sure]
    if sure:
        lines = [
            (a, b)
            for a, b in lines
            if not any(t.contains((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for t in sure)
        ]

    logger.info("Detalle: %d líneas rectas limpias.", len(lines))
    return lines
