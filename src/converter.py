"""Orquesta el pipeline completo: PDF -> imágenes -> líneas -> DXF -> DWG."""

from __future__ import annotations

import logging
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .dwg_converter import convert_dxf_to_dwg
from .deskew import deskew
from .dxf_writer import build_dxf
from .line_detector import detect_lines, filter_short_segments, merge_collinear_segments
from .muros import detect_walls_and_axes
from .pdf_processor import render_pdf_pages
from .utils import ConversionError, validate_pdf
from .vectorizer import trace_ink

logger = logging.getLogger("planos2dwg")

DEFAULT_MIN_LENGTH_MM = 8.0
MODE_TRACE = "fiel"
MODE_LINES = "lineas"
VALID_ROTATIONS = (0, 90, 180, 270)


def rotate_image(image: np.ndarray, degrees_ccw: int) -> np.ndarray:
    """Gira `image` en sentido antihorario (0, 90, 180 o 270 grados)."""
    if degrees_ccw not in VALID_ROTATIONS:
        raise ConversionError(f"El giro debe ser uno de {VALID_ROTATIONS}, no {degrees_ccw}.")
    if degrees_ccw == 0:
        return image
    return np.ascontiguousarray(np.rot90(image, degrees_ccw // 90))


@dataclass
class ConversionResult:
    pdf_path: Path
    success: bool
    outputs: list[Path] = field(default_factory=list)
    error: str | None = None


def convert_pdf(
    pdf_path: Path,
    output_dir: Path,
    dpi: int,
    generate_dwg: bool = True,
    min_length_mm: float = DEFAULT_MIN_LENGTH_MM,
    mode: str = MODE_TRACE,
    rotation: int = 0,
    ignore_bottom_fraction: float = 0.0,
    clean_only: bool = False,
) -> ConversionResult:
    """Convierte un único PDF a uno o varios archivos DXF/DWG (uno por página).

    No lanza excepciones hacia el llamador: cualquier error se captura y se
    devuelve dentro de ConversionResult para que un lote de PDFs pueda
    seguir procesando los siguientes archivos aunque uno falle.
    """
    pdf_path = Path(pdf_path)
    try:
        validate_pdf(pdf_path)
        pages = render_pdf_pages(pdf_path, dpi=dpi)

        outputs: list[Path] = []
        for page in pages:
            image = deskew(rotate_image(page.image, rotation), page.dpi)
            segments: list = []
            polylines: list = []
            walls: list = []
            axes: list = []
            if mode == MODE_LINES:
                segments = detect_lines(image)
                segments = merge_collinear_segments(segments, dpi=page.dpi)
                segments = filter_short_segments(
                    segments, min_length_mm=min_length_mm, dpi=page.dpi
                )
            else:
                walls, axes = detect_walls_and_axes(
                    image, page.dpi, ignore_bottom_fraction=ignore_bottom_fraction
                )
                if not clean_only:
                    polylines = trace_ink(image, dpi=page.dpi)
            if not segments and not polylines and not walls and not axes:
                logger.warning(
                    "'%s' página %d: no se detectó geometría; se omite esta página.",
                    pdf_path.name,
                    page.page_number,
                )
                continue

            suffix = "" if len(pages) == 1 else f"_p{page.page_number}"
            dxf_path = output_dir / f"{pdf_path.stem}{suffix}.dxf"
            try:
                build_dxf(
                    segments,
                    dpi=page.dpi,
                    image_height_px=image.shape[0],
                    output_path=dxf_path,
                    polylines=polylines,
                    walls=walls,
                    axes=axes,
                )
            except PermissionError:
                # El DXF anterior suele estar abierto en AutoCAD y Windows no
                # permite sobrescribirlo: se guarda uno nuevo con la hora.
                stamp = datetime.now().strftime("%H%M%S")
                dxf_path = dxf_path.with_name(f"{dxf_path.stem}_{stamp}.dxf")
                logger.warning(
                    "El archivo anterior está en uso (¿abierto en AutoCAD?); se guarda como %s",
                    dxf_path.name,
                )
                build_dxf(
                    segments,
                    dpi=page.dpi,
                    image_height_px=image.shape[0],
                    output_path=dxf_path,
                    polylines=polylines,
                    walls=walls,
                    axes=axes,
                )
            outputs.append(dxf_path)

            if generate_dwg:
                dwg_path = convert_dxf_to_dwg(dxf_path, output_dir)
                if dwg_path is not None:
                    outputs.append(dwg_path)

        if not outputs:
            return ConversionResult(
                pdf_path=pdf_path,
                success=False,
                error="No se detectó ninguna línea en el PDF; revisa la calidad del escaneo.",
            )

        return ConversionResult(pdf_path=pdf_path, success=True, outputs=outputs)

    except ConversionError as exc:
        logger.error("'%s': %s", pdf_path.name, exc)
        return ConversionResult(pdf_path=pdf_path, success=False, error=str(exc))
    except Exception as exc:  # protección final: un PDF problemático no debe tumbar el lote
        logger.exception("Error inesperado procesando '%s'", pdf_path.name)
        return ConversionResult(pdf_path=pdf_path, success=False, error=f"Error inesperado: {exc}")
