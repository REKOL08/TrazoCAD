from pathlib import Path

import pymupdf
import pytest

import main
from src.utils import OUTPUT_SUBFOLDER_NAME


def _crear_pdf_sintetico(path: Path) -> None:
    documento = pymupdf.open()
    pagina = documento.new_page(width=200, height=200)
    pagina.draw_line((20, 20), (180, 20))
    pagina.draw_line((20, 20), (20, 180))
    documento.save(path)
    documento.close()


def test_main_guarda_resultados_en_subcarpeta_del_programa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Los PDF de entrada viven en una carpeta distinta a la del programa
    # (como C:\Users\...\Downloads), para comprobar que la salida NO se
    # crea junto al PDF sino siempre dentro de la carpeta del programa.
    entrada_dir = tmp_path / "entrada"
    entrada_dir.mkdir()
    programa_dir = tmp_path / "programa"
    programa_dir.mkdir()
    monkeypatch.setattr(main, "PROJECT_ROOT", programa_dir)

    pdf_path = entrada_dir / "plano.pdf"
    _crear_pdf_sintetico(pdf_path)

    exit_code = main.main([str(pdf_path), "--no-dwg"])

    assert exit_code == 0
    salida_dir = programa_dir / OUTPUT_SUBFOLDER_NAME
    assert salida_dir.is_dir()
    assert (salida_dir / "plano.dxf").exists()
    # No debe dejar nada suelto junto al PDF original.
    assert not (entrada_dir / "plano.dxf").exists()
    assert not (entrada_dir / OUTPUT_SUBFOLDER_NAME).exists()
