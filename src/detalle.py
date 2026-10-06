"""Trazos de detalle de un solo trazo: todo lo que no es muro, eje, arco, puerta ni texto.

Lo que no se reconstruye con un detector específico (cotas, contornos de mobiliario y
sanitarios, escaleras, rayados, curvas pequeñas) se rehace como **líneas de un solo trazo**:
se borra de la tinta lo ya dibujado en otra capa y las letras leídas, lo que queda se
adelgaza a su línea central (esqueleto), se recorre como un grafo, se simplifica y se
endereza. El resultado son polilíneas finas y rectas donde el escaneo era recto, no el
doble contorno irregular de un relleno.
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from .centerline import Stroke, skeletonize, trace_skeleton
from .line_detector import Segment, merge_collinear_segments
from .texto import TextItem
from .vectorizer import binarize_ink

logger = logging.getLogger("planos2dwg")

_MM_PER_INCH = 25.4
_ERASE_BAND_PX_AT_300 = 9
_MIN_STROKE_LENGTH_MM = 0.9
_SPUR_MM = 0.8
_SIMPLIFY_MM = 0.14
_SNAP_MIN_MM = 3.0
_SNAP_ANGLE_DEG = 1.5
_MIN_COMPONENT_MM = 0.9
_DASH_MIN_MM = 0.3
_DASH_MAX_MM = 2.5
_DASH_ELONGATION = 2.0
_DASH_NEIGHBOUR_MM = 3.0
_DASH_MIN_NEIGHBOURS = 2
_JOIN_TOLERANCE_MM = 0.25
_JOIN_MIN_COSINE = math.cos(math.radians(35))
_DASH_LINE_ANGLE = math.sin(math.radians(2.5))  # rayas casi paralelas
_DASH_LINE_OFFSET_PX = 3.0  # ...y sobre la misma recta
_DASH_LINE_GAP_MM = 6.0  # separación máxima entre rayas seguidas de una misma línea (cubre los puntos del trazo y punto)
_DASH_LINE_MIN_DASHES = 3
_DASH_LINE_SHORT_MM = 10.0  # una recta más corta que esto puede ser una raya de una línea de trazos
_SCRIBBLE_MAX_MM = 8.0  # un trazo abierto más corto que esto y retorcido es un resto de letra o de sombra
_SCRIBBLE_MIN_POINTS = 4
_SCRIBBLE_STRAIGHTNESS = 0.85
_SCRIBBLE_MIN_REVERSALS = 2  # veces que el giro cambia de sentido: una curva suave no cambia nunca
_SCRIBBLE_MIN_TURN_DEG = 30  # los giros menores son el temblor del esqueleto, no un cambio de sentido
_DEBRIS_FAR_MM = 30.0  # un trazo corto a más de esto de todo lo reconocido (muros, ejes, textos...) es un resto suelto
_DEBRIS_MAX_MM = 100.0
_FRAME_EDGE_FRACTION = 0.06  # el marco de la hoja: una línea larga pegada al borde
_FRAME_MIN_FRACTION = 0.4


def _snap_orthogonal(points: list[tuple[float, float]], min_length_px: float) -> list[tuple[float, float]]:
    """Endereza a H/V exactos los tramos largos casi horizontales o verticales."""
    pts = [list(p) for p in points]
    tolerance = math.tan(math.radians(_SNAP_ANGLE_DEG))
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        dx, dy = x2 - x1, y2 - y1
        if math.hypot(dx, dy) < min_length_px:
            continue
        if abs(dy) <= tolerance * abs(dx):
            pts[i][1] = pts[i + 1][1] = (y1 + y2) / 2
        elif abs(dx) <= tolerance * abs(dy):
            pts[i][0] = pts[i + 1][0] = (x1 + x2) / 2
    return [(p[0], p[1]) for p in pts]


def _join_strokes(strokes: list[Stroke], tolerance_px: float) -> list[Stroke]:
    """Une los trazos cuyos extremos se tocan y siguen en la misma dirección.

    El esqueleto deja nudos falsos que parten una misma curva en trozos; un dibujo
    profesional tiene una polilínea por curva. Se une cada extremo solo con su vecino más
    cercano (si es mutuo) y solo cuando la unión es suave (giro de menos de 35°).
    """
    pieces = [list(s.points) for s in strokes if not s.closed]
    closed = [s for s in strokes if s.closed]

    def outward(points: list[tuple[float, float]], end: int) -> tuple[float, float]:
        (x1, y1), (x2, y2) = (points[-1], points[-2]) if end else (points[0], points[1])
        return x1 - x2, y1 - y2

    changed = True
    while changed:
        changed = False
        cells: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for index, points in enumerate(pieces):
            for end in (0, 1):
                x, y = points[-1] if end else points[0]
                cells.setdefault((int(x // tolerance_px), int(y // tolerance_px)), []).append((index, end))

        def nearest(index: int, end: int) -> tuple[int, int] | None:
            x, y = pieces[index][-1] if end else pieces[index][0]
            best, best_distance = None, tolerance_px
            for cx in range(int(x // tolerance_px) - 1, int(x // tolerance_px) + 2):
                for cy in range(int(y // tolerance_px) - 1, int(y // tolerance_px) + 2):
                    for other, other_end in cells.get((cx, cy), []):
                        if other == index:
                            continue
                        ox, oy = pieces[other][-1] if other_end else pieces[other][0]
                        distance = math.hypot(ox - x, oy - y)
                        if distance <= best_distance:
                            best, best_distance = (other, other_end), distance
            return best

        used: set[int] = set()
        merged: list[list[tuple[float, float]]] = []
        for index in range(len(pieces)):
            if index in used:
                continue
            joined = False
            for end in (1, 0):
                partner = nearest(index, end)
                if partner is None or partner[0] in used or partner[0] == index:
                    continue
                other, other_end = partner
                if nearest(other, other_end) != (index, end):
                    continue  # no es mutuo: hay un cruce, no una continuación
                ux, uy = outward(pieces[index], end)
                vx, vy = outward(pieces[other], other_end)
                norm = math.hypot(ux, uy) * math.hypot(vx, vy)
                if norm == 0 or -(ux * vx + uy * vy) / norm < _JOIN_MIN_COSINE:
                    continue
                first = pieces[index] if end else pieces[index][::-1]
                second = pieces[other][::-1] if other_end else pieces[other]
                merged.append(first + second)
                used.update((index, other))
                joined = changed = True
                break
            if not joined:
                merged.append(pieces[index])
                used.add(index)
        pieces = merged
    return [Stroke(points, False) for points in pieces] + closed


def group_dashes(dashes: list[Stroke], px_per_mm: float) -> list[Stroke]:
    """Une las rayas alineadas de una línea discontinua en UNA línea (marcada `dashed`), como la dibujaría un dibujante.

    Tres o más rayas casi paralelas, sobre la misma recta y con huecos cortos entre ellas son una sola línea de trazos
    o de trazo y punto. Las que no forman una cadena quedan como rayas sueltas.
    """
    if len(dashes) < _DASH_LINE_MIN_DASHES:
        return dashes
    gap_px = _DASH_LINE_GAP_MM * px_per_mm
    items = []
    for stroke in dashes:
        (x1, y1), (x2, y2) = stroke.points[0], stroke.points[-1]
        length = math.hypot(x2 - x1, y2 - y1)
        if length > 0:
            items.append((((x1 + x2) / 2, (y1 + y2) / 2), ((x2 - x1) / length, (y2 - y1) / length), stroke))

    clusters: list[list[int]] = []
    reference: list[tuple[tuple[float, float], tuple[float, float]]] = []  # (punto, dirección unitaria) por grupo
    for index, (middle, direction, _) in enumerate(items):
        for k, (point, u) in enumerate(reference):
            if abs(u[0] * direction[1] - u[1] * direction[0]) > _DASH_LINE_ANGLE:
                continue
            if abs((middle[0] - point[0]) * -u[1] + (middle[1] - point[1]) * u[0]) <= _DASH_LINE_OFFSET_PX:
                clusters[k].append(index)
                break
        else:
            clusters.append([index])
            reference.append((middle, direction))

    result: list[Stroke] = []
    grouped: set[int] = set()
    for members, (point, u) in zip(clusters, reference):
        if len(members) < _DASH_LINE_MIN_DASHES:
            continue

        def along(p: tuple[float, float]) -> float:
            return (p[0] - point[0]) * u[0] + (p[1] - point[1]) * u[1]

        spans = sorted(
            (min(along(items[m][2].points[0]), along(items[m][2].points[-1])), max(along(items[m][2].points[0]), along(items[m][2].points[-1])), m)
            for m in members
        )
        chain = [spans[0]]
        chains = []
        for span in spans[1:]:
            if span[0] - chain[-1][1] <= gap_px:
                chain.append((span[0], span[1], span[2]))
            else:
                chains.append(chain)
                chain = [span]
        chains.append(chain)
        for chain in chains:
            if len(chain) < _DASH_LINE_MIN_DASHES:
                continue
            offsets = [(items[m][0][0] - point[0]) * -u[1] + (items[m][0][1] - point[1]) * u[0] for _, _, m in chain]
            offset = sum(offsets) / len(offsets)
            low, high = min(c[0] for c in chain), max(c[1] for c in chain)
            start = (point[0] + u[0] * low - u[1] * offset, point[1] + u[1] * low + u[0] * offset)
            end = (point[0] + u[0] * high - u[1] * offset, point[1] + u[1] * high + u[0] * offset)
            result.append(Stroke([start, end], dashed=True))
            grouped.update(m for _, _, m in chain)
    loose = [items[i][2] for i in range(len(items)) if i not in grouped]
    return result + loose


def _turn_reversals(points: list[tuple[float, float]]) -> int:
    """Cuántas veces cambia de sentido el giro de una polilínea (ignorando los giros pequeños)."""
    signs = []
    for i in range(1, len(points) - 1):
        ax, ay = points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]
        bx, by = points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]
        angle = math.degrees(math.atan2(ax * by - ay * bx, ax * bx + ay * by))
        if abs(angle) >= _SCRIBBLE_MIN_TURN_DEG:
            signs.append(angle > 0)
    return sum(1 for a, b in zip(signs, signs[1:]) if a != b)


def drop_scribbles(strokes: list[Stroke], px_per_mm: float) -> list[Stroke]:
    """Quita los garabatos: trazos abiertos, cortos y retorcidos (restos de letras que el OCR no leyó, de sombras...)."""
    limit = _SCRIBBLE_MAX_MM * px_per_mm
    kept: list[Stroke] = []
    dropped = 0
    for stroke in strokes:
        points = stroke.points
        if not stroke.closed and len(points) >= _SCRIBBLE_MIN_POINTS:
            length = sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))
            if (
                length < limit
                and math.dist(points[0], points[-1]) / max(length, 1e-9) < _SCRIBBLE_STRAIGHTNESS
                and _turn_reversals(points) >= _SCRIBBLE_MIN_REVERSALS
            ):
                dropped += 1
                continue
        kept.append(stroke)
    if dropped:
        logger.info("Detalle: %d garabatos pequeños quitados.", dropped)
    return kept


def detect_detail_strokes(
    image: np.ndarray,
    dpi: int,
    explained: list[Segment],
    texts: list[TextItem],
    ignore_bottom_fraction: float = 0.0,
) -> list[Stroke]:
    """Devuelve los trazos de un solo trazo del dibujo que aún no está en otra capa."""
    px_per_mm = dpi / _MM_PER_INCH
    ink = binarize_ink(image, dpi)

    # borrar de la tinta lo ya reconstruido y las letras leídas con seguridad
    erase = np.zeros_like(ink)
    band = max(int(round(_ERASE_BAND_PX_AT_300 * dpi / 300)), 3)
    for a, b in explained:
        cv2.line(erase, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), 255, band)
    for item in texts:
        if item.sure:
            cv2.fillConvexPoly(erase, item.quad.astype(np.int32), 255)
    ink = cv2.bitwise_and(ink, cv2.bitwise_not(erase))
    if ignore_bottom_fraction > 0:
        ink[int(image.shape[0] * (1 - ignore_bottom_fraction)) :, :] = 0

    # cerrar huecos de 1 px y quitar las motas (manchas más cortas que ~1 mm); las rayas cortas
    # de una línea discontinua se conservan aparte: una mota suelta es ruido, pero varias
    # manchas cortas seguidas son los trazos de una línea de trazos o de trazo y punto
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(ink, connectivity=8)
    length = np.maximum(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT])

    # candidatas a raya de línea discontinua: manchas cortas Y alargadas (una "O" o una mota no lo son)
    dash_info: dict[int, tuple[float, float, float, float, float, float]] = {}
    for component in np.nonzero(
        (length >= _DASH_MIN_MM * px_per_mm)
        & (length <= _DASH_MAX_MM * px_per_mm)
        & (stats[:, cv2.CC_STAT_AREA] >= 4)
    )[0]:
        if component == 0:
            continue
        ys, xs = np.nonzero(labels == component)
        points = np.column_stack([xs, ys]).astype(np.float64)
        centre = points.mean(axis=0)
        eigenvalues, eigenvectors = np.linalg.eigh(np.cov((points - centre).T) + 1e-9 * np.eye(2))
        if np.sqrt(eigenvalues[1] / max(eigenvalues[0], 1e-9)) < _DASH_ELONGATION:
            continue
        direction = eigenvectors[:, 1]
        along = (points - centre) @ direction
        dash_info[int(component)] = (centre[0], centre[1], direction[0], direction[1], along.min(), along.max())

    # una raya suelta es ruido; varias seguidas son los trazos de una línea discontinua
    dashes: list[Stroke] = []
    ids = list(dash_info)
    if len(ids) > _DASH_MIN_NEIGHBOURS:
        centres = np.array([[dash_info[i][0], dash_info[i][1]] for i in ids])
        reach = _DASH_NEIGHBOUR_MM * px_per_mm
        dash_mask = np.zeros(count, dtype=bool)
        for k, component in enumerate(ids):
            if (np.hypot(*(centres - centres[k]).T) <= reach).sum() - 1 < _DASH_MIN_NEIGHBOURS:
                continue
            cx, cy, vx, vy, low, high = dash_info[component]
            dashes.append(Stroke([(float(cx + vx * low), float(cy + vy * low)), (float(cx + vx * high), float(cy + vy * high))]))
            dash_mask[component] = True
        ink[dash_mask[labels]] = 0
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(ink, connectivity=8)
        length = np.maximum(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT])

    keep = np.zeros(count, dtype=bool)
    keep[1:] = length[1:] >= _MIN_COMPONENT_MM * px_per_mm
    ink = np.where(keep[labels], 255, 0).astype(np.uint8)

    skeleton = skeletonize(ink)
    traced = trace_skeleton(
        skeleton, spur_px=_SPUR_MM * px_per_mm, min_length_px=_MIN_STROKE_LENGTH_MM * px_per_mm
    )

    traced = _join_strokes(traced, _JOIN_TOLERANCE_MM * px_per_mm)

    epsilon = _SIMPLIFY_MM * px_per_mm
    snap_min = _SNAP_MIN_MM * px_per_mm
    simplified: list[Stroke] = []
    for stroke in traced:
        approx = cv2.approxPolyDP(np.array(stroke.points, np.float32).reshape(-1, 1, 2), epsilon, stroke.closed)
        points = [(float(x), float(y)) for x, y in approx[:, 0, :]]
        if len(points) < 2 or (stroke.closed and len(points) < 3):
            continue
        simplified.append(Stroke(_snap_orthogonal(points, snap_min), stroke.closed))

    # los tramos rectos sueltos se unen cuando son colineales (un muro partido por un cruce)
    straight = [s for s in simplified if not s.closed and len(s.points) == 2]
    others = [s for s in simplified if s.closed or len(s.points) != 2]
    merged = merge_collinear_segments([(s.points[0], s.points[1]) for s in straight], dpi=dpi)
    # las rectas cortas (las rayas de una línea de trazos que el esqueleto sí recogió) se agrupan igual que las rayas detectadas
    short_limit = _DASH_LINE_SHORT_MM * px_per_mm
    pieces = [Stroke([a, b]) for a, b in merged]
    long_lines = [seg for seg in pieces if math.dist(seg.points[0], seg.points[1]) >= short_limit]
    short_lines = [seg for seg in pieces if math.dist(seg.points[0], seg.points[1]) < short_limit]
    result = drop_scribbles(others, px_per_mm) + long_lines + group_dashes(dashes + short_lines, px_per_mm)

    logger.info("Detalle: %d trazos (%d rectos, %d rayas en %d líneas discontinuas).", len(result), len(merged), len(dashes), sum(s.dashed for s in result))
    return result


def _stroke_length(stroke: Stroke) -> float:
    pts = stroke.points
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def drop_debris(strokes: list[Stroke], anchors: np.ndarray, dpi: int, image_shape: tuple[int, int]) -> list[Stroke]:
    """Quita los restos sueltos del escaneo: el marco de la hoja y los trazos cortos lejos de todo lo reconocido.

    `anchors` son puntos (x, y) de lo ya reconocido: muros, ejes, puertas, textos... Un detalle legítimo (una cota,
    una escalera, una proyección de cubierta) queda cerca de ellos; un sello de la hoja, una mancha o un trozo de
    marco no.
    """
    if not strokes:
        return strokes
    px_per_mm = dpi / _MM_PER_INCH
    far_px, max_px = _DEBRIS_FAR_MM * px_per_mm, _DEBRIS_MAX_MM * px_per_mm
    height, width = image_shape
    edge_x, edge_y = _FRAME_EDGE_FRACTION * width, _FRAME_EDGE_FRACTION * height
    kept: list[Stroke] = []
    dropped_frame = dropped_far = 0
    for stroke in strokes:
        xs = [p[0] for p in stroke.points]
        ys = [p[1] for p in stroke.points]
        span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
        near_edge = min(xs) < edge_x or max(xs) > width - edge_x or min(ys) < edge_y or max(ys) > height - edge_y
        if near_edge and (span_y >= _FRAME_MIN_FRACTION * height or span_x >= _FRAME_MIN_FRACTION * width):
            dropped_frame += 1
            continue
        if len(anchors) and _stroke_length(stroke) < max_px:
            points = np.array(stroke.points, dtype=np.float64)
            nearest = np.sqrt(((points[:, None, :] - anchors[None, :, :]) ** 2).sum(axis=2)).min()
            if nearest > far_px:
                dropped_far += 1
                continue
        kept.append(stroke)
    logger.info("Detalle: %d restos quitados (%d del marco de la hoja, %d sueltos lejos del plano).", dropped_frame + dropped_far, dropped_frame, dropped_far)
    return kept


_FIXTURE_REACH = 1.7  # los trazos dentro de la elipse de un sanitario (agrandada) son su contorno, ya dibujado limpio


def drop_inside_fixtures(strokes: list[Stroke], fixtures: list) -> list[Stroke]:
    """Quita los trazos que quedan dentro de la elipse de un sanitario detectado (su contorno dentado del escaneo).

    Cada sanitario se dibuja como una elipse limpia en su capa; el contorno que el esqueleto sacó del escaneo sobraría.
    Un trazo sale solo si TODOS sus puntos caen dentro (agrandada), para no tocar un muro que pasa al lado.
    """
    if not fixtures:
        return strokes
    kept: list[Stroke] = []
    dropped = 0
    for stroke in strokes:
        inside = False
        for f in fixtures:
            theta = math.radians(f.angle_deg)
            cos_t, sin_t = math.cos(theta), math.sin(theta)
            a, b = _FIXTURE_REACH * f.major / 2, _FIXTURE_REACH * f.minor / 2
            if all(
                (((x - f.cx) * cos_t + (y - f.cy) * sin_t) / a) ** 2 + ((-(x - f.cx) * sin_t + (y - f.cy) * cos_t) / b) ** 2 <= 1.0
                for x, y in stroke.points
            ):
                inside = True
                break
        if inside:
            dropped += 1
        else:
            kept.append(stroke)
    if dropped:
        logger.info("Detalle: %d trazos dentro de sanitarios quitados (ya van como elipse).", dropped)
    return kept
