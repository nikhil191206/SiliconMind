"""Hand-computed HPWL fixtures — INSTRUCTIONS.md Step 0.5: a toy placement
worked out on paper first, then asserted against the function. This is
ordinary unit-testing practice, not the "synthetic training data" Section
1.14/1.16 prohibits (see INSTRUCTIONS.md Step 0.5's explicit note on that
distinction).
"""

from shared.metrics.hpwl import compute_hpwl
from shared.schemas.circuit_graph import CircuitGraph, CircuitHyperedge, CircuitNode, Die, NodeType
from shared.schemas.placement import GenerationMetadata, Orientation, PlacementEntry, PlacementJSON

# Three 2x2 std cells, centers at (1,1), (11,1), (1,11) once placed below.
_NODES = [
    CircuitNode(node_id=0, type=NodeType.STD_CELL, width=2.0, height=2.0, pin_count=2),
    CircuitNode(node_id=1, type=NodeType.STD_CELL, width=2.0, height=2.0, pin_count=2),
    CircuitNode(node_id=2, type=NodeType.STD_CELL, width=2.0, height=2.0, pin_count=2),
]


def _graph(hyperedges: list[CircuitHyperedge]) -> CircuitGraph:
    return CircuitGraph(design_name="hpwl_toy", nodes=_NODES, hyperedges=hyperedges, die=Die(width=100.0, height=100.0))


def _placement() -> PlacementJSON:
    return PlacementJSON(
        design_name="hpwl_toy",
        placements=[
            PlacementEntry(node_id=0, x=0.0, y=0.0, orientation=Orientation.N),
            PlacementEntry(node_id=1, x=10.0, y=0.0, orientation=Orientation.N),
            PlacementEntry(node_id=2, x=0.0, y=10.0, orientation=Orientation.N),
        ],
        generation_metadata=GenerationMetadata(model_variant="toy", seed=0, is_legalized=True),
    )


def test_hpwl_three_pin_net_hand_computed():
    # Centers: (1,1), (11,1), (1,11) -> dx = 11-1 = 10, dy = 11-1 = 10 -> HPWL = 20.
    graph = _graph([CircuitHyperedge(net_id=0, driver_node=0, sink_nodes=[1, 2])])
    assert compute_hpwl(_placement(), graph) == 20.0


def test_hpwl_two_pin_net_hand_computed():
    # Centers: (1,1), (11,1) -> dx = 10, dy = 0 -> HPWL = 10.
    graph = _graph([CircuitHyperedge(net_id=0, driver_node=None, sink_nodes=[0, 1])])
    assert compute_hpwl(_placement(), graph) == 10.0


def test_hpwl_single_pin_net_contributes_zero():
    graph = _graph([CircuitHyperedge(net_id=0, driver_node=None, sink_nodes=[2])])
    assert compute_hpwl(_placement(), graph) == 0.0


def test_hpwl_sums_across_multiple_nets():
    graph = _graph(
        [
            CircuitHyperedge(net_id=0, driver_node=0, sink_nodes=[1, 2]),  # 20.0
            CircuitHyperedge(net_id=1, driver_node=None, sink_nodes=[0, 1]),  # 10.0
            CircuitHyperedge(net_id=2, driver_node=None, sink_nodes=[2]),  # 0.0
        ]
    )
    assert compute_hpwl(_placement(), graph) == 30.0
