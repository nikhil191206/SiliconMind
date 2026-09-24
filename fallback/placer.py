"""FALLBACK ONLY: classical, CPU-only placer standing in for Person B's
flow-matching generator while it is untrained.

This is deliberately a textbook algorithm, not a learned model, and every
placement it emits says so in generation_metadata.model_variant. Three stages:

  1. Macros: greedy floorplan over a candidate grid. Cost = distance to the
     die edge (macros at the periphery, cells in the middle) + wirelength to
     already-placed connected macros + optional edit directive + seeded
     jitter. Candidates overlapping an already-placed macro are rejected.
  2. Standard cells: quadratic-style wirelength pull (Jacobi averaging of net
     centroids, macros and fixed nodes act as anchors) alternated with
     capacity-aware recursive-bisection spreading around macro blockages.
  3. Legalization: Tetris-style row legalization into free row segments
     (rows minus macros minus fixed cells). No two std cells overlap and no
     std cell overlaps a macro, by construction.

Scoring is NOT done here: server.py scores every result with Person C's real
shared/metrics code, the same functions the real pipeline will use.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
from scipy import sparse

from shared.metrics.geometry import effective_dims
from shared.schemas.circuit_graph import CircuitGraph, NodeType
from shared.schemas.placement import GenerationMetadata, Orientation, PlacementEntry, PlacementJSON

MODEL_VARIANT = "FALLBACK classical placer (not the trained flow-matching model)"

# (candidate_centers_x, candidate_centers_y, w, h) -> extra cost per candidate
MacroHint = Callable[[np.ndarray, np.ndarray, float, float], np.ndarray]


class PlacementError(Exception):
    """Raised when the design cannot be placed (e.g. it does not fit the die)."""


@dataclass
class PlaceResult:
    placement: PlacementJSON
    stage_seconds: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# helpers


def _dims(graph: CircuitGraph, orient: list[Orientation]) -> tuple[np.ndarray, np.ndarray]:
    w = np.empty(len(graph.nodes))
    h = np.empty(len(graph.nodes))
    for n in graph.nodes:
        w[n.node_id], h[n.node_id] = effective_dims(n.width, n.height, orient[n.node_id])
    return w, h


def _incidence(graph: CircuitGraph) -> tuple[sparse.csr_matrix, np.ndarray]:
    """Net x node incidence matrix and a per-net weight (1/(k-1), big nets damped)."""
    rows, cols, weights = [], [], []
    r = 0
    for he in graph.hyperedges:
        pins = set(he.sink_nodes)
        if he.driver_node is not None:
            pins.add(he.driver_node)
        k = len(pins)
        if k < 2:
            continue
        for p in pins:
            rows.append(r)
            cols.append(p)
        weights.append(1.0 / (k - 1) if k <= 64 else 0.2 / (k - 1))
        r += 1
    mat = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(r, len(graph.nodes)))
    return mat, np.asarray(weights, dtype=float)


def _overlap_area(ax0, ay0, ax1, ay1, bx0, by0, bx1, by1):
    return np.clip(np.minimum(ax1, bx1) - np.maximum(ax0, bx0), 0, None) * np.clip(
        np.minimum(ay1, by1) - np.maximum(ay0, by0), 0, None
    )


# ---------------------------------------------------------------------------
# stage 1: macros


def _place_macros(
    graph: CircuitGraph,
    w: np.ndarray,
    h: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    movable: list[int],
    placed: list[int],
    inc: sparse.csr_matrix,
    net_w: np.ndarray,
    rng: np.random.Generator,
    hints: dict[int, MacroHint],
) -> None:
    W, H = graph.die.width, graph.die.height
    diag = math.hypot(W, H)
    halo = max(0.5, min(W, H) * 0.006)
    macro_ids = [n.node_id for n in graph.nodes if n.type == NodeType.MACRO]
    # macro-macro connectivity (weighted clique over shared nets)
    sub = inc[:, macro_ids]
    conn = (sub.T @ sparse.diags(net_w) @ sub).toarray()
    np.fill_diagonal(conn, 0.0)
    col_of = {m: i for i, m in enumerate(macro_ids)}

    order = sorted(movable, key=lambda m: (-(w[m] * h[m]), rng.random()))
    placed = list(placed)
    for m in order:
        for grid in (48, 96):
            xs = np.linspace(0.0, max(0.0, W - w[m]), grid)
            ys = np.linspace(0.0, max(0.0, H - h[m]), grid)
            gx, gy = np.meshgrid(xs, ys)
            gx, gy = gx.ravel(), gy.ravel()
            ok = np.ones(gx.shape, dtype=bool)
            for p in placed:
                ok &= ~(
                    (gx < x[p] + w[p] + halo)
                    & (x[p] < gx + w[m] + halo)
                    & (gy < y[p] + h[p] + halo)
                    & (y[p] < gy + h[m] + halo)
                )
            if ok.any():
                break
        cx, cy = gx + w[m] / 2, gy + h[m] / 2
        edge = np.minimum.reduce([gx, W - (gx + w[m]), gy, H - (gy + h[m])]) / (min(W, H) / 2)
        cost = 1.0 * edge
        wl = np.zeros_like(cost)
        for p in placed:
            if p in col_of and conn[col_of[m], col_of[p]] > 0:
                wl += conn[col_of[m], col_of[p]] * (
                    np.abs(cx - (x[p] + w[p] / 2)) + np.abs(cy - (y[p] + h[p] / 2))
                ) / diag
        cost += 0.6 * wl
        if m in hints:
            cost += 6.0 * hints[m](cx, cy, float(w[m]), float(h[m]))
        cost += 0.04 * rng.random(cost.shape)
        if not ok.any():
            # Nothing fits without overlap. Keep going (cheapest spot) and let
            # shared/metrics' legality check report the violation honestly.
            ok[:] = True
        cost[~ok] = np.inf
        best = int(np.argmin(cost))
        x[m], y[m] = gx[best], gy[best]
        placed.append(m)


# ---------------------------------------------------------------------------
# stage 2: std-cell global placement


def _free_area(rect: tuple[float, float, float, float], blocks: np.ndarray) -> float:
    x0, y0, x1, y1 = rect
    area = (x1 - x0) * (y1 - y0)
    if len(blocks):
        area -= float(_overlap_area(x0, y0, x1, y1, blocks[:, 0], blocks[:, 1], blocks[:, 2], blocks[:, 3]).sum())
    return max(area, 1e-9)


def _bisect_spread(
    cx: np.ndarray, cy: np.ndarray, idx: np.ndarray, rect, blocks: np.ndarray, out_x: np.ndarray, out_y: np.ndarray
) -> None:
    """Recursive bisection: split cells (by current order) in proportion to
    the free (non-macro) capacity of each half of the region."""
    x0, y0, x1, y1 = rect
    n = len(idx)
    if n == 0:
        return
    if n <= 6 or (x1 - x0) < 2 or (y1 - y0) < 2:
        # leaf: spread evenly inside the rect, preserving relative order
        k = math.ceil(math.sqrt(n))
        n_rows = math.ceil(n / k)
        by_y = idx[np.argsort(cy[idx], kind="stable")]
        for r in range(n_rows):
            chunk = by_y[r * k : (r + 1) * k]
            chunk = chunk[np.argsort(cx[chunk], kind="stable")]
            m = len(chunk)
            out_x[chunk] = x0 + (x1 - x0) * (np.arange(m) + 0.5) / m
            out_y[chunk] = y0 + (y1 - y0) * (r + 0.5) / n_rows
        return
    vertical = (x1 - x0) >= (y1 - y0)
    if vertical:
        mid = (x0 + x1) / 2
        ra, rb = (x0, y0, mid, y1), (mid, y0, x1, y1)
        order = idx[np.argsort(cx[idx], kind="stable")]
    else:
        mid = (y0 + y1) / 2
        ra, rb = (x0, y0, x1, mid), (x0, mid, x1, y1)
        order = idx[np.argsort(cy[idx], kind="stable")]
    ca, cb = _free_area(ra, blocks), _free_area(rb, blocks)
    na = int(round(n * ca / (ca + cb)))
    _bisect_spread(cx, cy, order[:na], ra, blocks, out_x, out_y)
    _bisect_spread(cx, cy, order[na:], rb, blocks, out_x, out_y)


def _global_place_cells(
    graph: CircuitGraph,
    w: np.ndarray,
    h: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    movable: np.ndarray,
    inc: sparse.csr_matrix,
    net_w: np.ndarray,
    rng: np.random.Generator,
    blocks: np.ndarray,
    init_from_current: bool,
) -> None:
    if len(movable) == 0:
        return
    W, H = graph.die.width, graph.die.height
    cx = x + w / 2
    cy = y + h / 2
    if not init_from_current:
        cx[movable] = W / 2 + rng.normal(0, W * 0.05, len(movable))
        cy[movable] = H / 2 + rng.normal(0, H * 0.05, len(movable))

    wn = sparse.diags(net_w)
    deg = np.asarray(inc.sum(axis=1)).ravel()
    deg[deg == 0] = 1
    node_w = np.asarray((inc.T @ net_w)).ravel()
    has_nets = node_w[movable] > 0
    mv = movable[has_nets]

    tx = np.empty_like(cx)
    ty = np.empty_like(cy)
    iters = 14
    for it in range(iters):
        for _ in range(4):
            gx = inc @ cx / deg
            gy = inc @ cy / deg
            px = (inc.T @ (wn @ gx)) / np.maximum(node_w, 1e-12)
            py = (inc.T @ (wn @ gy)) / np.maximum(node_w, 1e-12)
            cx[mv] = 0.4 * cx[mv] + 0.6 * px[mv]
            cy[mv] = 0.4 * cy[mv] + 0.6 * py[mv]
        _bisect_spread(cx, cy, movable, (0.0, 0.0, W, H), blocks, tx, ty)
        a = min(0.9, 0.35 + it * 0.05)
        cx[movable] = (1 - a) * cx[movable] + a * tx[movable]
        cy[movable] = (1 - a) * cy[movable] + a * ty[movable]
    _bisect_spread(cx, cy, movable, (0.0, 0.0, W, H), blocks, tx, ty)
    x[movable] = tx[movable] - w[movable] / 2
    y[movable] = ty[movable] - h[movable] / 2


# ---------------------------------------------------------------------------
# stage 3: row legalization


def _legalize_cells(
    graph: CircuitGraph,
    w: np.ndarray,
    h: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    movable: np.ndarray,
    obstacles: list[tuple[float, float, float, float]],
) -> None:
    if len(movable) == 0:
        return
    W, H = graph.die.width, graph.die.height
    row_h = float(h[movable].max())
    n_rows = int(H // row_h)
    if n_rows < 1:
        raise PlacementError(f"Die height {H} is smaller than the standard-cell row height {row_h}.")

    # free segments per row: [start, end, cursor]
    rows: list[list[list[float]]] = []
    obs = np.asarray(obstacles, dtype=float).reshape(-1, 4)
    for r in range(n_rows):
        ry0, ry1 = r * row_h, (r + 1) * row_h
        hit = obs[(obs[:, 1] < ry1 - 1e-9) & (obs[:, 3] > ry0 + 1e-9)] if len(obs) else obs
        ivs = sorted((float(a), float(c)) for a, _, c, _ in hit)
        segs, cur = [], 0.0
        for a, c in ivs:
            if a > cur + 1e-9:
                segs.append([cur, min(a, W), cur])
            cur = max(cur, c)
        if cur < W - 1e-9:
            segs.append([cur, W, cur])
        rows.append([s for s in segs if s[1] - s[0] > 1e-9])

    cap = sum(s[1] - s[0] for row in rows for s in row)
    need = float(w[movable].sum())
    if need > cap + 1e-6:
        raise PlacementError(
            f"Standard cells need {need:.0f} units of row length but only {cap:.0f} are free "
            f"(die {W:g} x {H:g}); the design does not fit this die."
        )

    for i in movable[np.argsort(x[movable], kind="stable")]:
        dx, dy, cw = float(x[i]), float(y[i]), float(w[i])
        r0 = min(n_rows - 1, max(0, int(round(dy / row_h))))
        best = None  # (cost, row, seg, xpos)
        for d in range(n_rows):
            if best is not None and d * row_h > best[0]:
                break
            for r in {r0 - d, r0 + d}:
                if r < 0 or r >= n_rows:
                    continue
                vcost = abs(r * row_h - dy)
                for seg in rows[r]:
                    xp = max(seg[2], min(dx, seg[1] - cw))
                    if xp + cw > seg[1] + 1e-9:
                        continue
                    cost = abs(xp - dx) + vcost
                    if best is None or cost < best[0]:
                        best = (cost, r, seg, xp)
        if best is None:
            raise PlacementError("Row legalization ran out of space; try a larger die.")
        _, r, seg, xp = best
        x[i], y[i] = xp, r * row_h
        seg[2] = xp + cw


# ---------------------------------------------------------------------------
# public entry point


def place(
    graph: CircuitGraph,
    seed: int = 0,
    fixed: Optional[dict[int, PlacementEntry]] = None,
    macro_hints: Optional[dict[int, MacroHint]] = None,
    cell_targets: Optional[dict[int, tuple[float, float]]] = None,
    start: Optional[PlacementJSON] = None,
) -> PlaceResult:
    """Place `graph`. Nodes in `fixed` keep their exact entry (bit-identical).

    `macro_hints` adds a cost term for specific movable macros (edits);
    `cell_targets` gives desired lower-left positions for movable std cells
    (edits: displaced cells want to stay where they were).
    """
    rng = np.random.default_rng(seed)
    fixed = fixed or {}
    macro_hints = macro_hints or {}
    t_all = time.perf_counter()
    stage: dict[str, float] = {}

    N = len(graph.nodes)
    orient = [fixed[i].orientation if i in fixed else Orientation.N for i in range(N)]
    w, h = _dims(graph, orient)
    x = np.zeros(N)
    y = np.zeros(N)
    if start is not None:
        for p in start.placements:
            x[p.node_id], y[p.node_id] = p.x, p.y
    for i, e in fixed.items():
        x[i], y[i] = e.x, e.y
    inc, net_w = _incidence(graph)

    is_macro = np.array([n.type == NodeType.MACRO for n in graph.nodes], dtype=bool)
    macros = [i for i in range(N) if is_macro[i]]
    mov_macros = [i for i in macros if i not in fixed]
    fixed_macros = [i for i in macros if i in fixed]

    t = time.perf_counter()
    _place_macros(graph, w, h, x, y, mov_macros, fixed_macros, inc, net_w, rng, macro_hints)
    stage["macros"] = time.perf_counter() - t

    macro_boxes = np.array([[x[m], y[m], x[m] + w[m], y[m] + h[m]] for m in macros]).reshape(-1, 4)
    cells_mov = np.array([i for i in range(N) if not is_macro[i] and i not in fixed], dtype=int)
    fixed_cells = [i for i in range(N) if not is_macro[i] and i in fixed]

    t = time.perf_counter()
    if cell_targets is not None:
        for i in cells_mov:
            x[i], y[i] = cell_targets.get(int(i), (x[i], y[i]))
    else:
        _global_place_cells(graph, w, h, x, y, cells_mov, inc, net_w, rng, macro_boxes, init_from_current=False)
    stage["global"] = time.perf_counter() - t

    t = time.perf_counter()
    obstacles = [tuple(b) for b in macro_boxes] + [(x[i], y[i], x[i] + w[i], y[i] + h[i]) for i in fixed_cells]
    _legalize_cells(graph, w, h, x, y, cells_mov, obstacles)
    stage["legalize"] = time.perf_counter() - t
    stage["total"] = time.perf_counter() - t_all

    entries = []
    for i in range(N):
        if i in fixed:
            entries.append(fixed[i])
        else:
            entries.append(PlacementEntry(node_id=i, x=round(float(x[i]), 4), y=round(float(y[i]), 4), orientation=orient[i]))
    pj = PlacementJSON(
        design_name=graph.design_name,
        placements=entries,
        generation_metadata=GenerationMetadata(model_variant=MODEL_VARIANT, seed=seed, is_legalized=False),
    )
    return PlaceResult(placement=pj, stage_seconds=stage)
