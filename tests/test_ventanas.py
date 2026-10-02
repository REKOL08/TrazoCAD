import cv2
import numpy as np

from src.puertas import binarize_ink
from src.ventanas import detect_windows

DPI = 300
ESPESOR = 14.0


def _muro_con_hueco(lineas_dentro: bool):
    """Muro horizontal de dos caras (y=300 e y=314) interrumpido entre x=400 y x=560."""
    image = np.full((700, 1000), 255, dtype=np.uint8)
    caras = []
    for y in (300, 314):
        for x1, x2 in ((100, 400), (560, 900)):
            cv2.line(image, (x1, y), (x2, y), 0, 3)
            caras.append(((float(x1), float(y)), (float(x2), float(y))))
    if lineas_dentro:
        for y in (300, 307, 314):  # cara, centro, cara a través del hueco
            cv2.line(image, (400, y), (560, y), 0, 2)
    return image, caras


def test_detecta_un_hueco_con_lineas_finas_como_ventana() -> None:
    image, caras = _muro_con_hueco(lineas_dentro=True)

    ventanas = detect_windows(caras, binarize_ink(image, DPI), DPI, ESPESOR)

    assert len(ventanas) == 1
    xs = sorted(p[0] for linea in ventanas[0].lines[:3] for p in linea)
    assert abs(xs[0] - 400) < 8 and abs(xs[-1] - 560) < 8
    assert len(ventanas[0].lines) == 5  # tres líneas y dos jambas


def test_un_hueco_vacio_no_es_ventana() -> None:
    image, caras = _muro_con_hueco(lineas_dentro=False)

    assert detect_windows(caras, binarize_ink(image, DPI), DPI, ESPESOR) == []


def test_un_muro_continuo_no_tiene_ventanas() -> None:
    image = np.full((700, 1000), 255, dtype=np.uint8)
    caras = []
    for y in (300, 314):
        cv2.line(image, (100, y), (900, y), 0, 3)
        caras.append(((100.0, float(y)), (900.0, float(y))))

    assert detect_windows(caras, binarize_ink(image, DPI), DPI, ESPESOR) == []
