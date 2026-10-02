"""Orquesta el pipeline completo: PDF -> imágenes -> líneas -> DXF -> DWG."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .dwg_converter import convert_dxf_to_dwg
from .dxf_writer import build_dxf
from .line_detector import detect_lines, filter_short_segments, merge_collinear_segments
from .pdf_processor import render_pdf_pages
from .utils import ConversionError, validate_pdf

logger = logging.getLogger("planos2dwg")

DEFAULT_MIN_LENGTH_MM = 8.0


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
            segments = detect_lines(page.image)
            segments = merge_collinear_segments(segments, dpi=page.dpi)
            segments = filter_short_segments(segments, min_length_mm=min_length_mm, dpi=page.dpi)
            if not segments:
                logger.warning(
                    "'%s' página %d: no se detectó geometría; se omite esta página.",
                    pdf_path.name,
                    page.page_number,
                )
                continue

            suffix = "" if len(pages) == 1 else f"_p{page.page_number}"
            dxf_path = output_dir / f"{pdf_path.stem}{suffix}.dxf"
            build_dxf(
                segments,
                dpi=page.dpi,
                image_height_px=page.image.shape[0],
                output_path=dxf_path,
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
