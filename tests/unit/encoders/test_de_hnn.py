import copy

import torch

from modules.encoders.de_hnn import DEHNNEncoder, DEHNNModel, build_incidence
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_generator_consumer import assert_valid_encoder_output
from shared.schemas.circuit_graph import CircuitGraph, CircuitNode, Die, NodeType


def test_build_incidence_includes_driver_and_sinks_per_net():
    graph = make_mock_circuit_graph()
    node_idx, edge_idx, num_edges = build_incidence(graph)
    assert num_edges == graph.num_hyperedges

    pairs = set(zip(node_idx.tolist(), edge_idx.tolist()))
    # net 0: driver=0, sinks=[2,3,4] -> members {0,2,3,4} all in hyperedge 0
    for member in (0, 2, 3, 4):
        assert (member, 0) in pairs
    # net 3: driver=None, sinks=[0,1] -> members {0,1}, no driver contribution needed
    assert (0, 3) in pairs
    assert (1, 3) in pairs


def test_build_incidence_handles_zero_hyperedges():
    nodes = [CircuitNode(node_id=0, type=NodeType.STD_CELL, width=1, height=1, pin_count=0)]
    graph = CircuitGraph(design_name="no_edges", nodes=nodes, hyperedges=[], die=Die(width=10, height=10))
    node_idx, edge_idx, num_edges = build_incidence(graph)
    assert num_edges == 0
    assert node_idx.numel() == 0
    assert edge_idx.numel() == 0


def test_de_hnn_encoder_output_matches_schema_attention_and_sum_aggregation():
    graph = make_mock_circuit_graph()
    for aggregation in ("attention_weighted_sum", "sum"):
        encoder = DEHNNEncoder(DEHNNModel(aggregation=aggregation))
        output = encoder.encode(graph)
        assert_valid_encoder_output(output, graph)


def test_de_hnn_encoder_handles_zero_hyperedge_graph():
    nodes = [CircuitNode(node_id=0, type=NodeType.STD_CELL, width=1, height=1, pin_count=0)]
    graph = CircuitGraph(design_name="no_edges", nodes=nodes, hyperedges=[], die=Die(width=10, height=10))
    output = DEHNNEncoder().encode(graph)
    assert_valid_encoder_output(output, graph)


def test_de_hnn_encoder_does_not_mutate_input_graph():
    graph = make_mock_circuit_graph()
    graph_before = copy.deepcopy(graph)
    DEHNNEncoder().encode(graph)
    assert graph == graph_before


def test_de_hnn_encoder_deterministic_in_eval_mode():
    graph = make_mock_circuit_graph()
    encoder = DEHNNEncoder()
    out1 = encoder.encode(graph)
    out2 = encoder.encode(graph)
    assert torch.equal(out1.node_embeddings, out2.node_embeddings)
    assert torch.equal(out1.global_embedding, out2.global_embedding)


def test_de_hnn_aggregation_is_permutation_equivariant_in_sink_order():
    """Reordering a hyperedge's sink_nodes list must not change the resulting
    node embeddings — sum/attention-weighted-sum aggregation is required to
    be permutation-equivariant over hyperedge membership (TECHNICAL.md
    Section 4.A)."""
    nodes = [
        CircuitNode(node_id=i, type=NodeType.STD_CELL, width=1, height=1, pin_count=1) for i in range(4)
    ]
    from shared.schemas.circuit_graph import CircuitHyperedge

    graph_a = CircuitGraph(
        design_name="perm_test",
        nodes=nodes,
        hyperedges=[CircuitHyperedge(net_id=0, driver_node=0, sink_nodes=[1, 2, 3])],
        die=Die(width=10, height=10),
    )
    graph_b = CircuitGraph(
        design_name="perm_test",
        nodes=nodes,
        hyperedges=[CircuitHyperedge(net_id=0, driver_node=0, sink_nodes=[3, 2, 1])],
        die=Die(width=10, height=10),
    )

    model = DEHNNModel()
    encoder = DEHNNEncoder(model)
    out_a = encoder.encode(graph_a)
    out_b = encoder.encode(graph_b)
    assert torch.allclose(out_a.node_embeddings, out_b.node_embeddings, atol=1e-6)
