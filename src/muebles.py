"""Sanitarios: inodoros y lavamanos, buscados solo dentro de los baños.

Un sanitario es una elipse (la taza o el lavamanos) en un cuarto etiquetado
como BAÑO. Una elipse suelta no basta: en un escaneo salen decenas de huecos
elípticos que no son nada (espacios entre cotas, peldaños). Por eso se usa el
contexto: solo se aceptan elipses cerca de una etiqueta BAÑO leída por el OCR
y con un tamaño razonable respecto al espesor de muro del plano.

Limitación honesta: solo se buscan sanitarios en baños y como elipses; muebles
(camas, sofás, cocinas) no se reconocen, y en un escaneo de baja resolución
algunos sanitarios no se distinguen.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import cv2
import numpy as np

from .texto import TextItem
from .vectorizer import binarize_ink

logger = logging.getLogger("planos2dwg")

_ROOM_WORDS = {"BAÑO", "BAÑOS", "BANO"}
_SEARCH_RADIUS_IN_WALL_THICKNESS = 15.0
_MAJOR_RANGE = (1.8, 4.5)
_MIN_MINOR = 1.4
_MAX_RATIO = 2.0
_ROUND_RATIO = 1.15
_ROUND_MAX_MAJOR = 3.4
_MAX_FIT_ERROR = 0.12
_MIN_CONVEXITY = 0.92
_DUPLICATE_CENTRE = 0.5


@dataclass(frozen=True)
class Fixture:
    """Un sanitario: tipo, centro y ejes de la elipse en píxeles de imagen."""

    kind: str  # "INODORO" o "LAVAMANOS"
    cx: float
    cy: float
    major: float  # eje mayor completo
    minor: float  # eje menor completo
    angle_deg: float  # dirección del eje mayor en la imagen (Y hacia abajo)

    def outline(self, points: int = 24) -> list[tuple[float, float]]:
        """Puntos del contorno, para medir cuánto calco explica este sanitario."""
        theta = math.radians(self.angle_deg)
        pts = []
        for k in range(points + 1):
            t = 2 * math.pi * k / points
            u, v = math.cos(t) * self.major / 2, math.sin(t) * self.minor / 2
            pts.append(
                (
                    self.cx + u * math.cos(theta) - v * math.sin(theta),
                    self.cy + u * math.sin(theta) + v * math.cos(theta),
                )
            )
        return pts


def _is_bathroom(text: str) -> bool:
    words = text.upper().split()
    return bool(words) and words[0] in _ROOM_WORDS


def detect_fixtures(
    image: np.ndarray, dpi: int, texts: list[TextItem], wall_thickness_px: float | None = None
) -> list[Fixture]:
    """Devuelve los sanitarios encontrados cerca de las etiquetas BAÑO."""
    rooms = [
        np.array(t.quad, dtype=np.float64).mean(axis=0) for t in texts if _is_bathroom(t.text)
    ]
    if not rooms:
        return []

    thickness = wall_thickness_px or (1.0 * dpi / 25.4)
    ink = binarize_ink(image, dpi)
    contours, hierarchy = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hierarchy is None:
        return []

    reach = _SEARCH_RADIUS_IN_WALL_THICKNESS * thickness
    min_area = math.pi * (_MAJOR_RANGE[0] * thickness / 2) * (_MIN_MINOR * thickness / 2) * 0.6
    max_area = math.pi * (_MAJOR_RANGE[1] * thickness / 2) ** 2 * 1.3
    candidates: list[Fixture] = []

    for index, contour in enumerate(contours):
        if hierarchy[0][index][3] < 0 or len(contour) < 12:  # solo huecos interiores
            continue
        area = cv2.contourArea(contour)
        if not (min_area <= area <= max_area):
            continue
        hull_area = cv2.contourArea(cv2.convexHull(contour))
        if hull_area <= 0 or area / hull_area < _MIN_CONVEXITY:
            continue
        (cx, cy), (width, height), angle = cv2.fitEllipse(contour)
        major, minor = max(width, height), min(width, height)
        if minor <= 0:
            continue
        ellipse_area = math.pi * major * minor / 4
        if abs(ellipse_area - area) / ellipse_area > _MAX_FIT_ERROR:
            continue
        if not (_MAJOR_RANGE[0] * thickness <= major <= _MAJOR_RANGE[1] * thickness):
            continue
        if minor < _MIN_MINOR * thickness or major / minor > _MAX_RATIO:
            continue
        if not any(math.hypot(cx - r[0], cy - r[1]) <= reach for r in rooms):
            continue
        axis_angle = angle if width >= height else angle + 90.0
        ratio = major / minor
        kind = "LAVAMANOS" if ratio <= _ROUND_RATIO and major <= _ROUND_MAX_MAJOR * thickness else "INODORO"
        candidates.append(Fixture(kind, float(cx), float(cy), float(major), float(minor), float(axis_angle)))

    # los trazos concéntricos de un mismo sanitario dan varios huecos: se queda el mayor
    fixtures: list[Fixture] = []
    for fixture in sorted(candidates, key=lambda f: -f.major):
        if not any(
            math.hypot(fixture.cx - other.cx, fixture.cy - other.cy) <= _DUPLICATE_CENTRE * thickness
            for other in fixtures
        ):
            fixtures.append(fixture)

    logger.info("Sanitarios: %d (inodoros %d, lavamanos %d).", len(fixtures),
                sum(f.kind == "INODORO" for f in fixtures), sum(f.kind == "LAVAMANOS" for f in fixtures))
    return fixtures
