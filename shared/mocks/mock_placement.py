"""Fixed, schema-valid PlacementJSON for the mock circuit graph.

A simple non-overlapping grid layout — doesn't need to be good, only
schema-valid and legal, so Person C and D can develop against it before
Person B's real generator exists.
"""

from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.placement import GenerationMetadata, Orientation, PlacementEntry, PlacementJSON


def make_mock_placement(graph: CircuitGraph, seed: int = 0) -> PlacementJSON:
    placements = []
    cursor_x, cursor_y = 0.0, 0.0
    row_height = 0.0
    for node in graph.nodes:
        if cursor_x + node.width > graph.die.width:
            cursor_x = 0.0
            cursor_y += row_height
            row_height = 0.0
        placements.append(
            PlacementEntry(node_id=node.node_id, x=cursor_x, y=cursor_y, orientation=Orientation.N)
        )
        cursor_x += node.width
        row_height = max(row_height, node.height)

    return PlacementJSON(
        design_name=graph.design_name,
        placements=placements,
        generation_metadata=GenerationMetadata(
            model_variant="mock_grid_v1", seed=seed, is_legalized=True
        ),
    )
