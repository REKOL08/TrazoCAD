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
