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


def _pdf_con_escaneo(path: Path, ancho_px: int, alto_px: int) -> None:
    import cv2
    import numpy as np

    imagen = np.full((alto_px, ancho_px), 255, dtype=np.uint8)
    cv2.line(imagen, (50, 50), (ancho_px - 50, 50), 0, 3)
    _, png = cv2.imencode(".png", imagen)
    documento = fitz.open()
    pagina = documento.new_page(width=612, height=792)  # 8.5 x 11 pulgadas
    pagina.insert_image(pagina.rect, stream=png.tobytes())
    documento.save(path)
    documento.close()


def test_calcula_la_resolucion_real_del_escaneo_incrustado(tmp_path: Path) -> None:
    pdf_path = tmp_path / "escaneo.pdf"
    _pdf_con_escaneo(pdf_path, 1275, 1650)

    paginas = render_pdf_pages(pdf_path, dpi=300)

    assert paginas[0].native_dpi == pytest.approx(150.0, abs=1.0)
    assert paginas[0].dpi == 300


def test_un_pdf_vectorial_no_tiene_resolucion_nativa(tmp_path: Path) -> None:
    pdf_path = tmp_path / "vectorial.pdf"
    _crear_pdf_sintetico(pdf_path)

    assert render_pdf_pages(pdf_path, dpi=150)[0].native_dpi is None


def test_avisa_si_el_escaneo_es_de_poca_resolucion(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from src.converter import convert_pdf

    pdf_path = tmp_path / "escaneo.pdf"
    _pdf_con_escaneo(pdf_path, 1275, 1650)

    with caplog.at_level(logging.WARNING, logger="planos2dwg"):
        convert_pdf(pdf_path, tmp_path / "salida", dpi=150, generate_dwg=False, read_text=False)

    assert any("150 dpi reales" in mensaje for mensaje in caplog.messages)


def test_no_avisa_si_el_escaneo_es_nitido(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from src.converter import convert_pdf

    pdf_path = tmp_path / "nitido.pdf"
    _pdf_con_escaneo(pdf_path, 2550, 3300)  # 300 dpi

    with caplog.at_level(logging.WARNING, logger="planos2dwg"):
        convert_pdf(pdf_path, tmp_path / "salida", dpi=150, generate_dwg=False, read_text=False)

    assert not any("dpi reales" in mensaje for mensaje in caplog.messages)
