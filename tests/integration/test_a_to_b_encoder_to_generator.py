"""A -> B second-wave integration (INSTRUCTIONS.md Section 1.2, first bullet):
feed a REAL (not mock) EncoderOutput from Person A's encoders into Person B's
REAL PlacementGenerator, confirm the schema handoff holds with two real
implementations instead of one real + one mock.

Covers all four of A's encoders, since each produces EncoderOutput via a
different internal path (star-expansion vs. native hypergraph, historical
cache or not) and B's generator must accept all of them identically —
that's the whole point of Section 3.2 being a fixed contract.
"""

import pytest

from modules.encoders.base import NetlistEncoder
from modules.encoders.deepgate4 import DeepGate4Encoder
from modules.encoders.de_hnn import DEHNNEncoder
from modules.encoders.gat import GATEncoder
from modules.encoders.gcn import GCNEncoder
from modules.generator.generator import PlacementGenerator
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.schemas.placement import PlacementJSON

ALL_ENCODERS: list[NetlistEncoder] = [GCNEncoder(), GATEncoder(), DEHNNEncoder(), DeepGate4Encoder()]


@pytest.mark.parametrize("encoder", ALL_ENCODERS, ids=lambda e: type(e).__name__)
def test_real_encoder_output_feeds_real_generator(encoder: NetlistEncoder):
    graph = make_mock_circuit_graph()

    encoder_output = encoder.encode(graph)
    placement = PlacementGenerator().generate(encoder_output, graph, seed=0)

    assert isinstance(placement, PlacementJSON)
    assert placement.design_name == graph.design_name
    assert {p.node_id for p in placement.placements} == {n.node_id for n in graph.nodes}
    assert placement.generation_metadata.is_legalized is False  # not yet through Person C
    for entry in placement.placements:
        assert 0.0 <= entry.x <= graph.die.width
        assert 0.0 <= entry.y <= graph.die.height


def test_generator_rejects_encoder_output_with_wrong_node_order():
    """The Section 3.2 contract requires node_id_order to match the graph's
    node order exactly — B's generate() enforces this defensively rather
    than silently misaligning embeddings to the wrong nodes."""
    graph = make_mock_circuit_graph()
    encoder_output = GCNEncoder().encode(graph)
    encoder_output.node_id_order = list(reversed(encoder_output.node_id_order))

    with pytest.raises(ValueError, match="node_id_order"):
        PlacementGenerator().generate(encoder_output, graph, seed=0)
