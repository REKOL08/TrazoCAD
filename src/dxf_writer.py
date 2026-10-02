"""Construcción de un archivo DXF editable a partir de segmentos detectados.

DXF (no DWG) es el formato que esta librería puede escribir de forma nativa
y 100% libre: ezdxf no tiene soporte de escritura de DWG binario (ninguna
librería de Python libre lo tiene). AutoCAD abre archivos .dxf de forma
nativa igual que un .dwg; la conversión opcional a .dwg real se hace en
`dwg_converter.py` apoyándose en una herramienta externa gratuita.
"""

from __future__ import annotations

import logging
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

from .arcos import Arc
from .line_detector import Segment
from .texto import TextItem
from .vectorizer import Polyline

logger = logging.getLogger("planos2dwg")

LAYER_LINES = "LINEAS_DETECTADAS"
LAYER_TRACE = "CALCADO_REFERENCIA"
LAYER_WALLS = "MUROS"
LAYER_AXES = "EJES"
LAYER_ARCS = "ARCOS"
TEXT_STYLE = "PLANOS"
LAYER_TEXT = "TEXTOS"
LAYER_TEXT_REVIEW = "TEXTOS_REVISAR"
_TEXT_HEIGHT_FACTOR = 0.78
MM_PER_INCH = 25.4


def _px_to_mm(value_px: float, dpi: int) -> float:
    return (value_px / dpi) * MM_PER_INCH


def build_dxf(
    segments: list[Segment],
    dpi: int,
    image_height_px: int,
    output_path: Path,
    polylines: list[Polyline] | None = None,
    walls: list[Segment] | None = None,
    axes: list[Segment] | None = None,
    arcs: list[Arc] | None = None,
    texts: list[TextItem] | None = None,
) -> Path:
    """Escribe `segments` y `polylines` (en píxeles) en un DXF nuevo.

    Los segmentos van como entidades LINE en la capa LINEAS_DETECTADAS y
    las polilíneas como LWPOLYLINE cerradas en TRAZO_ORIGINAL. El eje Y se
    invierte porque en la imagen crece hacia abajo y en DXF/CAD crece hacia
    arriba. Las unidades del documento quedan en milímetros.
    """
    polylines = polylines or []
    walls = walls or []
    axes = axes or []
    arcs = arcs or []
    texts = texts or []

    document = ezdxf.new(dxfversion="R2010", setup=True, units=ezdxf.units.MM)
    document.header["$INSUNITS"] = ezdxf.units.MM
    document.header["$LWDISPLAY"] = 1  # que AutoCAD muestre los grosores de línea por capa

    if TEXT_STYLE not in document.styles:
        document.styles.add(TEXT_STYLE, font="arial.ttf")

    layers = document.layers
    if LAYER_LINES not in layers:
        layers.add(name=LAYER_LINES, color=7)
    if LAYER_TRACE not in layers:
        layers.add(name=LAYER_TRACE, color=8, lineweight=13)
    if LAYER_WALLS not in layers:
        layers.add(name=LAYER_WALLS, color=7, lineweight=50)
    if LAYER_TEXT not in layers:
        layers.add(name=LAYER_TEXT, color=5)
    if LAYER_TEXT_REVIEW not in layers:
        layers.add(name=LAYER_TEXT_REVIEW, color=30)
    if LAYER_ARCS not in layers:
        layers.add(name=LAYER_ARCS, color=7, lineweight=25)
    if LAYER_AXES not in layers:
        layers.add(name=LAYER_AXES, color=1, linetype="CENTER", lineweight=18)

    modelspace = document.modelspace()

    def to_mm(x: float, y: float) -> tuple[float, float]:
        return (_px_to_mm(x, dpi), _px_to_mm(image_height_px - y, dpi))

    for (x1, y1), (x2, y2) in segments:
        modelspace.add_line(to_mm(x1, y1), to_mm(x2, y2), dxfattribs={"layer": LAYER_LINES})

    for (x1, y1), (x2, y2) in walls:
        modelspace.add_line(to_mm(x1, y1), to_mm(x2, y2), dxfattribs={"layer": LAYER_WALLS})

    for (x1, y1), (x2, y2) in axes:
        modelspace.add_line(to_mm(x1, y1), to_mm(x2, y2), dxfattribs={"layer": LAYER_AXES})

    for arc in arcs:
        centre = to_mm(arc.cx, arc.cy)
        radius = _px_to_mm(arc.radius, dpi)
        if arc.is_circle:
            modelspace.add_circle(centre, radius, dxfattribs={"layer": LAYER_ARCS})
        else:
            modelspace.add_arc(
                centre, radius, arc.start_deg, arc.end_deg, dxfattribs={"layer": LAYER_ARCS}
            )

    for item in texts:
        entity = modelspace.add_text(
            item.text,
            height=_px_to_mm(item.height_px, dpi) * _TEXT_HEIGHT_FACTOR,
            dxfattribs={
                "layer": LAYER_TEXT if item.sure else LAYER_TEXT_REVIEW,
                "style": TEXT_STYLE,
            },
        )
        # ajustado a lo largo de la caja leída: el texto ocupa el mismo ancho que el original
        entity.set_placement(
            to_mm(*item.baseline_start), to_mm(*item.baseline_end), align=TextEntityAlignment.FIT
        )

    for polyline in polylines:
        modelspace.add_lwpolyline(
            [to_mm(x, y) for x, y in polyline],
            close=True,
            dxfattribs={"layer": LAYER_TRACE},
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.saveas(output_path)
    logger.info(
        "DXF generado: %s (%d líneas, %d muros, %d ejes, %d arcos, %d textos, %d trazos de referencia)",
        output_path,
        len(segments),
        len(walls),
        len(axes),
        len(arcs),
        len(texts),
        len(polylines),
    )
    return output_path
