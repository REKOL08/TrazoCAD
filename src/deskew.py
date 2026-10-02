"""Enderezado de escaneos ligeramente inclinados."""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

logger = logging.getLogger("planos2dwg")

_MAX_SKEW_DEG = 5.0
_MIN_SKEW_DEG = 0.15
_MIN_SEGMENT_MM = 8.0


def estimate_skew_degrees(image: np.ndarray, dpi: int) -> float:
    """Inclinación dominante (grados, antihorario positivo) respecto a H/V.

    Se mide sobre los segmentos largos casi horizontales o verticales, que en
    un plano son muros, ejes y cotas; la mediana ponderada por longitud es
    robusta frente a elementos oblicuos como un abanico de habitaciones.
    """
    background = cv2.medianBlur(image, 51 if dpi >= 250 else 31)
    normalized = cv2.divide(image, background, scale=255)
    lines = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(normalized)[0]
    if lines is None:
        return 0.0
    lines = lines[:, 0, :]
    dx, dy = lines[:, 2] - lines[:, 0], lines[:, 3] - lines[:, 1]
    length = np.hypot(dx, dy)
    # en coordenadas de imagen y crece hacia abajo: se invierte dy para medir antihorario
    angle = np.degrees(np.arctan2(-dy, dx))
    folded = (angle + 45) % 90 - 45
    keep = (length >= _MIN_SEGMENT_MM * dpi / 25.4) & (np.abs(folded) <= _MAX_SKEW_DEG)
    if keep.sum() < 5:
        return 0.0
    order = np.argsort(folded[keep])
    values, weights = folded[keep][order], length[keep][order]
    cumulative = np.cumsum(weights)
    return float(values[np.searchsorted(cumulative, cumulative[-1] / 2)])


def deskew(image: np.ndarray, dpi: int) -> np.ndarray:
    """Gira `image` para corregir su inclinación; no hace nada si es mínima."""
    skew = estimate_skew_degrees(image, dpi)
    if abs(skew) < _MIN_SKEW_DEG:
        return image
    height, width = image.shape
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), -skew, 1.0)
    logger.info("Escaneo inclinado %.2f°: se endereza.", skew)
    return cv2.warpAffine(
        image, matrix, (width, height), flags=cv2.INTER_LINEAR, borderValue=255
    )
