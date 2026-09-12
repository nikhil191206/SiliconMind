import torch

from modules.encoders.graph_utils import NUM_NODE_FEATURES, node_features, star_expansion_edge_index
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.schemas.circuit_graph import CircuitGraph, CircuitHyperedge, CircuitNode, Die, NodeType


def test_node_features_shape_and_values():
    graph = make_mock_circuit_graph()
    feats = node_features(graph)
    assert feats.shape == (graph.num_nodes, NUM_NODE_FEATURES)
    # node 0 is a MACRO with width=20, height=15, pin_count=8 -> is_macro=1.0
    assert feats[0].tolist() == [20.0, 15.0, 8.0, 1.0]
    # node 2 is a STD_CELL -> is_macro=0.0
    assert feats[2, 3].item() == 0.0


def test_star_expansion_produces_bidirectional_driver_sink_pairs():
    graph = make_mock_circuit_graph()
    edge_index = star_expansion_edge_index(graph)
    assert edge_index.shape[0] == 2
    edges = set(zip(edge_index[0].tolist(), edge_index[1].tolist()))
    # net 0: driver=0, sinks=[2,3,4]
    for sink in (2, 3, 4):
        assert (0, sink) in edges
        assert (sink, 0) in edges
    # net 3 has driver_node=None (primary input) -> contributes no edges at all
    assert (0, 1) not in edges
    assert (1, 0) not in edges


def test_star_expansion_skips_primary_input_nets():
    nodes = [
        CircuitNode(node_id=0, type=NodeType.STD_CELL, width=1, height=1, pin_count=1),
        CircuitNode(node_id=1, type=NodeType.STD_CELL, width=1, height=1, pin_count=1),
    ]
    hyperedges = [CircuitHyperedge(net_id=0, driver_node=None, sink_nodes=[0, 1])]
    graph = CircuitGraph(design_name="pi_only", nodes=nodes, hyperedges=hyperedges, die=Die(width=10, height=10))

    edge_index = star_expansion_edge_index(graph)
    assert edge_index.shape == (2, 0)


def test_star_expansion_empty_graph_gives_empty_edge_index():
    nodes = [CircuitNode(node_id=0, type=NodeType.STD_CELL, width=1, height=1, pin_count=0)]
    graph = CircuitGraph(design_name="single_node", nodes=nodes, hyperedges=[], die=Die(width=10, height=10))
    edge_index = star_expansion_edge_index(graph)
    assert edge_index.dtype == torch.long
    assert edge_index.shape == (2, 0)
