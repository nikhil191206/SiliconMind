"""GCN netlist encoder — TECHNICAL.md Section 4.A.

3 message-passing layers (GCNConv), hidden dim 256, ReLU, dropout 0.1.
Baseline encoder for the comparative benchmark (Section 1.9.3) against
GAT / DE-HNN / DeepGate4.
"""

import torch
import torch.nn.functional as F
from torch import nn
from torch_geometric.nn import GCNConv, global_mean_pool

from modules.encoders.base import NetlistEncoder
from modules.encoders.graph_utils import NUM_NODE_FEATURES, node_features, star_expansion_edge_index
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.encoder_output import D_GLOBAL, D_NODE, EncoderOutput

HIDDEN_DIM = 256
NUM_LAYERS = 3
DROPOUT = 0.1


class GCNEncoderModel(nn.Module):
    def __init__(
        self,
        in_dim: int = NUM_NODE_FEATURES,
        hidden_dim: int = HIDDEN_DIM,
        out_dim: int = D_NODE,
        num_layers: int = NUM_LAYERS,
        dropout: float = DROPOUT,
    ):
        super().__init__()
        assert num_layers >= 2, "need at least an input and output conv layer"
        self.dropout = dropout

        dims = [in_dim] + [hidden_dim] * (num_layers - 1) + [out_dim]
        self.convs = nn.ModuleList(
            GCNConv(dims[i], dims[i + 1]) for i in range(num_layers)
        )
        self.global_proj = nn.Sequential(
            nn.Linear(out_dim, D_GLOBAL),
            nn.ReLU(),
            nn.Linear(D_GLOBAL, D_GLOBAL),
        )

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = x
        for i, conv in enumerate(self.convs):
            h = conv(h, edge_index)
            if i < len(self.convs) - 1:
                h = F.relu(h)
                h = F.dropout(h, p=self.dropout, training=self.training)

        batch = torch.zeros(h.shape[0], dtype=torch.long, device=h.device)
        pooled = global_mean_pool(h, batch)  # [1, out_dim]
        global_embedding = self.global_proj(pooled).squeeze(0)  # [D_GLOBAL]
        return h, global_embedding


class GCNEncoder(NetlistEncoder):
    """Wraps GCNEncoderModel to implement the NetlistEncoder / EncoderOutput contract."""

    def __init__(self, model: GCNEncoderModel | None = None):
        self.model = model if model is not None else GCNEncoderModel()

    def encode(self, graph: CircuitGraph) -> EncoderOutput:
        x = node_features(graph)
        edge_index = star_expansion_edge_index(graph)

        self.model.eval()
        with torch.no_grad():
            node_embeddings, global_embedding = self.model(x, edge_index)

        return EncoderOutput(
            node_embeddings=node_embeddings,
            global_embedding=global_embedding,
            node_id_order=[n.node_id for n in graph.nodes],
        )
