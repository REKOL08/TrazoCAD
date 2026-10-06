from pathlib import Path

import cv2
import ezdxf
import numpy as np

from src.burbujas import Bubble, find_axis_bubbles, read_labels
from src.dxf_writer import LAYER_AXES, build_dxf
from src.ejes import refine_axes
from src.vectorizer import binarize_ink

DPI = 300
RADIUS = 20
LETTER_ROWS = [150, 400, 650, 900]  # y de las burbujas A, B, C, D (columna izquierda)
BUBBLE_X = 100
CONTENT = (300.0, 100.0, 1000.0, 1100.0)  # x0, y0, x1, y1 de los muros


def _dash_dot(image: np.ndarray, y: int, x0: int, x1: int) -> None:
    x = x0
    while x < x1:
        cv2.line(image, (x, y), (min(x + 60, x1), y), 0, 2)
        cv2.circle(image, (min(x + 75, x1), y), 2, 0, -1)
        x += 100


def _plan() -> np.ndarray:
    """Un plano con 4 ejes horizontales con burbuja (A-D) y dos líneas largas falsas, sin burbuja."""
    image = np.full((1300, 1200), 255, np.uint8)
    for letter, y in zip("ABCD", LETTER_ROWS):
        cv2.circle(image, (BUBBLE_X, y), RADIUS, 150, 1, cv2.LINE_AA)  # aro fino y claro, como en el escaneo
        cv2.putText(image, letter, (BUBBLE_X - 9, y + 9), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2, cv2.LINE_AA)
        _dash_dot(image, y, BUBBLE_X + RADIUS + 2, 1000)
    cv2.rectangle(image, (300, 100), (1000, 1100), 0, 3)  # los muros
    cv2.line(image, (500, 120), (500, 1080), 0, 2)  # línea larga vertical dentro del plano: no es un eje
    return image


def _axes_detected() -> list:
    """Lo que el trazado entregaría: los 4 ejes buenos, una línea falsa dentro y una larga sin burbuja a la izquierda."""
    good = [((BUBBLE_X + RADIUS + 2, float(y)), (1000.0, float(y))) for y in LETTER_ROWS]
    false_inside = ((500.0, 120.0), (500.0, 1080.0))
    false_margin = ((60.0, 200.0), (60.0, 800.0))  # vertical en el margen, sin burbuja
    return good + [false_inside, false_margin]


def test_encuentra_las_burbujas_de_la_columna_de_ejes() -> None:
    image = _plan()
    bubbles = find_axis_bubbles(image, binarize_ink(image, DPI), _axes_detected(), DPI, CONTENT)

    assert len(bubbles) == 4
    assert sorted(round(b.y / 50) for b in bubbles) == sorted(round(y / 50) for y in LETTER_ROWS)
    assert all(abs(b.x - BUBBLE_X) <= 8 and abs(b.r - RADIUS) <= 3 and b.direction == "horizontal" for b in bubbles)


def test_un_circulo_suelto_en_el_plano_no_es_una_burbuja_de_eje() -> None:
    image = _plan()
    cv2.circle(image, (650, 600), RADIUS, 0, 2)  # un inodoro, una mesa...
    bubbles = find_axis_bubbles(image, binarize_ink(image, DPI), _axes_detected(), DPI, CONTENT)

    assert all(abs(b.x - BUBBLE_X) <= 8 for b in bubbles)


def test_los_ejes_sin_burbuja_se_descartan_y_los_demas_quedan_rectos() -> None:
    image = _plan()
    ink = binarize_ink(image, DPI)
    bubbles = find_axis_bubbles(image, ink, _axes_detected(), DPI, CONTENT)

    axes = refine_axes(_axes_detected(), bubbles, ink > 0, CONTENT)

    assert len(axes) == 4  # ni la línea de dentro ni la del margen
    for (x1, y1), (x2, y2) in axes:
        assert abs(y1 - y2) < 1e-6  # rectos
        assert x1 < 200 and x2 > 900  # salen de la burbuja y cruzan el plano
        assert min(abs(y1 - y) for y in LETTER_ROWS) <= 8


def test_si_no_hay_burbujas_los_ejes_se_dejan_como_estaban() -> None:
    image = np.full((600, 600), 255, np.uint8)
    axes = [((10.0, 100.0), (500.0, 100.0))]

    assert refine_axes(axes, [], image > 0, (0, 0, 600, 600)) == axes


def test_las_letras_de_la_columna_se_leen_en_orden() -> None:
    image = _plan()
    bubbles = [Bubble(float(BUBBLE_X), float(y), float(RADIUS), "horizontal") for y in LETTER_ROWS]

    assert read_labels(image, bubbles) == ["A", "B", "C", "D"]


def test_sin_suficientes_letras_no_se_inventan_etiquetas() -> None:
    image = _plan()

    assert read_labels(image, [Bubble(100.0, 150.0, 20.0, "horizontal")]) == [""]
    assert read_labels(image, []) == []


def test_el_dxf_lleva_la_burbuja_como_circulo_continuo_y_la_letra(tmp_path: Path) -> None:
    salida = tmp_path / "ejes.dxf"

    build_dxf([], dpi=300, image_height_px=1000, output_path=salida, axes=[((100.0, 500.0), (900.0, 500.0))],
              axis_bubbles=[(80.0, 500.0, 20.0, "A"), (700.0, 100.0, 20.0, "")])

    modelspace = ezdxf.readfile(salida).modelspace()
    circulos = list(modelspace.query("CIRCLE"))
    assert len(circulos) == 2 and all(c.dxf.layer == LAYER_AXES and c.dxf.linetype == "CONTINUOUS" for c in circulos)
    textos = list(modelspace.query("TEXT"))
    assert [t.dxf.text for t in textos] == ["A"] and textos[0].dxf.layer == LAYER_AXES


def _plan_con_radiales() -> np.ndarray:
    """Dos ejes radiales (burbujas con letra) que se cruzan en el centro, más un círculo con letra sin eje (una mesa)."""
    image = np.full((1400, 1400), 255, np.uint8)
    centro = (700, 700)
    for letra, angulo in (("7", -70), ("9", 20), ("11", 125)):
        rad = np.deg2rad(angulo)
        bx, by = int(700 + 520 * np.cos(rad)), int(700 + 520 * np.sin(rad))
        cv2.circle(image, (bx, by), RADIUS, 150, 1, cv2.LINE_AA)
        cv2.putText(image, letra[0], (bx - 7, by + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2, cv2.LINE_AA)
        # línea de trazo y punto desde la burbuja hasta el centro
        for t in np.arange(RADIUS + 4, 520, 40):
            a = (int(bx - np.cos(rad) * t), int(by - np.sin(rad) * t))
            b = (int(bx - np.cos(rad) * min(t + 28, 520)), int(by - np.sin(rad) * min(t + 28, 520)))
            cv2.line(image, a, b, 0, 2)
    cv2.circle(image, (200, 200), RADIUS, 150, 1, cv2.LINE_AA)
    cv2.putText(image, "A", (193, 208), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2, cv2.LINE_AA)  # una mesa con letra: sin eje
    return image


def test_los_ejes_radiales_salen_de_su_burbuja_y_se_cruzan_en_el_centro() -> None:
    from src.burbujas import find_loose_bubbles
    from src.ejes import radial_axes

    image = _plan_con_radiales()
    ink = binarize_ink(image, DPI)

    loose = find_loose_bubbles(image, ink, float(RADIUS), [])
    bubbles, segments, aligned = radial_axes(loose, ink > 0)

    assert len(bubbles) == 3 and len(segments) == 3 and not aligned  # la mesa de la esquina no es burbuja
    for (inicio, fin), bubble in zip(segments, bubbles):
        assert abs(fin[0] - 700) < 25 and abs(fin[1] - 700) < 25  # todos llegan al centro común
        assert np.hypot(inicio[0] - bubble.x, inicio[1] - bubble.y) <= RADIUS + 3  # y salen del borde de su círculo


def test_el_eje_sin_burbuja_detectada_recibe_su_circulo_alineado_con_las_demas() -> None:
    from src.ejes import complete_bubbles

    fila = [Bubble(300.0, 30.0, 20.0, "vertical"), Bubble(500.0, 34.0, 20.0, "vertical")]
    ejes = [((300.0, 50.0), (300.0, 900.0)), ((400.0, 6.0), (400.0, 900.0)), ((700.0, 300.0), (700.0, 800.0))]

    nuevos_ejes, anadidas = complete_bubbles(ejes, fila, 20.0)

    assert len(anadidas) == 1 and abs(anadidas[0].x - 400.0) < 1e-6 and abs(anadidas[0].y - 32.0) < 3
    assert nuevos_ejes[1][0][1] > 32.0  # el eje arranca en el borde del círculo, no dentro
    assert nuevos_ejes[2] == ejes[2]  # el eje que no llega a la fila queda igual
