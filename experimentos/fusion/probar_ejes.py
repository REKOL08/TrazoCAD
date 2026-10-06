import pickle, sys
from pathlib import Path
import cv2
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.burbujas import find_axis_bubbles
from src.ejes import refine_axes
from src.vectorizer import binarize_ink
OUT = ROOT / "experimentos" / "resultados"
img = cv2.imread(str(OUT / "fusion_plano.png"), cv2.IMREAD_GRAYSCALE)
walls, axes, arcs, th = pickle.load(open(OUT / "walls_fusion.pkl", "rb"))
bottom = float((OUT / "cajetin.txt").read_text())
ink = binarize_ink(img, 300)
xs = [p[0] for w in walls for p in w]; ys = [p[1] for w in walls for p in w]
box = (min(xs), min(ys), max(xs), max(ys))
bubbles = find_axis_bubbles(img, ink, axes, 300, box, max_y=img.shape[0] * (1 - bottom))
new = refine_axes(axes, bubbles, ink > 0, box)
print(len(axes), "ejes antes ->", len(new), "ejes con burbuja")
rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
for a, b in new:
    cv2.line(rgb, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (0, 0, 255), 3)
for b in bubbles:
    cv2.circle(rgb, (int(b.x), int(b.y)), int(b.r), (255, 0, 0), 3)
cv2.imwrite(str(OUT / "ejes_final.png"), cv2.resize(rgb[: int(rgb.shape[0] * 0.84)], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
