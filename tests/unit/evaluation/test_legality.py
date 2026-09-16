"""Hand-computed legality fixtures — TECHNICAL.md Section 1.4: number of
macro pairs with overlapping bounding boxes + number of macros with any
portion outside the die boundary.
"""

from shared.metrics.legality import compute_legality_violations
from shared.schemas.circuit_graph import CircuitGraph, CircuitHyperedge, CircuitNode, Die, NodeType
from shared.schemas.placement import GenerationMetadata, Orientation, PlacementEntry, PlacementJSON


def _placement(entries: list[PlacementEntry]) -> PlacementJSON:
    return PlacementJSON(
        design_name="legality_toy",
        placements=entries,
        generation_metadata=GenerationMetadata(model_variant="toy", seed=0, is_legalized=False),
    )


def test_overlapping_macro_pair_counted_but_overlapping_std_cells_are_not():
    graph = CircuitGraph(
        design_name="legality_toy",
        nodes=[
            CircuitNode(node_id=0, type=NodeType.MACRO, width=2.0, height=2.0, pin_count=1),
            CircuitNode(node_id=1, type=NodeType.MACRO, width=2.0, height=2.0, pin_count=1),
            CircuitNode(node_id=2, type=NodeType.STD_CELL, width=1.0, height=1.0, pin_count=1),
            CircuitNode(node_id=3, type=NodeType.STD_CELL, width=1.0, height=1.0, pin_count=1),
        ],
        hyperedges=[],
        die=Die(width=100.0, height=100.0),
    )
    placement = _placement(
        [
            PlacementEntry(node_id=0, x=0.0, y=0.0, orientation=Orientation.N),
            PlacementEntry(node_id=1, x=1.0, y=1.0, orientation=Orientation.N),  # overlaps node 0
            PlacementEntry(node_id=2, x=5.0, y=5.0, orientation=Orientation.N),
            PlacementEntry(node_id=3, x=5.0, y=5.0, orientation=Orientation.N),  # exactly overlaps node 2, ignored (std cell)
        ]
    )
    assert compute_legality_violations(placement, graph) == 1


def test_abutting_macros_are_legal():
    graph = CircuitGraph(
        design_name="legality_toy",
        nodes=[
            CircuitNode(node_id=0, type=NodeType.MACRO, width=2.0, height=2.0, pin_count=1),
            CircuitNode(node_id=1, type=NodeType.MACRO, width=2.0, height=2.0, pin_count=1),
        ],
        hyperedges=[],
        die=Die(width=100.0, height=100.0),
    )
    placement = _placement(
        [
            PlacementEntry(node_id=0, x=0.0, y=0.0, orientation=Orientation.N),
            PlacementEntry(node_id=1, x=2.0, y=0.0, orientation=Orientation.N),  # shares edge x=2, zero-area overlap
        ]
    )
    assert compute_legality_violations(placement, graph) == 0


def test_macro_outside_die_boundary_counted():
    graph = CircuitGraph(
        design_name="legality_toy",
        nodes=[CircuitNode(node_id=0, type=NodeType.MACRO, width=2.0, height=2.0, pin_count=1)],
        hyperedges=[],
        die=Die(width=10.0, height=10.0),
    )
    placement = _placement([PlacementEntry(node_id=0, x=9.0, y=0.0, orientation=Orientation.N)])  # x_max=11 > 10
    assert compute_legality_violations(placement, graph) == 1


def test_boundary_check_uses_orientation_aware_bounding_box():
    # 8x3 macro in a 10x5 die: legal upright (8<=10, 3<=5), illegal rotated
    # 90 degrees (eff. 3x8, since 8 > die.height=5) — proves the boundary
    # check applies effective_dims, not the raw authored width/height.
    graph = CircuitGraph(
        design_name="legality_toy",
        nodes=[CircuitNode(node_id=0, type=NodeType.MACRO, width=8.0, height=3.0, pin_count=1)],
        hyperedges=[],
        die=Die(width=10.0, height=5.0),
    )
    upright = _placement([PlacementEntry(node_id=0, x=0.0, y=0.0, orientation=Orientation.N)])
    rotated = _placement([PlacementEntry(node_id=0, x=0.0, y=0.0, orientation=Orientation.E)])

    assert compute_legality_violations(upright, graph) == 0
    assert compute_legality_violations(rotated, graph) == 1
