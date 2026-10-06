"""Compara lo que detecta el programa sobre el escaneo solo y sobre el escaneo fusionado con las fotos."""

import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.muros import detect_plan  # noqa: E402
from src.puertas import detect_doors  # noqa: E402
from src.ventanas import detect_windows  # noqa: E402
from src.vectorizer import binarize_ink  # noqa: E402

OUT = ROOT / "experimentos" / "resultados"
DPI = 300
bottom = float((OUT / "cajetin.txt").read_text())

for name in ("plano_300dpi.png", "fusion_plano.png"):
    image = cv2.imread(str(OUT / name), cv2.IMREAD_GRAYSCALE)
    t = time.time()
    walls, axes, arcs, thickness = detect_plan(image, DPI, ignore_bottom_fraction=bottom)
    doors = detect_doors(image, DPI, wall_thickness_px=thickness)
    windows = detect_windows(walls, binarize_ink(image, DPI), DPI, thickness or DPI / 25.4)
    print(f"{name:20s} muros={len(walls):3d} ejes={len(axes):2d} arcos={len(arcs):2d} puertas={len(doors):2d} ventanas={len(windows):2d} espesor={thickness}  ({time.time() - t:.0f}s)", flush=True)
