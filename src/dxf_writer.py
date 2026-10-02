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

from .line_detector import Segment

logger = logging.getLogger("planos2dwg")

LAYER_LINES = "LINEAS_DETECTADAS"
MM_PER_INCH = 25.4


def _px_to_mm(value_px: float, dpi: int) -> float:
    return (value_px / dpi) * MM_PER_INCH


def build_dxf(
    segments: list[Segment],
    dpi: int,
    image_height_px: int,
    output_path: Path,
) -> Path:
    """Escribe `segments` (en píxeles) como entidades LINE en un DXF nuevo.

    El eje Y se invierte porque en la imagen crece hacia abajo y en DXF/CAD
    crece hacia arriba. Las unidades del documento quedan en milímetros.
    """
    document = ezdxf.new(dxfversion="R2010", units=ezdxf.units.MM)
    document.header["$INSUNITS"] = ezdxf.units.MM

    layers = document.layers
    if LAYER_LINES not in layers:
        layers.add(name=LAYER_LINES, color=7)

    modelspace = document.modelspace()

    for (x1, y1), (x2, y2) in segments:
        start = (_px_to_mm(x1, dpi), _px_to_mm(image_height_px - y1, dpi))
        end = (_px_to_mm(x2, dpi), _px_to_mm(image_height_px - y2, dpi))
        modelspace.add_line(start, end, dxfattribs={"layer": LAYER_LINES})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.saveas(output_path)
    logger.info("DXF generado: %s (%d líneas)", output_path, len(segments))
    return output_path
