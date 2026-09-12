"""Random tensor matching EncoderOutput's shape (Section 3.2 defaults).

Lets Person B build the generator before Person A's real encoders exist.
"""

import torch

from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.encoder_output import D_GLOBAL, D_NODE, EncoderOutput


def make_mock_encoder_output(graph: CircuitGraph, seed: int = 0) -> EncoderOutput:
    generator = torch.Generator().manual_seed(seed)
    num_nodes = graph.num_nodes
    node_embeddings = torch.randn(num_nodes, D_NODE, generator=generator)
    global_embedding = torch.randn(D_GLOBAL, generator=generator)
    node_id_order = [n.node_id for n in graph.nodes]
    return EncoderOutput(
        node_embeddings=node_embeddings,
        global_embedding=global_embedding,
        node_id_order=node_id_order,
    )
