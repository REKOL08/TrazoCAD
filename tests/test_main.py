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
    assert len(list(salida_dir.glob("plano_*.dxf"))) == 1
    # No debe dejar nada suelto junto al PDF original.
    assert not list(entrada_dir.glob("*.dxf"))
    assert not (entrada_dir / OUTPUT_SUBFOLDER_NAME).exists()


def test_rotate_image_gira_en_sentido_antihorario() -> None:
    import numpy as np

    from src.converter import rotate_image

    imagen = np.zeros((2, 4), dtype=np.uint8)

    assert rotate_image(imagen, 0).shape == (2, 4)
    assert rotate_image(imagen, 90).shape == (4, 2)
    assert rotate_image(imagen, 180).shape == (2, 4)


def test_cada_conversion_genera_un_archivo_nuevo_con_hora(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import converter

    pdf_path = tmp_path / "plano.pdf"
    _crear_pdf_sintetico(pdf_path)
    salida = tmp_path / "salida"
    marcas = iter(["20261002_100000", "20261002_100001"])
    monkeypatch.setattr(converter, "_timestamp", lambda: next(marcas))

    primero = converter.convert_pdf(pdf_path, salida, dpi=150, generate_dwg=False)
    segundo = converter.convert_pdf(pdf_path, salida, dpi=150, generate_dwg=False)

    assert primero.success and segundo.success
    assert primero.outputs[0].name == "plano_20261002_100000.dxf"
    assert segundo.outputs[0].name == "plano_20261002_100001.dxf"
    assert primero.outputs[0].exists() and segundo.outputs[0].exists()
