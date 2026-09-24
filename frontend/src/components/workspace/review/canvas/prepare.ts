/**
 * Turns (CircuitGraph, PlacementJSON) into flat typed arrays + spatial
 * indexes once, so per-frame drawing and hit-testing never touch the JSON
 * objects again. Rebuilt only when the graph or placement object changes.
 */
import type { CircuitGraph, Orientation, PlacementJSON } from "../../../../lib/schemas";
import { effectiveDims, type BBox } from "../../../../lib/geometry/geometry";
import { SpatialIndex } from "../../../../lib/geometry/spatialIndex";

export interface PreparedPlacement {
  n: number;
  /** [x0, y0, x1, y1] per node_id (placed bounding box, die units). */
  boxes: Float64Array;
  isMacro: Uint8Array;
  orientation: Orientation[];
  /** node_ids of macros. */
  macroIds: Int32Array;
  /** node_ids of std cells. */
  cellIds: Int32Array;
  /** Index over macroIds (item i → macroIds[i]). */
  macroIndex: SpatialIndex;
  /** Index over cellIds (item i → cellIds[i]). */
  cellIndex: SpatialIndex;
  /** Die rectangle, the canvas' reference frame, never auto-fit to placements. */
  die: BBox;
  /** Die grown to include anything placed outside it. */
  extent: BBox;
  /** node_ids placed (partly) outside the die. */
  outOfDie: Int32Array;
  /** Nodes missing from the placement (would be a contract violation). */
  missing: number;
  /** node → incident net ids (CSR), for the "nets of selection" overlay. */
  netStart: Int32Array;
  netList: Int32Array;
}

function subsetBoxes(boxes: Float64Array, ids: Int32Array): Float64Array {
  const out = new Float64Array(ids.length * 4);
  for (let k = 0; k < ids.length; k++) {
    const i = ids[k] * 4;
    out[k * 4] = boxes[i];
    out[k * 4 + 1] = boxes[i + 1];
    out[k * 4 + 2] = boxes[i + 2];
    out[k * 4 + 3] = boxes[i + 3];
  }
  return out;
}

export function preparePlacement(graph: CircuitGraph, placement: PlacementJSON): PreparedPlacement {
  const n = graph.nodes.length;
  const boxes = new Float64Array(n * 4).fill(NaN);
  const isMacro = new Uint8Array(n);
  const orientation: Orientation[] = new Array(n).fill("N");
  let macroCount = 0;
  for (const node of graph.nodes) {
    if (node.type === "MACRO") {
      isMacro[node.node_id] = 1;
      macroCount++;
    }
  }

  for (const p of placement.placements) {
    const node = graph.nodes[p.node_id];
    if (!node) continue;
    const [w, h] = effectiveDims(node.width, node.height, p.orientation);
    const i = p.node_id * 4;
    boxes[i] = p.x;
    boxes[i + 1] = p.y;
    boxes[i + 2] = p.x + w;
    boxes[i + 3] = p.y + h;
    orientation[p.node_id] = p.orientation;
  }

  const die: BBox = { x0: 0, y0: 0, x1: graph.die.width, y1: graph.die.height };
  const extent: BBox = { ...die };
  const outside: number[] = [];
  let missing = 0;
  const eps = 1e-6;
  for (let id = 0; id < n; id++) {
    const i = id * 4;
    if (Number.isNaN(boxes[i])) {
      missing++;
      // Park missing nodes on a zero-size box at the origin so indexes stay valid.
      boxes[i] = boxes[i + 1] = boxes[i + 2] = boxes[i + 3] = 0;
      continue;
    }
    if (boxes[i] < -eps || boxes[i + 1] < -eps || boxes[i + 2] > die.x1 + eps || boxes[i + 3] > die.y1 + eps) {
      outside.push(id);
    }
    extent.x0 = Math.min(extent.x0, boxes[i]);
    extent.y0 = Math.min(extent.y0, boxes[i + 1]);
    extent.x1 = Math.max(extent.x1, boxes[i + 2]);
    extent.y1 = Math.max(extent.y1, boxes[i + 3]);
  }

  const macroIds = new Int32Array(macroCount);
  const cellIds = new Int32Array(n - macroCount);
  let m = 0;
  let c = 0;
  for (let id = 0; id < n; id++) {
    if (isMacro[id]) macroIds[m++] = id;
    else cellIds[c++] = id;
  }

  // Node → nets CSR.
  const deg = new Int32Array(n + 1);
  for (const net of graph.hyperedges) {
    if (net.driver_node !== null) deg[net.driver_node]++;
    for (const s of net.sink_nodes) deg[s]++;
  }
  const netStart = new Int32Array(n + 1);
  for (let i = 0; i < n; i++) netStart[i + 1] = netStart[i] + deg[i];
  const fill = netStart.slice(0, n);
  const netList = new Int32Array(netStart[n]);
  for (const net of graph.hyperedges) {
    if (net.driver_node !== null) netList[fill[net.driver_node]++] = net.net_id;
    for (const s of net.sink_nodes) netList[fill[s]++] = net.net_id;
  }

  return {
    n,
    boxes,
    isMacro,
    orientation,
    macroIds,
    cellIds,
    macroIndex: new SpatialIndex(subsetBoxes(boxes, macroIds), extent, 4),
    cellIndex: new SpatialIndex(subsetBoxes(boxes, cellIds), extent, 24),
    die,
    extent,
    outOfDie: Int32Array.from(outside),
    missing,
    netStart,
    netList,
  };
}
