import numpy as np

from src.line_detector import detect_lines


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
