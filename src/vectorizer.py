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

import cv2
import numpy as np

logger = logging.getLogger("planos2dwg")

Polyline = list[tuple[float, float]]

_REFERENCE_DPI = 300
_BACKGROUND_KERNEL_AT_REF_DPI = 51
_SIMPLIFY_EPSILON_PX_AT_REF_DPI = 0.7
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


def trace_ink(image: np.ndarray, dpi: int) -> list[Polyline]:
    """Calca la tinta de `image` como polilíneas cerradas en píxeles."""
    ink = binarize_ink(image, dpi)
    contours, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    scale = dpi / _REFERENCE_DPI
    min_area = _MIN_SPECK_AREA_PX_AT_REF_DPI * scale * scale
    min_points = _MIN_SPECK_POINTS_AT_REF_DPI * scale
    epsilon = _SIMPLIFY_EPSILON_PX_AT_REF_DPI * scale

    polylines: list[Polyline] = []
    for contour in contours:
        if cv2.contourArea(contour) < min_area and len(contour) < min_points:
            continue
        simplified = cv2.approxPolyDP(contour, epsilon, True)
        if len(simplified) < 3:
            continue
        polylines.append([(float(x), float(y)) for x, y in simplified[:, 0, :]])

    logger.info("Calcado de tinta: %d contornos -> %d polilíneas.", len(contours), len(polylines))
    return polylines
