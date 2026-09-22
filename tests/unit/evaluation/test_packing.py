from modules.evaluation.packing import grid_pack
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.metrics.legality import compute_legality_violations
from shared.schemas.placement import GenerationMetadata, PlacementJSON


def test_grid_pack_covers_every_node_exactly_once():
    graph = make_mock_circuit_graph()
    entries = grid_pack(graph.nodes, graph.die)
    assert {e.node_id for e in entries} == {n.node_id for n in graph.nodes}
    assert len(entries) == len(graph.nodes)


def test_grid_pack_produces_no_macro_overlaps():
    graph = make_mock_circuit_graph()
    entries = grid_pack(graph.nodes, graph.die)
    placement = PlacementJSON(
        design_name=graph.design_name,
        placements=entries,
        generation_metadata=GenerationMetadata(model_variant="grid_pack_test", seed=0, is_legalized=False),
    )
    assert compute_legality_violations(placement, graph) == 0


def test_grid_pack_on_subset_of_nodes():
    graph = make_mock_circuit_graph()
    subset = [n for n in graph.nodes if n.node_id in (2, 3, 4)]
    entries = grid_pack(subset, graph.die)
    assert {e.node_id for e in entries} == {2, 3, 4}
