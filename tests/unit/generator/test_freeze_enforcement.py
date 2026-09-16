"""TECHNICAL.md Section 4.B: "a test in tests/unit/generator/ that calls
generate() with a non-empty frozen_placements, then asserts every frozen
node's output coordinate is bit-identical to its input coordinate. This
test must exist before this module is considered 'done'." This is that
test.
"""

from modules.generator.generator import PlacementGenerator
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_encoder_output import make_mock_encoder_output
from shared.schemas.placement import Orientation, PlacementEntry


def test_frozen_nodes_are_bit_identical_to_input():
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)
    generator = PlacementGenerator()

    frozen = [
        PlacementEntry(node_id=0, x=12.5, y=30.25, orientation=Orientation.N),
        PlacementEntry(node_id=3, x=55.0, y=10.0, orientation=Orientation.FE),
    ]

    result = generator.generate(encoder_output, graph, frozen_placements=frozen, seed=0)
    result_by_id = {p.node_id: p for p in result.placements}

    for fp in frozen:
        out = result_by_id[fp.node_id]
        assert out.x == fp.x
        assert out.y == fp.y
        assert out.orientation == fp.orientation


def test_frozen_nodes_stay_bit_identical_with_guidance_active():
    """The freeze guarantee must hold even when guidance terms are actively
    pushing on the tensor every ODE step (Section 1.7: index-level
    exclusion, not "the loss/guidance keeps it stable")."""
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)
    generator = PlacementGenerator()

    from modules.generator.types import GuidanceConfig

    frozen = [PlacementEntry(node_id=1, x=40.0, y=60.0, orientation=Orientation.S)]
    guidance = GuidanceConfig(legality_weight=5.0, wirelength_weight=5.0, congestion_weight=5.0)

    result = generator.generate(
        encoder_output, graph, frozen_placements=frozen, guidance_terms=guidance, seed=0
    )
    out = next(p for p in result.placements if p.node_id == 1)
    assert out.x == 40.0
    assert out.y == 60.0
    assert out.orientation == Orientation.S


def test_all_nodes_frozen_reproduces_input_exactly():
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)
    generator = PlacementGenerator()

    frozen = [
        PlacementEntry(node_id=n.node_id, x=float(n.node_id) * 2.0, y=float(n.node_id) * 3.0, orientation=Orientation.N)
        for n in graph.nodes
    ]

    result = generator.generate(encoder_output, graph, frozen_placements=frozen, seed=0)
    result_by_id = {p.node_id: p for p in result.placements}
    for fp in frozen:
        out = result_by_id[fp.node_id]
        assert out.x == fp.x
        assert out.y == fp.y
