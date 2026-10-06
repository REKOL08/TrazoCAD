"""Orquesta el pipeline completo: PDF -> imágenes -> líneas -> DXF -> DWG."""

from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

import math

import numpy as np

from .dwg_converter import convert_dxf_to_dwg
from .deskew import deskew
from .detalle import detect_detail_strokes, drop_debris, drop_inside_fixtures
from .dxf_writer import build_dxf
from .line_detector import detect_lines, filter_short_segments, merge_collinear_segments
from .muebles import detect_fixtures
from .orientacion import detect_rotation, detect_title_block_fraction
from .muros import detect_plan
from .puertas import detect_doors
from .ventanas import detect_windows
from .vectorizer import binarize_ink
from .pdf_processor import render_pdf_pages
from .burbujas import Bubble, find_axis_bubbles, find_loose_bubbles, read_labels
from .ejes import complete_bubbles, radial_axes, refine_axes
from .fotos import fuse_photos, register_photos
from .organizar import FOLDER_PDF, FOLDER_PHOTOS, FOLDER_PLAN, FOLDER_PREVIEW, copy_unique, save_scan_preview, write_readme
from .texto import TextItem, read_texts
from .vista_previa import render_dxf_preview
from .utils import ConversionError, validate_pdf
from .vectorizer import trace_shapes

logger = logging.getLogger("planos2dwg")

DEFAULT_MIN_LENGTH_MM = 8.0
MODE_TRACE = "fiel"
MODE_LINES = "lineas"
VALID_ROTATIONS = (0, 90, 180, 270)


def _without_read_letters(shapes: list, texts: list[TextItem]) -> list:
    """Quita del calco las letras que el OCR leyó con seguridad (ya son texto editable).

    Las lecturas dudosas se dejan en el calco para poder comparar y corregir.
    """
    sure = [t for t in texts if t.sure]
    if not sure:
        return shapes
    kept = []
    for shape in shapes:
        outer = shape[0]
        cx = sum(p[0] for p in outer) / len(outer)
        cy = sum(p[1] for p in outer) / len(outer)
        if not any(t.contains(cx, cy) for t in sure):
            kept.append(shape)
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


def _door_segments(doors: list) -> list:
    """Segmentos que representan las puertas (arco aproximado y hoja), para medir el calco."""
    segments = _arc_segments([door.arc for door in doors])
    segments.extend(door.leaf for door in doors if door.leaf is not None)
    return segments


def _without_door_arcs(arcs: list, doors: list, tol_px: float) -> list:
    """Quita de ARCOS los arcos que en realidad son el giro de una puerta ya detectada."""
    return [
        arc
        for arc in arcs
        if not any(
            math.hypot(arc.cx - door.arc.cx, arc.cy - door.arc.cy) < tol_px
            and abs(arc.radius - door.arc.radius) < tol_px
            for door in doors
        )
    ]


def _without_explained(shapes: list, clean_segments: list, tol_px: float, share: float = 0.85) -> list:
    """Quita del calco los contornos que ya están representados por líneas limpias.

    El calco de un muro o de un eje es el contorno fino alrededor de la línea
    que ya se dibujó limpia en MUROS, EJES o ARCOS; dejarlo duplica el trazo y
    ensucia el dibujo. Se descarta el contorno cuyos vértices están (en su
    gran mayoría) pegados a alguna línea limpia.
    """
    if not clean_segments or not shapes:
        return shapes
    starts = np.array([a for a, _b in clean_segments], dtype=np.float64)
    ends = np.array([b for _a, b in clean_segments], dtype=np.float64)
    along = ends - starts
    squared = np.maximum((along**2).sum(axis=1), 1e-9)
    kept = []
    for shape in shapes:
        points = np.array(shape[0], dtype=np.float64)
        t = np.clip(((points[:, None, :] - starts[None]) * along[None]).sum(axis=2) / squared, 0.0, 1.0)
        nearest = starts[None] + t[..., None] * along[None]
        distance = np.hypot(*(points[:, None, :] - nearest).transpose(2, 0, 1)).min(axis=1)
        if (distance <= tol_px).mean() < share:
            kept.append(shape)
    return kept


def rotate_image(image: np.ndarray, degrees_ccw: int) -> np.ndarray:
    """Gira `image` en sentido antihorario (0, 90, 180 o 270 grados)."""
    if degrees_ccw not in VALID_ROTATIONS:
        raise ConversionError(f"El giro debe ser uno de {VALID_ROTATIONS}, no {degrees_ccw}.")
    if degrees_ccw == 0:
        return image
    return np.ascontiguousarray(np.rot90(image, degrees_ccw // 90))


def _copy_replacing(source: Path, target: Path) -> Path:
    """Copia `source` a `target` (reemplazándolo). Si Windows lo tiene bloqueado, usa otro nombre."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, target)
    except PermissionError:
        target = target.with_name(f"{target.stem}_{datetime.now().strftime('%H%M%S')}{target.suffix}")
        logger.warning("El archivo anterior está en uso (¿abierto en AutoCAD?); se guarda como %s", target.name)
        shutil.copy2(source, target)
    return target


def _deliver(dxf_path: Path, output_dir: Path, generate_dwg: bool, keep_dxf: bool) -> list[Path]:
    """Entrega UN archivo por plano: el .dwg si se puede generar; si no, el .dxf.

    El DXF se construye en una carpeta temporal; solo se guarda junto al DWG si se
    pidió conservarlo.
    """
    if generate_dwg:
        with tempfile.TemporaryDirectory(prefix="planos2dwg_dwg_") as tmp:
            built = convert_dxf_to_dwg(dxf_path, Path(tmp))
            if built is not None:
                delivered = [_copy_replacing(built, output_dir / built.name)]
                if keep_dxf:
                    delivered.append(_copy_replacing(dxf_path, output_dir / dxf_path.name))
                return delivered
    return [_copy_replacing(dxf_path, output_dir / dxf_path.name)]


def _bubble_outline(bubble: Bubble, sides: int = 24) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """El aro de una burbuja como segmentos, para quitarlo del detalle (ya se dibuja como círculo)."""
    points = [
        (bubble.x + bubble.r * math.cos(2 * math.pi * k / sides), bubble.y + bubble.r * math.sin(2 * math.pi * k / sides))
        for k in range(sides + 1)
    ]
    return list(zip(points, points[1:]))


def _axes_with_bubbles(image, ink, walls, axes, dpi: int, bottom: float):
    """Valida los ejes con sus burbujas: descarta los falsos y completa los que faltaban."""
    if not walls or not axes:
        return axes, [], []
    xs = [p[0] for wall in walls for p in wall]
    ys = [p[1] for wall in walls for p in wall]
    box = (min(xs), min(ys), max(xs), max(ys))
    bubbles = find_axis_bubbles(image, ink, axes, dpi, box, max_y=image.shape[0] * (1 - bottom))
    if len(bubbles) < 3:
        return axes, [], []
    labels = read_labels(image, bubbles)
    refined = refine_axes(axes, bubbles, ink > 0, box)
    # las burbujas de los ejes radiales (la parte circular) y las de abajo: todas miden lo mismo que las ya vistas
    radius = float(np.median([b.r for b in bubbles]))
    loose = find_loose_bubbles(image, ink, radius, bubbles, max_y=image.shape[0] * (1 - bottom))
    radial_bubbles, radial_segments, aligned = radial_axes(loose, ink > 0)
    everyone = bubbles + aligned + radial_bubbles
    refined, missing = complete_bubbles(refined + radial_segments, everyone, radius)
    everyone += missing
    return refined, everyone, labels + [""] * (len(everyone) - len(labels))


def _anchor_points(segments: list, texts: list, bubbles: list, step: float = 25.0) -> np.ndarray:
    """Puntos que representan lo ya reconocido (segmentos muestreados, centros de texto y de burbuja)."""
    points: list[tuple[float, float]] = []
    for (x1, y1), (x2, y2) in segments:
        n = max(int(math.hypot(x2 - x1, y2 - y1) // step), 1)
        points.extend((x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(n + 1))
    points.extend((float(t.quad[:, 0].mean()), float(t.quad[:, 1].mean())) for t in texts)
    points.extend((b.x, b.y) for b in bubbles)
    return np.array(points, dtype=np.float64).reshape(-1, 2)


def _make_previews(dxf_path: Path, image, preview_dir: Path, stem: str) -> list[Path]:
    """Imagen del resultado (dibujada desde el DXF) y del escaneo enderezado. Un fallo no tumba la conversión."""
    made: list[Path] = []
    try:
        result = render_dxf_preview(dxf_path, preview_dir / f"{stem}_resultado.png")
        if result is not None:
            made.append(result)
        made.append(save_scan_preview(image, preview_dir / f"{stem}_escaneo.png"))
    except Exception:
        logger.warning("No se pudo generar la vista previa de '%s'.", stem, exc_info=True)
    return made


LOW_RESOLUTION_DPI = 250


def _warn_if_low_resolution(pdf_name: str, native_dpi: float | None) -> None:
    if native_dpi is not None and native_dpi < LOW_RESOLUTION_DPI:
        logger.warning(
            "'%s': el escaneo del PDF tiene solo %d dpi reales. Los textos pequeños y las cotas "
            "no se podrán leer bien; para un buen resultado escanea a 300-400 dpi.",
            pdf_name,
            round(native_dpi),
        )


@dataclass
class ConversionResult:
    pdf_path: Path
    success: bool
    outputs: list[Path] = field(default_factory=list)
    error: str | None = None
    summary: dict[str, int] = field(default_factory=dict)
    previews: list[Path] = field(default_factory=list)
    photos_used: list[Path] = field(default_factory=list)


def convert_pdf(
    pdf_path: Path,
    output_dir: Path,
    dpi: int,
    generate_dwg: bool = True,
    min_length_mm: float = DEFAULT_MIN_LENGTH_MM,
    mode: str = MODE_TRACE,
    rotation: int | None = None,
    ignore_bottom_fraction: float | None = None,
    clean_only: bool = False,
    wall_thickness_mm: float | None = None,
    read_text: bool = True,
    keep_dxf: bool = False,
    trace_visible: bool = False,
    photos: list[Path] | None = None,
    organize: bool = False,
) -> ConversionResult:
    """Convierte un único PDF en un archivo de AutoCAD por página (.dwg, o .dxf sin ODA).

    `rotation` e `ignore_bottom_fraction` en None se detectan solos (giro de página y cajetín).
    `photos`: fotos de partes del plano; las que coinciden con él se fusionan con el escaneo para
    ganar detalle en muros, líneas, textos y cotas (las que no coinciden, se ignoran).
    `organize`: ordena `output_dir` en subcarpetas (plano, vista previa, fotos usadas, PDF original).

    No lanza excepciones hacia el llamador: cualquier error se captura y se
    devuelve dentro de ConversionResult para que un lote de PDFs pueda
    seguir procesando los siguientes archivos aunque uno falle.
    """
    pdf_path = Path(pdf_path)
    try:
        validate_pdf(pdf_path)
        pages = render_pdf_pages(pdf_path, dpi=dpi)

        outputs: list[Path] = []
        previews: list[Path] = []
        photos_used: list[Path] = []
        summary: dict[str, int] = {}
        plan_dir = output_dir / FOLDER_PLAN if organize else output_dir
        for page in pages:
            _warn_if_low_resolution(pdf_path.name, page.native_dpi)
            page_rotation = detect_rotation(page.image, page.dpi) if rotation is None else rotation
            image = deskew(rotate_image(page.image, page_rotation), page.dpi)
            registered = register_photos(image, photos) if photos else []
            if registered:
                image = fuse_photos(image, registered)
                photos_used.extend(r.path for r in registered if r.path not in photos_used)
            bottom = detect_title_block_fraction(image, page.dpi) if ignore_bottom_fraction is None else ignore_bottom_fraction
            segments: list = []
            polylines: list = []
            shapes: list = []
            walls: list = []
            axes: list = []
            arcs: list = []
            texts: list = []
            doors: list = []
            windows: list = []
            fixtures: list = []
            detail: list = []
            bubbles: list = []
            bubble_labels: list = []
            if mode == MODE_LINES:
                segments = detect_lines(image)
                segments = merge_collinear_segments(segments, dpi=page.dpi)
                segments = filter_short_segments(
                    segments, min_length_mm=min_length_mm, dpi=page.dpi
                )
            else:
                walls, axes, arcs, thickness = detect_plan(
                    image,
                    page.dpi,
                    ignore_bottom_fraction=bottom,
                    wall_thickness_mm=wall_thickness_mm,
                )
                ink = binarize_ink(image, page.dpi)
                axes, bubbles, bubble_labels = _axes_with_bubbles(image, ink, walls, axes, page.dpi, bottom)
                doors = detect_doors(image, page.dpi, wall_thickness_px=thickness)
                arcs = _without_door_arcs(arcs, doors, tol_px=1.5 * (thickness or page.dpi / 25.4))
                windows = detect_windows(walls, ink, page.dpi, thickness or page.dpi / 25.4)
                if read_text:
                    texts = read_texts(image, ignore_bottom_fraction=bottom)
                fixtures = detect_fixtures(image, page.dpi, texts, wall_thickness_px=thickness)
                explained = (
                    list(walls)
                    + list(axes)
                    + _arc_segments(arcs)
                    + _door_segments(doors)
                    + [line for window in windows for line in window.lines]
                    + [seg for f in fixtures for seg in zip(f.outline(), f.outline()[1:])]
                    + [seg for b in bubbles for seg in _bubble_outline(b)]
                )
                # la letra de una burbuja leída se escribe como texto: se borra del detalle para no repetirla
                label_boxes = [
                    TextItem(label, 1.0, np.array([[b.x - 0.6 * b.r, b.y - 0.6 * b.r], [b.x + 0.6 * b.r, b.y - 0.6 * b.r], [b.x + 0.6 * b.r, b.y + 0.6 * b.r], [b.x - 0.6 * b.r, b.y + 0.6 * b.r]]), True)
                    for b, label in zip(bubbles, bubble_labels)
                    if label
                ]
                detail = detect_detail_strokes(image, page.dpi, explained, texts + label_boxes, ignore_bottom_fraction=bottom)
                detail = drop_debris(detail, _anchor_points(explained, texts, bubbles), page.dpi, image.shape[:2])
                detail = drop_inside_fixtures(detail, fixtures)
                if not clean_only:
                    shapes = _without_read_letters(trace_shapes(image, dpi=page.dpi), texts)
                    before = len(shapes)
                    shapes = _without_explained(shapes, explained, tol_px=0.45 * page.dpi / 25.4)
                    logger.info(
                        "Calco: %d contornos ya explicados por muros, ejes y arcos se quitan.",
                        before - len(shapes),
                    )
            if not any((segments, shapes, walls, axes, arcs, texts, doors, windows, fixtures, detail)):
                logger.warning(
                    "'%s' página %d: no se detectó geometría; se omite esta página.",
                    pdf_path.name,
                    page.page_number,
                )
                continue

            suffix = "" if len(pages) == 1 else f"_p{page.page_number}"
            with tempfile.TemporaryDirectory(prefix="planos2dwg_dxf_") as tmp:
                dxf_path = Path(tmp) / f"{pdf_path.stem}{suffix}.dxf"
                build_dxf(
                    segments,
                    dpi=page.dpi,
                    image_height_px=image.shape[0],
                    output_path=dxf_path,
                    shapes=shapes,
                    walls=walls,
                    axes=axes,
                    arcs=arcs,
                    texts=texts,
                    doors=doors,
                    windows=windows,
                    fixtures=fixtures,
                    detail=detail,
                    trace_visible=trace_visible,
                    axis_bubbles=[(b.x, b.y, b.r, label) for b, label in zip(bubbles, bubble_labels)],
                )
                outputs.extend(_deliver(dxf_path, plan_dir, generate_dwg, keep_dxf))
                if organize:
                    previews.extend(_make_previews(dxf_path, image, output_dir / FOLDER_PREVIEW, f"{pdf_path.stem}{suffix}"))
            for key, items in (
                ("muros", walls), ("ejes", axes), ("arcos", arcs), ("puertas", doors),
                ("ventanas", windows), ("sanitarios", fixtures), ("burbujas de eje", bubbles), ("textos", texts), ("lineas de detalle", detail),
            ):
                summary[key] = summary.get(key, 0) + len(items)

        if not outputs:
            return ConversionResult(
                pdf_path=pdf_path,
                success=False,
                error="No se detectó ninguna línea en el PDF; revisa la calidad del escaneo.",
            )

        if organize:
            copy_unique(pdf_path, output_dir / FOLDER_PDF)
            kept = [copy_unique(p, output_dir / FOLDER_PHOTOS) for p in photos_used]
            write_readme(output_dir, pdf_path.name, summary, len(kept))
            photos_used = kept

        return ConversionResult(
            pdf_path=pdf_path, success=True, outputs=outputs, summary=summary, previews=previews, photos_used=photos_used
        )

    except ConversionError as exc:
        logger.error("'%s': %s", pdf_path.name, exc)
        return ConversionResult(pdf_path=pdf_path, success=False, error=str(exc))
    except Exception as exc:  # protección final: un PDF problemático no debe tumbar el lote
        logger.exception("Error inesperado procesando '%s'", pdf_path.name)
        return ConversionResult(pdf_path=pdf_path, success=False, error=f"Error inesperado: {exc}")
