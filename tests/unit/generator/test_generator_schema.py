from modules.generator.generator import PlacementGenerator
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_encoder_output import make_mock_encoder_output
from shared.mocks.mock_legalizer import mock_legalize_and_score
from shared.schemas.placement import PlacementJSON


def test_generate_matches_placement_schema():
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)
    generator = PlacementGenerator()

    result = generator.generate(encoder_output, graph, seed=0)

    assert isinstance(result, PlacementJSON)
    assert result.design_name == graph.design_name
    assert {p.node_id for p in result.placements} == {n.node_id for n in graph.nodes}
    assert result.generation_metadata.is_legalized is False
    assert result.generation_metadata.seed == 0
    assert result.generation_metadata.model_variant


def test_generate_output_within_die_bounds():
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=1)
    generator = PlacementGenerator()

    result = generator.generate(encoder_output, graph, seed=1)

    for p in result.placements:
        assert 0.0 <= p.x <= graph.die.width
        assert 0.0 <= p.y <= graph.die.height


def test_generate_is_deterministic_given_seed():
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)
    generator = PlacementGenerator()

    r1 = generator.generate(encoder_output, graph, seed=42)
    r2 = generator.generate(encoder_output, graph, seed=42)

    p1_by_id = {p.node_id: p for p in r1.placements}
    p2_by_id = {p.node_id: p for p in r2.placements}
    for node_id in p1_by_id:
        assert p1_by_id[node_id].x == p2_by_id[node_id].x
        assert p1_by_id[node_id].y == p2_by_id[node_id].y


def test_generate_rejects_mismatched_node_id_order():
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)
    encoder_output.node_id_order = list(reversed(encoder_output.node_id_order))
    generator = PlacementGenerator()

    try:
        generator.generate(encoder_output, graph, seed=0)
        assert False, "expected ValueError for mismatched node_id_order"
    except ValueError:
        pass


def test_generate_output_feeds_mock_legalizer():
    """Second-wave integration check (INSTRUCTIONS.md 1.2): B's real output
    into C's mock legalizer, on the mock circuit graph."""
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)
    generator = PlacementGenerator()

    result = generator.generate(encoder_output, graph, seed=0)
    legalized, metrics = mock_legalize_and_score(result)

    assert legalized.generation_metadata.is_legalized is True
    assert metrics.legality_violations == 0
