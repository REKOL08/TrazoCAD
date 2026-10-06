"""Adelgazado de tinta a su línea central y trazado de caminos.

Una línea de plano escaneada tiene 3-6 px de grosor. Aquí se reduce cada
trazo a 1 px (esqueleto de Zhang-Suen, vectorizado con numpy para no
depender de scikit-image) y se recorre el esqueleto como un grafo para
obtener cadenas de puntos: una sola línea por trazo, no un contorno doble.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

Point = tuple[float, float]


@dataclass
class Stroke:
    """Un trazo calcado: polilínea abierta o cerrada, en píxeles (x, y)."""

    points: list[Point]
    closed: bool = False
    dashed: bool = False  # una línea discontinua entera (varias rayas alineadas), no una raya suelta


def skeletonize(ink: np.ndarray) -> np.ndarray:
    """Adelgaza una máscara 0/255 (255 = tinta) a esqueleto de 1 px (bool)."""
    ys, xs = np.nonzero(ink)
    if len(ys) == 0:
        return np.zeros(ink.shape, dtype=bool)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    padded = np.pad((ink[y0:y1, x0:x1] > 0).astype(np.uint8), 1)

    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p = padded
            p2, p3, p4 = p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:]
            p5, p6, p7 = p[2:, 2:], p[2:, 1:-1], p[2:, :-2]
            p8, p9, centre = p[1:-1, :-2], p[:-2, :-2], p[1:-1, 1:-1]

            neighbours = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            ring = (p2, p3, p4, p5, p6, p7, p8, p9, p2)
            transitions = sum(
                ((ring[i] == 0) & (ring[i + 1] == 1)).astype(np.uint8) for i in range(8)
            )
            remove = (centre == 1) & (neighbours >= 2) & (neighbours <= 6) & (transitions == 1)
            if step == 0:
                remove &= (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                remove &= (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)

            if remove.any():
                centre[remove] = 0
                changed = True

    result = np.zeros(ink.shape, dtype=bool)
    result[y0:y1, x0:x1] = padded[1:-1, 1:-1] > 0
    return result


_NEIGHBOUR_OFFSETS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


@dataclass
class _Chain:
    pts: list[Point]
    a: int | None  # nodo al inicio (None = extremo libre)
    b: int | None  # nodo al final


def _walk_components(edge_pixels: set[tuple[int, int]]) -> list[tuple[list[tuple[int, int]], bool]]:
    """Ordena los píxeles de cada camino simple. Devuelve (píxeles, cerrado)."""

    def neighbours(pixel: tuple[int, int]) -> list[tuple[int, int]]:
        y, x = pixel
        return [(y + dy, x + dx) for dy, dx in _NEIGHBOUR_OFFSETS if (y + dy, x + dx) in edge_pixels]

    visited: set[tuple[int, int]] = set()
    paths: list[tuple[list[tuple[int, int]], bool]] = []

    def walk(start: tuple[int, int]) -> tuple[list[tuple[int, int]], bool]:
        path = [start]
        visited.add(start)
        current = start
        while True:
            options = [q for q in neighbours(current) if q not in visited]
            if not options:
                break
            # prefiere vecinos en cruz (4-conectados) para no cortar esquinas
            options.sort(key=lambda q: abs(q[0] - current[0]) + abs(q[1] - current[1]))
            current = options[0]
            visited.add(current)
            path.append(current)
        closed = len(path) > 2 and current in neighbours(start)
        return path, closed

    ordered = sorted(edge_pixels, key=lambda q: len(neighbours(q)))
    for pixel in ordered:
        if pixel not in visited and len(neighbours(pixel)) <= 1:
            paths.append(walk(pixel))
    for pixel in ordered:
        if pixel not in visited:
            paths.append(walk(pixel))
    return paths


def trace_skeleton(skeleton: np.ndarray, spur_px: float, min_length_px: float) -> list[Stroke]:
    """Convierte un esqueleto de 1 px en trazos (cadenas de puntos).

    Los cruces se resuelven como nodos: los nodos por los que pasan solo dos
    caminos se fusionan en una sola cadena (así un muro no queda partido en
    cada escalón del esqueleto), y se podan las "espinas" cortas que el
    adelgazado deja en los extremos de las líneas gruesas.
    """
    if not skeleton.any():
        return []

    sk = skeleton.astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    kernel[1, 1] = 0
    neighbour_count = cv2.filter2D(sk, -1, kernel, borderType=cv2.BORDER_CONSTANT)
    junction = ((sk == 1) & (neighbour_count >= 3)).astype(np.uint8)

    node_count, node_labels, _stats, centroids = cv2.connectedComponentsWithStats(
        junction, connectivity=8
    )
    node_centres: dict[int, Point] = {
        label: (float(centroids[label][0]), float(centroids[label][1]))
        for label in range(1, node_count)
    }

    edge_mask = (sk == 1) & (junction == 0)
    edge_pixels = {(int(y), int(x)) for y, x in np.argwhere(edge_mask)}
    height, width = sk.shape

    def node_at(pixel: tuple[int, int]) -> int | None:
        y, x = pixel
        for dy, dx in _NEIGHBOUR_OFFSETS:
            ny, nx = y + dy, x + dx
            if 0 <= ny < height and 0 <= nx < width and node_labels[ny, nx] > 0:
                return int(node_labels[ny, nx])
        return None

    chains: dict[int, _Chain] = {}
    closed_strokes: list[Stroke] = []
    next_id = 0
    for pixels, closed in _walk_components(edge_pixels):
        points = [(float(x), float(y)) for y, x in pixels]
        if closed:
            closed_strokes.append(Stroke(points=points, closed=True))
            continue
        chains[next_id] = _Chain(points, node_at(pixels[0]), node_at(pixels[-1]))
        next_id += 1

    def length(points: list[Point]) -> float:
        return float(sum(np.hypot(p[0] - q[0], p[1] - q[1]) for p, q in zip(points, points[1:])))

    for chain_id in list(chains):
        chain = chains[chain_id]
        size = length(chain.pts)
        free_ends = (chain.a is None) + (chain.b is None)
        if (free_ends == 2 and size < min_length_px) or (free_ends == 1 and size < spur_px):
            del chains[chain_id]

    node_chains: dict[int, list[int]] = {}
    for chain_id, chain in chains.items():
        for node in (chain.a, chain.b):
            if node is not None:
                node_chains.setdefault(node, []).append(chain_id)

    for node in list(node_chains):
        ids = node_chains.get(node, [])
        if len(ids) != 2:
            continue
        first_id, second_id = ids
        centre = node_centres[node]
        if first_id == second_id:
            chain = chains.pop(first_id)
            closed_strokes.append(Stroke(points=chain.pts + [centre], closed=True))
            del node_chains[node]
            continue
        first, second = chains[first_id], chains[second_id]
        if first.b != node:
            first.pts.reverse()
            first.a, first.b = first.b, first.a
        if second.a != node:
            second.pts.reverse()
            second.a, second.b = second.b, second.a
        merged = _Chain(first.pts + [centre] + second.pts, first.a, second.b)
        chains.pop(first_id)
        chains.pop(second_id)
        chains[next_id] = merged
        del node_chains[node]
        for far_node, old_id in ((merged.a, first_id), (merged.b, second_id)):
            if far_node is not None:
                node_chains[far_node] = [
                    next_id if cid == old_id else cid for cid in node_chains[far_node]
                ]
        next_id += 1

    strokes = list(closed_strokes)
    for chain in chains.values():
        points = list(chain.pts)
        if chain.a is not None:
            points.insert(0, node_centres[chain.a])
        if chain.b is not None:
            points.append(node_centres[chain.b])
        if len(points) >= 2:
            strokes.append(Stroke(points=points, closed=False))
    return strokes
