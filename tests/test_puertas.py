import math

import cv2
import numpy as np

from src.puertas import detect_doors


def _plano_con_puerta(con_hoja: bool, con_muro: bool = True) -> np.ndarray:
    image = np.full((700, 900), 255, dtype=np.uint8)
    if con_muro:
        # jamba: muro grueso que llega hasta la bisagra
        cv2.rectangle(image, (150, 388), (300, 412), 0, -1)
    # cuarto de círculo de radio 100 px con centro (300, 400): de 0° a 90° (Y hacia arriba)
    cv2.ellipse(image, (300, 400), (100, 100), 0, -90, 0, 0, 2)
    if con_hoja:
        cv2.line(image, (300, 400), (300, 300), 0, 2)  # hoja abierta, perpendicular al muro
    return image


def test_detecta_el_arco_de_giro_de_una_puerta() -> None:
    puertas = detect_doors(_plano_con_puerta(con_hoja=False), dpi=300, wall_thickness_px=14)

    assert len(puertas) == 1
    arco = puertas[0].arc
    assert abs(arco.cx - 300) < 6 and abs(arco.cy - 400) < 6
    assert abs(arco.radius - 100) < 6
    assert puertas[0].leaf is None


def test_detecta_la_hoja_si_esta_dibujada() -> None:
    puertas = detect_doors(_plano_con_puerta(con_hoja=True), dpi=300, wall_thickness_px=14)

    assert len(puertas) == 1
    assert puertas[0].leaf is not None
    (hx, hy), (tx, ty) = puertas[0].leaf
    assert math.hypot(hx - 300, hy - 400) < 6
    assert abs(math.hypot(tx - hx, ty - hy) - 100) < 8


def test_una_circunferencia_completa_no_es_una_puerta() -> None:
    image = np.full((700, 900), 255, dtype=np.uint8)
    cv2.circle(image, (300, 400), 100, 0, 2)

    assert detect_doors(image, dpi=300, wall_thickness_px=14) == []


def test_un_trazo_recto_no_es_una_puerta() -> None:
    image = np.full((700, 900), 255, dtype=np.uint8)
    cv2.line(image, (100, 400), (800, 400), 0, 2)

    assert detect_doors(image, dpi=300, wall_thickness_px=14) == []


def test_un_arco_sin_muro_en_la_bisagra_no_es_puerta() -> None:
    image = _plano_con_puerta(con_hoja=False, con_muro=False)

    assert detect_doors(image, dpi=300, wall_thickness_px=14) == []
