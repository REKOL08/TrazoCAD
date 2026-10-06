import pickle, sys
from pathlib import Path
import cv2
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.burbujas import find_loose_bubbles
from src.ejes import radial_axes
from src.vectorizer import binarize_ink
OUT = ROOT / "experimentos" / "resultados"
img = cv2.imread(str(OUT / "fusion_plano.png"), cv2.IMREAD_GRAYSCALE)
bottom = float((OUT / "cajetin.txt").read_text())
ink = binarize_ink(img, 300)
loose = find_loose_bubbles(img, ink, 21.0, [], max_y=img.shape[0] * (1 - bottom))
print(len(loose), "burbujas sueltas")
bubbles, segs = radial_axes(loose, ink > 0)
print(len(bubbles), "confirmadas")
rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
for b in loose: cv2.circle(rgb, (int(b.x), int(b.y)), int(b.r) + 5, (0, 160, 255), 3)
for b in bubbles: cv2.circle(rgb, (int(b.x), int(b.y)), int(b.r) + 5, (255, 0, 0), 4)
for a, b in segs: cv2.line(rgb, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (0, 0, 255), 3)
cv2.imwrite(str(OUT / "radiales_ejes.png"), cv2.resize(rgb[: int(rgb.shape[0] * 0.84)], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
