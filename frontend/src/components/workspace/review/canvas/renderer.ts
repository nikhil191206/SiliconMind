/**
 * Canvas2D renderer for a placement (FRONTEND_SPEC.md §5).
 *
 * Draws ONLY geometry from PlacementJSON + CircuitGraph: rectangles, lines,
 * text. Layer order:
 *   1. canvas background + world grid
 *   2. die boundary (always drawn at true coordinates; never auto-fit)
 *   3. standard cells, individually when few/large enough on screen,
 *      otherwise as a density map (level of detail, §5.2)
 *   4. diff ghosts (previous positions) + motion arrows (§6.3)
 *   5. macros, always individual, with orientation-aware pin-1 marker (§5.3)
 *   6. nets of the selection (opt-in, §5.3)
 *   7. selection / out-of-die / unexpected-move highlights, box-select marquee
 *
 * Only nodes intersecting the viewport are touched (spatial index culling).
 */
import { pinOneCorner } from "../../../../lib/geometry/geometry";
import type { CircuitGraph } from "../../../../lib/schemas";
import type { PreparedPlacement } from "./prepare";
import { toScreenX, toScreenY, visibleWorld, type View } from "./viewport";

/**
 * LOD thresholds. Chosen by measuring the demo's 12,752-node (ibm01-sized)
 * and 120k-node synthetic designs in Chrome: individual cell rects stay
 * well above 30 fps up to ~25k visible cells. Re-measure on real designs
 * (spec §5.2: "pick the threshold empirically").
 */
export const LOD = {
  maxIndividualCells: 25_000,
  minCellPixels: 1.2,
  densityBinPx: 3,
};

export interface DiffOverlay {
  /** Previous placement's boxes, for ghosts/arrows. */
  previous: PreparedPlacement;
  moved: Set<number>;
  unexpected: Set<number>;
}

export interface RenderOptions {
  graph: CircuitGraph;
  selection: Set<number>;
  hovered: number | null;
  showNets: boolean;
  showLabels: boolean;
  diff: DiffOverlay | null;
  marquee: { x0: number; y0: number; x1: number; y1: number } | null;
}

export interface RenderStats {
  mode: "individual" | "density";
  visibleCells: number;
  visibleMacros: number;
  ms: number;
}

const COLORS = {
  bg: "#fbfbfa",
  grid: "#efeeeb",
  gridMajor: "#e4e3df",
  die: "#0a0a0a",
  dieFill: "#ffffff",
  cell: "#8a8a8a",
  macroFill: "#e9e8e4",
  macroStroke: "#262626",
  macroLabel: "#404040",
  pin: "#0a0a0a",
  select: "#2563eb",
  selectFill: "rgba(37, 99, 235, 0.10)",
  hover: "#60a5fa",
  moved: "#f97316",
  movedFill: "rgba(252, 166, 92, 0.25)",
  ghost: "rgba(38, 38, 38, 0.45)",
  unexpected: "#dc2626",
  outside: "#dc2626",
  net: "rgba(37, 99, 235, 0.55)",
};

let densityCanvas: HTMLCanvasElement | null = null;
const seenCells = { arr: new Uint8Array(0) };
const seenMacros = { arr: new Uint8Array(0) };

function ensureSeen(holder: { arr: Uint8Array }, n: number): Uint8Array {
  if (holder.arr.length < n) holder.arr = new Uint8Array(n);
  return holder.arr;
}

function drawGrid(ctx: CanvasRenderingContext2D, v: View): void {
  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(0, 0, v.width, v.height);
  // Grid step: a "nice" world step that's ~48px on screen.
  const target = 48 / v.scale;
  const pow = Math.pow(10, Math.floor(Math.log10(target)));
  const step = [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= target) ?? pow * 10;
  const w = visibleWorld(v);
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = Math.floor(w.x0 / step) * step; x <= w.x1; x += step) {
    const sx = Math.round(toScreenX(v, x)) + 0.5;
    ctx.moveTo(sx, 0);
    ctx.lineTo(sx, v.height);
  }
  for (let y = Math.floor(w.y0 / step) * step; y <= w.y1; y += step) {
    const sy = Math.round(toScreenY(v, y)) + 0.5;
    ctx.moveTo(0, sy);
    ctx.lineTo(v.width, sy);
  }
  ctx.strokeStyle = COLORS.grid;
  ctx.stroke();
}

function rectOf(v: View, b: Float64Array, id: number): [number, number, number, number] {
  const i = id * 4;
  const x = toScreenX(v, b[i]);
  const y = toScreenY(v, b[i + 3]);
  return [x, y, (b[i + 2] - b[i]) * v.scale, (b[i + 3] - b[i + 1]) * v.scale];
}

function drawCells(
  ctx: CanvasRenderingContext2D,
  v: View,
  p: PreparedPlacement,
): { mode: "individual" | "density"; count: number } {
  const world = visibleWorld(v);
  const seen = ensureSeen(seenCells, p.cellIds.length);
  const visible: number[] = [];
  p.cellIndex.query(world, (k) => visible.push(k), seen);

  // Estimate on-screen cell size from the first few visible cells.
  let avgPx = 0;
  const sample = Math.min(visible.length, 64);
  for (let s = 0; s < sample; s++) {
    const id = p.cellIds[visible[s]];
    avgPx += (p.boxes[id * 4 + 2] - p.boxes[id * 4]) * v.scale;
  }
  avgPx = sample ? avgPx / sample : 0;

  const individual = visible.length <= LOD.maxIndividualCells && avgPx >= LOD.minCellPixels;
  if (individual) {
    ctx.beginPath();
    for (const k of visible) {
      const id = p.cellIds[k];
      const [x, y, w, h] = rectOf(v, p.boxes, id);
      if (x > v.width || y > v.height || x + w < 0 || y + h < 0) continue;
      const inset = w > 3 ? 0.5 : 0;
      ctx.rect(x + inset, y + inset, Math.max(0.8, w - inset * 2), Math.max(0.8, h - inset * 2));
    }
    ctx.fillStyle = COLORS.cell;
    ctx.fill();
    return { mode: "individual", count: visible.length };
  }

  // Density map: fraction of each screen bin's area covered by cells.
  const bin = LOD.densityBinPx;
  const cols = Math.ceil(v.width / bin);
  const rows = Math.ceil(v.height / bin);
  const cover = new Float32Array(cols * rows);
  const binArea = bin * bin;
  for (const k of visible) {
    const id = p.cellIds[k];
    const [x, y, w, h] = rectOf(v, p.boxes, id);
    const c = Math.floor((x + w / 2) / bin);
    const r = Math.floor((y + h / 2) / bin);
    if (c < 0 || r < 0 || c >= cols || r >= rows) continue;
    cover[r * cols + c] += (w * h) / binArea;
  }
  if (!densityCanvas) densityCanvas = document.createElement("canvas");
  densityCanvas.width = cols;
  densityCanvas.height = rows;
  const dctx = densityCanvas.getContext("2d")!;
  const img = dctx.createImageData(cols, rows);
  for (let i = 0; i < cover.length; i++) {
    if (cover[i] <= 0) continue;
    const a = Math.min(1, cover[i]);
    img.data[i * 4] = 70;
    img.data[i * 4 + 1] = 70;
    img.data[i * 4 + 2] = 72;
    img.data[i * 4 + 3] = Math.round(40 + a * 190);
  }
  dctx.putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(densityCanvas, 0, 0, cols * bin, rows * bin);
  return { mode: "density", count: visible.length };
}

function drawMacro(
  ctx: CanvasRenderingContext2D,
  v: View,
  p: PreparedPlacement,
  id: number,
  opts: RenderOptions,
): void {
  const [x, y, w, h] = rectOf(v, p.boxes, id);
  const moved = opts.diff?.moved.has(id);
  ctx.fillStyle = moved ? COLORS.movedFill : COLORS.macroFill;
  ctx.fillRect(x, y, w, h);
  ctx.lineWidth = 1.25;
  ctx.strokeStyle = moved ? COLORS.moved : COLORS.macroStroke;
  ctx.strokeRect(x + 0.5, y + 0.5, Math.max(0, w - 1), Math.max(0, h - 1));

  // Pin-1 marker: a filled corner triangle, placed per orientation so that
  // rotation AND mirroring are visible geometrically (spec §5.3).
  const size = Math.min(w, h) * 0.22;
  if (size >= 3) {
    const [u, vv] = pinOneCorner(p.orientation[id]);
    // u: 0 = left, 1 = right. vv: 0 = bottom (screen: y + h), 1 = top (screen: y).
    const cx = u === 0 ? x : x + w;
    const cy = vv === 0 ? y + h : y;
    const dx = u === 0 ? size : -size;
    const dy = vv === 0 ? -size : size;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + dx, cy);
    ctx.lineTo(cx, cy + dy);
    ctx.closePath();
    ctx.fillStyle = COLORS.pin;
    ctx.fill();
  }

  if (opts.showLabels && w > 34 && h > 16) {
    ctx.fillStyle = COLORS.macroLabel;
    ctx.font = `500 ${Math.min(13, Math.max(10, h * 0.18))}px "JetBrains Mono Variable", ui-monospace, monospace`;
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    ctx.fillText(`M${id}`, x + w / 2, y + h / 2);
  }
}

function centerOf(p: PreparedPlacement, id: number): [number, number] {
  const i = id * 4;
  return [(p.boxes[i] + p.boxes[i + 2]) / 2, (p.boxes[i + 1] + p.boxes[i + 3]) / 2];
}

function drawArrow(ctx: CanvasRenderingContext2D, x0: number, y0: number, x1: number, y1: number, color: string): void {
  const len = Math.hypot(x1 - x0, y1 - y0);
  if (len < 4) return;
  const a = Math.atan2(y1 - y0, x1 - x0);
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 1.5;
  ctx.setLineDash([4, 3]);
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();
  ctx.setLineDash([]);
  const head = Math.min(9, len * 0.4);
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x1 - head * Math.cos(a - 0.45), y1 - head * Math.sin(a - 0.45));
  ctx.lineTo(x1 - head * Math.cos(a + 0.45), y1 - head * Math.sin(a + 0.45));
  ctx.closePath();
  ctx.fill();
}

function drawDiff(ctx: CanvasRenderingContext2D, v: View, p: PreparedPlacement, diff: DiffOverlay): void {
  const draw = (id: number, color: string) => {
    const [gx, gy, gw, gh] = rectOf(v, diff.previous.boxes, id);
    if (gw >= 2 && gh >= 2) {
      ctx.setLineDash([3, 3]);
      ctx.strokeStyle = COLORS.ghost;
      ctx.lineWidth = 1;
      ctx.strokeRect(gx + 0.5, gy + 0.5, gw - 1, gh - 1);
      ctx.setLineDash([]);
    }
    const [ax, ay] = centerOf(diff.previous, id);
    const [bx, by] = centerOf(p, id);
    drawArrow(ctx, toScreenX(v, ax), toScreenY(v, ay), toScreenX(v, bx), toScreenY(v, by), color);
  };
  // Macros always. Displaced std cells only once zoomed in far enough for
  // their arrows to be legible (otherwise they bury the macro moves).
  let cellBudget = 300;
  for (const id of diff.moved) {
    if (p.isMacro[id]) {
      draw(id, COLORS.moved);
      continue;
    }
    const cellPx = (p.boxes[id * 4 + 2] - p.boxes[id * 4]) * v.scale;
    if (cellPx >= 6 && cellBudget-- > 0) draw(id, "rgba(249, 115, 22, 0.55)");
  }
  for (const id of diff.unexpected) draw(id, COLORS.unexpected);
}

function drawNets(ctx: CanvasRenderingContext2D, v: View, p: PreparedPlacement, opts: RenderOptions): void {
  const nets = new Set<number>();
  for (const id of opts.selection) {
    for (let e = p.netStart[id]; e < p.netStart[id + 1]; e++) nets.add(p.netList[e]);
    if (nets.size > 4000) break;
  }
  ctx.strokeStyle = COLORS.net;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (const netId of nets) {
    const net = opts.graph.hyperedges[netId];
    const pins = net.driver_node === null ? net.sink_nodes : [net.driver_node, ...net.sink_nodes];
    if (pins.length < 2) continue;
    // Star from the driver (or first pin), the same pin set HPWL uses.
    const [hx, hy] = centerOf(p, pins[0]);
    const sx0 = toScreenX(v, hx);
    const sy0 = toScreenY(v, hy);
    for (let k = 1; k < pins.length; k++) {
      const [px, py] = centerOf(p, pins[k]);
      ctx.moveTo(sx0, sy0);
      ctx.lineTo(toScreenX(v, px), toScreenY(v, py));
    }
  }
  ctx.stroke();
}

export function renderPlacement(
  ctx: CanvasRenderingContext2D,
  v: View,
  p: PreparedPlacement,
  opts: RenderOptions,
): RenderStats {
  const t0 = performance.now();
  drawGrid(ctx, v);

  // Die: white fill + strong outline, at its true coordinates.
  const dx = toScreenX(v, p.die.x0);
  const dy = toScreenY(v, p.die.y1);
  const dw = (p.die.x1 - p.die.x0) * v.scale;
  const dh = (p.die.y1 - p.die.y0) * v.scale;
  ctx.fillStyle = COLORS.dieFill;
  ctx.fillRect(dx, dy, dw, dh);

  const cells = drawCells(ctx, v, p);

  if (opts.diff) drawDiff(ctx, v, p, opts.diff);

  const world = visibleWorld(v);
  const seen = ensureSeen(seenMacros, p.macroIds.length);
  let macroCount = 0;
  p.macroIndex.query(
    world,
    (k) => {
      macroCount++;
      drawMacro(ctx, v, p, p.macroIds[k], opts);
    },
    seen,
  );

  // Die outline on top of contents so overflow past it is obvious.
  ctx.strokeStyle = COLORS.die;
  ctx.lineWidth = 2;
  ctx.strokeRect(dx, dy, dw, dh);

  if (opts.showNets && opts.selection.size > 0) drawNets(ctx, v, p, opts);

  // Out-of-die nodes: red outline so they can't hide.
  if (p.outOfDie.length) {
    ctx.strokeStyle = COLORS.outside;
    ctx.lineWidth = 2;
    for (const id of p.outOfDie) {
      const [x, y, w, h] = rectOf(v, p.boxes, id);
      ctx.strokeRect(x - 1, y - 1, Math.max(3, w + 2), Math.max(3, h + 2));
    }
  }

  // Selection + hover.
  for (const id of opts.selection) {
    const [x, y, w, h] = rectOf(v, p.boxes, id);
    ctx.fillStyle = COLORS.selectFill;
    ctx.fillRect(x - 2, y - 2, Math.max(4, w + 4), Math.max(4, h + 4));
    ctx.strokeStyle = COLORS.select;
    ctx.lineWidth = 2;
    ctx.strokeRect(x - 2, y - 2, Math.max(4, w + 4), Math.max(4, h + 4));
  }
  if (opts.hovered !== null && !opts.selection.has(opts.hovered)) {
    const [x, y, w, h] = rectOf(v, p.boxes, opts.hovered);
    ctx.strokeStyle = COLORS.hover;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x - 1.5, y - 1.5, Math.max(3, w + 3), Math.max(3, h + 3));
  }

  if (opts.marquee) {
    const m = opts.marquee;
    ctx.fillStyle = "rgba(37, 99, 235, 0.08)";
    ctx.strokeStyle = COLORS.select;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    const x = Math.min(m.x0, m.x1);
    const y = Math.min(m.y0, m.y1);
    ctx.fillRect(x, y, Math.abs(m.x1 - m.x0), Math.abs(m.y1 - m.y0));
    ctx.strokeRect(x + 0.5, y + 0.5, Math.abs(m.x1 - m.x0), Math.abs(m.y1 - m.y0));
    ctx.setLineDash([]);
  }

  return { mode: cells.mode, visibleCells: cells.count, visibleMacros: macroCount, ms: performance.now() - t0 };
}

/** Hit test: macros take priority; std cells only when zoomed in enough to see them. */
export function hitTest(v: View, p: PreparedPlacement, wx: number, wy: number): number | null {
  const tol = 3 / v.scale;
  const q = { x0: wx - tol, y0: wy - tol, x1: wx + tol, y1: wy + tol };
  let hit: number | null = null;
  const inside = (id: number) => {
    const i = id * 4;
    return wx >= p.boxes[i] - tol && wx <= p.boxes[i + 2] + tol && wy >= p.boxes[i + 1] - tol && wy <= p.boxes[i + 3] + tol;
  };
  p.macroIndex.query(q, (k) => {
    if (hit === null && inside(p.macroIds[k])) hit = p.macroIds[k];
  }, ensureSeen(seenMacros, p.macroIds.length));
  if (hit !== null) return hit;
  const avgCellPx =
    p.cellIds.length > 0 ? (p.boxes[p.cellIds[0] * 4 + 2] - p.boxes[p.cellIds[0] * 4]) * v.scale : 0;
  if (avgCellPx < 4) return null;
  p.cellIndex.query(q, (k) => {
    if (hit === null && inside(p.cellIds[k])) hit = p.cellIds[k];
  }, ensureSeen(seenCells, p.cellIds.length));
  return hit;
}

/** All macros (and cells, if zoomed in) fully or partly inside a world box. */
export function boxSelect(p: PreparedPlacement, x0: number, y0: number, x1: number, y1: number): number[] {
  const q = { x0: Math.min(x0, x1), y0: Math.min(y0, y1), x1: Math.max(x0, x1), y1: Math.max(y0, y1) };
  const out: number[] = [];
  const intersects = (id: number) => {
    const i = id * 4;
    return p.boxes[i] < q.x1 && p.boxes[i + 2] > q.x0 && p.boxes[i + 1] < q.y1 && p.boxes[i + 3] > q.y0;
  };
  p.macroIndex.query(q, (k) => {
    if (intersects(p.macroIds[k])) out.push(p.macroIds[k]);
  }, ensureSeen(seenMacros, p.macroIds.length));
  return out;
}
