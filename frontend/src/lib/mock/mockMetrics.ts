/**
 * DEMO MODE ONLY: the mock backend's stand-in for Person C's shared/metrics/.
 *
 * In the real system the frontend NEVER computes metrics (every reported
 * number must trace back to shared/metrics/). This file exists solely so the
 * in-browser mock can play the backend's role. HPWL follows hpwl.py exactly
 * (pins at node bbox centres, nets with <2 pins contribute 0). Congestion is a
 * RUDY-style estimate and legality counts overlapping pairs + out-of-die
 * nodes, plausible stand-ins, not ports of C's code.
 */
import type { CircuitGraph, MetricsObject, PlacementJSON } from "../schemas";
import { effectiveDims } from "../geometry/geometry";

interface Placed {
  x0: Float64Array;
  y0: Float64Array;
  x1: Float64Array;
  y1: Float64Array;
}

export function placedBoxes(placement: PlacementJSON, graph: CircuitGraph): Placed {
  const n = graph.nodes.length;
  const out: Placed = {
    x0: new Float64Array(n),
    y0: new Float64Array(n),
    x1: new Float64Array(n),
    y1: new Float64Array(n),
  };
  for (const p of placement.placements) {
    const node = graph.nodes[p.node_id];
    const [w, h] = effectiveDims(node.width, node.height, p.orientation);
    out.x0[p.node_id] = p.x;
    out.y0[p.node_id] = p.y;
    out.x1[p.node_id] = p.x + w;
    out.y1[p.node_id] = p.y + h;
  }
  return out;
}

export function computeHpwl(placement: PlacementJSON, graph: CircuitGraph): number {
  const b = placedBoxes(placement, graph);
  let total = 0;
  for (const net of graph.hyperedges) {
    const pins = net.driver_node === null ? net.sink_nodes : [...net.sink_nodes, net.driver_node];
    if (pins.length < 2) continue;
    let xmin = Infinity;
    let xmax = -Infinity;
    let ymin = Infinity;
    let ymax = -Infinity;
    for (const id of pins) {
      const cx = (b.x0[id] + b.x1[id]) / 2;
      const cy = (b.y0[id] + b.y1[id]) / 2;
      if (cx < xmin) xmin = cx;
      if (cx > xmax) xmax = cx;
      if (cy < ymin) ymin = cy;
      if (cy > ymax) ymax = cy;
    }
    total += xmax - xmin + (ymax - ymin);
  }
  return total;
}

export function computeCongestionOverflow(placement: PlacementJSON, graph: CircuitGraph, bins = 32): number {
  const b = placedBoxes(placement, graph);
  const { width, height } = graph.die;
  const bw = width / bins;
  const bh = height / bins;
  const demand = new Float64Array(bins * bins);
  for (const net of graph.hyperedges) {
    const pins = net.driver_node === null ? net.sink_nodes : [...net.sink_nodes, net.driver_node];
    if (pins.length < 2) continue;
    let xmin = Infinity;
    let xmax = -Infinity;
    let ymin = Infinity;
    let ymax = -Infinity;
    for (const id of pins) {
      const cx = (b.x0[id] + b.x1[id]) / 2;
      const cy = (b.y0[id] + b.y1[id]) / 2;
      xmin = Math.min(xmin, cx);
      xmax = Math.max(xmax, cx);
      ymin = Math.min(ymin, cy);
      ymax = Math.max(ymax, cy);
    }
    const w = Math.max(xmax - xmin, bw * 0.5);
    const h = Math.max(ymax - ymin, bh * 0.5);
    const density = (w + h) / (w * h); // RUDY
    const c0 = Math.max(0, Math.floor(xmin / bw));
    const c1 = Math.min(bins - 1, Math.floor((xmin + w) / bw));
    const r0 = Math.max(0, Math.floor(ymin / bh));
    const r1 = Math.min(bins - 1, Math.floor((ymin + h) / bh));
    for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) demand[r * bins + c] += density * bw * bh;
  }
  // Capacity: 1.3x the mean demand of occupied bins, so overflow measures
  // hotspots relative to this design rather than an arbitrary absolute scale.
  let sum = 0;
  let occupied = 0;
  for (let i = 0; i < demand.length; i++) {
    if (demand[i] > 0) {
      sum += demand[i];
      occupied++;
    }
  }
  const capacity = occupied ? (sum / occupied) * 1.3 : 1;
  let overflow = 0;
  for (let i = 0; i < demand.length; i++) overflow += Math.max(0, demand[i] - capacity);
  // Normalised by total capacity -> a small, comparable ratio.
  return overflow / (capacity * bins * bins);
}

/** Overlapping node pairs (grid-hashed) + nodes extending outside the die. */
export function computeLegalityViolations(placement: PlacementJSON, graph: CircuitGraph): number {
  const b = placedBoxes(placement, graph);
  const n = graph.nodes.length;
  const eps = 1e-6;
  let violations = 0;
  for (let i = 0; i < n; i++) {
    if (b.x0[i] < -eps || b.y0[i] < -eps || b.x1[i] > graph.die.width + eps || b.y1[i] > graph.die.height + eps) {
      violations++;
    }
  }
  const cell = Math.max(2, Math.sqrt((graph.die.width * graph.die.height) / Math.max(1, n)) * 2);
  const grid = new Map<number, number[]>();
  const key = (c: number, r: number) => r * 1_000_003 + c;
  for (let i = 0; i < n; i++) {
    const c0 = Math.floor(b.x0[i] / cell);
    const c1 = Math.floor((b.x1[i] - eps) / cell);
    const r0 = Math.floor(b.y0[i] / cell);
    const r1 = Math.floor((b.y1[i] - eps) / cell);
    for (let r = r0; r <= r1; r++) {
      for (let c = c0; c <= c1; c++) {
        const k = key(c, r);
        const list = grid.get(k);
        if (list) list.push(i);
        else grid.set(k, [i]);
      }
    }
  }
  const counted = new Set<number>();
  for (const list of grid.values()) {
    for (let a = 0; a < list.length; a++) {
      for (let z = a + 1; z < list.length; z++) {
        const i = list[a];
        const j = list[z];
        if (b.x0[i] < b.x1[j] - eps && b.x0[j] < b.x1[i] - eps && b.y0[i] < b.y1[j] - eps && b.y0[j] < b.y1[i] - eps) {
          const pairKey = Math.min(i, j) * n + Math.max(i, j);
          if (!counted.has(pairKey)) {
            counted.add(pairKey);
            violations++;
          }
        }
      }
    }
  }
  return violations;
}

export function computeMetrics(placement: PlacementJSON, graph: CircuitGraph, runtimeSeconds: number): MetricsObject {
  return {
    hpwl: computeHpwl(placement, graph),
    congestion_overflow: computeCongestionOverflow(placement, graph),
    legality_violations: computeLegalityViolations(placement, graph),
    runtime_seconds: runtimeSeconds,
  };
}
