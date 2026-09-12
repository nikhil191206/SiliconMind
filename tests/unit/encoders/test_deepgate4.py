import copy

import torch

from modules.encoders.deepgate4 import DeepGate4Encoder, HistoricalEmbeddingCache
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_generator_consumer import assert_valid_encoder_output
from shared.schemas.circuit_graph import CircuitGraph, CircuitNode, Die, NodeType


def test_deepgate4_encoder_output_matches_schema():
    graph = make_mock_circuit_graph()
    output = DeepGate4Encoder().encode(graph)
    assert_valid_encoder_output(output, graph)


def test_deepgate4_encoder_does_not_mutate_input_graph():
    graph = make_mock_circuit_graph()
    graph_before = copy.deepcopy(graph)
    DeepGate4Encoder().encode(graph)
    assert graph == graph_before


def test_deepgate4_handles_single_node_graph():
    nodes = [CircuitNode(node_id=0, type=NodeType.STD_CELL, width=1, height=1, pin_count=0)]
    graph = CircuitGraph(design_name="single", nodes=nodes, hyperedges=[], die=Die(width=10, height=10))
    output = DeepGate4Encoder().encode(graph)
    assert_valid_encoder_output(output, graph)


def test_deepgate4_first_call_ignores_active_node_ids_when_cache_empty():
    """No historical embeddings exist yet, so even a restrictive active set
    must fall back to a full first pass rather than silently returning
    uninitialized data for the rest of the graph."""
    graph = make_mock_circuit_graph()
    encoder = DeepGate4Encoder()
    output = encoder.encode(graph, active_node_ids={0})
    assert_valid_encoder_output(output, graph)
    assert not output.node_embeddings.isnan().any()


def test_deepgate4_historical_reuse_is_bit_identical_for_inactive_nodes():
    """This is the direct, code-level check on the sub-linear-memory /
    historical-embedding-reuse guarantee (TECHNICAL.md Section 4.A): after a
    full pass populates the cache, re-encoding with a restricted active set
    must leave every non-active node's embedding exactly unchanged, and must
    change at least the active nodes' embeddings."""
    graph = make_mock_circuit_graph()
    encoder = DeepGate4Encoder()

    full_output = encoder.encode(graph)
    active_ids = {2, 3}
    incremental_output = encoder.encode(graph, active_node_ids=active_ids)

    for i, node_id in enumerate(incremental_output.node_id_order):
        if node_id not in active_ids:
            assert torch.equal(incremental_output.node_embeddings[i], full_output.node_embeddings[i]), (
                f"node {node_id} was supposed to be frozen via historical reuse but changed"
            )

    changed = any(
        not torch.equal(incremental_output.node_embeddings[i], full_output.node_embeddings[i])
        for i, node_id in enumerate(incremental_output.node_id_order)
        if node_id in active_ids
    )
    assert changed, "active nodes should have been recomputed, not silently reused"


def test_historical_embedding_cache_get_update_clear():
    cache = HistoricalEmbeddingCache()
    assert cache.get("design", 0) is None

    embedding = torch.randn(256)
    cache.update("design", 0, embedding)
    assert torch.equal(cache.get("design", 0), embedding)

    # mutating the original tensor after caching must not affect the cached copy
    embedding[0] = 999.0
    assert not torch.equal(cache.get("design", 0), embedding)

    cache.clear("design")
    assert cache.get("design", 0) is None


def test_deepgate4_deterministic_in_eval_mode():
    graph = make_mock_circuit_graph()
    encoder = DeepGate4Encoder()
    out1 = encoder.encode(graph)
    encoder2 = DeepGate4Encoder(model=encoder.model)
    out2 = encoder2.encode(graph)
    assert torch.equal(out1.node_embeddings, out2.node_embeddings)
