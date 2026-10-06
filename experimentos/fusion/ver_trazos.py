"""Dibuja los trazos de DETALLE que el programa genera sobre un recorte del plano fusionado (para ver dónde sale sucio)."""
import pickle, sys, time
from pathlib import Path
import cv2, numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.detalle import detect_detail_strokes
OUT = ROOT / "experimentos" / "resultados"
name = sys.argv[1] if len(sys.argv) > 1 else "fusion_plano.png"
tag = sys.argv[2] if len(sys.argv) > 2 else "base"
img = cv2.imread(str(OUT / name), cv2.IMREAD_GRAYSCALE)
walls, axes, arcs, th = pickle.load(open(OUT / "walls_fusion.pkl", "rb"))
r0, r1, c0, c1 = 330, 1130, 560, 1460
crop = img[r0:r1, c0:c1]
explained = [((a[0] - c0, a[1] - r0), (b[0] - c0, b[1] - r0)) for a, b in list(walls) + list(axes)]
t = time.time()
strokes = detect_detail_strokes(crop, 300, explained, [])
print(len(strokes), "trazos en %.1fs" % (time.time() - t), "· puntos:", sum(len(s.points) for s in strokes))
vis = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
vis = cv2.addWeighted(vis, 0.35, np.full_like(vis, 255), 0.65, 0)
for s in strokes:
    pts = np.array(s.points, np.int32).reshape(-1, 1, 2)
    cv2.polylines(vis, [pts], s.closed, (0, 0, 220), 2)
    for p in s.points: cv2.circle(vis, (int(p[0]), int(p[1])), 2, (200, 0, 0), -1)
for a, b in explained:
    cv2.line(vis, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (0, 150, 0), 2)
cv2.imwrite(str(OUT / f"trazos_{tag}.png"), cv2.resize(vis, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC))
