"""Carpeta de resultados ordenada: el plano, sus vistas previas, las fotos usadas y el PDF original.

    <nombre>/
        1_Plano_AutoCAD/   el .dwg (y el .dxf si se pidió)
        2_Vista_previa/    imagen del resultado y del escaneo, para verlos sin abrir AutoCAD
        3_Fotos_usadas/    las fotos que sí coincidieron con el plano
        4_PDF_original/    copia del PDF de entrada
        LEEME.txt          qué hay en cada carpeta y qué contiene cada plano
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

FOLDER_PLAN = "1_Plano_AutoCAD"
FOLDER_PREVIEW = "2_Vista_previa"
FOLDER_PHOTOS = "3_Fotos_usadas"
FOLDER_PDF = "4_PDF_original"
FOLDERS = (FOLDER_PLAN, FOLDER_PREVIEW, FOLDER_PHOTOS, FOLDER_PDF)

_README_HEADER = """RESULTADOS DE LA CONVERSION
===========================

  1_Plano_AutoCAD   El plano en formato AutoCAD (.dwg). Abrelo con AutoCAD.
  2_Vista_previa    Imagenes del resultado y del escaneo, para verlos sin abrir AutoCAD.
  3_Fotos_usadas    Las fotos de partes del plano que se usaron para leer mejor las cotas.
  4_PDF_original    Copia del PDF que se convirtio.

Planos convertidos:
"""


def copy_unique(source: Path, folder: Path) -> Path:
    """Copia `source` dentro de `folder`; si el nombre ya existe con otro contenido, agrega un número."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / source.name
    counter = 2
    while target.exists() and target.read_bytes() != source.read_bytes():
        target = folder / f"{source.stem}_{counter}{source.suffix}"
        counter += 1
    if not target.exists():
        shutil.copy2(source, target)
    return target


def save_scan_preview(image: np.ndarray, output_png: Path, max_px: int = 2400) -> Path:
    """Guarda el escaneo ya enderezado (gris), reducido a `max_px` de lado mayor."""
    output_png.parent.mkdir(parents=True, exist_ok=True)
    scale = max_px / max(image.shape[:2])
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(output_png), image)
    return output_png


def write_readme(root: Path, pdf_name: str, summary: dict[str, int], photos_used: int) -> Path:
    """Agrega una línea por plano al LEEME.txt de la carpeta de resultados."""
    readme = root / "LEEME.txt"
    if not readme.exists():
        readme.write_text(_README_HEADER, encoding="utf-8")
    contents = ", ".join(f"{count} {name}" for name, count in summary.items() if count)
    line = f"  - {pdf_name} ({datetime.now():%d/%m/%Y %H:%M}): {contents or 'sin detalle'}; fotos usadas: {photos_used}\n"
    with readme.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return readme
