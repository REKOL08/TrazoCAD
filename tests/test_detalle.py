import cv2
import numpy as np

from src.detalle import detect_detail_strokes
from src.texto import TextItem

DPI = 300


def _imagen(dibujar) -> np.ndarray:
    image = np.full((700, 900), 255, dtype=np.uint8)
    dibujar(image)
    return image


def test_una_linea_gruesa_sale_como_un_solo_trazo_recto() -> None:
    image = _imagen(lambda im: cv2.line(im, (100, 300), (500, 300), 0, 5))  # 5 px de grosor

    trazos = detect_detail_strokes(image, DPI, explained=[], texts=[])

    assert len(trazos) == 1
    assert len(trazos[0].points) == 2  # una sola recta, no un contorno doble
    (x1, y1), (x2, y2) = trazos[0].points
    assert abs(y1 - 300) < 3 and abs(y1 - y2) < 1e-6  # centrada y enderezada
    assert abs(abs(x2 - x1) - 400) < 20


def test_una_curva_queda_completa_en_pocos_trazos_con_su_longitud() -> None:
    import math

    image = _imagen(lambda im: cv2.ellipse(im, (450, 350), (150, 100), 0, 200, 340, 0, 4))

    trazos = detect_detail_strokes(image, DPI, explained=[], texts=[])

    # longitud real del arco de elipse dibujado (~ 140 grados), por integración numérica
    angulos = np.radians(np.linspace(200, 340, 400))
    esperado = sum(
        math.hypot(150 * (math.cos(b) - math.cos(a)), 100 * (math.sin(b) - math.sin(a)))
        for a, b in zip(angulos, angulos[1:])
    )
    total = sum(math.dist(s.points[i], s.points[i + 1]) for s in trazos for i in range(len(s.points) - 1))
    assert len(trazos) <= 6  # el esqueleto deja algún nudo, pero no se desmenuza en decenas
    assert 0.9 * esperado < total < 1.25 * esperado


def test_lo_que_ya_esta_en_otra_capa_se_borra() -> None:
    image = _imagen(lambda im: cv2.line(im, (100, 300), (500, 300), 0, 5))
    muro = [((100.0, 300.0), (500.0, 300.0))]

    assert detect_detail_strokes(image, DPI, explained=muro, texts=[]) == []


def test_las_motas_pequenas_no_son_trazos() -> None:
    image = _imagen(lambda im: cv2.circle(im, (300, 300), 3, 0, -1))  # mota de ~0.5 mm

    assert detect_detail_strokes(image, DPI, explained=[], texts=[]) == []


def test_las_letras_leidas_con_seguridad_se_borran() -> None:
    image = _imagen(lambda im: cv2.line(im, (100, 300), (500, 300), 0, 5))
    caja = np.array([[80.0, 270.0], [520.0, 270.0], [520.0, 330.0], [80.0, 330.0]])

    assert detect_detail_strokes(image, DPI, explained=[], texts=[TextItem("COCINA", 0.9, caja, sure=True)]) == []


def test_la_franja_del_cajetin_se_ignora() -> None:
    image = _imagen(lambda im: cv2.line(im, (100, 650), (500, 650), 0, 5))

    assert detect_detail_strokes(image, DPI, explained=[], texts=[], ignore_bottom_fraction=0.15) == []


def test_las_rayas_cortas_de_una_linea_discontinua_se_conservan() -> None:
    def rayas(im: np.ndarray) -> None:
        for k in range(8):  # 8 rayas de ~0.6 mm (7 px) separadas ~1.7 mm, en una fila
            x = 100 + 27 * k
            cv2.line(im, (x, 300), (x + 7, 300), 0, 3)

    image = _imagen(rayas)

    trazos = detect_detail_strokes(image, DPI, explained=[], texts=[])

    assert len(trazos) >= 6  # no se tiran como si fueran motas
    assert all(len(t.points) == 2 for t in trazos)


def test_una_mota_aislada_sigue_siendo_ruido() -> None:
    image = _imagen(lambda im: cv2.line(im, (300, 300), (307, 300), 0, 3))

    assert detect_detail_strokes(image, DPI, explained=[], texts=[]) == []


def test_los_restos_lejos_de_lo_reconocido_se_quitan_y_el_detalle_cercano_se_queda() -> None:
    import numpy as np

    from src.centerline import Stroke
    from src.detalle import drop_debris

    anclas = np.array([[1000.0, 1000.0], [1100.0, 1000.0]])  # un muro reconocido
    cerca = Stroke([(1050.0, 1040.0), (1090.0, 1040.0)])  # una cota junto al muro
    sello = Stroke([(2400.0, 200.0), (2450.0, 200.0)])  # trazo corto lejos de todo
    largo_lejos = Stroke([(700.0, 1500.0), (2600.0, 1500.0)])  # largo (>100 mm): no es un resto, se conserva

    resultado = drop_debris([cerca, sello, largo_lejos], anclas, DPI, (2550, 3300))

    assert cerca in resultado and sello not in resultado and largo_lejos in resultado


def test_el_marco_de_la_hoja_se_quita() -> None:
    import numpy as np

    from src.centerline import Stroke
    from src.detalle import drop_debris

    marco = Stroke([(60.0, 50.0), (60.0, 2400.0)])  # línea larga pegada al borde izquierdo
    muro_borde = Stroke([(60.0, 500.0), (60.0, 560.0)])  # corta: no es el marco
    anclas = np.array([[60.0, 520.0]])

    resultado = drop_debris([marco, muro_borde], anclas, DPI, (2550, 3300))

    assert marco not in resultado and muro_borde in resultado


def test_sin_anclas_solo_se_quita_el_marco() -> None:
    import numpy as np

    from src.centerline import Stroke
    from src.detalle import drop_debris

    trazo = Stroke([(1000.0, 1000.0), (1040.0, 1000.0)])

    assert drop_debris([trazo], np.empty((0, 2)), DPI, (2550, 3300)) == [trazo]
