import copy

from modules.encoders.gat import GATEncoder
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_generator_consumer import assert_valid_encoder_output


def test_gat_encoder_output_matches_schema():
    graph = make_mock_circuit_graph()
    encoder = GATEncoder()
    output = encoder.encode(graph)
    assert_valid_encoder_output(output, graph)


def test_gat_encoder_does_not_mutate_input_graph():
    graph = make_mock_circuit_graph()
    graph_before = copy.deepcopy(graph)
    GATEncoder().encode(graph)
    assert graph == graph_before


def test_gat_encoder_deterministic_in_eval_mode():
    graph = make_mock_circuit_graph()
    encoder = GATEncoder()
    out1 = encoder.encode(graph)
    out2 = encoder.encode(graph)
    assert (out1.node_embeddings == out2.node_embeddings).all()
    assert (out1.global_embedding == out2.global_embedding).all()
