"""Orientación automática del plano: giro de página y franja del cajetín.

Un plano escaneado puede venir de lado (el PDF de prueba trae la planta girada
90°) y lleva un cajetín con los datos del plano que no es dibujo. Para que el
usuario no tenga que indicarlo, se detectan los dos:

* **Giro:** se lee el texto de los trozos con más tinta en las cuatro
  orientaciones y gana la que reconoce más palabras de plano (COCINA, BAÑO,
  PISO...). Sin OCR instalado no se puede decidir y no se gira.
* **Cajetín:** el recuadro de datos es una pila de líneas horizontales largas en
  la franja baja de la hoja; la línea más alta de esa pila marca dónde empieza.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from .texto import _engine_without_classifier, correct_spanish, ocr_available
from .vectorizer import binarize_ink

logger = logging.getLogger("planos2dwg")

_TILE_PX = 700
_SAMPLE_TILES = 4
_WIDE_RATIO = 1.3
_MIN_CONFIDENCE = 0.6
_MIN_EVIDENCE = 1.5
_STRONG_EVIDENCE = 6.0
_FUZZY_WEIGHT = 0.25
_MIN_RATIO = 1.3
_LONG_LINE_FRACTION = 0.45
_LOWER_ZONE = 0.60
_STACK_REACH = 0.20
_MARGIN = 0.005
_MAX_BLOCK = 0.40


def _densest_tiles(image: np.ndarray, count: int, tile_px: int) -> list[np.ndarray]:
    height, width = image.shape[:2]
    step = tile_px
    scored: list[tuple[float, np.ndarray]] = []
    for y0 in range(0, max(height - tile_px // 2, 1), step):
        for x0 in range(0, max(width - tile_px // 2, 1), step):
            tile = image[y0 : y0 + tile_px, x0 : x0 + tile_px]
            if min(tile.shape[:2]) < 200:
                continue
            scored.append(((tile < 128).mean(), tile))
    scored.sort(key=lambda item: -item[0])
    return [tile for _density, tile in scored[:count]]


def _orientation_score(tiles: list[np.ndarray], quarter_turns: int) -> float:
    """Suma de confianzas de las palabras de plano leídas en líneas HORIZONTALES.

    El OCR lee bien el texto vertical porque gira solo los cuadros altos; por eso
    leer palabras no basta para distinguir la orientación. Solo cuenta lo leído en
    un cuadro más ancho que alto: el texto tumbado o boca abajo no puntúa.
    """
    engine = _engine_without_classifier()
    total = 0.0
    for tile in tiles:
        rotated = np.ascontiguousarray(np.rot90(tile, quarter_turns))
        # motor sin clasificador de 180°: un texto boca abajo debe leerse mal, no corregirse solo
        result, _ = engine(rotated)
        for entry in result or []:
            text, score = str(entry[1]).strip(), float(entry[2])
            if score < _MIN_CONFIDENCE or len(text) < 4:
                continue
            quad = np.array(entry[0], dtype=np.float64).reshape(4, 2)
            width = float(np.linalg.norm(quad[1] - quad[0]))
            height = float(np.linalg.norm(quad[3] - quad[0]))
            if width < _WIDE_RATIO * height:
                continue
            corrected, known = correct_spanish(text)
            if known:
                # una palabra leída tal cual es mucho más fiable que una corregida por
                # parecido: leído boca abajo, el OCR da basura que "casi" parece alguna
                exact = corrected.replace("Ñ", "N").upper() == text.replace("Ñ", "N").upper()
                total += score * (1.0 if exact else _FUZZY_WEIGHT)
    return total


def detect_rotation(image: np.ndarray, dpi: int) -> int:
    """Giro antihorario (0, 90, 180 o 270) que deja los textos derechos; 0 si no hay evidencia."""
    if not ocr_available():
        logger.info("Sin OCR no se puede detectar el giro de la página; se deja como viene.")
        return 0
    tiles = _densest_tiles(image, _SAMPLE_TILES, int(_TILE_PX * dpi / 300))
    if not tiles:
        return 0
    # una orientación equivocada puntúa casi cero (el texto tumbado o boca abajo no cuenta),
    # así que se para en cuanto una tiene evidencia fuerte: el caso normal (plano derecho)
    # cuesta una sola prueba. Orden: derecho, 90° antihorario, 90° horario, boca abajo.
    scores = [0.0, 0.0, 0.0, 0.0]
    for k in (0, 1, 3, 2):
        scores[k] = _orientation_score(tiles, k)
        if scores[k] >= _STRONG_EVIDENCE:
            break
    best = int(np.argmax(scores))
    others = sorted((s for k, s in enumerate(scores) if k != best), reverse=True)
    if scores[best] < _MIN_EVIDENCE or (others and scores[best] < _MIN_RATIO * max(others[0], 1e-9)):
        logger.info("Giro de página no concluyente (puntajes %s); se deja como viene.", [round(s, 1) for s in scores])
        return 0
    if best:
        logger.info("Página girada: se gira %d° (puntajes %s).", best * 90, [round(s, 1) for s in scores])
    return best * 90


def detect_title_block_fraction(image: np.ndarray, dpi: int) -> float:
    """Fracción inferior de la hoja ocupada por el cajetín (0 si no se encuentra)."""
    height, width = image.shape[:2]
    ink = binarize_ink(image, dpi)
    bridged = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5)))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(int(_LONG_LINE_FRACTION * width), 3), 1))
    long_lines = cv2.morphologyEx(bridged, cv2.MORPH_OPEN, kernel)
    rows = np.nonzero(long_lines.sum(axis=1) > 0)[0]

    groups: list[list[int]] = []
    for y in rows:
        if groups and y - groups[-1][-1] <= 4:
            groups[-1].append(int(y))
        else:
            groups.append([int(y)])
    centres = [float(np.mean(group)) for group in groups if np.mean(group) > _LOWER_ZONE * height]

    for index, top in enumerate(centres):
        below = [c for c in centres[index + 1 :] if c - top <= _STACK_REACH * height]
        if below:  # una pila de líneas largas: el recuadro del cajetín
            fraction = (height - top) / height + _MARGIN
            if fraction <= _MAX_BLOCK:
                logger.info("Cajetín detectado: se ignora el %.1f %% inferior de la hoja.", fraction * 100)
                return fraction
    return 0.0
