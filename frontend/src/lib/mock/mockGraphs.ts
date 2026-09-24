/**
 * DEMO MODE ONLY: CircuitGraph fixtures for the in-browser mock backend.
 *
 * `makeMockToyGraph` is a byte-for-byte port of shared/mocks/mock_circuit_graph.py.
 * `makeSyntheticGraph` builds larger, clustered, schema-valid graphs purely so
 * the UI (LOD, culling, diffing) can be exercised at realistic node counts
 * before real benchmark chips are wired up. They are NOT real designs and the
 * UI labels them as synthetic wherever they appear.
 */
import type { CircuitGraph, CircuitHyperedge, CircuitNode } from "../schemas";
import { mulberry32 } from "../random";

export function makeMockToyGraph(): CircuitGraph {
  const cell = (id: number, pins: number): CircuitNode => ({
    node_id: id,
    type: "STD_CELL",
    width: 1,
    height: 1,
    pin_count: pins,
  });
  return {
    design_name: "mock_toy_design",
    nodes: [
      { node_id: 0, type: "MACRO", width: 20, height: 15, pin_count: 8 },
      { node_id: 1, type: "MACRO", width: 18, height: 12, pin_count: 6 },
      cell(2, 3),
      cell(3, 3),
      cell(4, 2),
      cell(5, 3),
      cell(6, 2),
      cell(7, 4),
    ],
    hyperedges: [
      { net_id: 0, driver_node: 0, sink_nodes: [2, 3, 4] },
      { net_id: 1, driver_node: 2, sink_nodes: [5] },
      { net_id: 2, driver_node: 1, sink_nodes: [6, 7] },
      { net_id: 3, driver_node: null, sink_nodes: [0, 1] },
    ],
    die: { width: 100, height: 100 },
  };
}

export interface SyntheticSpec {
  designName: string;
  macros: number;
  stdCells: number;
  seed: number;
}

/**
 * Clustered synthetic netlist: every std cell belongs to one macro's cluster
 * and most nets stay inside a cluster, with a few global nets between macros -
 * enough structure that HPWL responds sensibly to edits.
 */
export function makeSyntheticGraph(spec: SyntheticSpec): CircuitGraph {
  const rand = mulberry32(spec.seed);
  const nodes: CircuitNode[] = [];
  let macroArea = 0;

  for (let i = 0; i < spec.macros; i++) {
    const w = Math.round(14 + rand() * 30 + (i % 5 === 0 ? 18 : 0));
    const h = Math.round(10 + rand() * 24 + (i % 7 === 0 ? 14 : 0));
    macroArea += w * h;
    nodes.push({ node_id: i, type: "MACRO", width: w, height: h, pin_count: 16 + Math.floor(rand() * 240) });
  }
  for (let j = 0; j < spec.stdCells; j++) {
    nodes.push({
      node_id: spec.macros + j,
      type: "STD_CELL",
      width: 1,
      height: 1,
      pin_count: 2 + Math.floor(rand() * 4),
    });
  }

  // Die: macros at ~40% packing + cells at ~62% utilisation, square-ish.
  const area = macroArea / 0.4 + spec.stdCells / 0.62;
  const side = Math.ceil(Math.sqrt(area));
  const die = { width: side, height: Math.ceil(side * (0.85 + rand() * 0.2)) };

  const hyperedges: CircuitHyperedge[] = [];
  const clusterOf = (j: number) => j % Math.max(1, spec.macros);
  const cellsByCluster: number[][] = Array.from({ length: Math.max(1, spec.macros) }, () => []);
  for (let j = 0; j < spec.stdCells; j++) cellsByCluster[clusterOf(j)].push(spec.macros + j);

  // Intra-cluster nets: chains of small fan-out rooted near the macro.
  for (let c = 0; c < cellsByCluster.length; c++) {
    const members = cellsByCluster[c];
    for (let k = 0; k < members.length; k++) {
      if (rand() < 0.35) continue;
      const fanout = 1 + Math.floor(rand() * 3);
      const sinks: number[] = [];
      for (let f = 0; f < fanout; f++) {
        const idx = Math.min(members.length - 1, k + 1 + Math.floor(rand() * 12));
        if (members[idx] !== members[k] && !sinks.includes(members[idx])) sinks.push(members[idx]);
      }
      if (sinks.length === 0) continue;
      const driver = k < 4 && spec.macros > 0 ? c : members[k];
      hyperedges.push({ net_id: hyperedges.length, driver_node: driver, sink_nodes: sinks });
    }
  }
  // Global nets between macros (a bus-like backbone plus random links).
  for (let i = 0; i + 1 < spec.macros; i++) {
    hyperedges.push({ net_id: hyperedges.length, driver_node: i, sink_nodes: [i + 1] });
    if (rand() < 0.5) {
      const other = Math.floor(rand() * spec.macros);
      if (other !== i) hyperedges.push({ net_id: hyperedges.length, driver_node: i, sink_nodes: [other] });
    }
  }
  if (spec.macros > 1) {
    hyperedges.push({
      net_id: hyperedges.length,
      driver_node: null,
      sink_nodes: Array.from({ length: Math.min(spec.macros, 6) }, (_, i) => i),
    });
  }

  return { design_name: spec.designName, nodes, hyperedges, die };
}

export interface DemoSample {
  id: string;
  label: string;
  description: string;
  build: () => CircuitGraph;
}

export const DEMO_SAMPLES: DemoSample[] = [
  {
    id: "toy",
    label: "mock_toy_design",
    description: "8 nodes · the exact fixture from shared/mocks/mock_circuit_graph.py",
    build: makeMockToyGraph,
  },
  {
    id: "small",
    label: "synthetic_small",
    description: "12 macros · 3,000 cells · synthetic",
    build: () => makeSyntheticGraph({ designName: "synthetic_small", macros: 12, stdCells: 3_000, seed: 11 }),
  },
  {
    id: "ibm01",
    label: "synthetic_ibm01_scale",
    description: "12,752 nodes (ibm01's size) · synthetic, for perf testing",
    build: () =>
      makeSyntheticGraph({ designName: "synthetic_ibm01_scale", macros: 24, stdCells: 12_728, seed: 1 }),
  },
  {
    id: "stress",
    label: "synthetic_stress_120k",
    description: "120,000 nodes · synthetic, exercises level-of-detail",
    build: () =>
      makeSyntheticGraph({ designName: "synthetic_stress_120k", macros: 48, stdCells: 119_952, seed: 7 }),
  },
];
