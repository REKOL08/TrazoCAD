import cv2
import numpy as np

from src.deskew import deskew, estimate_skew_degrees
from src.muros import detect_walls_and_axes


def _plano_con_muro_doble() -> np.ndarray:
    image = np.full((900, 1200), 255, dtype=np.uint8)
    # un muro horizontal = dos caras paralelas a 14 px (unos 1.2 mm a 300 dpi)
    cv2.line(image, (200, 400), (1000, 400), 0, 3)
    cv2.line(image, (200, 414), (1000, 414), 0, 3)
    return image


def test_detecta_muro_como_dos_caras_paralelas() -> None:
    muros, _ejes = detect_walls_and_axes(_plano_con_muro_doble(), dpi=300)

    assert len(muros) >= 2
    ys = sorted({round((s[0][1] + s[1][1]) / 2) for s in muros})
    assert max(ys) - min(ys) in range(10, 19)
    # enderezado exacto a horizontal
    assert all(abs(s[0][1] - s[1][1]) < 1e-6 for s in muros)


def test_una_sola_linea_no_es_muro() -> None:
    image = np.full((900, 1200), 255, dtype=np.uint8)
    cv2.line(image, (200, 400), (1000, 400), 0, 3)

    muros, _ejes = detect_walls_and_axes(image, dpi=300)

    assert muros == []


def test_detecta_eje_de_trazo_y_punto() -> None:
    image = np.full((900, 1600), 255, dtype=np.uint8)
    x = 100
    while x < 1500:
        cv2.line(image, (x, 450), (x + 120, 450), 0, 3)  # raya larga
        cv2.line(image, (x + 150, 450), (x + 158, 450), 0, 3)  # punto
        x += 190

    _muros, ejes = detect_walls_and_axes(image, dpi=300)

    assert len(ejes) == 1
    (x1, _), (x2, _) = ejes[0]
    assert abs(x2 - x1) > 1000


def test_deskew_corrige_una_inclinacion_leve() -> None:
    image = _plano_con_muro_doble()
    for desplazamiento in (60, 120, 180):
        cv2.line(image, (200, 400 + desplazamiento), (1000, 400 + desplazamiento), 0, 3)
        cv2.line(image, (200 + desplazamiento, 100), (200 + desplazamiento, 800), 0, 3)
    height, width = image.shape
    matriz = cv2.getRotationMatrix2D((width / 2, height / 2), 1.2, 1.0)
    inclinada = cv2.warpAffine(image, matriz, (width, height), borderValue=255)

    estimada = estimate_skew_degrees(inclinada, dpi=300)
    corregida = estimate_skew_degrees(deskew(inclinada, dpi=300), dpi=300)

    assert 0.8 < abs(estimada) < 1.6
    assert abs(corregida) < abs(estimada) / 2
