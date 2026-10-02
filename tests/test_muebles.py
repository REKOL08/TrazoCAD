import cv2
import numpy as np

from src.muebles import detect_fixtures
from src.texto import TextItem

DPI = 300
ESPESOR = 12.0


def _etiqueta(texto: str, x: float, y: float) -> TextItem:
    caja = np.array([[x - 40, y - 8], [x + 40, y - 8], [x + 40, y + 8], [x - 40, y + 8]])
    return TextItem(texto, 0.9, caja)


def _plano_con_taza(x: int = 300, y: int = 300) -> np.ndarray:
    image = np.full((700, 900), 255, dtype=np.uint8)
    cv2.ellipse(image, (x, y), (22, 15), 30, 0, 360, 0, 3)  # taza: 44 x 30 px = 3.7T x 2.5T
    return image


def test_detecta_una_taza_dentro_de_un_bano() -> None:
    image = _plano_con_taza()

    fixtures = detect_fixtures(image, DPI, [_etiqueta("BAÑO", 330, 340)], wall_thickness_px=ESPESOR)

    assert len(fixtures) == 1
    f = fixtures[0]
    assert f.kind == "INODORO"
    assert abs(f.cx - 300) < 4 and abs(f.cy - 300) < 4
    assert 38 < f.major < 50 and 24 < f.minor < 36


def test_un_circulo_pequeno_es_un_lavamanos() -> None:
    image = np.full((700, 900), 255, dtype=np.uint8)
    cv2.circle(image, (300, 300), 17, 0, 3)  # 34 px = 2.8T

    fixtures = detect_fixtures(image, DPI, [_etiqueta("BAÑO", 330, 340)], wall_thickness_px=ESPESOR)

    assert [f.kind for f in fixtures] == ["LAVAMANOS"]


def test_una_elipse_lejos_de_un_bano_no_es_sanitario() -> None:
    image = _plano_con_taza(x=700, y=550)

    fixtures = detect_fixtures(image, DPI, [_etiqueta("BAÑO", 150, 100)], wall_thickness_px=ESPESOR)

    assert fixtures == []


def test_sin_etiqueta_de_bano_no_hay_sanitarios() -> None:
    image = _plano_con_taza()

    assert detect_fixtures(image, DPI, [_etiqueta("COMEDOR", 330, 340)], wall_thickness_px=ESPESOR) == []


def test_una_linea_fina_alargada_no_es_sanitario() -> None:
    image = np.full((700, 900), 255, dtype=np.uint8)
    cv2.ellipse(image, (300, 300), (30, 5), 0, 0, 360, 0, 2)  # sliver: relación 6

    fixtures = detect_fixtures(image, DPI, [_etiqueta("BAÑO", 330, 340)], wall_thickness_px=ESPESOR)

    assert fixtures == []
