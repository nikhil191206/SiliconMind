/**
 * Frontend mirror of shared/metrics/geometry.py: the ONE place that fixes the
 * project's placement conventions, so the renderer never disagrees with the
 * metrics the backend reports:
 *
 *   - (x, y) is the node's bounding-box origin (lower-left corner).
 *   - N / S / FN / FS are 0° orientations: width/height as authored.
 *   - E / W / FE / FW are 90° rotations: effective width/height swap.
 *   - F-prefixed = mirrored (about the Y axis, per LEF/DEF), which does not
 *     change the bounding box but DOES change where pin-1 sits, so the
 *     canvas draws a pin-1 marker to make orientation visible (spec §5.3).
 */
import type { CircuitNode, Orientation, PlacementEntry } from "../schemas";

const ROTATED_90 = new Set<Orientation>(["E", "W", "FE", "FW"]);

export function effectiveDims(width: number, height: number, o: Orientation): [number, number] {
  return ROTATED_90.has(o) ? [height, width] : [width, height];
}

export interface BBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export function nodeBBox(entry: PlacementEntry, node: CircuitNode): BBox {
  const [w, h] = effectiveDims(node.width, node.height, entry.orientation);
  return { x0: entry.x, y0: entry.y, x1: entry.x + w, y1: entry.y + h };
}

export function nodeCenter(entry: PlacementEntry, node: CircuitNode): [number, number] {
  const b = nodeBBox(entry, node);
  return [(b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2];
}

export function bboxOverlap(a: BBox, b: BBox): boolean {
  return a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
}

/**
 * Where the pin-1 corner lands, as fractions (u, v) of the placed bounding
 * box, measured from its lower-left. For N the authored pin-1 is the
 * lower-left corner (0,0); every other orientation rotates/mirrors it.
 * Rotations are counter-clockwise as in LEF/DEF: W = 90°, S = 180°, E = 270°.
 */
export function pinOneCorner(o: Orientation): [number, number] {
  switch (o) {
    case "N":
      return [0, 0];
    case "W":
      return [1, 0];
    case "S":
      return [1, 1];
    case "E":
      return [0, 1];
    case "FN":
      return [1, 0];
    case "FW":
      return [1, 1];
    case "FS":
      return [0, 1];
    case "FE":
      return [0, 0];
  }
}

/** Human description, used in the node detail panel. */
export function describeOrientation(o: Orientation): string {
  const map: Record<Orientation, string> = {
    N: "North, 0°, as authored",
    S: "South, rotated 180°",
    E: "East, rotated 270°",
    W: "West, rotated 90°",
    FN: "Flipped North, mirrored, 0°",
    FS: "Flipped South, mirrored, 180°",
    FE: "Flipped East, mirrored, 270°",
    FW: "Flipped West, mirrored, 90°",
  };
  return map[o];
}
