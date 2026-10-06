import pickle, sys
from pathlib import Path
import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.burbujas import find_axis_bubbles
from src.vectorizer import binarize_ink
OUT = ROOT / "experimentos" / "resultados"
img = cv2.imread(str(OUT / "fusion_plano.png"), cv2.IMREAD_GRAYSCALE)
walls, axes, arcs, th = pickle.load(open(OUT / "walls_fusion.pkl", "rb"))
bottom = float((OUT / "cajetin.txt").read_text())
ink = binarize_ink(img, 300)
xs = [p[0] for w in walls for p in w]; ys = [p[1] for w in walls for p in w]
bubbles = find_axis_bubbles(img, ink, axes, 300, (min(xs), min(ys), max(xs), max(ys)), max_y=img.shape[0] * (1 - bottom))

N = 32
def norm_glyph(binary):
    ys_, xs_ = np.nonzero(binary)
    if len(xs_) < 8: return None
    g = binary[ys_.min(): ys_.max() + 1, xs_.min(): xs_.max() + 1].astype(np.uint8) * 255
    h, w = g.shape
    s = (N - 4) / max(h, w)
    g = cv2.resize(g, (max(int(w * s), 1), max(int(h * s), 1)), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((N, N), np.uint8)
    oy, ox = (N - g.shape[0]) // 2, (N - g.shape[1]) // 2
    canvas[oy: oy + g.shape[0], ox: ox + g.shape[1]] = g
    return cv2.GaussianBlur(canvas, (3, 3), 0).astype(np.float32)

def templates(chars, font_name="arial.ttf"):
    out = {}
    for ch in chars:
        for thick in (0, 1, 2):
            im = Image.new("L", (120, 120), 0)
            font = ImageFont.truetype(font_name, 80)
            ImageDraw.Draw(im).text((20, 10), ch, font=font, fill=255, stroke_width=thick, stroke_fill=255)
            g = norm_glyph(np.array(im) > 128)
            if g is not None: out.setdefault(ch, []).append(g)
    return out

LETTERS = templates("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
DIGITS = templates("0123456789")
def glyph_of(b):
    r = int(b.r * 0.62)
    cx, cy = int(b.x), int(b.y)
    crop = img[cy - r: cy + r, cx - r: cx + r]
    bw = (crop < (np.percentile(crop, 12) + 55))
    # quitar el aro: solo el interior
    yy, xx = np.mgrid[-r:r, -r:r]
    bw &= (yy ** 2 + xx ** 2) < (0.88 * r) ** 2
    return norm_glyph(bw)
def classify(g, bank):
    if g is None: return None, 0
    scores = {}
    for ch, ts in bank.items():
        scores[ch] = max(float(np.corrcoef(g.ravel(), t.ravel())[0, 1]) for t in ts)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    return ranked[0], ranked[1]
for b in sorted(bubbles, key=lambda b: (b.direction, b.y if b.direction == "horizontal" else b.x)):
    bank = LETTERS if b.direction == "horizontal" else DIGITS
    best, second = classify(glyph_of(b), bank)
    print(b.direction[0], int(b.x), int(b.y), best, second)
