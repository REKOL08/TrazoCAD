"""Calcado vectorial fiel de la tinta de un plano escaneado.

En vez de adivinar "líneas" (que en un escaneo real produce solo rayas
sueltas), se separa la tinta del papel y se calca el contorno de cada
trazo como una polilínea. El resultado en CAD se ve igual que el PDF:
ejes, textos, símbolos y curvas incluidos. No son objetos CAD "inteligentes"
(un muro no es un muro, un texto no es TEXT), sino geometría fiel que un
dibujante puede usar como base para redibujar o limpiar.
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

logger = logging.getLogger("planos2dwg")

Polyline = list[tuple[float, float]]

_REFERENCE_DPI = 300
_BACKGROUND_KERNEL_AT_REF_DPI = 51
_SIMPLIFY_EPSILON_PX_AT_REF_DPI = 1.1
_SMOOTH_SIGMA_PX_AT_REF_DPI = 1.3
_SNAP_MIN_SEGMENT_MM = 3.0
_SMALL_COMPONENT_MM = 5.0
_SNAP_ANGLE_DEG = 1.5
_MIN_SPECK_AREA_PX_AT_REF_DPI = 8
_MIN_SPECK_POINTS_AT_REF_DPI = 12


def _odd(value: float) -> int:
    number = max(3, int(round(value)))
    return number if number % 2 == 1 else number + 1


def binarize_ink(image: np.ndarray, dpi: int) -> np.ndarray:
    """Devuelve una máscara 0/255 donde 255 es tinta.

    Primero se divide la imagen por su fondo desenfocado: esto elimina
    sombras, bordes de hoja y manchas de iluminación típicas de un escaneo
    o foto, de modo que un umbral global (Otsu) funcione en toda la página.
    """
    if image.ndim != 2:
        raise ValueError("binarize_ink espera una imagen en escala de grises (2D)")

    scale = dpi / _REFERENCE_DPI
    background = cv2.medianBlur(image, _odd(_BACKGROUND_KERNEL_AT_REF_DPI * scale))
    normalized = cv2.divide(image, background, scale=255)
    normalized = cv2.GaussianBlur(normalized, (0, 0), 0.8 * scale)
    _, ink = cv2.threshold(normalized, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return ink


Shape = list[Polyline]  # [contorno exterior, hueco, hueco...]: una mancha de tinta con sus agujeros


def trace_shapes(image: np.ndarray, dpi: int) -> list[Shape]:
    """Calca la tinta de `image` como manchas (contorno exterior + agujeros) en píxeles.

    Cada mancha se puede rellenar como un sólido (una letra "O" lleva su agujero), lo que se
    ve como la tinta impresa y no como un doble contorno irregular.
    """
    sharp = binarize_ink(image, dpi)
    scale = dpi / _REFERENCE_DPI

    # Las líneas grandes se suavizan (quita la escalera de píxeles que se ve como
    # temblor); los componentes pequeños (letras, símbolos) se dejan con todo su
    # detalle porque el suavizado los empasta y dejan de leerse.
    smooth_sigma = _SMOOTH_SIGMA_PX_AT_REF_DPI * scale
    smooth = (cv2.GaussianBlur(sharp, (0, 0), smooth_sigma) > 127).astype(np.uint8) * 255
    count, labels, stats, _ = cv2.connectedComponentsWithStats(sharp, connectivity=8)
    small_limit = _SMALL_COMPONENT_MM * dpi / 25.4
    is_small = np.zeros(count, dtype=bool)
    is_small[1:] = np.maximum(stats[1:, cv2.CC_STAT_WIDTH], stats[1:, cv2.CC_STAT_HEIGHT]) <= small_limit
    small_mask = is_small[labels].astype(np.uint8) * 255
    near_small = cv2.dilate(small_mask, np.ones((5, 5), np.uint8))
    ink = np.where(small_mask > 0, sharp, np.where(near_small > 0, 0, smooth)).astype(np.uint8)
    contours, hierarchy = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hierarchy is None:
        return []

    min_area = _MIN_SPECK_AREA_PX_AT_REF_DPI * scale * scale
    min_points = _MIN_SPECK_POINTS_AT_REF_DPI * scale
    epsilon = _SIMPLIFY_EPSILON_PX_AT_REF_DPI * scale
    fine_epsilon = 0.6 * scale
    snap_min = _SNAP_MIN_SEGMENT_MM * dpi / 25.4

    def simplify(contour: np.ndarray) -> Polyline | None:
        _x, _y, box_w, box_h = cv2.boundingRect(contour)
        small = max(box_w, box_h) <= small_limit
        simplified = cv2.approxPolyDP(contour, fine_epsilon if small else epsilon, True)
        if len(simplified) < 3:
            return None
        points = [(float(x), float(y)) for x, y in simplified[:, 0, :]]
        return points if small else _snap_orthogonal(points, snap_min)

    shapes: list[Shape] = []
    for index, contour in enumerate(contours):
        if hierarchy[0][index][3] >= 0:  # los agujeros se recogen desde su contorno exterior
            continue
        if cv2.contourArea(contour) < min_area and len(contour) < min_points:
            continue
        outer = simplify(contour)
        if outer is None:
            continue
        shape: Shape = [outer]
        child = hierarchy[0][index][2]
        while child >= 0:
            if cv2.contourArea(contours[child]) >= min_area:
                hole = simplify(contours[child])
                if hole is not None:
                    shape.append(hole)
            child = hierarchy[0][child][0]
        shapes.append(shape)

    logger.info("Calcado de tinta: %d manchas.", len(shapes))
    return shapes


def trace_ink(image: np.ndarray, dpi: int) -> list[Polyline]:
    """Calca la tinta como polilíneas cerradas sueltas (contornos exteriores y agujeros)."""
    return [polyline for shape in trace_shapes(image, dpi) for polyline in shape]


def _snap_orthogonal(points: Polyline, min_length_px: float) -> Polyline:
    """Endereza a H/V exactos los tramos largos casi horizontales o verticales."""
    pts = [list(p) for p in points]
    tolerance = math.tan(math.radians(_SNAP_ANGLE_DEG))
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        (x1, y1), (x2, y2) = pts[i], pts[j]
        dx, dy = x2 - x1, y2 - y1
        if math.hypot(dx, dy) < min_length_px:
            continue
        if abs(dy) <= tolerance * abs(dx):
            pts[i][1] = pts[j][1] = (y1 + y2) / 2
        elif abs(dx) <= tolerance * abs(dy):
            pts[i][0] = pts[j][0] = (x1 + x2) / 2
    return [(p[0], p[1]) for p in pts]
