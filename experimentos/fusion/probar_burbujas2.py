import pickle, sys, time
from pathlib import Path
import cv2
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.burbujas import find_axis_bubbles
from src.vectorizer import binarize_ink
OUT = ROOT / "experimentos" / "resultados"
img = cv2.imread(str(OUT / "fusion_plano.png"), cv2.IMREAD_GRAYSCALE)
walls, axes, arcs, th = pickle.load(open(OUT / "walls_fusion.pkl", "rb"))
ink = binarize_ink(img, 300)
bottom = float((OUT / "cajetin.txt").read_text())
t = time.time()
xs = [p[0] for w in walls for p in w]; ys = [p[1] for w in walls for p in w]
box = (min(xs), min(ys), max(xs), max(ys)); print('contenido', [int(v) for v in box])
g = find_axis_bubbles(img, ink, axes, 300, box, max_y=img.shape[0] * (1 - bottom))
print(len(g), "burbujas en %.1f s" % (time.time() - t))
rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
for b in g:
    cv2.circle(rgb, (int(b.x), int(b.y)), int(b.r) + 6, (0, 0, 255) if b.direction == "horizontal" else (255, 0, 0), 5)
cv2.imwrite(str(OUT / "burbujas_ok.png"), cv2.resize(rgb[: int(rgb.shape[0] * 0.84)], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
print(sorted((int(b.x), int(b.y), int(b.r), b.direction[0]) for b in g))
