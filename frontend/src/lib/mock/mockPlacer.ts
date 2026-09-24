/**
 * DEMO MODE ONLY: a fast, deterministic, *legal-by-construction* placer that
 * stands in for encoder → flow-matching generator → legalizer while
 * backend/main.py doesn't exist. It is not the project's generator and makes
 * no claim to quality; it exists so every UI state can be exercised.
 *
 *   1. Macros: seeded rejection sampling with a halo, largest first.
 *   2. Std cells: each cell is attached to its nearest macro by net hops
 *      (multi-source BFS), gets a Gaussian target around that macro, and is
 *      then assigned to a free row site with a locality-preserving sweep -
 *      so cells never overlap each other or macros.
 */
import type { CircuitGraph, Orientation, PlacementEntry, PlacementJSON } from "../schemas";
import { effectiveDims } from "../geometry/geometry";
import { gaussian, hashString, mulberry32 } from "../random";

export const DEMO_MODEL_VARIANT = "flow_matching (demo mock, not the real generator)";

// ---- Site grid ----------------------------------------------------------

export interface SiteGrid {
  pitchX: number;
  pitchY: number;
  cols: number;
  rows: number;
  /** 1 = blocked by a macro. */
  blocked: Uint8Array;
}

export function buildSiteGrid(graph: CircuitGraph, macroBoxes: Array<[number, number, number, number]>): SiteGrid {
  let pitchX = 1;
  let pitchY = 1;
  for (const n of graph.nodes) {
    if (n.type !== "STD_CELL") continue;
    pitchX = Math.max(pitchX, n.width, n.height);
    pitchY = Math.max(pitchY, n.width, n.height);
  }
  pitchX = Math.ceil(pitchX);
  pitchY = Math.ceil(pitchY);
  const cols = Math.max(1, Math.floor(graph.die.width / pitchX));
  const rows = Math.max(1, Math.floor(graph.die.height / pitchY));
  const blocked = new Uint8Array(cols * rows);
  for (const [x0, y0, x1, y1] of macroBoxes) {
    const c0 = Math.max(0, Math.floor(x0 / pitchX));
    const c1 = Math.min(cols - 1, Math.ceil(x1 / pitchX) - 1);
    const r0 = Math.max(0, Math.floor(y0 / pitchY));
    const r1 = Math.min(rows - 1, Math.ceil(y1 / pitchY) - 1);
    for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) blocked[r * cols + c] = 1;
  }
  return { pitchX, pitchY, cols, rows, blocked };
}

// ---- Macros -------------------------------------------------------------

const ORIENT_0: Orientation[] = ["N", "S", "FN", "FS"];
const ORIENT_90: Orientation[] = ["E", "W", "FE", "FW"];

function overlapsAny(
  box: [number, number, number, number],
  others: Array<[number, number, number, number]>,
  halo: number,
): boolean {
  for (const o of others) {
    if (box[0] < o[2] + halo && o[0] < box[2] + halo && box[1] < o[3] + halo && o[1] < box[3] + halo) return true;
  }
  return false;
}

export function placeMacros(
  graph: CircuitGraph,
  rand: () => number,
): { entries: Map<number, PlacementEntry>; boxes: Array<[number, number, number, number]> } {
  const macros = graph.nodes.filter((n) => n.type === "MACRO").sort((a, b) => b.width * b.height - a.width * a.height);
  const entries = new Map<number, PlacementEntry>();
  const boxes: Array<[number, number, number, number]> = [];
  const { width: W, height: H } = graph.die;
  const halo = Math.max(1, Math.min(W, H) * 0.012);

  for (const m of macros) {
    let placed = false;
    for (let attempt = 0; attempt < 600 && !placed; attempt++) {
      const rotate = rand() < 0.2;
      const orientation = (rotate ? ORIENT_90 : ORIENT_0)[Math.floor(rand() * 4)];
      const [w, h] = effectiveDims(m.width, m.height, orientation);
      if (w > W || h > H) continue;
      // Bias toward the periphery: macros on real floorplans hug the edges.
      const edgeBias = rand() < 0.6;
      let x = rand() * (W - w);
      let y = rand() * (H - h);
      if (edgeBias) {
        const side = Math.floor(rand() * 4);
        if (side === 0) x = halo;
        else if (side === 1) x = W - w - halo;
        else if (side === 2) y = halo;
        else y = H - h - halo;
      }
      x = Math.round(Math.max(0, Math.min(W - w, x)));
      y = Math.round(Math.max(0, Math.min(H - h, y)));
      const box: [number, number, number, number] = [x, y, x + w, y + h];
      if (!overlapsAny(box, boxes, halo)) {
        boxes.push(box);
        entries.set(m.node_id, { node_id: m.node_id, x, y, orientation });
        placed = true;
      }
    }
    if (!placed) {
      // Honest fallback: place it anyway. The legality metric will count the
      // overlap and the mock will report the placement as unverifiable.
      const [w, h] = effectiveDims(m.width, m.height, "N");
      const x = Math.max(0, Math.round(rand() * Math.max(0, W - w)));
      const y = Math.max(0, Math.round(rand() * Math.max(0, H - h)));
      boxes.push([x, y, x + w, y + h]);
      entries.set(m.node_id, { node_id: m.node_id, x, y, orientation: "N" });
    }
  }
  return { entries, boxes };
}

// ---- Std cells ----------------------------------------------------------

/** For every node: index of the nearest macro by net hops, or -1. */
function nearestMacroByHops(graph: CircuitGraph): Int32Array {
  const n = graph.nodes.length;
  // Star adjacency per net (pins ↔ first pin) keeps E linear in pin count.
  const deg = new Int32Array(n);
  for (const net of graph.hyperedges) {
    const pins = net.driver_node === null ? net.sink_nodes : [net.driver_node, ...net.sink_nodes];
    for (let k = 1; k < pins.length; k++) {
      deg[pins[0]]++;
      deg[pins[k]]++;
    }
  }
  const start = new Int32Array(n + 1);
  for (let i = 0; i < n; i++) start[i + 1] = start[i] + deg[i];
  const adj = new Int32Array(start[n]);
  const fill = start.slice(0, n);
  for (const net of graph.hyperedges) {
    const pins = net.driver_node === null ? net.sink_nodes : [net.driver_node, ...net.sink_nodes];
    for (let k = 1; k < pins.length; k++) {
      adj[fill[pins[0]]++] = pins[k];
      adj[fill[pins[k]]++] = pins[0];
    }
  }
  const owner = new Int32Array(n).fill(-1);
  const queue = new Int32Array(n);
  let head = 0;
  let tail = 0;
  for (const node of graph.nodes) {
    if (node.type === "MACRO") {
      owner[node.node_id] = node.node_id;
      queue[tail++] = node.node_id;
    }
  }
  while (head < tail) {
    const u = queue[head++];
    for (let e = start[u]; e < start[u + 1]; e++) {
      const v = adj[e];
      if (owner[v] === -1) {
        owner[v] = owner[u];
        queue[tail++] = v;
      }
    }
  }
  return owner;
}

export function placeCells(
  graph: CircuitGraph,
  macroEntries: Map<number, PlacementEntry>,
  grid: SiteGrid,
  rand: () => number,
): Map<number, PlacementEntry> {
  const owner = nearestMacroByHops(graph);
  const cells = graph.nodes.filter((n) => n.type === "STD_CELL");
  const { width: W, height: H } = graph.die;

  const clusterSize = new Map<number, number>();
  for (const c of cells) clusterSize.set(owner[c.node_id], (clusterSize.get(owner[c.node_id]) ?? 0) + 1);

  const targets = cells.map((c) => {
    const o = owner[c.node_id];
    const m = o >= 0 ? macroEntries.get(o) : undefined;
    if (!m) return { id: c.node_id, tx: rand() * W, ty: rand() * H };
    const mn = graph.nodes[o];
    const [mw, mh] = effectiveDims(mn.width, mn.height, m.orientation);
    const spread = Math.sqrt(clusterSize.get(o) ?? 1) * 0.9 + Math.max(mw, mh) * 0.35;
    return {
      id: c.node_id,
      tx: Math.min(W, Math.max(0, m.x + mw / 2 + gaussian(rand) * spread)),
      ty: Math.min(H, Math.max(0, m.y + mh / 2 + gaussian(rand) * spread)),
    };
  });

  // Free sites per row.
  const rowFree: number[][] = [];
  let totalFree = 0;
  for (let r = 0; r < grid.rows; r++) {
    const free: number[] = [];
    for (let c = 0; c < grid.cols; c++) if (!grid.blocked[r * grid.cols + c]) free.push(c);
    rowFree.push(free);
    totalFree += free.length;
  }

  const out = new Map<number, PlacementEntry>();
  if (totalFree < targets.length) {
    // Doesn't fit: place at targets (overlapping). Legality will say so.
    for (const t of targets) out.set(t.id, { node_id: t.id, x: t.tx, y: t.ty, orientation: "N" });
    return out;
  }

  targets.sort((a, b) => a.ty - b.ty);
  let taken = 0;
  let cumFree = 0;
  for (let r = 0; r < grid.rows; r++) {
    const free = rowFree[r];
    cumFree += free.length;
    const quota = Math.round((cumFree / totalFree) * targets.length) - taken;
    if (quota <= 0 || free.length === 0) continue;
    const band = targets.slice(taken, taken + quota).sort((a, b) => a.tx - b.tx);
    taken += band.length;
    // Monotone nearest-site sweep: preserves x order, never runs out of sites.
    let s = -1;
    for (let k = 0; k < band.length; k++) {
      const wantCol = band[k].tx / grid.pitchX;
      let lo = s + 1;
      let hi = free.length - (band.length - k);
      // binary search nearest free column ≥ lo
      let a = lo;
      let b = hi;
      while (a < b) {
        const mid = (a + b) >> 1;
        if (free[mid] < wantCol) a = mid + 1;
        else b = mid;
      }
      s = Math.max(lo, Math.min(hi, a));
      out.set(band[k].id, {
        node_id: band[k].id,
        x: free[s] * grid.pitchX,
        y: r * grid.pitchY,
        orientation: rand() < 0.5 ? "N" : "FS",
      });
      lo = s + 1;
    }
  }
  return out;
}

export function generateDemoPlacement(graph: CircuitGraph, seed: number): PlacementJSON {
  const rand = mulberry32((seed * 2654435761) ^ hashString(graph.design_name));
  const { entries: macros, boxes } = placeMacros(graph, rand);
  const grid = buildSiteGrid(graph, boxes);
  const cells = placeCells(graph, macros, grid, rand);
  const placements: PlacementEntry[] = graph.nodes.map((n) => macros.get(n.node_id) ?? cells.get(n.node_id)!);
  return {
    design_name: graph.design_name,
    placements,
    generation_metadata: { model_variant: DEMO_MODEL_VARIANT, seed, is_legalized: false },
  };
}

/**
 * After macros move during an edit: any std cell now covered by a macro is
 * relocated to the nearest free site (ring search). Returns the ids moved.
 */
export function relocateCoveredCells(graph: CircuitGraph, placements: PlacementEntry[]): number[] {
  const macroBoxes: Array<[number, number, number, number]> = [];
  for (const p of placements) {
    const n = graph.nodes[p.node_id];
    if (n.type !== "MACRO") continue;
    const [w, h] = effectiveDims(n.width, n.height, p.orientation);
    macroBoxes.push([p.x, p.y, p.x + w, p.y + h]);
  }
  const grid = buildSiteGrid(graph, macroBoxes);
  const occupied = new Uint8Array(grid.cols * grid.rows);
  const toMove: PlacementEntry[] = [];
  for (const p of placements) {
    if (graph.nodes[p.node_id].type !== "STD_CELL") continue;
    const c = Math.round(p.x / grid.pitchX);
    const r = Math.round(p.y / grid.pitchY);
    const inGrid = c >= 0 && r >= 0 && c < grid.cols && r < grid.rows;
    const idx = r * grid.cols + c;
    if (!inGrid || grid.blocked[idx] || occupied[idx]) toMove.push(p);
    else occupied[idx] = 1;
  }
  const moved: number[] = [];
  for (const p of toMove) {
    const c0 = Math.round(p.x / grid.pitchX);
    const r0 = Math.round(p.y / grid.pitchY);
    let found = false;
    for (let radius = 1; radius < Math.max(grid.cols, grid.rows) && !found; radius++) {
      for (let dr = -radius; dr <= radius && !found; dr++) {
        for (let dc = -radius; dc <= radius && !found; dc++) {
          if (Math.max(Math.abs(dr), Math.abs(dc)) !== radius) continue;
          const r = r0 + dr;
          const c = c0 + dc;
          if (r < 0 || c < 0 || r >= grid.rows || c >= grid.cols) continue;
          const idx = r * grid.cols + c;
          if (grid.blocked[idx] || occupied[idx]) continue;
          occupied[idx] = 1;
          p.x = c * grid.pitchX;
          p.y = r * grid.pitchY;
          moved.push(p.node_id);
          found = true;
        }
      }
    }
  }
  return moved;
}
