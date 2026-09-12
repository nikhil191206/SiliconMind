"""Shared conversion from Circuit Graph JSON (Section 3.1) to tensor form.

CircuitGraph is a directed hypergraph (each hyperedge has one optional driver
and many sinks). GCN/GAT are pairwise message-passing nets, so they consume a
star-expansion of each hyperedge: driver -> sink and sink -> driver directed
edges (undirected connectivity, direction-tagged) for every driver/sink pair
in the net. Primary-input nets (driver_node is None) contribute no edges but
their sink nodes still exist as graph nodes.

DE-HNN and DeepGate4 consume the hypergraph structure directly (see de_hnn.py
/ deepgate4.py) and do NOT use this star expansion — this module is only for
the two pairwise-message-passing baselines.
"""

import torch

from shared.schemas.circuit_graph import CircuitGraph, NodeType

NUM_NODE_FEATURES = 4  # [width, height, pin_count, is_macro]


def node_features(graph: CircuitGraph) -> torch.Tensor:
    """[num_nodes, NUM_NODE_FEATURES] float tensor: width, height, pin_count, is_macro."""
    rows = []
    for node in graph.nodes:
        is_macro = 1.0 if node.type == NodeType.MACRO else 0.0
        rows.append([node.width, node.height, float(node.pin_count), is_macro])
    return torch.tensor(rows, dtype=torch.float32)


def star_expansion_edge_index(graph: CircuitGraph) -> torch.Tensor:
    """[2, num_edges] long tensor of directed driver<->sink pairs, one pair
    per (driver, sink) combination in each hyperedge, both directions."""
    src, dst = [], []
    for hyperedge in graph.hyperedges:
        if hyperedge.driver_node is None:
            continue
        for sink in hyperedge.sink_nodes:
            src.append(hyperedge.driver_node)
            dst.append(sink)
            src.append(sink)
            dst.append(hyperedge.driver_node)

    if not src:
        # No edges (e.g. all-primary-input mock graph fragment): PyG conv
        # layers accept an empty [2, 0] edge_index.
        return torch.empty((2, 0), dtype=torch.long)

    return torch.tensor([src, dst], dtype=torch.long)
