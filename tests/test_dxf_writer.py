from pathlib import Path

import ezdxf

from src.dxf_writer import LAYER_LINES, build_dxf


def test_build_dxf_crea_archivo_con_lineas(tmp_path: Path) -> None:
    segmentos = [
        ((0.0, 0.0), (100.0, 0.0)),
        ((0.0, 0.0), (0.0, 100.0)),
    ]
    salida = tmp_path / "plano.dxf"

    resultado = build_dxf(segmentos, dpi=300, image_height_px=1000, output_path=salida)

    assert resultado == salida
    assert salida.exists()

    documento = ezdxf.readfile(salida)
    modelspace = documento.modelspace()
    lineas = list(modelspace.query("LINE"))
    assert len(lineas) == 2
    assert all(linea.dxf.layer == LAYER_LINES for linea in lineas)


def test_build_dxf_sin_segmentos_crea_dxf_vacio(tmp_path: Path) -> None:
    salida = tmp_path / "vacio.dxf"

    build_dxf([], dpi=300, image_height_px=1000, output_path=salida)

    documento = ezdxf.readfile(salida)
    assert list(documento.modelspace().query("LINE")) == []


def test_build_dxf_escribe_polilineas_cerradas_en_capa_de_trazo(tmp_path: Path) -> None:
    from src.dxf_writer import LAYER_TRACE

    polilineas = [[(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)]]
    salida = tmp_path / "trazo.dxf"

    build_dxf([], dpi=300, image_height_px=1000, output_path=salida, polylines=polilineas)

    entidades = list(ezdxf.readfile(salida).modelspace().query("LWPOLYLINE"))
    assert len(entidades) == 1
    assert entidades[0].closed
    assert entidades[0].dxf.layer == LAYER_TRACE


def test_build_dxf_escribe_muros_y_ejes_en_sus_capas(tmp_path: Path) -> None:
    from src.dxf_writer import LAYER_AXES, LAYER_WALLS

    salida = tmp_path / "muros.dxf"
    muros = [((0.0, 0.0), (100.0, 0.0)), ((0.0, 14.0), (100.0, 14.0))]
    ejes = [((0.0, 7.0), (200.0, 7.0))]

    build_dxf([], dpi=300, image_height_px=1000, output_path=salida, walls=muros, axes=ejes)

    documento = ezdxf.readfile(salida)
    capas = [linea.dxf.layer for linea in documento.modelspace().query("LINE")]
    assert capas.count(LAYER_WALLS) == 2
    assert capas.count(LAYER_AXES) == 1
    assert documento.layers.get(LAYER_AXES).dxf.linetype == "CENTER"


def test_build_dxf_escribe_arcos_y_circulos(tmp_path: Path) -> None:
    from src.arcos import Arc
    from src.dxf_writer import LAYER_ARCS

    salida = tmp_path / "arcos.dxf"
    arcos = [Arc(500.0, 500.0, 118.1, 10.0, 100.0), Arc(900.0, 500.0, 59.0, 0.0, 360.0)]

    build_dxf([], dpi=300, image_height_px=1000, output_path=salida, arcs=arcos)

    modelspace = ezdxf.readfile(salida).modelspace()
    arc = list(modelspace.query("ARC"))
    circulos = list(modelspace.query("CIRCLE"))
    assert len(arc) == 1 and len(circulos) == 1
    assert arc[0].dxf.layer == LAYER_ARCS
    assert abs(arc[0].dxf.radius - 10.0) < 0.05  # 118.1 px a 300 dpi = 10 mm
    assert abs(arc[0].dxf.start_angle - 10.0) < 1e-6


def test_las_capas_llevan_grosor_de_linea(tmp_path: Path) -> None:
    from src.dxf_writer import LAYER_AXES, LAYER_WALLS

    salida = tmp_path / "grosores.dxf"
    build_dxf([], dpi=300, image_height_px=1000, output_path=salida)

    documento = ezdxf.readfile(salida)
    assert documento.layers.get(LAYER_WALLS).dxf.lineweight == 50
    assert documento.layers.get(LAYER_AXES).dxf.lineweight == 18
    assert documento.header["$LWDISPLAY"] == 1


def test_build_dxf_escribe_textos_en_sus_capas(tmp_path: Path) -> None:
    import numpy as np

    from src.dxf_writer import LAYER_TEXT, LAYER_TEXT_REVIEW
    from src.texto import TextItem

    caja = np.array([[100.0, 100.0], [300.0, 100.0], [300.0, 140.0], [100.0, 140.0]])
    textos = [
        TextItem("COCINA", 0.9, caja, sure=True),
        TextItem("PISO XX", 0.6, caja + 500, sure=False),
    ]
    salida = tmp_path / "textos.dxf"

    build_dxf([], dpi=300, image_height_px=1000, output_path=salida, texts=textos)

    entidades = {e.dxf.text: e for e in ezdxf.readfile(salida).modelspace().query("TEXT")}
    assert entidades["COCINA"].dxf.layer == LAYER_TEXT
    assert entidades["PISO XX"].dxf.layer == LAYER_TEXT_REVIEW
    assert entidades["COCINA"].dxf.height > 0


def test_build_dxf_escribe_puertas_y_ventanas_en_sus_capas(tmp_path: Path) -> None:
    from src.arcos import Arc
    from src.dxf_writer import LAYER_DOORS, LAYER_WINDOWS
    from src.puertas import Door
    from src.ventanas import Window

    puerta = Door(arc=Arc(300.0, 400.0, 100.0, 0.0, 90.0), leaf=((300.0, 400.0), (400.0, 400.0)))
    ventana = Window(lines=[((0.0, 0.0), (100.0, 0.0)), ((0.0, 7.0), (100.0, 7.0))])
    salida = tmp_path / "pv.dxf"

    build_dxf([], dpi=300, image_height_px=1000, output_path=salida, doors=[puerta], windows=[ventana])

    modelspace = ezdxf.readfile(salida).modelspace()
    arcos = list(modelspace.query("ARC"))
    lineas = {e.dxf.layer for e in modelspace.query("LINE")}
    assert [a.dxf.layer for a in arcos] == [LAYER_DOORS]
    assert lineas == {LAYER_DOORS, LAYER_WINDOWS}


def test_las_cifras_de_cota_van_en_su_capa(tmp_path: Path) -> None:
    import numpy as np

    from src.dxf_writer import LAYER_DIMENSIONS, LAYER_TEXT
    from src.texto import TextItem

    caja = np.array([[100.0, 100.0], [200.0, 100.0], [200.0, 130.0], [100.0, 130.0]])
    textos = [TextItem("2.05", 0.9, caja), TextItem("COCINA", 0.9, caja + 400)]
    salida = tmp_path / "cotas.dxf"

    build_dxf([], dpi=300, image_height_px=1000, output_path=salida, texts=textos)

    capas = {e.dxf.text: e.dxf.layer for e in ezdxf.readfile(salida).modelspace().query("TEXT")}
    assert capas == {"2.05": LAYER_DIMENSIONS, "COCINA": LAYER_TEXT}


def test_build_dxf_escribe_sanitarios_como_elipses(tmp_path: Path) -> None:
    from src.dxf_writer import LAYER_FIXTURES
    from src.muebles import Fixture

    taza = Fixture("INODORO", 300.0, 400.0, 59.0, 35.0, 0.0)  # 59 px a 300 dpi = 5 mm
    salida = tmp_path / "san.dxf"

    build_dxf([], dpi=300, image_height_px=1000, output_path=salida, fixtures=[taza])

    elipses = list(ezdxf.readfile(salida).modelspace().query("ELLIPSE"))
    assert len(elipses) == 1
    assert elipses[0].dxf.layer == LAYER_FIXTURES
    assert abs(elipses[0].dxf.ratio - 35.0 / 59.0) < 1e-6
    assert abs(elipses[0].dxf.major_axis.x - 2.5) < 0.05  # semieje mayor de 2.5 mm
