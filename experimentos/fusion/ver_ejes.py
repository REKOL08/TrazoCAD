import math, pickle, sys
from pathlib import Path
import cv2
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
OUT = Path(__file__).resolve().parents[2] / "experimentos" / "resultados"
img = cv2.imread(str(OUT / "fusion_plano.png"), cv2.IMREAD_GRAYSCALE)
walls, axes, arcs, th = pickle.load(open(OUT / "walls_fusion.pkl", "rb"))
rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
for k, (a, b) in enumerate(axes):
    cv2.line(rgb, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (0, 0, 255), 3)
    mx, my = int((a[0] + b[0]) / 2), int((a[1] + b[1]) / 2)
    cv2.putText(rgb, str(k), (mx, my - 8), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (255, 0, 0), 4)
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180
    print(k, "len=%4d ang=%5.1f  (%4d,%4d)->(%4d,%4d)" % (math.dist(a, b), ang, *a, *b))
cv2.imwrite(str(OUT / "ejes_numerados.png"), cv2.resize(rgb[: int(rgb.shape[0] * 0.84)], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
