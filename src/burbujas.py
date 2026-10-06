"""Burbujas de los ejes: los círculos con la letra o el número de cada eje (A, B, C... y 1, 2, 3...).

Un eje de verdad termina en una burbuja. Encontrarlas sirve para descartar las líneas largas que no son ejes
(cotas, muros, líneas de corte) y para completar los ejes que el trazado no encontró.

El aro de la burbuja es una línea muy fina y clara que, al binarizar, se rompe en trozos; por eso se mide sobre el
gris. Y para no confundirlo con otros círculos del plano (inodoros, mesas, escaleras), solo se busca en lugares
donde una burbuja tiene sentido: al final de un eje y, desde ahí, a lo largo de su fila o columna.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import cv2
import numpy as np

from .line_detector import Segment

logger = logging.getLogger("planos2dwg")

_MM_PER_INCH = 25.4
_RADIUS_MM = (1.3, 2.4)  # radio de una burbuja sobre el papel (por debajo, el aro se confunde con la letra)
_RING_SAMPLES = 72
_RING_DARKER_BY = 28  # cuánto más oscuro que el fondo es un punto del aro (niveles de gris)
_RING_MIN_COVERAGE = 0.66
_FILL_MIN_COVERAGE = 0.40  # ya se sabe que ahí va una burbuja: se acepta un aro más tenue
_INSIDE_INK = (0.04, 0.55)  # la letra o el número ocupan una parte del interior
_OUTSIDE_MAX_DARK = 0.30  # fuera del aro hay papel en blanco (salvo donde entra la línea del eje)
_MARGIN_MM = 5.0  # el extremo de un eje con burbuja queda fuera del contenido del plano al menos esto
_SEED_REACH_RADII = 4.5  # hasta dónde, más allá del extremo del eje, se busca su burbuja (en radios)
_SEED_STEP_PX = 3
_LATERAL_PX = 6  # cuánto puede desviarse el centro de la burbuja de la línea del eje
_FILL_LATERAL_PX = 16  # las burbujas de una fila o columna no quedan en una recta perfecta
_FILL_STEP_PX = 3
_FILL_RADIUS_TOLERANCE = 2
_MIN_AXIS_MM = 25.0  # un eje más corto no es un eje de la cuadrícula
_LINE_GROUP_PX = 8  # semillas a esta distancia en x (o y) están en la misma columna (o fila)


@dataclass(frozen=True)
class Bubble:
    x: float
    y: float
    r: float
    direction: str  # hacia dónde sale su eje: "horizontal" o "vertical"
    ring: float = 0.0  # qué tan completo está el aro (0 a 1)


class _Ring:
    def __init__(self, gray: np.ndarray, ink: np.ndarray) -> None:
        self.gray = gray
        self.darkest = cv2.erode(gray, np.ones((3, 3), np.uint8))
        self.ink = ink > 0
        angles = np.linspace(0, 2 * math.pi, _RING_SAMPLES, endpoint=False)
        self.cos, self.sin = np.cos(angles), np.sin(angles)
        self.h, self.w = gray.shape

    def _gather(self, source: np.ndarray, cx: np.ndarray, cy: np.ndarray, r: float) -> np.ndarray:
        xs = np.clip(np.round(cx[:, None] + r * self.cos[None, :]).astype(np.intp), 0, self.w - 1)
        ys = np.clip(np.round(cy[:, None] + r * self.sin[None, :]).astype(np.intp), 0, self.h - 1)
        return source[ys, xs]

    def coverage_many(self, cx: np.ndarray, cy: np.ndarray, r: float, factor: float = 1.0) -> np.ndarray:
        """Parte del aro (de radio r*factor) más oscura que el papel de al lado, para muchos centros a la vez."""
        background = np.median(self._gather(self.gray, cx, cy, 1.5 * r), axis=1)
        ring = self._gather(self.darkest, cx, cy, factor * r).astype(np.int32)
        return ((background[:, None] - ring) > _RING_DARKER_BY).mean(axis=1)

    def scores(self, cx: np.ndarray, cy: np.ndarray, r: float, relaxed: bool) -> np.ndarray:
        """Para cada centro: el aro (0..1) si ahí hay una burbuja, o 0. `relaxed`: basta un aro tenue con letra."""
        inside = (cx > r) & (cx < self.w - r) & (cy > r) & (cy < self.h - r)
        result = np.zeros(len(cx))
        if not inside.any():
            return result
        needed = _FILL_MIN_COVERAGE if relaxed else _RING_MIN_COVERAGE
        idx = np.nonzero(inside)[0]
        ring = self.coverage_many(cx[idx], cy[idx], r)
        for k in idx[ring >= needed]:
            x, y = float(cx[k]), float(cy[k])
            patch = self.ink[int(y - 0.65 * r) : int(y + 0.65 * r), int(x - 0.65 * r) : int(x + 0.65 * r)]
            if patch.size == 0 or not (_INSIDE_INK[0] <= float(patch.mean()) <= _INSIDE_INK[1]):
                continue
            if not relaxed and self.coverage_many(cx[k : k + 1], cy[k : k + 1], r, 1.28)[0] > _OUTSIDE_MAX_DARK:
                continue
            result[k] = ring[list(idx).index(k)]
        return result


def _radii(dpi: int) -> list[float]:
    low, high = (v * dpi / _MM_PER_INCH for v in _RADIUS_MM)
    return [float(r) for r in np.arange(round(low), round(high) + 1, 1.0)]


def _seed_for_end(ring: _Ring, end: tuple[float, float], other: tuple[float, float], radii: list[float]) -> Bubble | None:
    """Busca una burbuja pegada al extremo `end` del eje, en la prolongación de la línea."""
    dx, dy = end[0] - other[0], end[1] - other[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return None
    ux, uy = dx / length, dy / length
    direction = "horizontal" if abs(ux) > abs(uy) else "vertical"
    best: tuple[float, float, Bubble] | None = None  # (radio, aro, burbuja): gana el radio mayor que pasa
    laterals = np.arange(-_LATERAL_PX, _LATERAL_PX + 1, 3.0)
    for r in radii:
        t = np.arange(-1.6 * r, _SEED_REACH_RADII * r * 2, _SEED_STEP_PX)
        tt, ll = np.meshgrid(t, laterals)
        cx = end[0] + ux * (tt + r) - uy * ll
        cy = end[1] + uy * (tt + r) + ux * ll
        score = ring.scores(cx.ravel(), cy.ravel(), r, relaxed=True)
        k = int(np.argmax(score))
        if score[k] > 0 and (best is None or (r, float(score[k])) > (best[0], best[1])):
            best = (r, float(score[k]), Bubble(float(cx.ravel()[k]), float(cy.ravel()[k]), r, direction, float(score[k])))
    return best[2] if best else None


def _fill_line(ring: _Ring, seeds: list[Bubble]) -> list[Bubble]:
    """Busca las demás burbujas de la misma columna o fila que las semillas."""
    direction = seeds[0].direction
    horizontal = direction == "horizontal"  # eje horizontal => la burbuja está en una columna (x casi fijo)
    fixed = float(np.mean([s.x if horizontal else s.y for s in seeds]))
    radius = float(np.median([s.r for s in seeds]))
    length = ring.h if horizontal else ring.w
    positions = np.arange(0, length, _FILL_STEP_PX, dtype=np.float64)
    laterals = np.arange(-_FILL_LATERAL_PX, _FILL_LATERAL_PX + 1, 4.0)
    pp, ll = np.meshgrid(positions, laterals)
    cx = (fixed + ll if horizontal else pp).ravel()
    cy = (pp if horizontal else fixed + ll).ravel()
    found: list[Bubble] = []
    for r in np.arange(radius - _FILL_RADIUS_TOLERANCE, radius + _FILL_RADIUS_TOLERANCE + 1, 1.0):
        score = ring.scores(cx, cy, float(r), relaxed=True)
        for k in np.nonzero(score)[0]:
            found.append(Bubble(float(cx[k]), float(cy[k]), float(r), direction, float(score[k])))
    return found


def _one_per_circle(bubbles: list[Bubble]) -> list[Bubble]:
    """El mismo círculo sale en varias posiciones vecinas: se queda la de mejor aro."""
    kept: list[Bubble] = []
    for b in sorted(bubbles, key=lambda b: -b.ring):
        if all(math.hypot(b.x - k.x, b.y - k.y) > 1.8 * max(b.r, k.r) for k in kept):
            kept.append(b)
    return kept


def _outside(end: tuple[float, float], other: tuple[float, float], box: tuple[float, float, float, float], margin: float) -> bool:
    """True si `end` queda fuera del contenido del plano, más allá de su borde, en la dirección del eje."""
    x0, y0, x1, y1 = box
    if abs(end[0] - other[0]) >= abs(end[1] - other[1]):  # eje horizontal
        return end[0] < x0 - margin or end[0] > x1 + margin
    return end[1] < y0 - margin or end[1] > y1 + margin


def find_axis_bubbles(
    gray: np.ndarray,
    ink: np.ndarray,
    axes: list[Segment],
    dpi: int,
    content_box: tuple[float, float, float, float],
    max_y: float | None = None,
) -> list[Bubble]:
    """Burbujas de la cuadrícula de ejes: las de los extremos de los ejes y las demás de su fila o columna.

    `content_box` es el rectángulo (x0, y0, x1, y1) que ocupan los muros: la burbuja de un eje cae fuera de él.
    `max_y` deja fuera todo lo que está más abajo (el cajetín).
    """
    ring = _Ring(gray, ink)
    radii = _radii(dpi)
    min_len = _MIN_AXIS_MM * dpi / _MM_PER_INCH
    margin = _MARGIN_MM * dpi / _MM_PER_INCH
    ends = [
        (end, other)
        for a, b in axes
        if math.dist(a, b) >= min_len
        for end, other in ((a, b), (b, a))
        if _outside(end, other, content_box, margin)
    ]

    def seeds_with(candidate_radii: list[float]) -> list[Bubble]:
        found = (_seed_for_end(ring, end, other, candidate_radii) for end, other in ends)
        return [s for s in found if s]

    # primera pasada con radios espaciados: en un plano todas las burbujas miden casi lo mismo (letras y números)
    coarse = seeds_with(radii[::3] or radii)
    if not coarse:
        logger.info("Burbujas de eje: ninguna.")
        return []
    strong = [s for s in coarse if s.ring >= _RING_MIN_COVERAGE] or coarse
    typical = float(np.median([s.r for s in strong]))
    # segunda pasada: solo radios cerca del típico, que no se confunden con las letras ni con otros círculos
    seeds = seeds_with([r for r in radii if abs(r - typical) <= _FILL_RADIUS_TOLERANCE])

    bubbles: list[Bubble] = []
    for horizontal in (True, False):
        mine = sorted((s for s in seeds if (s.direction == "horizontal") == horizontal), key=lambda s: s.x if horizontal else s.y)
        group: list[Bubble] = []
        for s in mine + [None]:  # type: ignore[list-item]
            coordinate = (lambda b: b.x) if horizontal else (lambda b: b.y)
            if group and (s is None or coordinate(s) - coordinate(group[0]) > _LINE_GROUP_PX):
                if len(group) >= 2:  # una línea de burbujas alineadas: se busca el resto de su fila o columna
                    bubbles.extend(_fill_line(ring, group))
                group = []
            if s is not None:
                group.append(s)

    result = [b for b in _one_per_circle(bubbles) if max_y is None or b.y < max_y]
    logger.info("Burbujas de eje: %d semillas, %d burbujas en la cuadrícula.", len(seeds), len(result))
    return result


_GLYPH_SIZE = 32
_FONT_CANDIDATES = ("arial.ttf", "segoeui.ttf", "calibri.ttf", "DejaVuSans.ttf")
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_MIN_GLYPH_MATCH = 0.60
_SEQUENCE_MIN_SHARE = 0.6  # parte de las letras que debe coincidir con la secuencia A, B, C... para aceptarla


def _normalised_glyph(binary: np.ndarray) -> np.ndarray | None:
    """Recorta la letra, la lleva a un cuadrado de 32 px y la difumina un poco, para compararla con plantillas."""
    ys, xs = np.nonzero(binary)
    if len(xs) < 8:
        return None
    glyph = binary[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1].astype(np.uint8) * 255
    h, w = glyph.shape
    scale = (_GLYPH_SIZE - 4) / max(h, w)
    glyph = cv2.resize(glyph, (max(int(w * scale), 1), max(int(h * scale), 1)), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((_GLYPH_SIZE, _GLYPH_SIZE), np.uint8)
    oy, ox = (_GLYPH_SIZE - glyph.shape[0]) // 2, (_GLYPH_SIZE - glyph.shape[1]) // 2
    canvas[oy : oy + glyph.shape[0], ox : ox + glyph.shape[1]] = glyph
    return cv2.GaussianBlur(canvas, (3, 3), 0).astype(np.float32)


def _letter_templates() -> dict[str, list[np.ndarray]] | None:
    """Plantillas de A..Z con la fuente del sistema, en tres grosores (el rótulo de CAD es delgado)."""
    from PIL import Image, ImageDraw, ImageFont

    font = None
    for name in _FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(name, 80)
            break
        except OSError:
            continue
    if font is None:
        return None
    bank: dict[str, list[np.ndarray]] = {}
    for letter in _LETTERS:
        for thickness in (0, 1, 2):
            image = Image.new("L", (120, 120), 0)
            ImageDraw.Draw(image).text((20, 10), letter, font=font, fill=255, stroke_width=thickness, stroke_fill=255)
            glyph = _normalised_glyph(np.array(image) > 128)
            if glyph is not None:
                bank.setdefault(letter, []).append(glyph)
    return bank


def _glyph_inside(gray: np.ndarray, bubble: Bubble) -> np.ndarray | None:
    r = int(bubble.r * 0.62)
    cx, cy = int(bubble.x), int(bubble.y)
    crop = gray[cy - r : cy + r, cx - r : cx + r]
    if crop.size == 0:
        return None
    yy, xx = np.mgrid[-r:r, -r:r]
    ink = (crop < np.percentile(crop, 12) + 55) & ((yy**2 + xx**2) < (0.88 * r) ** 2)  # sin el aro
    return _normalised_glyph(ink)


def read_labels(gray: np.ndarray, bubbles: list[Bubble]) -> list[str]:
    """Letra de cada burbuja de una columna de ejes (A, B, C...); '' para las que no se pueden leer con seguridad.

    El OCR no lee letras sueltas dentro de un círculo, así que cada letra se compara con plantillas. Un acierto aislado
    no basta: las letras de una columna van en orden, y solo se aceptan si la mayoría encaja con la secuencia A, B, C...
    (así una G leída como C no estropea nada). Los números de las filas no se leen: se dibujan sin texto.
    """
    labels = [""] * len(bubbles)
    letters = sorted((i for i, b in enumerate(bubbles) if b.direction == "horizontal"), key=lambda i: bubbles[i].y)
    if len(letters) < 3:
        return labels
    bank = _letter_templates()
    if bank is None:
        return labels
    guesses: list[str | None] = []
    for i in letters:
        glyph = _glyph_inside(gray, bubbles[i])
        if glyph is None:
            guesses.append(None)
            continue
        scores = {ch: max(float(np.corrcoef(glyph.ravel(), t.ravel())[0, 1]) for t in ts) for ch, ts in bank.items()}
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        guesses.append(best if scores[best] >= _MIN_GLYPH_MATCH else None)
    starts = [ord(ch) - k for k, ch in enumerate(guesses) if ch]
    if not starts:
        return labels
    start = max(set(starts), key=starts.count)
    if starts.count(start) < _SEQUENCE_MIN_SHARE * len(letters) or not (ord("A") <= start and start + len(letters) - 1 <= ord("Z")):
        return labels
    for k, i in enumerate(letters):
        labels[i] = chr(start + k)
    return labels


_LOOSE_MIN_RING = 0.66
_LOOSE_RADIUS_SPREAD = 3


def find_loose_bubbles(
    gray: np.ndarray,
    ink: np.ndarray,
    typical_radius: float,
    known: list[Bubble],
    max_y: float | None = None,
) -> list[Bubble]:
    """Burbujas fuera de la cuadrícula (las de los ejes radiales de una parte circular, las de abajo...).

    Todas las burbujas de un plano miden casi lo mismo, así que se busca solo ese radio: círculos con aro completo,
    letra o número dentro y papel en blanco alrededor. No son burbujas de verdad hasta que sale de ellas la línea de un
    eje (eso lo comprueba `ejes.radial_axes`): un inodoro o una mesa también cumplen lo anterior.
    """
    ring = _Ring(gray, ink)
    low, high = typical_radius - _LOOSE_RADIUS_SPREAD, typical_radius + _LOOSE_RADIUS_SPREAD
    blur = cv2.GaussianBlur(gray, (5, 5), 1.2)
    found = cv2.HoughCircles(
        blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=typical_radius, param1=110, param2=20, minRadius=int(low), maxRadius=int(high)
    )
    if found is None:
        return []
    kept: list[Bubble] = []
    for x, y, _ in found[0]:
        for r in np.arange(typical_radius - 2, typical_radius + 2.5, 1.0):
            score = float(ring.scores(np.array([x]), np.array([y]), float(r), relaxed=False)[0])
            if score >= _LOOSE_MIN_RING:
                kept.append(Bubble(float(x), float(y), float(r), "radial", score))
                break
    result: list[Bubble] = []
    for b in sorted(kept, key=lambda b: -b.ring):
        if (max_y is None or b.y < max_y) and all(math.hypot(b.x - o.x, b.y - o.y) > 1.8 * typical_radius for o in known + result):
            result.append(b)
    return result
