import pickle, sys, time
from pathlib import Path
import cv2
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.converter import _axes_with_bubbles
from src.vectorizer import binarize_ink
OUT = ROOT / "experimentos" / "resultados"
img = cv2.imread(str(OUT / "fusion_plano.png"), cv2.IMREAD_GRAYSCALE)
walls, axes, arcs, th = pickle.load(open(OUT / "walls_fusion.pkl", "rb"))
bottom = float((OUT / "cajetin.txt").read_text())
ink = binarize_ink(img, 300)
t = time.time()
new_axes, bubbles, labels = _axes_with_bubbles(img, ink, walls, axes, 300, bottom)
print("%.1fs: %d ejes, %d burbujas, etiquetas %s" % (time.time() - t, len(new_axes), len(bubbles), "".join(l or "·" for l in labels)))
rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
for a, b in new_axes: cv2.line(rgb, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (0, 0, 255), 3)
for b in bubbles: cv2.circle(rgb, (int(b.x), int(b.y)), int(b.r), (255, 0, 0), 3)
cv2.imwrite(str(OUT / "cuadricula.png"), cv2.resize(rgb[: int(rgb.shape[0] * 0.84)], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
