from pathlib import Path

import cv2
import numpy as np

from src.fotos import find_photos, fuse_photos, register_photos, unique_photos
from src.texto import correct_spanish


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


def test_unique_photos_ignora_repetidas_y_lo_que_no_es_imagen(tmp_path: Path) -> None:
    foto = np.full((40, 40, 3), 90, np.uint8)
    cv2.imwrite(str(tmp_path / "a.png"), foto)
    cv2.imwrite(str(tmp_path / "copia.png"), foto)
    (tmp_path / "notas.txt").write_text("hola")

    resultado = unique_photos([tmp_path / "a.png", tmp_path / "copia.png", tmp_path / "notas.txt", tmp_path / "no_existe.jpg"])

    assert [p.name for p in resultado] == ["a.png"]


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


def test_la_fusion_da_mas_detalle_solo_donde_hay_foto(tmp_path: Path) -> None:
    nitido = _plano_con_textura()
    escaneo = cv2.GaussianBlur(nitido, (0, 0), 2.2)  # el escaneo de baja resolución pierde detalle
    trozo = nitido[300:1100, 400:1300]
    cv2.imwrite(str(tmp_path / "foto.png"), np.ascontiguousarray(np.rot90(trozo, 1)))
    registradas = register_photos(escaneo, [tmp_path / "foto.png"])
    assert len(registradas) == 1

    fusionado = fuse_photos(escaneo, registradas)

    nitidez = lambda im, zona: float(cv2.Laplacian(im, cv2.CV_32F)[zona].var())  # noqa: E731
    dentro = (slice(500, 900), slice(600, 1100))
    assert nitidez(fusionado, dentro) > 1.5 * nitidez(escaneo, dentro)
    # lejos de la foto el escaneo queda exactamente igual
    assert np.array_equal(fusionado[:150, :], escaneo[:150, :])
    assert np.array_equal(fusionado[:, 1500:], escaneo[:, 1500:])


def test_sin_fotos_la_fusion_devuelve_el_escaneo_tal_cual() -> None:
    escaneo = np.full((100, 100), 200, np.uint8)

    assert fuse_photos(escaneo, []) is escaneo


def test_las_cotas_con_letras_por_cifras_se_arreglan() -> None:
    assert correct_spanish("RO.85")[0] == "R0.85"
    assert correct_spanish("z.05")[0] == "2.05"
    assert correct_spanish("1.60")[0] == "1.60"
    assert correct_spanish("OTT")[0] == "OTT"  # no es una cota: no se toca
