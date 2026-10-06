import pickle, sys
from pathlib import Path
import cv2, numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "experimentos" / "resultados"
img = cv2.imread(str(OUT / "fusion_plano.png"), cv2.IMREAD_GRAYSCALE)
strokes, st = pickle.load(open(OUT / "trazos_zona.pkl", "rb"))
crop = img[330:1130, 560:1460]
vis = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
vis = cv2.addWeighted(vis, 0.3, np.full_like(vis, 255), 0.7, 0)
for s in strokes:
    pts = np.array(s.points, np.int32).reshape(-1, 1, 2)
    color = (0, 160, 0) if s.dashed else ((0, 0, 230) if len(s.points) == 2 else (200, 0, 200))
    cv2.polylines(vis, [pts], s.closed, color, 3)
cv2.imwrite(str(OUT / "trazos_clasificados.png"), cv2.resize(vis, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC))
