"""Lectura de los textos de un plano escaneado con OCR local (opcional).

El texto de un plano no es texto de documento: es pequeño, disperso, a veces
vertical y está rodeado de líneas que un OCR de página confunde con tablas.
Por eso se trocea la imagen en tiles con solape (cada uno a resolución
nativa) y se prueban varias rotaciones por tile; las cajas repetidas se
deduplican quedándose con la lectura más segura.

El motor es RapidOCR (modelos ONNX, corre en local, sin binario de sistema).
Es una dependencia opcional: sin ella el programa sigue funcionando y los
textos solo aparecen como calco en la capa de referencia.
"""

from __future__ import annotations

import difflib
import logging
import math
import re
import threading
from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np

logger = logging.getLogger("planos2dwg")

_TILE_PX = 900
_OVERLAP = 0.20
_ROTATIONS = (0, 90, 270)
_MIN_CONFIDENCE = 0.60
_IOU_THRESHOLD = 0.35
_MIN_CHARS = 1
_CONTAINMENT = 0.6
_DOUBT_OVERLAP = 0.15  # una lectura dudosa que se encima tanto con una segura es la misma palabra mal leída
_BLANK_TILE_INK = 0.004
_SURE_CONFIDENCE = 0.80
_NUMBER = re.compile(r"^\d+[.,]\d{1,2}$")

# Vocabulario típico de planos en español (MAYÚSCULAS, sin tildes salvo la Ñ).
# Sirve para corregir las confusiones habituales del OCR (BARO -> BAÑO).
_VOCABULARY = (
    "COCINA COCINETA BAÑO BAÑOS ALCOBA ALCOBAS SERVICIO SALA COMEDOR DEPOSITO ACCESO PORCHE "
    "TERRAZA HALL JARDIN VESTIBULO SALON SOCIAL ROPAS AREA DE EN PISO CERAMICA MADERA LAMINA "
    "CONCRETO ENCOCHETE PROYECCION CUBIERTA ESCALERA GARAJE PATIO ESTUDIO DORMITORIO PRINCIPAL "
    "LAVADERO CLOSET BALCON ALFAJIA PASOS NIVEL PLANTA CUARTO UTIL ZONA ESPEJO AGUA MUEBLE "
    "DUCHA LAVAMANOS SANITARIO CORTE FACHADA LOSA VIVIENDA UNIFAMILIAR ESCALA PLANO "
    "ARQUITECTO PROPIETARIO CONTIENE CONTIENEN DETALLE DETALLES"
).split()
_LOCAL = threading.local()


@dataclass(frozen=True)
class TextItem:
    """Un texto reconocido, con su caja en píxeles de la imagen de entrada."""

    text: str
    confidence: float
    quad: np.ndarray  # 4x2: arriba-izq, arriba-der, abajo-der, abajo-izq del texto
    sure: bool = True  # False = lectura dudosa, para revisar a mano

    @property
    def angle_deg(self) -> float:
        """Dirección de la línea base, antihoraria con Y hacia arriba (como CAD)."""
        dx, dy = self.quad[1] - self.quad[0]
        return math.degrees(math.atan2(-dy, dx))

    @property
    def height_px(self) -> float:
        return float(np.linalg.norm(self.quad[3] - self.quad[0]))

    @property
    def baseline_start(self) -> tuple[float, float]:
        """Esquina inferior izquierda del texto, donde se inserta el TEXT de CAD."""
        return float(self.quad[3][0]), float(self.quad[3][1])

    @property
    def baseline_end(self) -> tuple[float, float]:
        """Esquina inferior derecha del texto: fin de la línea base."""
        return float(self.quad[2][0]), float(self.quad[2][1])

    def contains(self, x: float, y: float) -> bool:
        return cv2.pointPolygonTest(self.quad.astype(np.float32), (float(x), float(y)), False) >= 0


def ocr_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def _engine():
    engine = getattr(_LOCAL, "engine", None)
    if engine is None:
        from rapidocr_onnxruntime import RapidOCR

        engine = _LOCAL.engine = RapidOCR()
    return engine


def _engine_without_classifier():
    """Motor sin el clasificador de 180°: el texto boca abajo NO se corrige, se lee mal.

    Solo para detectar la orientación de la página; la lectura normal usa `_engine`.
    """
    engine = getattr(_LOCAL, "engine_no_cls", None)
    if engine is None:
        from rapidocr_onnxruntime import RapidOCR

        engine = _LOCAL.engine_no_cls = RapidOCR(use_angle_cls=False)
    return engine


def _rotate(image: np.ndarray, degrees: int) -> np.ndarray:
    if degrees == 0:
        return image
    if degrees == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if degrees == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)


def _unrotate_quad(quad: np.ndarray, degrees: int, tile_shape: tuple[int, int]) -> np.ndarray:
    """Lleva la caja del tile girado de vuelta a las coordenadas del tile."""
    height, width = tile_shape
    points = np.array(quad, dtype=np.float64).reshape(-1, 2)
    if degrees == 0:
        return points
    if degrees == 90:
        return np.column_stack([points[:, 1], (height - 1) - points[:, 0]])
    if degrees == 180:
        return np.column_stack([(width - 1) - points[:, 0], (height - 1) - points[:, 1]])
    return np.column_stack([(width - 1) - points[:, 1], points[:, 0]])


def _upright_quad(quad: np.ndarray, text: str) -> np.ndarray:
    """Ordena los vértices para que la línea base siga el lado largo y se lea derecha.

    Una lectura obtenida con una rotación de prueba puede traer los vértices en
    otro orden (el texto horizontal aparece "vertical"). Para textos de 3 o más
    letras el lado largo de la caja es la línea base; después se evita el texto
    boca abajo: el ángulo queda en (-90°, 90°].
    """
    ordered = np.array(quad, dtype=np.float64).reshape(4, 2)
    along = float(np.linalg.norm(ordered[1] - ordered[0]))
    across = float(np.linalg.norm(ordered[3] - ordered[0]))
    if len(text) >= 3 and across > 1.5 * along:
        ordered = ordered[[1, 2, 3, 0]]
    dx, dy = ordered[1] - ordered[0]
    angle = math.degrees(math.atan2(-dy, dx))
    if angle > 90.0 + 1e-6 or angle <= -90.0 + 1e-6:
        ordered = ordered[[2, 3, 0, 1]]
    return ordered


def _bbox_iou(a: np.ndarray, b: np.ndarray) -> float:
    ax0, ay0, ax1, ay1 = a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max()
    bx0, by0, bx1, by1 = b[:, 0].min(), b[:, 1].min(), b[:, 0].max(), b[:, 1].max()
    inter_w, inter_h = min(ax1, bx1) - max(ax0, bx0), min(ay1, by1) - max(ay0, by0)
    if inter_w <= 0 or inter_h <= 0:
        return 0.0
    inter = inter_w * inter_h
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return float(inter / union) if union > 0 else 0.0


def _contained(inner: np.ndarray, outer: np.ndarray) -> bool:
    """True si la mayor parte de la caja `inner` cae dentro de `outer`."""
    ix0, iy0, ix1, iy1 = inner[:, 0].min(), inner[:, 1].min(), inner[:, 0].max(), inner[:, 1].max()
    ox0, oy0, ox1, oy1 = outer[:, 0].min(), outer[:, 1].min(), outer[:, 0].max(), outer[:, 1].max()
    width, height = min(ix1, ox1) - max(ix0, ox0), min(iy1, oy1) - max(iy0, oy0)
    area = max((ix1 - ix0) * (iy1 - iy0), 1e-9)
    return width > 0 and height > 0 and (width * height) / area >= _CONTAINMENT


def _deduplicate(items: list[TextItem]) -> list[TextItem]:
    """Quita lecturas repetidas por el solape de tiles y cajas metidas dentro de otra."""
    kept: list[TextItem] = []
    for item in sorted(items, key=lambda t: -t.confidence):
        if not any(
            _bbox_iou(item.quad, other.quad) > _IOU_THRESHOLD or _contained(item.quad, other.quad)
            for other in kept
        ):
            kept.append(item)
    return kept


_DIGIT_LOOKALIKES = str.maketrans({"O": "0", "o": "0", "D": "0", "S": "5", "s": "5", "Z": "2", "z": "2", "l": "1", "I": "1", "|": "1", "B": "8"})
_MEASURE = re.compile(r"^(R?)(\d{1,2})[.,](\d{1,2})(m?)$")
_MEASURE_LOOSE = re.compile(r"^R?[0-9OoDSsZzlI|B]{1,2}[.,][0-9OoDSsZzlI|B]{1,2}m?$")


def _fix_measure(token: str) -> str:
    """Una cota o radio como 'RO.85' o 'z.05' se lee con letras por cifras: se arregla."""
    if not _MEASURE_LOOSE.match(token) or not any(ch.isdigit() for ch in token):
        return token
    prefix = "R" if token.startswith("R") else ""
    body = token[len(prefix):]
    fixed = prefix + body[:-1].translate(_DIGIT_LOOKALIKES) + (body[-1] if body[-1] == "m" else body[-1].translate(_DIGIT_LOOKALIKES))
    return fixed if _MEASURE.match(fixed) else token


def correct_spanish(text: str) -> tuple[str, bool]:
    """Corrige palabras casi iguales a las del vocabulario de planos.

    Devuelve (texto corregido, True si alguna palabra se corrigió o ya era del
    vocabulario). Las cifras y las palabras desconocidas se dejan como están.
    """
    changed_or_known = False
    words = []
    for token in text.split():
        letters = re.sub(r"[^A-ZÑ]", "", token.upper().replace("Ñ", "N").replace("~", ""))
        if len(letters) < 3 or any(ch.isdigit() for ch in token):
            words.append(_fix_measure(token))
            continue
        plain = {w.replace("Ñ", "N"): w for w in _VOCABULARY}
        if letters in plain:
            words.append(plain[letters])
            changed_or_known = True
            continue
        cutoff = 0.8 if len(letters) <= 3 else (0.74 if len(letters) == 4 else 0.72)
        match = difflib.get_close_matches(letters, list(plain), n=1, cutoff=cutoff)
        if match:
            words.append(plain[match[0]])
            changed_or_known = True
        else:
            words.append(token)
    return " ".join(words), changed_or_known


def _without_overlapped_doubts(items: list[TextItem]) -> list[TextItem]:
    """Quita las lecturas dudosas que caen sobre una lectura segura: en el plano salían una encima de la otra."""
    sure = [t for t in items if t.sure]

    def intersection_share(small: np.ndarray, big: np.ndarray) -> float:
        sx0, sy0, sx1, sy1 = small[:, 0].min(), small[:, 1].min(), small[:, 0].max(), small[:, 1].max()
        bx0, by0, bx1, by1 = big[:, 0].min(), big[:, 1].min(), big[:, 0].max(), big[:, 1].max()
        width, height = min(sx1, bx1) - max(sx0, bx0), min(sy1, by1) - max(sy0, by0)
        return (width * height) / max((sx1 - sx0) * (sy1 - sy0), 1e-9) if width > 0 and height > 0 else 0.0

    return [t for t in items if t.sure or not any(intersection_share(t.quad, other.quad) >= _DOUBT_OVERLAP for other in sure)]


def read_texts(
    image: np.ndarray,
    min_confidence: float = _MIN_CONFIDENCE,
    rotations: Sequence[int] = _ROTATIONS,
    tile_px: int = _TILE_PX,
    ignore_bottom_fraction: float = 0.0,
) -> list[TextItem]:
    """Lee los textos de `image` (gris). Lista vacía si no hay OCR instalado.

    `ignore_bottom_fraction` salta la franja inferior (el rótulo del plano).
    """
    if not ocr_available():
        logger.warning(
            "OCR no instalado: los textos solo saldrán como calco. "
            "Para leerlos como texto editable: pip install rapidocr-onnxruntime"
        )
        return []

    engine = _engine()
    if ignore_bottom_fraction > 0:
        image = image[: int(image.shape[0] * (1 - ignore_bottom_fraction))]
    height, width = image.shape[:2]
    step = max(int(tile_px * (1.0 - _OVERLAP)), 1)
    found: list[TextItem] = []

    for y0 in range(0, max(height - 1, 1), step):
        for x0 in range(0, max(width - 1, 1), step):
            x1, y1 = min(x0 + tile_px, width), min(y0 + tile_px, height)
            if x1 - x0 < 40 or y1 - y0 < 40:
                continue
            tile = image[y0:y1, x0:x1]
            if (tile < 128).mean() < _BLANK_TILE_INK:
                continue  # trozo en blanco: no hay nada que leer
            for degrees in rotations:
                result, _ = engine(_rotate(tile, degrees))
                for entry in result or []:
                    quad, text, score = entry[0], str(entry[1]).strip(), float(entry[2])
                    if score < min_confidence or len(text) < _MIN_CHARS:
                        continue
                    box = _unrotate_quad(quad, degrees, tile.shape[:2])
                    box[:, 0] += x0
                    box[:, 1] += y0
                    corrected, known = correct_spanish(text)
                    sure = score >= _SURE_CONFIDENCE or known or bool(_NUMBER.match(text))
                    found.append(
                        TextItem(
                            text=corrected,
                            confidence=score,
                            quad=_upright_quad(box, corrected),
                            sure=sure,
                        )
                    )

    texts = _without_overlapped_doubts(_deduplicate(found))
    logger.info("OCR: %d textos leídos (de %d lecturas).", len(texts), len(found))
    return texts
