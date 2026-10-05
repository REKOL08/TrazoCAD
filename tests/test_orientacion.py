import cv2
import numpy as np
import pytest

from src.orientacion import detect_rotation, detect_title_block_fraction
from src.texto import ocr_available


def _plano_con_cajetin(alto: int = 1000, ancho: int = 1400) -> np.ndarray:
    image = np.full((alto, ancho), 255, dtype=np.uint8)
    cv2.line(image, (100, 300), (1300, 300), 0, 3)  # un muro largo arriba, solo
    for y in (800, 900, 950):  # pila de líneas largas: el recuadro del cajetín
        cv2.line(image, (50, y), (1350, y), 0, 3)
    return image


def test_detecta_el_cajetin_como_una_pila_de_lineas_largas() -> None:
    fraccion = detect_title_block_fraction(_plano_con_cajetin(), dpi=300)

    assert fraccion == pytest.approx((1000 - 800) / 1000 + 0.005, abs=0.01)


def test_una_sola_linea_larga_abajo_no_es_cajetin() -> None:
    image = np.full((1000, 1400), 255, dtype=np.uint8)
    cv2.line(image, (100, 800), (1300, 800), 0, 3)

    assert detect_title_block_fraction(image, dpi=300) == 0.0


def test_un_plano_sin_lineas_largas_no_tiene_cajetin() -> None:
    assert detect_title_block_fraction(np.full((1000, 1400), 255, dtype=np.uint8), dpi=300) == 0.0


def _hoja_con_palabras() -> np.ndarray:
    image = np.full((1100, 1100), 255, dtype=np.uint8)
    palabras = ["COCINA", "COMEDOR", "ALCOBA", "TERRAZA", "DEPOSITO", "PORCHE"]
    for k, palabra in enumerate(palabras):
        cv2.putText(image, palabra, (60 + 40 * (k % 2), 120 + 170 * k), cv2.FONT_HERSHEY_SIMPLEX, 2.2, 0, 4)
    return image


@pytest.mark.skipif(not ocr_available(), reason="rapidocr-onnxruntime no está instalado")
@pytest.mark.parametrize(
    "vueltas_antihorarias, giro_esperado",
    [(0, 0), (1, 270), (3, 90), (2, 180)],
)
def test_detecta_el_giro_de_la_pagina(vueltas_antihorarias: int, giro_esperado: int) -> None:
    hoja = np.ascontiguousarray(np.rot90(_hoja_con_palabras(), vueltas_antihorarias))

    assert detect_rotation(hoja, dpi=300) == giro_esperado


def test_sin_texto_no_se_gira(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import orientacion

    monkeypatch.setattr(orientacion, "ocr_available", lambda: False)

    assert detect_rotation(np.full((500, 500), 255, dtype=np.uint8), dpi=300) == 0
