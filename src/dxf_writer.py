"""Construcción de un archivo DXF editable a partir de segmentos detectados.

DXF (no DWG) es el formato que esta librería puede escribir de forma nativa
y 100% libre: ezdxf no tiene soporte de escritura de DWG binario (ninguna
librería de Python libre lo tiene). AutoCAD abre archivos .dxf de forma
nativa igual que un .dwg; la conversión opcional a .dwg real se hace en
`dwg_converter.py` apoyándose en una herramienta externa gratuita.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

from .arcos import Arc
from .line_detector import Segment
from .puertas import Door
from .texto import TextItem
from .ventanas import Window
from .vectorizer import Polyline

logger = logging.getLogger("planos2dwg")

LAYER_LINES = "LINEAS_DETECTADAS"
LAYER_TRACE = "CALCADO_REFERENCIA"
LAYER_WALLS = "MUROS"
LAYER_AXES = "EJES"
LAYER_ARCS = "ARCOS"
LAYER_DOORS = "PUERTAS"
LAYER_WINDOWS = "VENTANAS"
TEXT_STYLE = "PLANOS"
LAYER_DIMENSIONS = "COTAS"
_DIMENSION_NUMBER = re.compile(r"^\d{1,2}[.,]\d{2}$")
LAYER_TEXT = "TEXTOS"
LAYER_TEXT_REVIEW = "TEXTOS_REVISAR"
_TEXT_HEIGHT_FACTOR = 0.78
MM_PER_INCH = 25.4


def _text_layer(item: TextItem) -> str:
    """Las cifras de cota (2.05, 0.90...) van aparte de los nombres de los espacios."""
    if item.sure and _DIMENSION_NUMBER.match(item.text):
        return LAYER_DIMENSIONS
    return LAYER_TEXT if item.sure else LAYER_TEXT_REVIEW


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
    doors: list[Door] | None = None,
    windows: list[Window] | None = None,
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
    doors = doors or []
    windows = windows or []

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
    if LAYER_DIMENSIONS not in layers:
        layers.add(name=LAYER_DIMENSIONS, color=3)
    if LAYER_TEXT not in layers:
        layers.add(name=LAYER_TEXT, color=5)
    if LAYER_TEXT_REVIEW not in layers:
        layers.add(name=LAYER_TEXT_REVIEW, color=30)
    if LAYER_WINDOWS not in layers:
        layers.add(name=LAYER_WINDOWS, color=4, lineweight=18)
    if LAYER_DOORS not in layers:
        layers.add(name=LAYER_DOORS, color=2, lineweight=25)
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

    for window in windows:
        for (x1, y1), (x2, y2) in window.lines:
            modelspace.add_line(to_mm(x1, y1), to_mm(x2, y2), dxfattribs={"layer": LAYER_WINDOWS})

    for door in doors:
        modelspace.add_arc(
            to_mm(door.arc.cx, door.arc.cy),
            _px_to_mm(door.arc.radius, dpi),
            door.arc.start_deg,
            door.arc.end_deg,
            dxfattribs={"layer": LAYER_DOORS},
        )
        if door.leaf is not None:
            (hx, hy), (tx, ty) = door.leaf
            modelspace.add_line(to_mm(hx, hy), to_mm(tx, ty), dxfattribs={"layer": LAYER_DOORS})

    for item in texts:
        entity = modelspace.add_text(
            item.text,
            height=_px_to_mm(item.height_px, dpi) * _TEXT_HEIGHT_FACTOR,
            dxfattribs={
                "layer": _text_layer(item),
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
        "DXF generado: %s (%d líneas, %d muros, %d ejes, %d arcos, %d puertas, %d ventanas, %d textos, %d trazos de referencia)",
        output_path,
        len(segments),
        len(walls),
        len(axes),
        len(arcs),
        len(doors),
        len(windows),
        len(texts),
        len(polylines),
    )
    return output_path
