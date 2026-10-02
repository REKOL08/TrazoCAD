from pathlib import Path

import pymupdf

import main
from src.utils import OUTPUT_SUBFOLDER_NAME


def _crear_pdf_sintetico(path: Path) -> None:
    documento = pymupdf.open()
    pagina = documento.new_page(width=200, height=200)
    pagina.draw_line((20, 20), (180, 20))
    pagina.draw_line((20, 20), (20, 180))
    documento.save(path)
    documento.close()


def test_main_guarda_resultados_en_subcarpeta_automatica(tmp_path: Path) -> None:
    pdf_path = tmp_path / "plano.pdf"
    _crear_pdf_sintetico(pdf_path)

    exit_code = main.main([str(pdf_path), "--no-dwg"])

    assert exit_code == 0
    salida_dir = tmp_path / OUTPUT_SUBFOLDER_NAME
    assert salida_dir.is_dir()
    assert (salida_dir / "plano.dxf").exists()
    # No debe dejar nada suelto junto al PDF original.
    assert not (tmp_path / "plano.dxf").exists()
