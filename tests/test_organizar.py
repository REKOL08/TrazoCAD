from pathlib import Path

import cv2
import ezdxf
import numpy as np

from src.gui_logic import friendly_event
from src.organizar import FOLDER_PDF, copy_unique, save_scan_preview, write_readme
from src.vista_previa import render_dxf_preview


def _dxf_pequeno(ruta: Path, con_calco_apagado: bool = True) -> Path:
    doc = ezdxf.new("R2010")
    doc.layers.add("MUROS", color=5, lineweight=35)
    doc.layers.add("TEXTOS", color=1)
    doc.layers.add("CALCADO_REFERENCIA", color=8)
    if con_calco_apagado:
        doc.layers.get("CALCADO_REFERENCIA").off()
    msp = doc.modelspace()
    msp.add_line((0, 0), (200, 0), dxfattribs={"layer": "MUROS"})
    msp.add_lwpolyline([(0, 0), (0, 150), (200, 150)], dxfattribs={"layer": "MUROS"})
    msp.add_arc((100, 75), 40, 0, 90, dxfattribs={"layer": "MUROS"})
    msp.add_circle((50, 50), 10, dxfattribs={"layer": "MUROS"})
    msp.add_text("SALÓN", height=8, dxfattribs={"layer": "TEXTOS", "insert": (60, 100), "rotation": 30})
    msp.add_line((1000, 1000), (2000, 2000), dxfattribs={"layer": "CALCADO_REFERENCIA"})  # apagada: no cuenta
    doc.saveas(ruta)
    return ruta


def test_la_vista_previa_dibuja_el_dxf_y_no_las_capas_apagadas(tmp_path: Path) -> None:
    dxf = _dxf_pequeno(tmp_path / "plano.dxf")

    png = render_dxf_preview(dxf, tmp_path / "prev" / "plano.png", max_px=800)

    assert png is not None and png.exists()
    imagen = cv2.imread(str(png))
    assert max(imagen.shape[:2]) in range(790, 801)  # el lado mayor respeta el tamaño pedido
    assert (imagen < 200).any()  # hay trazos dibujados
    # la línea de la capa apagada (1000..2000) habría estirado el dibujo: el plano ocupa casi todo el lienzo
    oscuros = np.argwhere(imagen.min(axis=2) < 200)
    assert (oscuros.max(axis=0) - oscuros.min(axis=0)).max() > 600


def test_un_dxf_sin_nada_visible_no_da_vista_previa(tmp_path: Path) -> None:
    doc = ezdxf.new("R2010")
    doc.saveas(tmp_path / "vacio.dxf")

    assert render_dxf_preview(tmp_path / "vacio.dxf", tmp_path / "v.png") is None


def test_copy_unique_no_pisa_un_archivo_distinto_con_el_mismo_nombre(tmp_path: Path) -> None:
    carpeta = tmp_path / "originales"
    uno = tmp_path / "a" / "plano.pdf"
    dos = tmp_path / "b" / "plano.pdf"
    uno.parent.mkdir()
    dos.parent.mkdir()
    uno.write_bytes(b"uno")
    dos.write_bytes(b"dos")

    primero = copy_unique(uno, carpeta)
    repetido = copy_unique(uno, carpeta)
    distinto = copy_unique(dos, carpeta)

    assert primero == repetido == carpeta / "plano.pdf"
    assert distinto.name == "plano_2.pdf" and distinto.read_bytes() == b"dos"


def test_el_escaneo_se_guarda_reducido(tmp_path: Path) -> None:
    gris = np.full((3000, 4000), 200, np.uint8)

    png = save_scan_preview(gris, tmp_path / "v" / "escaneo.png", max_px=1000)

    assert cv2.imread(str(png), cv2.IMREAD_GRAYSCALE).shape == (750, 1000)


def test_el_leeme_acumula_una_linea_por_plano(tmp_path: Path) -> None:
    write_readme(tmp_path, "a.pdf", {"muros": 5, "ejes": 0}, 2)
    write_readme(tmp_path, "b.pdf", {"muros": 7}, 0)

    texto = (tmp_path / "LEEME.txt").read_text(encoding="utf-8")

    assert texto.count("RESULTADOS DE LA CONVERSION") == 1
    assert "a.pdf" in texto and "5 muros" in texto and "0 ejes" not in texto and "fotos usadas: 2" in texto
    assert "b.pdf" in texto and FOLDER_PDF in texto


def test_las_vistas_previas_y_fotos_usadas_llegan_como_eventos() -> None:
    linea = "2026-10-05 17:42:47 [INFO]   -> VISTA PREVIA: C:/x/2_Vista_previa/a_resultado.png"
    foto = "2026-10-05 17:42:47 [INFO]   -> FOTO USADA: C:/x/3_Fotos_usadas/f1.jpeg"

    assert friendly_event(linea, set()).kind == "preview"
    assert friendly_event(linea, set()).text == "C:/x/2_Vista_previa/a_resultado.png"
    assert friendly_event(foto, set()).kind == "photo"
