"""Person A's own testing contract (TECHNICAL.md Section 4.A).

Asserts an EncoderOutput matches Section 3.2's schema/shape and does nothing
else — this lets encoder work be validated independent of Person B's actual
generator existing.
"""

from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.encoder_output import D_GLOBAL, D_NODE, EncoderOutput


def assert_valid_encoder_output(output: EncoderOutput, graph: CircuitGraph) -> None:
    assert output.node_embeddings.shape == (graph.num_nodes, D_NODE), (
        f"expected node_embeddings shape {(graph.num_nodes, D_NODE)}, got {tuple(output.node_embeddings.shape)}"
    )
    assert output.global_embedding.shape == (D_GLOBAL,), (
        f"expected global_embedding shape {(D_GLOBAL,)}, got {tuple(output.global_embedding.shape)}"
    )
    assert output.node_id_order == [n.node_id for n in graph.nodes], (
        "node_id_order must match Circuit Graph JSON node_id order exactly"
    )
    assert not output.node_embeddings.isnan().any(), "node_embeddings contains NaN"
    assert not output.global_embedding.isnan().any(), "global_embedding contains NaN"
