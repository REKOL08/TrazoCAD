import cv2
import numpy as np

from src.vectorizer import trace_ink


def _imagen_con_rectangulo() -> np.ndarray:
    image = np.full((300, 300), 255, dtype=np.uint8)
    cv2.rectangle(image, (50, 50), (250, 200), color=0, thickness=3)
    return image


def test_trace_ink_calca_un_rectangulo_dibujado() -> None:
    polilineas = trace_ink(_imagen_con_rectangulo(), dpi=300)

    assert len(polilineas) >= 1
    assert all(len(p) >= 3 for p in polilineas)


def test_trace_ink_imagen_en_blanco_no_devuelve_nada() -> None:
    image = np.full((200, 200), 255, dtype=np.uint8)

    assert trace_ink(image, dpi=300) == []


def test_trace_ink_rechaza_imagen_a_color() -> None:
    import pytest

    with pytest.raises(ValueError):
        trace_ink(np.zeros((10, 10, 3), dtype=np.uint8), dpi=300)
