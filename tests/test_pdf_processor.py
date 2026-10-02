from pathlib import Path

import pymupdf as fitz
import pytest

from src.pdf_processor import render_pdf_pages
from src.utils import ConversionError


def _crear_pdf_sintetico(path: Path, paginas: int = 1) -> None:
    documento = fitz.open()
    for _ in range(paginas):
        pagina = documento.new_page(width=200, height=200)
        pagina.draw_line((20, 20), (180, 20))
    documento.save(path)
    documento.close()


def test_render_pdf_pages_devuelve_una_imagen_por_pagina(tmp_path: Path) -> None:
    pdf_path = tmp_path / "plano.pdf"
    _crear_pdf_sintetico(pdf_path, paginas=2)

    paginas = render_pdf_pages(pdf_path, dpi=150)

    assert len(paginas) == 2
    assert paginas[0].image.ndim == 2
    assert paginas[0].dpi == 150


def test_render_pdf_pages_pdf_corrupto_lanza_error(tmp_path: Path) -> None:
    pdf_path = tmp_path / "corrupto.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nesto no es un pdf valido")

    with pytest.raises(ConversionError):
        render_pdf_pages(pdf_path, dpi=150)
