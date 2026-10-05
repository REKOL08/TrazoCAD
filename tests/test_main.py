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
    # un solo archivo por plano, con el nombre del PDF
    assert [p.name for p in salida_dir.iterdir()] == ["plano.dxf"]
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


def test_entrega_un_solo_archivo_por_plano_y_lo_reemplaza(tmp_path: Path) -> None:
    from src import converter

    pdf_path = tmp_path / "plano.pdf"
    _crear_pdf_sintetico(pdf_path)
    salida = tmp_path / "salida"

    primero = converter.convert_pdf(pdf_path, salida, dpi=150, generate_dwg=False, rotation=0)
    segundo = converter.convert_pdf(pdf_path, salida, dpi=150, generate_dwg=False, rotation=0)

    assert primero.success and segundo.success
    assert [p.name for p in salida.iterdir()] == ["plano.dxf"]
    assert primero.outputs == segundo.outputs == [salida / "plano.dxf"]


def test_si_el_archivo_anterior_esta_en_uso_guarda_otro_con_la_hora(tmp_path: Path) -> None:
    import os

    from src import converter

    pdf_path = tmp_path / "plano.pdf"
    _crear_pdf_sintetico(pdf_path)
    salida = tmp_path / "salida"
    salida.mkdir()
    bloqueado = salida / "plano.dxf"
    bloqueado.write_text("abierto en AutoCAD")
    os.chmod(bloqueado, 0o444)  # en Windows equivale a un archivo que no se puede sobrescribir

    try:
        resultado = converter.convert_pdf(pdf_path, salida, dpi=150, generate_dwg=False, rotation=0)
    finally:
        os.chmod(bloqueado, 0o666)

    assert resultado.success
    assert resultado.outputs[0].name != "plano.dxf"
    assert resultado.outputs[0].name.startswith("plano_")
    assert resultado.outputs[0].exists()


def test_el_resumen_cuenta_lo_detectado(tmp_path: Path) -> None:
    from src import converter

    pdf_path = tmp_path / "plano.pdf"
    _crear_pdf_sintetico(pdf_path)

    resultado = converter.convert_pdf(
        pdf_path, tmp_path / "salida", dpi=150, generate_dwg=False, rotation=0, read_text=False
    )

    assert set(resultado.summary) >= {"muros", "ejes", "arcos", "puertas", "textos"}
