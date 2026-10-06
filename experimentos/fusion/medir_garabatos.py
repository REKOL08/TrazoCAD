import math, pickle, sys
from pathlib import Path
import cv2, numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.detalle import detect_detail_strokes
OUT = ROOT / "experimentos" / "resultados"
img = cv2.imread(str(OUT / "fusion_plano.png"), cv2.IMREAD_GRAYSCALE)
walls, axes, arcs, th = pickle.load(open(OUT / "walls_fusion.pkl", "rb"))
texts = pickle.load(open(OUT / "textos_fusion.pkl", "rb"))
r0, r1, c0, c1 = 330, 1130, 560, 1460
crop = img[r0:r1, c0:c1]
explained = [((a[0] - c0, a[1] - r0), (b[0] - c0, b[1] - r0)) for a, b in list(walls) + list(axes)]
from src.texto import TextItem
shifted = [TextItem(t.text, t.confidence, t.quad - np.array([c0, r0]), t.sure) for t in texts]
strokes = detect_detail_strokes(crop, 300, explained, shifted)
def stats(s):
    p = np.array(s.points); seg = np.diff(p, axis=0); L = np.hypot(*seg.T).sum()
    ang = np.arctan2(seg[:, 1], seg[:, 0]); turn = np.abs((np.diff(ang) + np.pi) % (2 * np.pi) - np.pi).sum() if len(ang) > 1 else 0
    diag = math.hypot(*(p.max(0) - p.min(0)))
    return L, len(p), math.degrees(turn), diag
rows = sorted((stats(s) + (i,) for i, s in enumerate(strokes)), key=lambda r: r[0])
print("n=", len(strokes))
print("longitud(px) puntos giro_total(°) diagonal  | giro por mm | rectitud=diag/long")
import collections
bins = collections.Counter()
for L, n, turn, diag, i in rows:
    mm = L / 11.81
    straight = diag / max(L, 1e-9)
    kind = "recto" if n == 2 else ("curva suave" if straight > 0.9 else "garabato?")
    bins[(kind, "<10mm" if mm < 10 else "<25mm" if mm < 25 else ">=25mm")] += 1
for k, v in sorted(bins.items()): print(k, v)
pickle.dump((strokes, [stats(s) for s in strokes]), open(OUT / "trazos_zona.pkl", "wb"))
