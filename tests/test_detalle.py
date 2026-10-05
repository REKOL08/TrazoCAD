import cv2
import numpy as np

from src.detalle import detect_detail_lines
from src.muros import _lsd_segments
from src.texto import TextItem

DPI = 300


def _imagen_con_linea(x1=100, x2=400, y=300, grosor=3) -> np.ndarray:
    image = np.full((600, 800), 255, dtype=np.uint8)
    cv2.line(image, (x1, y), (x2, y), 0, grosor)
    return image


def test_una_linea_fina_sale_como_un_solo_trazo_recto() -> None:
    lineas = detect_detail_lines(_imagen_con_linea(), DPI, explained=[], texts=[])

    assert len(lineas) == 1
    (x1, y1), (x2, y2) = lineas[0]
    assert abs(y1 - y2) < 1e-6  # enderezada a horizontal exacta
    assert abs(abs(x2 - x1) - 300) < 12


def test_lo_que_ya_esta_dibujado_en_otra_capa_no_se_repite() -> None:
    muro = [((100.0, 300.0), (400.0, 300.0))]

    assert detect_detail_lines(_imagen_con_linea(), DPI, explained=muro, texts=[]) == []


def test_los_trazos_cortos_se_descartan_como_ruido() -> None:
    corta = _imagen_con_linea(x1=100, x2=118)  # 18 px = 1.5 mm, menos que el mínimo

    assert detect_detail_lines(corta, DPI, explained=[], texts=[]) == []


def test_lo_que_cae_sobre_un_texto_leido_no_es_detalle() -> None:
    caja = np.array([[90.0, 270.0], [420.0, 270.0], [420.0, 330.0], [90.0, 330.0]])
    texto = TextItem("COCINA", 0.9, caja, sure=True)

    assert detect_detail_lines(_imagen_con_linea(), DPI, explained=[], texts=[texto]) == []


def test_la_cache_de_segmentos_no_mezcla_imagenes_distintas() -> None:
    una = _imagen_con_linea(y=200)
    otra = _imagen_con_linea(y=400)

    primero = _lsd_segments(una, DPI)
    segundo = _lsd_segments(otra, DPI)
    primero[:] = 0  # modificar la copia no debe alterar la caché
    de_nuevo = _lsd_segments(una, DPI)

    assert abs(segundo[:, 1].mean() - 400) < 6
    assert abs(de_nuevo[:, 1].mean() - 200) < 6
