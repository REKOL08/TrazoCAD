import pickle, sys
from pathlib import Path
import cv2, numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.texto import read_texts
OUT = ROOT / "experimentos" / "resultados"
cache = OUT / "textos_fusion.pkl"
if cache.exists():
    texts = pickle.load(open(cache, "rb"))
else:
    img = cv2.imread(str(OUT / "fusion_plano.png"), cv2.IMREAD_GRAYSCALE)
    texts = read_texts(img, ignore_bottom_fraction=float((OUT / "cajetin.txt").read_text()))
    pickle.dump(texts, open(cache, "wb"))
sure = [t for t in texts if t.sure]; doubt = [t for t in texts if not t.sure]
print(len(texts), "textos:", len(sure), "seguros,", len(doubt), "dudosos")
def box(t): return t.quad[:, 0].min(), t.quad[:, 1].min(), t.quad[:, 0].max(), t.quad[:, 1].max()
def inter(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1])); return ix * iy
def area(a): return max((a[2] - a[0]) * (a[3] - a[1]), 1e-9)
over = []
for d in doubt:
    bd = box(d)
    hit = [s for s in sure if inter(bd, box(s)) / area(bd) >= 0.25]
    if hit: over.append((d.text, [h.text for h in hit]))
print(len(over), "dudosos encimados sobre uno seguro:")
for d, h in over[:30]: print("  ", repr(d), "sobre", h)
print("dudosos que no se encimen:", [t.text for t in doubt if not any(t.text == o[0] for o in over)][:30])
