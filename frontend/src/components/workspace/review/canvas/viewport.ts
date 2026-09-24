/**
 * World (die units, Y up, origin lower-left) ↔ screen (CSS px, Y down).
 * The view is a centre point plus a scale; zoom keeps the cursor's world
 * point fixed.
 */
import type { BBox } from "../../../../lib/geometry/geometry";

export interface View {
  cx: number;
  cy: number;
  /** CSS pixels per die unit. */
  scale: number;
  width: number;
  height: number;
}

export const MIN_SCALE_FACTOR = 0.2; // relative to "fit die"
export const MAX_SCALE_FACTOR = 4000;

export function toScreenX(v: View, x: number): number {
  return (x - v.cx) * v.scale + v.width / 2;
}

export function toScreenY(v: View, y: number): number {
  return v.height / 2 - (y - v.cy) * v.scale;
}

export function toWorld(v: View, sx: number, sy: number): [number, number] {
  return [(sx - v.width / 2) / v.scale + v.cx, (v.height / 2 - sy) / v.scale + v.cy];
}

export function visibleWorld(v: View): BBox {
  const [x0, y1] = toWorld(v, 0, 0);
  const [x1, y0] = toWorld(v, v.width, v.height);
  return { x0, y0, x1, y1 };
}

/** Scale that fits the DIE (not the placements) with padding, spec §5.3. */
export function fitScale(die: BBox, width: number, height: number, pad = 36): number {
  const w = Math.max(die.x1 - die.x0, 1e-9);
  const h = Math.max(die.y1 - die.y0, 1e-9);
  return Math.max(1e-9, Math.min((width - pad * 2) / w, (height - pad * 2) / h));
}

export function fitView(die: BBox, width: number, height: number): View {
  return {
    cx: (die.x0 + die.x1) / 2,
    cy: (die.y0 + die.y1) / 2,
    scale: fitScale(die, width, height),
    width,
    height,
  };
}

export function zoomAt(v: View, sx: number, sy: number, factor: number, baseScale: number): View {
  const next = Math.min(baseScale * MAX_SCALE_FACTOR, Math.max(baseScale * MIN_SCALE_FACTOR, v.scale * factor));
  const [wx, wy] = toWorld(v, sx, sy);
  const nv = { ...v, scale: next };
  // Keep (wx, wy) under the cursor.
  const [ax, ay] = toWorld(nv, sx, sy);
  return { ...nv, cx: nv.cx + (wx - ax), cy: nv.cy + (wy - ay) };
}
