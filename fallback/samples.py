"""FALLBACK ONLY: sample CircuitGraphs for the demo.

`mock_toy_design` is the exact fixture from shared/mocks. The rest are
synthetic, clustered netlists (same recipe as the frontend's
lib/mock/mockGraphs.ts) built so HPWL responds sensibly to placement and
edits. None of them is a real benchmark chip, and the UI labels them so.
"""
from __future__ import annotations

import numpy as np

from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.schemas.circuit_graph import CircuitGraph, CircuitHyperedge, CircuitNode, Die, NodeType


def make_synthetic_graph(design_name: str, macros: int, std_cells: int, seed: int) -> CircuitGraph:
    rng = np.random.default_rng(seed)
    nodes: list[CircuitNode] = []
    macro_area = 0.0
    for i in range(macros):
        w = float(round(14 + rng.random() * 30 + (18 if i % 5 == 0 else 0)))
        h = float(round(10 + rng.random() * 24 + (14 if i % 7 == 0 else 0)))
        macro_area += w * h
        nodes.append(CircuitNode(node_id=i, type=NodeType.MACRO, width=w, height=h, pin_count=int(16 + rng.integers(0, 240))))
    for j in range(std_cells):
        nodes.append(
            CircuitNode(node_id=macros + j, type=NodeType.STD_CELL, width=1.0, height=1.0, pin_count=int(2 + rng.integers(0, 4)))
        )

    # Die: macros at ~40% packing + cells at ~62% utilisation, square-ish.
    area = macro_area / 0.4 + std_cells / 0.62
    side = float(np.ceil(np.sqrt(max(area, 16.0))))
    die = Die(width=side, height=float(np.ceil(side * (0.85 + rng.random() * 0.2))))

    edges: list[tuple[int | None, list[int]]] = []
    n_clusters = max(1, macros)
    clusters: list[list[int]] = [[] for _ in range(n_clusters)]
    for j in range(std_cells):
        clusters[j % n_clusters].append(macros + j)

    # Intra-cluster nets: short chains of small fan-out, rooted at the macro.
    for c, members in enumerate(clusters):
        for k in range(len(members)):
            if rng.random() < 0.35:
                continue
            fanout = 1 + int(rng.integers(0, 3))
            sinks: list[int] = []
            for _ in range(fanout):
                idx = min(len(members) - 1, k + 1 + int(rng.integers(0, 12)))
                if members[idx] != members[k] and members[idx] not in sinks:
                    sinks.append(members[idx])
            if not sinks:
                continue
            driver = c if (k < 4 and macros > 0) else members[k]
            edges.append((driver, sinks))

    # Global nets between macros: a bus-like backbone plus random links.
    for i in range(macros - 1):
        edges.append((i, [i + 1]))
        if rng.random() < 0.5:
            other = int(rng.integers(0, macros))
            if other != i:
                edges.append((i, [other]))
    if macros > 1:
        edges.append((None, list(range(min(macros, 6)))))

    hyperedges = [CircuitHyperedge(net_id=k, driver_node=d, sink_nodes=s) for k, (d, s) in enumerate(edges)]
    return CircuitGraph(design_name=design_name, nodes=nodes, hyperedges=hyperedges, die=die)


SAMPLES = {
    "toy": {
        "label": "mock_toy_design",
        "description": "8 nodes · the exact fixture from shared/mocks/mock_circuit_graph.py",
        "build": make_mock_circuit_graph,
    },
    "small": {
        "label": "synthetic_small",
        "description": "12 macros · 3,000 cells · synthetic clustered netlist",
        "build": lambda: make_synthetic_graph("synthetic_small", macros=12, std_cells=3_000, seed=11),
    },
    "medium": {
        "label": "synthetic_medium",
        "description": "20 macros · 8,000 cells · synthetic clustered netlist",
        "build": lambda: make_synthetic_graph("synthetic_medium", macros=20, std_cells=8_000, seed=5),
    },
    "ibm01": {
        "label": "synthetic_ibm01_scale",
        "description": "12,752 nodes (ibm01's size) · synthetic, NOT the real ibm01",
        "build": lambda: make_synthetic_graph("synthetic_ibm01_scale", macros=24, std_cells=12_728, seed=1),
    },
}
