"""Imagen de vista previa del plano convertido, dibujada a partir del propio DXF.

Sirve para ver el resultado sin abrir AutoCAD. Se lee el DXF que se va a entregar (lo mismo que
contiene el .dwg): líneas, polilíneas, arcos, círculos, elipses y textos, con el color y el grosor
de su capa. Las capas apagadas (el relleno gris del escaneo) no se dibujan.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import ezdxf
from ezdxf import colors as dxf_colors
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("planos2dwg")

_SUPERSAMPLE = 2
_MARGIN_FRACTION = 0.03
_MIN_LINE_PX = 1.0
_FONT_CANDIDATES = ("arial.ttf", "segoeui.ttf", "calibri.ttf", "DejaVuSans.ttf")


def _layer_color(doc, layer_name: str) -> tuple[int, int, int]:
    layer = doc.layers.get(layer_name)
    aci = abs(layer.color) if layer is not None else 7
    if aci in (7, 0, 255):  # el blanco de CAD se vería invisible sobre papel claro
        return (30, 38, 52)
    return tuple(dxf_colors.aci2rgb(aci))  # type: ignore[return-value]


def _layer_width(doc, layer_name: str) -> float:
    layer = doc.layers.get(layer_name)
    weight = getattr(layer.dxf, "lineweight", -3) if layer is not None else -3
    return weight / 100.0 if weight and weight > 0 else 0.18  # milímetros sobre el papel


def _is_visible(doc, layer_name: str) -> bool:
    layer = doc.layers.get(layer_name)
    return layer is None or not (layer.is_off() or layer.is_frozen())


def _font(size_px: float) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, max(int(round(size_px)), 6))
        except OSError:
            continue
    return ImageFont.load_default()


def _entity_points(entity) -> list[tuple[float, float]]:
    kind = entity.dxftype()
    if kind == "LINE":
        return [(entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)]
    if kind == "LWPOLYLINE":
        return [(p[0], p[1]) for p in entity.get_points("xy")]
    if kind in ("CIRCLE", "ARC"):
        c, r = entity.dxf.center, entity.dxf.radius
        return [(c.x - r, c.y - r), (c.x + r, c.y + r)]
    if kind == "ELLIPSE":
        c, major = entity.dxf.center, entity.dxf.major_axis
        radius = math.hypot(major.x, major.y)
        return [(c.x - radius, c.y - radius), (c.x + radius, c.y + radius)]
    if kind == "TEXT":
        return [(entity.dxf.insert.x, entity.dxf.insert.y)]
    return []


def _dashed_line(draw, start: tuple[float, float], end: tuple[float, float], color, width: int, scale: float) -> None:
    """Línea de trazos: raya de 3 mm y hueco de 1,5 mm sobre el papel (como el DASHED del DXF con LTSCALE 0,25)."""
    length = math.dist(start, end)
    if length == 0:
        return
    dash, gap = 3.2 * scale, 1.6 * scale
    ux, uy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
    position = 0.0
    while position < length:
        stop = min(position + dash, length)
        draw.line((start[0] + ux * position, start[1] + uy * position, start[0] + ux * stop, start[1] + uy * stop), fill=color, width=width)
        position += dash + gap


def render_dxf_preview(dxf_path: Path, output_png: Path, max_px: int = 2400) -> Path | None:
    """Dibuja el DXF en un PNG de lado mayor `max_px`. Devuelve la ruta, o None si no hay nada que dibujar."""
    doc = ezdxf.readfile(dxf_path)
    modelspace = doc.modelspace()
    entities = [e for e in modelspace if _is_visible(doc, e.dxf.layer) and e.dxftype() in
                ("LINE", "LWPOLYLINE", "CIRCLE", "ARC", "ELLIPSE", "TEXT")]
    points = [pt for e in entities for pt in _entity_points(e)]
    if not points:
        return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    span = max(max_x - min_x, max_y - min_y, 1e-6)
    scale = max_px * _SUPERSAMPLE / (span * (1 + 2 * _MARGIN_FRACTION))
    pad = span * _MARGIN_FRACTION
    width = int((max_x - min_x + 2 * pad) * scale) + 1
    height = int((max_y - min_y + 2 * pad) * scale) + 1

    def to_px(x: float, y: float) -> tuple[float, float]:
        return (x - min_x + pad) * scale, (max_y - y + pad) * scale

    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    # los trazos finos primero y los muros encima, como en un plano real
    for entity in sorted(entities, key=lambda e: _layer_width(doc, e.dxf.layer)):
        layer = entity.dxf.layer
        color = _layer_color(doc, layer)
        line_px = max(_layer_width(doc, layer) * scale, _MIN_LINE_PX * _SUPERSAMPLE)
        width_px = max(int(round(line_px)), 1)
        kind = entity.dxftype()
        if kind == "LINE" and layer == "LINEAS_DISCONTINUAS":
            _dashed_line(draw, to_px(*_entity_points(entity)[0]), to_px(*_entity_points(entity)[1]), color, width_px, scale)
        elif kind in ("LINE", "LWPOLYLINE"):
            pts = [to_px(x, y) for x, y in _entity_points(entity)]
            if kind == "LWPOLYLINE" and entity.closed and len(pts) > 2:
                pts.append(pts[0])
            if len(pts) >= 2:
                draw.line(pts, fill=color, width=width_px, joint="curve")
        elif kind == "CIRCLE":
            cx, cy = to_px(entity.dxf.center.x, entity.dxf.center.y)
            r = entity.dxf.radius * scale
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=width_px)
        elif kind == "ARC":
            cx, cy = to_px(entity.dxf.center.x, entity.dxf.center.y)
            r = entity.dxf.radius * scale
            # el eje Y de la imagen va hacia abajo: los ángulos se espejan
            draw.arc((cx - r, cy - r, cx + r, cy + r), -entity.dxf.end_angle, -entity.dxf.start_angle, fill=color, width=width_px)
        elif kind == "ELLIPSE":
            cx, cy = to_px(entity.dxf.center.x, entity.dxf.center.y)
            major = entity.dxf.major_axis
            a = math.hypot(major.x, major.y) * scale
            b = a * entity.dxf.ratio
            # elipse inclinada: se muestrea como polilínea
            tilt = math.atan2(major.y, major.x)
            samples = []
            for k in range(0, 73):
                t = 2 * math.pi * k / 72
                ex, ey = a * math.cos(t), b * math.sin(t)
                samples.append((cx + ex * math.cos(tilt) + ey * math.sin(tilt), cy + ex * math.sin(tilt) - ey * math.cos(tilt)))
            draw.line(samples, fill=color, width=width_px)
        elif kind == "TEXT":
            text = entity.dxf.text
            if not text.strip():
                continue
            size_px = entity.dxf.height * scale
            if size_px < 4:
                continue
            font = _font(size_px)
            box = draw.textbbox((0, 0), text, font=font)
            tile = Image.new("RGBA", (box[2] + 4, box[3] + 4), (255, 255, 255, 0))
            ImageDraw.Draw(tile).text((0, 0), text, font=font, fill=color + (255,))
            angle = float(entity.dxf.get("rotation", 0.0))
            tw, th = tile.size
            rotated = tile.rotate(angle, expand=True, resample=Image.BICUBIC)
            rad = math.radians(angle)
            # el texto se inserta por su esquina inferior izquierda: se lleva esa esquina a (x, y)
            corner_x = -tw / 2 * math.cos(rad) + th / 2 * math.sin(rad)
            corner_y = tw / 2 * math.sin(rad) + th / 2 * math.cos(rad)
            x, y = to_px(entity.dxf.insert.x, entity.dxf.insert.y)
            image.paste(rotated, (int(x - rotated.width / 2 - corner_x), int(y - rotated.height / 2 - corner_y)), rotated)

    output_png.parent.mkdir(parents=True, exist_ok=True)
    image = image.resize((max(width // _SUPERSAMPLE, 1), max(height // _SUPERSAMPLE, 1)), Image.LANCZOS)
    image.save(output_png, optimize=True)
    logger.info("Vista previa: %s", output_png)
    return output_png
