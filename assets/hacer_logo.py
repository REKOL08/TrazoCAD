"""Genera el logo (assets/logo.png y assets/planos2dwg.ico). Se ejecuta una vez: python assets/hacer_logo.py"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
S = 2048  # se dibuja grande y se reduce para que los bordes salgan suaves


def gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        for x in range(size):
            px[x, y] = color
    return img


def build() -> Image.Image:
    base = gradient(S, (14, 78, 190), (6, 150, 214)).convert("RGBA")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((60, 60, S - 60, S - 60), radius=430, fill=255)

    art = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(art)
    # cuadrícula de plano técnico, muy tenue
    for k in range(180, S - 180, 220):
        d.line((k, 150, k, S - 150), fill=(255, 255, 255, 26), width=6)
        d.line((150, k, S - 150, k), fill=(255, 255, 255, 26), width=6)

    white = (255, 255, 255, 255)
    cyan = (150, 235, 255, 255)
    x0, y0, x1, y1 = 420, 470, 1630, 1480
    w = 64  # grosor de muro
    # muros exteriores con vano de puerta abajo
    d.rectangle((x0, y0, x1, y0 + w), fill=white)
    d.rectangle((x0, y0, x0 + w, y1), fill=white)
    d.rectangle((x1 - w, y0, x1, y1), fill=white)
    d.rectangle((x0, y1 - w, 900, y1), fill=white)
    d.rectangle((1150, y1 - w, x1, y1), fill=white)
    # muros interiores
    d.rectangle((1000, y0, 1000 + w // 2 + 8, 1000), fill=white)
    d.rectangle((x0, 1000, 1000, 1000 + w // 2 + 8), fill=white)
    # puerta con su arco de giro
    d.line((900, y1 - w // 2, 900, y1 - 330), fill=cyan, width=26)
    d.arc((900 - 330, y1 - w // 2 - 330, 900 + 330, y1 - w // 2 + 330), 270, 360, fill=cyan, width=22)
    # ventana arriba (tres líneas)
    for off in (-14, 0, 14):
        d.line((620, y0 + w // 2 + off, 860, y0 + w // 2 + off), fill=(14, 78, 190, 255), width=8)
    # cotas
    d.line((x0, y0 - 90, x1, y0 - 90), fill=cyan, width=14)
    for xx in (x0, x1):
        d.line((xx, y0 - 140, xx, y0 - 40), fill=cyan, width=14)
        d.polygon([(xx, y0 - 90), (xx + (46 if xx == x0 else -46), y0 - 118), (xx + (46 if xx == x0 else -46), y0 - 62)], fill=cyan)
    # flecha de "convertir" en esquina inferior derecha
    cx, cy, r = 1560, 1560, 270
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 196, 38, 255))
    d.line((cx - 120, cy, cx + 80, cy), fill=(30, 40, 70, 255), width=56)
    d.polygon([(cx + 40, cy - 110), (cx + 160, cy), (cx + 40, cy + 110)], fill=(30, 40, 70, 255))

    shadow = art.filter(ImageFilter.GaussianBlur(18))
    shadow = Image.composite(Image.new("RGBA", (S, S), (0, 20, 70, 110)), Image.new("RGBA", (S, S), (0, 0, 0, 0)), shadow.split()[3])
    base.alpha_composite(shadow, (0, 22))
    base.alpha_composite(art)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    return out


if __name__ == "__main__":
    logo = build()
    logo.resize((512, 512), Image.LANCZOS).save(HERE / "logo.png")
    logo.resize((44, 44), Image.LANCZOS).save(HERE / "logo_44.png")  # para la cabecera de la ventana
    sizes = [16, 24, 32, 48, 64, 128, 256]
    logo.resize((256, 256), Image.LANCZOS).save(HERE / "planos2dwg.ico", sizes=[(s, s) for s in sizes])
    print("ok")
