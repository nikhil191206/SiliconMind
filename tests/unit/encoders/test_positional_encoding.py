import torch

from modules.encoders.graph_utils import star_expansion_edge_index
from modules.encoders.positional_encoding import compute_global_pe, compute_local_pe
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.schemas.circuit_graph import CircuitGraph, CircuitNode, Die, NodeType


def test_local_pe_shape_and_degree():
    graph = make_mock_circuit_graph()
    edge_index = star_expansion_edge_index(graph)
    pe = compute_local_pe(graph, edge_index)
    assert pe.shape == (graph.num_nodes, 3)
    # node 0 is driver of net 0 (3 sinks) -> degree 3 in star expansion, in 2 hyperedges (net 0 and net 3)
    assert pe[0, 0].item() == 3.0
    assert pe[0, 1].item() == 2.0


def test_global_pe_shape_small_graph_fallback():
    nodes = [CircuitNode(node_id=0, type=NodeType.STD_CELL, width=1, height=1, pin_count=0)]
    graph = CircuitGraph(design_name="tiny", nodes=nodes, hyperedges=[], die=Die(width=10, height=10))
    edge_index = star_expansion_edge_index(graph)
    pe = compute_global_pe(graph, edge_index, k=8)
    assert pe.shape == (1, 8)
    assert torch.all(pe == 0)


def test_global_pe_shape_normal_graph():
    graph = make_mock_circuit_graph()
    edge_index = star_expansion_edge_index(graph)
    pe = compute_global_pe(graph, edge_index, k=8)
    assert pe.shape == (graph.num_nodes, 8)
    assert not torch.isnan(pe).any()
