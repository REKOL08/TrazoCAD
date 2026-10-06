"""Fotos de partes del plano para ganar detalle: se **fusionan** con el escaneo.

Un escaneo de 150 dpi pierde las cotas pequeñas y los trazos finos; una foto de celular de un trozo del
mismo plano es 2 o 3 veces más nítida en esa zona. Cada foto se **registra** contra el plano (puntos SIFT
sobre imágenes sin sombras, homografía con RANSAC, se prueban los 4 giros) y su zona útil reemplaza ese
trozo del escaneo, con los tonos igualados y un borde difuminado. Todo el programa (muros, puertas, textos,
detalle) trabaja después sobre la imagen fusionada. Las fotos que no corresponden a este plano no encuentran
coincidencias y se descartan.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger("planos2dwg")

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
_MIN_INLIERS = 40
_MIN_INLIER_RATIO = 0.25
_RATIO_TEST = 0.78
_RANSAC_PX = 6.0
_SCALE_RANGE = (0.4, 3.0)
_MAX_FEATURES = 12000
_BACKGROUND_KERNEL = 51
_INNER_MARGIN = 0.07  # el borde de la foto está más desenfocado y deformado: no se usa
_FEATHER_PX = 40.0  # ancho del degradado entre la foto y el escaneo
_MIN_ZONE_PX = 20000


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


def unique_photos(paths: list[Path]) -> list[Path]:
    """Las imágenes de la lista que se pueden usar, sin repetir las idénticas byte a byte."""
    seen: set[str] = set()
    photos: list[Path] = []
    for path in paths:
        path = Path(path)
        if path.suffix.lower() not in PHOTO_EXTENSIONS or not path.is_file():
            continue
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        photos.append(path)
    return photos


def find_photos(folder: Path) -> list[Path]:
    """Las imágenes de la carpeta, sin repetir las que son idénticas byte a byte."""
    if not folder.is_dir():
        return []
    return unique_photos(sorted(folder.iterdir()))


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


def _tone_matched(source: np.ndarray, reference: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Lleva los tonos de `source` a los de `reference` (por percentiles) mirando solo la máscara."""
    levels = np.linspace(0, 100, 101)
    source_q = np.maximum.accumulate(np.percentile(source[mask > 0], levels))
    reference_q = np.percentile(reference[mask > 0], levels)
    table = np.interp(np.arange(256), source_q, reference_q).astype(np.uint8)
    return table[source]


def fuse_photos(plan: np.ndarray, photos: list[RegisteredPhoto]) -> np.ndarray:
    """Devuelve `plan` (gris) con la zona útil de cada foto puesta encima, con los tonos igualados.

    Las partes que ninguna foto cubre quedan exactamente como en el escaneo.
    """
    if not photos:
        return plan
    height, width = plan.shape
    plan_flat = _flatten(plan)
    fused = plan.copy()
    best_weight = np.zeros((height, width), np.float32)
    covered = 0.0

    for photo in photos:
        photo_h, photo_w = photo.gray.shape
        useful = np.full((photo_h, photo_w), 255, np.uint8)
        margin = int(_INNER_MARGIN * min(photo_h, photo_w))
        useful[:margin] = useful[-margin:] = 0
        useful[:, :margin] = useful[:, -margin:] = 0
        zone = cv2.warpPerspective(useful, photo.homography, (width, height), flags=cv2.INTER_NEAREST)
        if int((zone > 0).sum()) < _MIN_ZONE_PX:
            continue
        warped = cv2.warpPerspective(_flatten(photo.gray), photo.homography, (width, height), flags=cv2.INTER_CUBIC, borderValue=255)
        matched = _tone_matched(warped, plan_flat, zone)
        weight = np.clip(cv2.distanceTransform((zone > 0).astype(np.uint8), cv2.DIST_L2, 3) / _FEATHER_PX, 0.0, 1.0)
        wins = weight > best_weight
        blended = fused.astype(np.float32) * (1.0 - weight) + matched.astype(np.float32) * weight
        fused = np.where(wins, blended, fused).astype(np.uint8)
        best_weight = np.maximum(best_weight, weight)

    covered = float((best_weight > 0.99).mean())
    logger.info("Fotos: %d fusionadas con el escaneo (%.0f%% de la hoja con más detalle).", len(photos), 100 * covered)
    return fused
