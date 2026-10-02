"""Rasterización de páginas PDF a imágenes para su posterior análisis.

Se usa PyMuPDF (paquete `pymupdf`, módulo `fitz`) en lugar de `pdf2image`
porque no depende de instalar Poppler por separado en Windows: es un único
paquete de pip con binarios incluidos, lo que mantiene la instalación en
un solo paso (`pip install -r requirements.txt`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz  # PyMuPDF (el alias "fitz" sigue funcionando pero está deprecado)
import numpy as np

from .utils import ConversionError

logger = logging.getLogger("planos2dwg")


@dataclass
class PageImage:
    """Una página rasterizada lista para procesar con OpenCV."""

    page_number: int
    image: np.ndarray  # imagen en escala de grises, forma (alto, ancho)
    dpi: int
    native_dpi: float | None = None  # resolución real del escaneo incrustado (None si es vectorial)


def _native_dpi(document: "fitz.Document", page: "fitz.Page") -> float | None:
    """Resolución real de la imagen más grande incrustada en la página.

    Renderizar a más dpi que esto solo interpola: no añade detalle. Un escaneo
    de 150 dpi tiene los textos pequeños (cotas) demasiado borrosos para leerlos.
    """
    best = 0.0
    for image in page.get_images(full=True):
        try:
            info = document.extract_image(image[0])
        except Exception:  # imagen que no se puede extraer: se ignora
            continue
        width_in = page.rect.width / 72.0
        if width_in > 0:
            best = max(best, info["width"] / width_in)
    return best or None


def render_pdf_pages(pdf_path: Path, dpi: int) -> list[PageImage]:
    """Convierte cada página de `pdf_path` en una imagen en escala de grises.

    Lanza ConversionError si el PDF está cifrado, corrupto o no tiene páginas.
    """
    try:
        document = fitz.open(pdf_path)
    except fitz.FileDataError as exc:
        raise ConversionError(f"El PDF está corrupto o no es válido: {pdf_path.name}") from exc
    except Exception as exc:  # cualquier otro fallo de apertura de fitz
        raise ConversionError(f"No se pudo abrir el PDF '{pdf_path.name}': {exc}") from exc

    try:
        if document.needs_pass:
            raise ConversionError(
                f"El PDF '{pdf_path.name}' está protegido con contraseña; "
                "quítale la protección antes de convertirlo."
            )

        if document.page_count == 0:
            raise ConversionError(f"El PDF '{pdf_path.name}' no tiene páginas.")

        zoom = dpi / 72.0  # 72 DPI es la resolución base interna de un PDF
        matrix = fitz.Matrix(zoom, zoom)

        pages: list[PageImage] = []
        for index in range(document.page_count):
            page = document.load_page(index)
            pixmap = page.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY, alpha=False)
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height, pixmap.width
            )
            pages.append(
                PageImage(
                    page_number=index + 1,
                    image=image.copy(),
                    dpi=dpi,
                    native_dpi=_native_dpi(document, page),
                )
            )
            logger.debug(
                "Página %d de %s rasterizada a %dx%d px (%d DPI)",
                index + 1,
                pdf_path.name,
                pixmap.width,
                pixmap.height,
                dpi,
            )

        return pages
    finally:
        document.close()
