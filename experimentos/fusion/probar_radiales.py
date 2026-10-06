import math, pickle, sys, time
from pathlib import Path
import cv2, numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.burbujas import _Ring
from src.vectorizer import binarize_ink
OUT = ROOT / "experimentos" / "resultados"
img = cv2.imread(str(OUT / "fusion_plano.png"), cv2.IMREAD_GRAYSCALE)
ink = binarize_ink(img, 300)
ring = _Ring(img, ink)
R = 21
t = time.time()
blur = cv2.GaussianBlur(img, (5, 5), 1.2)
found = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=R, param1=110, param2=20, minRadius=R - 3, maxRadius=R + 3)[0]
print(len(found), "candidatos Hough en %.1fs" % (time.time() - t))
good = []
for x, y, r in found:
    for rr in (R - 2, R - 1, R, R + 1, R + 2):
        s = ring.scores(np.array([x]), np.array([y]), float(rr), relaxed=False)[0]
        if s >= 0.66:
            good.append((s, float(x), float(y), float(rr))); break
print(len(good), "pasan aro+letra+aislada")
# una por círculo
keep = []
for s, x, y, r in sorted(good, reverse=True):
    if all(math.hypot(x - k[1], y - k[2]) > 1.8 * R for k in keep): keep.append((s, x, y, r))
print(len(keep), "círculos distintos")
rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
for s, x, y, r in keep: cv2.circle(rgb, (int(x), int(y)), int(r) + 6, (0, 0, 255), 4)
cv2.imwrite(str(OUT / "radiales_candidatos.png"), cv2.resize(rgb[: int(rgb.shape[0] * 0.84)], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
print(sorted((int(x), int(y)) for s, x, y, r in keep))
