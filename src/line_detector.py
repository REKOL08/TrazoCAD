"""Detección de segmentos de línea en una imagen de plano escaneado.

Usa un pipeline clásico de visión por computador (OpenCV): binarización
adaptativa, adelgazamiento de trazos y transformada de Hough probabilística.
No intenta reconocer símbolos ni texto: eso lo documenta el README como
limitación conocida y queda a cargo de un dibujante para la corrección final.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger("planos2dwg")

Segment = tuple[tuple[float, float], tuple[float, float]]


def detect_lines(
    image: np.ndarray,
    min_line_length: int = 25,
    max_line_gap: int = 6,
) -> list[Segment]:
    """Devuelve los segmentos de línea detectados en `image` (píxeles).

    `image` debe ser una matriz en escala de grises (alto, ancho).
    Cada segmento es ((x1, y1), (x2, y2)) en coordenadas de píxel con
    origen arriba-izquierda, tal como lo entrega OpenCV.
    """
    if image.ndim != 2:
        raise ValueError("detect_lines espera una imagen en escala de grises (2D)")

    denoised = cv2.medianBlur(image, 3)

    binary = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=25,
        C=10,
    )

    # Cierre morfológico leve para unir trazos discontinuos típicos de
    # escaneos de baja calidad, sin fusionar líneas paralelas cercanas.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    edges = cv2.Canny(binary, 50, 150, apertureSize=3)

    raw_lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=40,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )

    if raw_lines is None:
        logger.warning("No se detectaron líneas en la página; revisa la calidad del escaneo.")
        return []

    segments: list[Segment] = [
        ((float(x1), float(y1)), (float(x2), float(y2)))
        for (x1, y1, x2, y2) in raw_lines[:, 0, :]
    ]

    logger.info("Se detectaron %d segmentos de línea.", len(segments))
    return segments
