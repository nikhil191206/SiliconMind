"""HPWL (half-perimeter wirelength) — TECHNICAL.md Section 1.4.

    HPWL(net) = (max(x_i) - min(x_i)) + (max(y_i) - min(y_i))
                for all pins i in net
    Total HPWL = sum over all nets

Must be implemented identically everywhere it's used in the project — owned
by Person C, imported by everyone else, never reimplemented locally.
"""

from shared.metrics.geometry import node_center
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.placement import PlacementJSON


def compute_hpwl(placement: PlacementJSON, graph: CircuitGraph) -> float:
    """Circuit Graph JSON (Section 3.1) has no per-pin offsets — only
    per-node width/height — so each net's pins are approximated at their
    node's bounding-box center, the standard simplification used whenever
    only cell-level (not pin-level) geometry is available. A net with fewer
    than 2 distinct pin-bearing nodes contributes 0 (no wire to measure)."""
    node_by_id = {n.node_id: n for n in graph.nodes}
    placement_by_id = {p.node_id: p for p in placement.placements}

    total = 0.0
    for hyperedge in graph.hyperedges:
        pin_node_ids = list(hyperedge.sink_nodes)
        if hyperedge.driver_node is not None:
            pin_node_ids.append(hyperedge.driver_node)
        if len(pin_node_ids) < 2:
            continue

        xs = []
        ys = []
        for node_id in pin_node_ids:
            node = node_by_id[node_id]
            entry = placement_by_id[node_id]
            cx, cy = node_center(entry.x, entry.y, node.width, node.height, entry.orientation)
            xs.append(cx)
            ys.append(cy)

        total += (max(xs) - min(xs)) + (max(ys) - min(ys))

    return total
