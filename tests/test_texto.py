import cv2
import numpy as np
import pytest

from src.texto import TextItem, _upright_quad, correct_spanish, ocr_available, read_texts


def test_corrige_confusiones_tipicas_del_ocr() -> None:
    assert correct_spanish("COCIHA") == ("COCINA", True)
    assert correct_spanish("BARO") == ("BAÑO", True)
    assert correct_spanish("SERVICIQ") == ("SERVICIO", True)
    assert correct_spanish("ALCOBADE SERVICIQ")[0].endswith("SERVICIO")


def test_no_toca_cifras_ni_palabras_desconocidas() -> None:
    assert correct_spanish("2.35") == ("2.35", False)
    assert correct_spanish("XYZQW") == ("XYZQW", False)


def test_orienta_la_caja_con_la_linea_base_en_el_lado_largo() -> None:
    # caja horizontal (100 x 20) cuyos vértices vienen girados 90°
    girada = np.array([[100.0, 0.0], [100.0, 20.0], [0.0, 20.0], [0.0, 0.0]])

    caja = _upright_quad(girada, "COMEDOR")
    item = TextItem("COMEDOR", 0.9, caja)

    assert abs(item.angle_deg) < 1e-6
    assert item.height_px == pytest.approx(20.0)
    assert item.baseline_start == (0.0, 20.0)


def test_nunca_deja_el_texto_boca_abajo() -> None:
    boca_abajo = np.array([[100.0, 20.0], [0.0, 20.0], [0.0, 0.0], [100.0, 0.0]])

    caja = _upright_quad(boca_abajo, "COCINA")

    assert -90.0 < TextItem("COCINA", 0.9, caja).angle_deg <= 90.0


def test_sin_ocr_instalado_devuelve_lista_vacia(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import texto

    monkeypatch.setattr(texto, "ocr_available", lambda: False)

    assert read_texts(np.full((100, 100), 255, dtype=np.uint8)) == []


@pytest.mark.skipif(not ocr_available(), reason="rapidocr-onnxruntime no está instalado")
def test_lee_un_texto_dibujado_en_el_plano() -> None:
    image = np.full((400, 900), 255, dtype=np.uint8)
    cv2.putText(image, "COMEDOR", (120, 220), cv2.FONT_HERSHEY_SIMPLEX, 2.2, 0, 4)

    textos = read_texts(image)

    assert any(t.text == "COMEDOR" for t in textos)
    leido = next(t for t in textos if t.text == "COMEDOR")
    assert abs(leido.angle_deg) < 5
    assert 100 < leido.baseline_start[0] < 160
