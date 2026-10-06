"""Experimento: fusionar las fotos del plano con el escaneo para ganar detalle en el DIBUJO (no solo en textos).

Se ejecuta con el entorno del proyecto, después de `experimentos/vision/preparar_plano.py`:
    .venv\\Scripts\\python.exe experimentos\\fusion\\probar_fusion.py
Deja imágenes de comparación en experimentos/resultados/.
"""

import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.fotos import _flatten, find_photos, register_photos  # noqa: E402

OUT = ROOT / "experimentos" / "resultados"
plan = cv2.imread(str(OUT / "plano_300dpi.png"), cv2.IMREAD_GRAYSCALE)
H, W = plan.shape
plan_flat = _flatten(plan)

photos = register_photos(plan, find_photos(ROOT / "planos_de_prueba"))
print("fotos alineadas:", len(photos))


def corr_in_mask(img_a, img_b, mask):
    """Correlación de bordes (Sobel) entre dos imágenes dentro de una máscara."""
    ga = cv2.GaussianBlur(img_a, (0, 0), 1.2).astype(np.float32)
    gb = cv2.GaussianBlur(img_b, (0, 0), 1.2).astype(np.float32)
    ea = np.hypot(cv2.Sobel(ga, cv2.CV_32F, 1, 0), cv2.Sobel(ga, cv2.CV_32F, 0, 1))[mask > 0]
    eb = np.hypot(cv2.Sobel(gb, cv2.CV_32F, 1, 0), cv2.Sobel(gb, cv2.CV_32F, 0, 1))[mask > 0]
    return float(np.corrcoef(ea, eb)[0, 1])


def match_tone(source, reference, mask):
    """Lleva los tonos de `source` a los de `reference` (CDF) dentro de la máscara."""
    qs = np.linspace(0, 100, 101)
    src_q = np.percentile(source[mask > 0], qs)
    ref_q = np.percentile(reference[mask > 0], qs)
    lut = np.interp(np.arange(256), np.maximum.accumulate(src_q), ref_q).astype(np.uint8)
    return lut[source]


fused = plan.copy()
weights = np.zeros((H, W), np.float32)
stats = []
for photo in photos:
    h, w = photo.gray.shape
    ones = np.full((h, w), 255, np.uint8)
    inner_margin = int(0.07 * min(h, w))
    ones[:inner_margin] = ones[-inner_margin:] = 0
    ones[:, :inner_margin] = ones[:, -inner_margin:] = 0
    valid = cv2.warpPerspective(ones, photo.homography, (W, H), flags=cv2.INTER_NEAREST)
    warped = cv2.warpPerspective(_flatten(photo.gray), photo.homography, (W, H), flags=cv2.INTER_CUBIC, borderValue=255)
    area = int((valid > 0).sum())
    before = corr_in_mask(plan_flat, warped, valid)
    # nitidez: varianza del laplaciano dentro de la zona
    lap = lambda im: float(cv2.Laplacian(im, cv2.CV_32F)[valid > 0].var())  # noqa: E731
    print(f"{photo.path.name[-14:]}: zona {area / (H * W):.1%} de la hoja · correlación de bordes {before:.3f} · nitidez escaneo {lap(plan_flat):.0f} vs foto {lap(warped):.0f}")
    matched = match_tone(warped, plan_flat, valid)
    feather = np.clip(cv2.distanceTransform((valid > 0).astype(np.uint8), cv2.DIST_L2, 3) / 40.0, 0, 1)
    better = feather > weights
    alpha = np.where(better, feather, 0)
    fused = np.where(better, (fused * (1 - alpha) + matched * alpha), fused).astype(np.uint8)
    weights = np.maximum(weights, feather)
    stats.append((photo.path.name, area / (H * W), before))

OUT.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(OUT / "fusion_plano.png"), fused)
# recortes de comparación (zona de la cocina/comedor, cubierta por las fotos)
ys, xs = np.nonzero(weights > 0.99)
cy, cx = int(np.median(ys)), int(np.median(xs))
box = (slice(max(cy - 350, 0), cy + 350), slice(max(cx - 500, 0), cx + 500))
pair = np.hstack([plan[box], fused[box]])
cv2.imwrite(str(OUT / "fusion_comparacion_recorte.png"), pair)
print("recorte:", pair.shape, "centro", (cx, cy))
print("cobertura total de fotos: %.1f%% de la hoja" % (100 * (weights > 0.99).mean()))
