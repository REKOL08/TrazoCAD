from pathlib import Path

import cv2
import numpy as np

from src.fotos import find_photos, merge_texts, register_photos
from src.texto import TextItem, correct_spanish


def _caja(x: float, y: float, w: float = 80, h: float = 30) -> np.ndarray:
    return np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=np.float64)


def _plano_con_textura() -> np.ndarray:
    rng = np.random.default_rng(7)
    plano = np.full((1400, 1800), 255, np.uint8)
    for _ in range(400):
        x, y = int(rng.integers(0, 1800)), int(rng.integers(0, 1400))
        if rng.random() < 0.5:
            cv2.line(plano, (x, y), (x + int(rng.integers(-150, 150)), y + int(rng.integers(-150, 150))), 0, 2)
        else:
            cv2.circle(plano, (x, y), int(rng.integers(8, 40)), 0, 2)
        cv2.putText(plano, str(int(rng.integers(0, 99))), (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 0, 2)
    return plano


def test_fotos_identicas_se_cuentan_una_sola_vez(tmp_path: Path) -> None:
    foto = np.full((50, 50, 3), 128, np.uint8)
    cv2.imwrite(str(tmp_path / "a.jpg"), foto)
    cv2.imwrite(str(tmp_path / "b.jpg"), foto)
    (tmp_path / "LEEME.txt").write_text("no es una imagen")

    assert len(find_photos(tmp_path)) == 1


def test_carpeta_inexistente_no_da_fotos(tmp_path: Path) -> None:
    assert find_photos(tmp_path / "no_existe") == []


def test_una_foto_girada_de_un_trozo_se_alinea_con_el_plano(tmp_path: Path) -> None:
    plano = _plano_con_textura()
    trozo = plano[300:1100, 400:1300]
    foto = cv2.GaussianBlur(np.ascontiguousarray(np.rot90(trozo, 1)), (3, 3), 0)  # girada 90°
    cv2.imwrite(str(tmp_path / "foto.png"), foto)

    registradas = register_photos(plano, [tmp_path / "foto.png"])

    assert len(registradas) == 1
    h = registradas[0].homography
    # el centro de la foto (ya girada al derecho) debe caer en el centro del trozo dentro del plano
    girada = registradas[0].gray
    cy, cx = girada.shape[0] / 2, girada.shape[1] / 2
    x, y = cv2.perspectiveTransform(np.array([[[cx, cy]]], np.float32), h)[0, 0]
    assert abs(x - 850) < 6 and abs(y - 700) < 6, (x, y)


def test_una_foto_de_otro_plano_se_descarta(tmp_path: Path) -> None:
    plano = _plano_con_textura()
    otra = np.random.default_rng(1).integers(0, 255, (600, 800), dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "otra.png"), otra)

    assert register_photos(plano, [tmp_path / "otra.png"]) == []


def test_un_texto_nuevo_de_la_foto_se_agrega_y_uno_repetido_no() -> None:
    escaneo = [TextItem("COCINA", 0.7, _caja(100, 100), True)]
    de_foto = [
        TextItem("COCINA", 0.9, _caja(102, 101), True),   # mismo lugar, mejor lectura
        TextItem("1.80", 0.8, _caja(500, 500), True),     # texto que el escaneo no leyó
    ]

    resultado = merge_texts(escaneo, de_foto, (1000, 1000))

    assert sorted(t.text for t in resultado) == ["1.80", "COCINA"]
    assert [t.confidence for t in resultado if t.text == "COCINA"] == [0.9]


def test_la_franja_del_cajetin_no_recibe_textos_de_fotos() -> None:
    de_foto = [TextItem("1.80", 0.8, _caja(500, 950), True)]

    assert merge_texts([], de_foto, (1000, 1000), bottom_fraction=0.15) == []


def test_las_cotas_con_letras_por_cifras_se_arreglan() -> None:
    assert correct_spanish("RO.85")[0] == "R0.85"
    assert correct_spanish("z.05")[0] == "2.05"
    assert correct_spanish("1.60")[0] == "1.60"
    assert correct_spanish("OTT")[0] == "OTT"  # no es una cota: no se toca
