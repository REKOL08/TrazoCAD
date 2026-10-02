import numpy as np

from src.line_detector import detect_lines, filter_short_segments, merge_collinear_segments


def _imagen_con_lineas() -> np.ndarray:
    """Genera una imagen sintética en blanco con dos líneas negras gruesas."""
    import cv2

    image = np.full((200, 200), 255, dtype=np.uint8)
    cv2.line(image, (20, 20), (180, 20), color=0, thickness=3)
    cv2.line(image, (20, 20), (20, 180), color=0, thickness=3)
    return image


def test_detect_lines_encuentra_segmentos_en_imagen_sintetica() -> None:
    image = _imagen_con_lineas()

    segmentos = detect_lines(image, min_line_length=30, max_line_gap=5)

    assert len(segmentos) > 0


def test_detect_lines_imagen_en_blanco_no_encuentra_nada() -> None:
    image = np.full((200, 200), 255, dtype=np.uint8)

    segmentos = detect_lines(image)

    assert segmentos == []


def test_detect_lines_rechaza_imagen_a_color() -> None:
    image_color = np.zeros((10, 10, 3), dtype=np.uint8)

    try:
        detect_lines(image_color)
        assert False, "debía lanzar ValueError para una imagen a color"
    except ValueError:
        pass


def test_merge_collinear_segments_fusiona_fragmentos_de_un_mismo_muro() -> None:
    # Tres fragmentos del mismo eje horizontal (y=10), con pequeños huecos
    # entre ellos, como los que deja un escaneo con cotas/texto encima.
    fragmentos = [
        ((0.0, 10.0), (50.0, 10.0)),
        ((55.0, 10.0), (100.0, 10.0)),
        ((104.0, 10.0), (200.0, 10.0)),
    ]

    fusionados = merge_collinear_segments(fragmentos, dpi=300)

    assert len(fusionados) == 1
    (x1, _), (x2, _) = fusionados[0]
    assert min(x1, x2) == 0.0
    assert max(x1, x2) == 200.0


def test_merge_collinear_segments_no_fusiona_lineas_de_distinto_angulo() -> None:
    horizontal = ((0.0, 0.0), (50.0, 0.0))
    vertical = ((0.0, 0.0), (0.0, 50.0))

    fusionados = merge_collinear_segments([horizontal, vertical], dpi=300)

    assert len(fusionados) == 2


def test_filter_short_segments_descarta_segmentos_cortos() -> None:
    corto = ((0.0, 0.0), (5.0, 0.0))  # ~0.4mm a 300 dpi
    largo = ((0.0, 0.0), (200.0, 0.0))  # ~17mm a 300 dpi

    filtrados = filter_short_segments([corto, largo], min_length_mm=8.0, dpi=300)

    assert filtrados == [largo]


def test_filter_short_segments_con_cero_no_descarta_nada() -> None:
    segmentos = [((0.0, 0.0), (1.0, 0.0))]

    filtrados = filter_short_segments(segmentos, min_length_mm=0, dpi=300)

    assert filtrados == segmentos
