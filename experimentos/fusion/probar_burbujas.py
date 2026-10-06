import sys
from pathlib import Path
import cv2, numpy as np
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experimentos" / "resultados"
img = cv2.imread(str(OUT / "fusion_plano.png"), cv2.IMREAD_GRAYSCALE)
blur = cv2.GaussianBlur(img, (5, 5), 1.2)
for p2 in (22, 28, 35):
    c = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30, param1=110, param2=p2, minRadius=14, maxRadius=30)
    print("param2", p2, "->", 0 if c is None else c.shape[1], "círculos")
c = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30, param1=110, param2=28, minRadius=14, maxRadius=30)[0]
rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
for x, y, r in c:
    cv2.circle(rgb, (int(x), int(y)), int(r), (0, 0, 255), 3)
cv2.imwrite(str(OUT / "burbujas_hough.png"), cv2.resize(rgb[: int(rgb.shape[0] * 0.84)], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
print(sorted((int(x), int(y), int(r)) for x, y, r in c)[:60])
