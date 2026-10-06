"""Paso 1 de la prueba de visión: deja el plano derecho (girado y enderezado) como imagen PNG.

Se ejecuta con el entorno del proyecto:
    .venv\\Scripts\\python.exe experimentos\\vision\\preparar_plano.py "C:\\ruta\\plano.pdf"
"""

import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.converter import rotate_image  # noqa: E402
from src.deskew import deskew  # noqa: E402
from src.orientacion import detect_rotation, detect_title_block_fraction  # noqa: E402
from src.pdf_processor import render_pdf_pages  # noqa: E402

OUT = ROOT / "experimentos" / "resultados"


def main(pdf: str, dpi: int = 300) -> None:
    page = render_pdf_pages(Path(pdf), dpi=dpi)[0]
    rotation = detect_rotation(page.image, page.dpi)
    image = deskew(rotate_image(page.image, rotation), page.dpi)
    bottom = detect_title_block_fraction(image, page.dpi)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "plano_300dpi.png"
    cv2.imwrite(str(target), image)
    print(f"plano guardado: {target}  tamaño={image.shape[::-1]}  giro={rotation}  cajetin={bottom:.2f}")
    (OUT / "cajetin.txt").write_text(f"{bottom:.4f}", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
