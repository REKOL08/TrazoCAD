"""Fotos de partes del plano como fuente extra de lectura.

Un escaneo de 150 dpi no deja leer las cotas pequeñas; una foto de celular de un trozo del
mismo plano tiene el doble de resolución efectiva en esa zona. Cada foto se **registra** contra
el plano (puntos SIFT sobre imágenes sin sombras, homografía con RANSAC, se prueban los 4 giros),
se lee su texto con el mismo OCR y las cajas se llevan, con la homografía, al marco del plano.
Las fotos que no corresponden a este plano no encuentran coincidencias y se descartan.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .texto import TextItem, _bbox_iou, _contained, _upright_quad, correct_spanish, read_texts

logger = logging.getLogger("planos2dwg")

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
_MIN_INLIERS = 40
_MIN_INLIER_RATIO = 0.25
_RATIO_TEST = 0.78
_RANSAC_PX = 6.0
_EDGE_MARGIN = 0.04  # el borde de la foto está más desenfocado y deformado
_SCALE_RANGE = (0.4, 3.0)
_MAX_FEATURES = 12000
_BACKGROUND_KERNEL = 51
_OVERLAP_IOU = 0.30
_PHOTO_MIN_CONFIDENCE = 0.80
_MEASURE_TEXT = re.compile(r"^(R?\d{1,2}[.,]\d{1,2}|-?\d[.,]\d{1,2}m)$")


@dataclass
class RegisteredPhoto:
    """Una foto alineada con el plano: `homography` lleva píxeles de la foto girada al plano."""

    path: Path
    quarter_turns: int
    homography: np.ndarray
    inliers: int
    gray: np.ndarray  # la foto ya girada, en gris


def _flatten(gray: np.ndarray) -> np.ndarray:
    """Quita sombras y el tono del papel dividiendo por el fondo."""
    return cv2.divide(gray, cv2.medianBlur(gray, _BACKGROUND_KERNEL), scale=255)


def find_photos(folder: Path) -> list[Path]:
    """Las imágenes de la carpeta, sin repetir las que son idénticas byte a byte."""
    if not folder.is_dir():
        return []
    seen: set[str] = set()
    photos: list[Path] = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in PHOTO_EXTENSIONS or not path.is_file():
            continue
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        photos.append(path)
    return photos


def register_photos(reference: np.ndarray, photos: list[Path]) -> list[RegisteredPhoto]:
    """Alinea cada foto con `reference` (gris, plano derecho); descarta las que no coinciden."""
    if not photos:
        return []
    sift = cv2.SIFT_create(nfeatures=_MAX_FEATURES)
    ref_keypoints, ref_descriptors = sift.detectAndCompute(_flatten(reference), None)
    if ref_descriptors is None or len(ref_keypoints) < _MIN_INLIERS:
        return []
    matcher = cv2.BFMatcher()
    registered: list[RegisteredPhoto] = []

    for path in photos:
        photo = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if photo is None:
            logger.warning("Foto '%s': no se pudo abrir; se omite.", path.name)
            continue
        best: tuple[int, int, np.ndarray, np.ndarray] | None = None
        for turns in range(4):
            rotated = np.ascontiguousarray(np.rot90(photo, turns))
            keypoints, descriptors = sift.detectAndCompute(_flatten(rotated), None)
            if descriptors is None or len(keypoints) < _MIN_INLIERS:
                continue
            pairs = matcher.knnMatch(descriptors, ref_descriptors, k=2)
            good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < _RATIO_TEST * p[1].distance]
            if len(good) < _MIN_INLIERS:
                continue
            src = np.float32([keypoints[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst = np.float32([ref_keypoints[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            homography, mask = cv2.findHomography(src, dst, cv2.RANSAC, _RANSAC_PX)
            if homography is None or mask is None:
                continue
            inliers = int(mask.sum())
            if inliers < _MIN_INLIERS or inliers / len(good) < _MIN_INLIER_RATIO:
                continue
            if best is None or inliers > best[0]:
                best = (inliers, turns, homography, rotated)
        if best is None:
            logger.info("Foto '%s': no corresponde a este plano (sin coincidencias); se omite.", path.name)
            continue
        inliers, turns, homography, rotated = best
        h, w = rotated.shape
        corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
        quad = cv2.perspectiveTransform(corners, homography).reshape(-1, 2)
        area = cv2.contourArea(quad.astype(np.float32))
        scale = float(np.sqrt(area / (h * w)))
        if not cv2.isContourConvex(quad.astype(np.float32)) or not _SCALE_RANGE[0] <= scale <= _SCALE_RANGE[1]:
            logger.info("Foto '%s': la alineación no es creíble; se omite.", path.name)
            continue
        logger.info(
            "Foto '%s': alineada con el plano (%d puntos, giro %d°, escala %.2f).",
            path.name, inliers, turns * 90, scale,
        )
        registered.append(RegisteredPhoto(path, turns, homography, inliers, rotated))
    return registered


def _credible(item: TextItem) -> bool:
    """Una lectura de foto se acepta si es una cota, una palabra del vocabulario o muy segura."""
    _, known = correct_spanish(item.text)
    return known or bool(_MEASURE_TEXT.match(item.text)) or item.confidence >= _PHOTO_MIN_CONFIDENCE


def _to_plan(item: TextItem, photo: RegisteredPhoto) -> TextItem | None:
    """Lleva el texto de la foto al marco del plano; None si cae en el borde o fuera."""
    h, w = photo.gray.shape
    centre = item.quad.mean(axis=0)
    if not (_EDGE_MARGIN * w <= centre[0] <= (1 - _EDGE_MARGIN) * w
            and _EDGE_MARGIN * h <= centre[1] <= (1 - _EDGE_MARGIN) * h):
        return None
    quad = cv2.perspectiveTransform(item.quad.astype(np.float32).reshape(-1, 1, 2), photo.homography).reshape(4, 2)
    return TextItem(item.text, item.confidence, _upright_quad(quad.astype(np.float64), item.text), item.sure)


def read_photo_texts(photos: list[RegisteredPhoto]) -> list[TextItem]:
    """Lee el texto de cada foto y lo devuelve en coordenadas del plano."""
    found: list[TextItem] = []
    for photo in photos:
        flat = _flatten(photo.gray)
        items = read_texts(flat)
        mapped = [m for m in (_to_plan(i, photo) for i in items if _credible(i)) if m is not None]
        logger.info("Foto '%s': %d textos leídos (%d dentro de su zona útil).", photo.path.name, len(items), len(mapped))
        found.extend(mapped)
    return found


def merge_texts(scan: list[TextItem], extra: list[TextItem], image_shape: tuple[int, int], bottom_fraction: float = 0.0) -> list[TextItem]:
    """Suma las lecturas de las fotos a las del escaneo.

    Un texto de foto que no coincide con ninguno del escaneo se agrega; si coincide con uno,
    se queda el de mayor confianza (solo si la foto lo lee con seguridad).
    """
    height, width = image_shape
    limit = height * (1 - bottom_fraction)
    merged = list(scan)
    added = replaced = 0
    for item in extra:
        cx, cy = item.quad.mean(axis=0)
        if not (0 <= cx < width and 0 <= cy < limit):
            continue
        overlapping = [
            i for i, other in enumerate(merged)
            if _bbox_iou(item.quad, other.quad) >= _OVERLAP_IOU
            or _contained(item.quad, other.quad) or _contained(other.quad, item.quad)
        ]
        if not overlapping:
            merged.append(item)
            added += 1
            continue
        current = [merged[i] for i in overlapping]
        if item.sure and item.confidence > max(c.confidence for c in current) and len(overlapping) == 1:
            merged[overlapping[0]] = item
            replaced += 1
    logger.info("Fotos: %d textos nuevos y %d lecturas mejoradas respecto al escaneo.", added, replaced)
    return merged
