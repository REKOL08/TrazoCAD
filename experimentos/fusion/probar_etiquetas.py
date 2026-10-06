import pickle, sys
from pathlib import Path
import cv2
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.burbujas import find_axis_bubbles, read_labels
from src.vectorizer import binarize_ink
OUT = ROOT / "experimentos" / "resultados"
img = cv2.imread(str(OUT / "fusion_plano.png"), cv2.IMREAD_GRAYSCALE)
walls, axes, arcs, th = pickle.load(open(OUT / "walls_fusion.pkl", "rb"))
bottom = float((OUT / "cajetin.txt").read_text())
ink = binarize_ink(img, 300)
xs = [p[0] for w in walls for p in w]; ys = [p[1] for w in walls for p in w]
bubbles = find_axis_bubbles(img, ink, axes, 300, (min(xs), min(ys), max(xs), max(ys)), max_y=img.shape[0] * (1 - bottom))
labels = read_labels(img, bubbles)
for b, l in sorted(zip(bubbles, labels), key=lambda t: (t[0].direction, t[0].x if t[0].direction == "vertical" else t[0].y)):
    print(b.direction[0], int(b.x), int(b.y), repr(l))
