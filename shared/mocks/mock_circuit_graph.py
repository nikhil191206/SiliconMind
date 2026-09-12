"""Deterministic toy CircuitGraph for development ahead of real netlist parsing.

INSTRUCTIONS.md Step 0.4. Hand-chosen, fixed values — not a training dataset,
just a schema-valid fixture every module can build against.
"""

from shared.schemas.circuit_graph import CircuitGraph, CircuitHyperedge, CircuitNode, Die, NodeType


def make_mock_circuit_graph() -> CircuitGraph:
    """8 nodes (2 macros, 6 std cells), 4 hyperedges, on a 100x100 die."""
    nodes = [
        CircuitNode(node_id=0, type=NodeType.MACRO, width=20.0, height=15.0, pin_count=8),
        CircuitNode(node_id=1, type=NodeType.MACRO, width=18.0, height=12.0, pin_count=6),
        CircuitNode(node_id=2, type=NodeType.STD_CELL, width=1.0, height=1.0, pin_count=3),
        CircuitNode(node_id=3, type=NodeType.STD_CELL, width=1.0, height=1.0, pin_count=3),
        CircuitNode(node_id=4, type=NodeType.STD_CELL, width=1.0, height=1.0, pin_count=2),
        CircuitNode(node_id=5, type=NodeType.STD_CELL, width=1.0, height=1.0, pin_count=3),
        CircuitNode(node_id=6, type=NodeType.STD_CELL, width=1.0, height=1.0, pin_count=2),
        CircuitNode(node_id=7, type=NodeType.STD_CELL, width=1.0, height=1.0, pin_count=4),
    ]
    hyperedges = [
        CircuitHyperedge(net_id=0, driver_node=0, sink_nodes=[2, 3, 4]),
        CircuitHyperedge(net_id=1, driver_node=2, sink_nodes=[5]),
        CircuitHyperedge(net_id=2, driver_node=1, sink_nodes=[6, 7]),
        CircuitHyperedge(net_id=3, driver_node=None, sink_nodes=[0, 1]),
    ]
    return CircuitGraph(
        design_name="mock_toy_design",
        nodes=nodes,
        hyperedges=hyperedges,
        die=Die(width=100.0, height=100.0),
    )
