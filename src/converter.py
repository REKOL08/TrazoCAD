"""Orquesta el pipeline completo: PDF -> imágenes -> líneas -> DXF -> DWG."""

from __future__ import annotations

import logging
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

import math

import numpy as np

from .dwg_converter import convert_dxf_to_dwg
from .deskew import deskew
from .dxf_writer import build_dxf
from .line_detector import detect_lines, filter_short_segments, merge_collinear_segments
from .muros import detect_walls_and_axes
from .pdf_processor import render_pdf_pages
from .texto import TextItem, read_texts
from .utils import ConversionError, validate_pdf
from .vectorizer import trace_ink

logger = logging.getLogger("planos2dwg")

DEFAULT_MIN_LENGTH_MM = 8.0
MODE_TRACE = "fiel"
MODE_LINES = "lineas"
VALID_ROTATIONS = (0, 90, 180, 270)


def _without_read_letters(polylines: list, texts: list[TextItem]) -> list:
    """Quita del calco las letras que el OCR leyó con seguridad (ya son texto editable).

    Las lecturas dudosas se dejan en el calco para poder comparar y corregir.
    """
    sure = [t for t in texts if t.sure]
    if not sure:
        return polylines
    kept = []
    for polyline in polylines:
        cx = sum(p[0] for p in polyline) / len(polyline)
        cy = sum(p[1] for p in polyline) / len(polyline)
        if not any(t.contains(cx, cy) for t in sure):
            kept.append(polyline)
    return kept


def _arc_segments(arcs: list, step_px: float = 15.0) -> list:
    """Aproxima cada arco por segmentos cortos (para medir distancias al calco)."""
    segments = []
    for arc in arcs:
        span = 360.0 if arc.is_circle else (arc.end_deg - arc.start_deg) % 360.0
        count = max(int(math.radians(span) * arc.radius / step_px), 3)
        points = [
            (
                arc.cx + arc.radius * math.cos(math.radians(arc.start_deg + span * k / count)),
                arc.cy - arc.radius * math.sin(math.radians(arc.start_deg + span * k / count)),
            )
            for k in range(count + 1)
        ]
        segments.extend(zip(points, points[1:]))
    return segments


def _without_explained(polylines: list, clean_segments: list, tol_px: float, share: float = 0.85) -> list:
    """Quita del calco los contornos que ya están representados por líneas limpias.

    El calco de un muro o de un eje es el contorno fino alrededor de la línea
    que ya se dibujó limpia en MUROS, EJES o ARCOS; dejarlo duplica el trazo y
    ensucia el dibujo. Se descarta el contorno cuyos vértices están (en su
    gran mayoría) pegados a alguna línea limpia.
    """
    if not clean_segments or not polylines:
        return polylines
    starts = np.array([a for a, _b in clean_segments], dtype=np.float64)
    ends = np.array([b for _a, b in clean_segments], dtype=np.float64)
    along = ends - starts
    squared = np.maximum((along**2).sum(axis=1), 1e-9)
    kept = []
    for polyline in polylines:
        points = np.array(polyline, dtype=np.float64)
        t = np.clip(((points[:, None, :] - starts[None]) * along[None]).sum(axis=2) / squared, 0.0, 1.0)
        nearest = starts[None] + t[..., None] * along[None]
        distance = np.hypot(*(points[:, None, :] - nearest).transpose(2, 0, 1)).min(axis=1)
        if (distance <= tol_px).mean() < share:
            kept.append(polyline)
    return kept


def rotate_image(image: np.ndarray, degrees_ccw: int) -> np.ndarray:
    """Gira `image` en sentido antihorario (0, 90, 180 o 270 grados)."""
    if degrees_ccw not in VALID_ROTATIONS:
        raise ConversionError(f"El giro debe ser uno de {VALID_ROTATIONS}, no {degrees_ccw}.")
    if degrees_ccw == 0:
        return image
    return np.ascontiguousarray(np.rot90(image, degrees_ccw // 90))


def _save_dxf(path: Path, **geometry) -> Path:
    """Escribe el DXF; si Windows lo tiene bloqueado, lo guarda con otra hora en el nombre."""
    try:
        build_dxf(output_path=path, **geometry)
    except PermissionError:
        path = path.with_name(f"{path.stem}_{datetime.now().strftime('%H%M%S')}.dxf")
        logger.warning("El archivo está en uso (¿abierto en AutoCAD?); se guarda como %s", path.name)
        build_dxf(output_path=path, **geometry)
    return path


def _timestamp() -> str:
    """Marca de tiempo para el nombre del archivo: cada conversión es un archivo nuevo."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


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
    wall_thickness_mm: float | None = None,
    read_text: bool = True,
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
            arcs: list = []
            texts: list = []
            if mode == MODE_LINES:
                segments = detect_lines(image)
                segments = merge_collinear_segments(segments, dpi=page.dpi)
                segments = filter_short_segments(
                    segments, min_length_mm=min_length_mm, dpi=page.dpi
                )
            else:
                walls, axes, arcs = detect_walls_and_axes(
                    image,
                    page.dpi,
                    ignore_bottom_fraction=ignore_bottom_fraction,
                    wall_thickness_mm=wall_thickness_mm,
                )
                if read_text:
                    texts = read_texts(image, ignore_bottom_fraction=ignore_bottom_fraction)
                if not clean_only:
                    polylines = _without_read_letters(trace_ink(image, dpi=page.dpi), texts)
                    before = len(polylines)
                    polylines = _without_explained(
                        polylines,
                        list(walls) + list(axes) + _arc_segments(arcs),
                        tol_px=0.45 * page.dpi / 25.4,
                    )
                    logger.info(
                        "Calco: %d contornos ya explicados por muros, ejes y arcos se quitan.",
                        before - len(polylines),
                    )
            if not segments and not polylines and not walls and not axes and not arcs and not texts:
                logger.warning(
                    "'%s' página %d: no se detectó geometría; se omite esta página.",
                    pdf_path.name,
                    page.page_number,
                )
                continue

            suffix = "" if len(pages) == 1 else f"_p{page.page_number}"
            # nombre único por conversión: nunca se pisa un DXF que AutoCAD,
            # OneDrive o el antivirus puedan tener bloqueado
            base = output_dir / f"{pdf_path.stem}{suffix}_{_timestamp()}"

            # Con calco se entregan dos archivos: el completo (con el calco de
            # referencia) y el limpio (solo lo reconstruido), para no tener que
            # apagar capas a mano.
            variants = [("", polylines)]
            if mode == MODE_TRACE and not clean_only:
                variants = [("_completo", polylines), ("_limpio", [])]

            for tag, variant_polylines in variants:
                dxf_path = _save_dxf(
                    Path(f"{base}{tag}.dxf"),
                    segments=segments,
                    dpi=page.dpi,
                    image_height_px=image.shape[0],
                    polylines=variant_polylines,
                    walls=walls,
                    axes=axes,
                    arcs=arcs,
                    texts=texts,
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
