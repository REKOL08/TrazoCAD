"""Detección de segmentos de línea en una imagen de plano escaneado.

Usa un pipeline clásico de visión por computador (OpenCV): binarización
adaptativa, adelgazamiento de trazos y transformada de Hough probabilística.
No intenta reconocer símbolos ni texto: eso lo documenta el README como
limitación conocida y queda a cargo de un dibujante para la corrección final.
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

logger = logging.getLogger("planos2dwg")

Segment = tuple[tuple[float, float], tuple[float, float]]

# Tolerancias de fusión de segmentos colineales, calibradas para 300 DPI y
# escaladas linealmente con el DPI real (ver merge_collinear_segments).
_REFERENCE_DPI = 300
_ANGLE_TOLERANCE_DEG = 2.0
_OFFSET_TOLERANCE_PX_AT_REF_DPI = 4.0
_GAP_TOLERANCE_PX_AT_REF_DPI = 12.0


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


def _angle_and_offset(segment: Segment) -> tuple[float, float]:
    """Ángulo (0..pi, módulo 180°) y distancia perpendicular al origen.

    Dos segmentos con el mismo ángulo y el mismo offset están sobre la
    misma recta infinita, sin importar en qué punto de ella caen.
    """
    (x1, y1), (x2, y2) = segment
    angle = math.atan2(y2 - y1, x2 - x1) % math.pi
    normal_x, normal_y = -math.sin(angle), math.cos(angle)
    offset = x1 * normal_x + y1 * normal_y
    return angle, offset


def merge_collinear_segments(
    segments: list[Segment],
    dpi: int,
    angle_tolerance_deg: float = _ANGLE_TOLERANCE_DEG,
) -> list[Segment]:
    """Fusiona segmentos casi colineales y cercanos en uno solo más largo.

    Un escaneo real divide casi siempre un mismo muro en varios segmentos
    cortos (lo cruzan cotas, texto, manchas). Esto los reconstruye en una
    sola línea por pared, lo que además deja el filtro de longitud mínima
    (`filter_short_segments`) funcionar correctamente.

    Las tolerancias de distancia se expresan en píxeles a `_REFERENCE_DPI`
    y se escalan al `dpi` real, porque el grosor de un trazo en píxeles
    crece proporcionalmente con la resolución de escaneo.
    """
    if not segments:
        return []

    scale = dpi / _REFERENCE_DPI
    offset_tolerance = _OFFSET_TOLERANCE_PX_AT_REF_DPI * scale
    gap_tolerance = _GAP_TOLERANCE_PX_AT_REF_DPI * scale
    angle_tolerance = math.radians(angle_tolerance_deg)

    angles_offsets = [_angle_and_offset(segment) for segment in segments]

    # Agrupar primero por ángulo (redondeado) para no comparar cada segmento
    # contra todos los demás: en un plano real la mayoría de los segmentos
    # de "ruido" no comparten ángulo con los muros reales.
    bucket_size_deg = max(1, round(angle_tolerance_deg))
    num_buckets = max(1, 180 // bucket_size_deg)
    buckets: dict[int, list[int]] = {}
    for index, (angle, _offset) in enumerate(angles_offsets):
        bucket_id = int(math.degrees(angle) // bucket_size_deg) % num_buckets
        buckets.setdefault(bucket_id, []).append(index)

    parent = list(range(len(segments)))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_a] = root_b

    for bucket_id, indices in buckets.items():
        neighbor_indices: list[int] = []
        for neighbor_bucket in (bucket_id - 1, bucket_id, bucket_id + 1):
            neighbor_indices.extend(buckets.get(neighbor_bucket % num_buckets, []))

        for position, i in enumerate(indices):
            angle_i, offset_i = angles_offsets[i]
            for j in neighbor_indices:
                if j <= i:
                    continue
                angle_j, offset_j = angles_offsets[j]
                delta_angle = abs(angle_i - angle_j)
                delta_angle = min(delta_angle, math.pi - delta_angle)
                if delta_angle <= angle_tolerance and abs(offset_i - offset_j) <= offset_tolerance:
                    union(i, j)

    groups: dict[int, list[int]] = {}
    for index in range(len(segments)):
        groups.setdefault(find(index), []).append(index)

    merged: list[Segment] = []
    for indices in groups.values():
        representative_angle = angles_offsets[indices[0]][0]
        direction = (math.cos(representative_angle), math.sin(representative_angle))

        anchor_x, anchor_y = segments[indices[0]][0]
        anchor_projection = anchor_x * direction[0] + anchor_y * direction[1]
        anchor = (
            anchor_x - anchor_projection * direction[0],
            anchor_y - anchor_projection * direction[1],
        )

        intervals: list[tuple[float, float]] = []
        for index in indices:
            (x1, y1), (x2, y2) = segments[index]
            p1 = x1 * direction[0] + y1 * direction[1]
            p2 = x2 * direction[0] + y2 * direction[1]
            intervals.append((min(p1, p2), max(p1, p2)))
        intervals.sort()

        current_start, current_end = intervals[0]
        for start, end in intervals[1:]:
            if start <= current_end + gap_tolerance:
                current_end = max(current_end, end)
            else:
                merged.append(_interval_to_segment(anchor, direction, current_start, current_end))
                current_start, current_end = start, end
        merged.append(_interval_to_segment(anchor, direction, current_start, current_end))

    logger.info("Fusión de colineales: %d segmentos -> %d.", len(segments), len(merged))
    return merged


def _interval_to_segment(
    anchor: tuple[float, float],
    direction: tuple[float, float],
    start: float,
    end: float,
) -> Segment:
    start_point = (anchor[0] + start * direction[0], anchor[1] + start * direction[1])
    end_point = (anchor[0] + end * direction[0], anchor[1] + end * direction[1])
    return (start_point, end_point)


def filter_short_segments(
    segments: list[Segment],
    min_length_mm: float,
    dpi: int,
) -> list[Segment]:
    """Descarta segmentos más cortos que `min_length_mm` (tras la fusión).

    Elimina la mayoría del ruido de texto, cotas y achurados de escaneos
    reales, que casi siempre son fragmentos mucho más cortos que un muro.
    """
    if min_length_mm <= 0:
        return segments

    min_length_px = (min_length_mm / 25.4) * dpi
    kept = [
        segment
        for segment in segments
        if math.dist(segment[0], segment[1]) >= min_length_px
    ]

    discarded = len(segments) - len(kept)
    if discarded:
        logger.info(
            "Filtro de longitud mínima (%.1f mm): se descartan %d segmentos cortos, quedan %d.",
            min_length_mm,
            discarded,
            len(kept),
        )
    return kept
