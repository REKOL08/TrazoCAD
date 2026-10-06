"""Paso 2: prueba (solo diagnóstico) del modelo FloorCAD YOLOv8n sobre el plano escaneado.

Mide cuántas puertas, ventanas y sanitarios encuentra con distintos ajustes y deja imágenes con las
cajas dibujadas en `experimentos/resultados/`. Se ejecuta con un entorno que tenga PyTorch y Ultralytics
(NO es el del proyecto: el producto final usará solo onnxruntime).
"""

import collections
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experimentos" / "resultados"
MODEL = ROOT / "modelos" / "floorcad-yolov8n-detect.pt"
KEYS = ("door", "window", "toilet", "sink", "stair", "bath")
COLORS = {"door": (0, 0, 255), "window": (255, 120, 0), "toilet": (0, 160, 0), "sink": (0, 170, 170)}

gray = cv2.imread(str(OUT / "plano_300dpi.png"), cv2.IMREAD_GRAYSCALE)
bottom = float((OUT / "cajetin.txt").read_text()) if (OUT / "cajetin.txt").exists() else 0.0
gray = gray[: int(gray.shape[0] * (1 - bottom))]
rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
model = YOLO(str(MODEL))
names = model.names


def interesting(counter: collections.Counter) -> dict:
    return {k: v for k, v in counter.items() if any(t in k.lower() for t in KEYS)}


def run_tiles(tile: int, overlap: float, imgsz: int, conf: float):
    found = []
    step = int(tile * (1 - overlap))
    for y0 in range(0, max(rgb.shape[0] - 1, 1), step):
        for x0 in range(0, max(rgb.shape[1] - 1, 1), step):
            crop = rgb[y0 : y0 + tile, x0 : x0 + tile]
            if min(crop.shape[:2]) < 200 or (crop < 128).mean() < 0.003:
                continue
            result = model.predict(crop, imgsz=imgsz, conf=conf, verbose=False)[0]
            for b, c, s in zip(result.boxes.xyxy.numpy(), result.boxes.cls.numpy(), result.boxes.conf.numpy()):
                found.append((b[0] + x0, b[1] + y0, b[2] + x0, b[3] + y0, int(c), float(s)))
    keep = []
    for b in sorted(found, key=lambda t: -t[5]):
        for k in keep:
            if k[4] != b[4]:
                continue
            ix, iy = max(0, min(k[2], b[2]) - max(k[0], b[0])), max(0, min(k[3], b[3]) - max(k[1], b[1]))
            inter = ix * iy
            union = (k[2] - k[0]) * (k[3] - k[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
            if union > 0 and inter / union > 0.4:
                break
        else:
            keep.append(b)
    return keep


def draw(items, tag):
    over = rgb.copy()
    for x0, y0, x1, y1, c, s in items:
        name = names[c].lower()
        key = next((k for k in COLORS if k in name), None)
        if key:
            color = COLORS[key]
            cv2.rectangle(over, (int(x0), int(y0)), (int(x1), int(y1)), color, 4)
            cv2.putText(over, f"{names[c][:9]} {s:.2f}", (int(x0), max(int(y0) - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
    target = OUT / f"vision_{tag}.png"
    cv2.imwrite(str(target), cv2.resize(over, None, fx=0.45, fy=0.45, interpolation=cv2.INTER_AREA))
    return target


summary = {}
for label, tile, overlap, imgsz, conf in (
    ("mosaicos 1100 px", 1100, 0.25, 640, 0.25),
    ("mosaicos 800 px", 800, 0.25, 640, 0.25),
    ("mosaicos 800 px, confianza baja", 800, 0.25, 640, 0.15),
):
    items = run_tiles(tile, overlap, imgsz, conf)
    counts = collections.Counter(names[b[4]] for b in items)
    summary[label] = interesting(counts)
    print(f"[{label}] total={len(items)}  de interés: {interesting(counts)}", flush=True)
    draw(items, label.replace(" ", "_").replace(",", ""))

(OUT / "vision_resumen.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print("listo")
