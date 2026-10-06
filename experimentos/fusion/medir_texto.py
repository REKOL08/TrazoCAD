import re, sys, time
from pathlib import Path
import cv2
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.texto import read_texts
OUT = ROOT / "experimentos" / "resultados"
bottom = float((OUT / "cajetin.txt").read_text())
num = re.compile(r"^R?\d{1,2}[.,]\d{1,2}m?$")
for name in ("plano_300dpi.png", "fusion_plano.png"):
    img = cv2.imread(str(OUT / name), cv2.IMREAD_GRAYSCALE)
    t = time.time()
    texts = read_texts(img, ignore_bottom_fraction=bottom)
    print(f"{name:20s} textos={len(texts):3d} cotas={sum(1 for x in texts if num.match(x.text)):3d} ({time.time()-t:.0f}s)", flush=True)
