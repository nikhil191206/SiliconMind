"""DE-HNN netlist encoder — TECHNICAL.md Section 4.A, reproducing Luo et al.,
*DE-HNN* (AISTATS 2024).

Unlike GCN/GAT (graph_utils.star_expansion_edge_index), DE-HNN consumes the
netlist's native hypergraph structure directly: each net is one hyperedge
connecting all its member pins' nodes (driver + sinks), not decomposed into
pairwise edges. This preserves the "all these pins are on the same net"
signal that a clique/star expansion partially discards.

Architecture: 2 rounds of alternating node<->hyperedge updates (a bipartite
node/hyperedge message-passing scheme), hidden dim 256, permutation-
equivariant aggregation per round (sum, or attention-weighted sum — the
project treats this as a tunable ablation per TECHNICAL.md Section 4.A, not
a fixed architectural choice; default is attention-weighted sum here).
"""

from typing import Literal

import torch
import torch.nn.functional as F
from torch import nn
from torch_geometric.utils import scatter, softmax

from modules.encoders.base import NetlistEncoder
from modules.encoders.graph_utils import NUM_NODE_FEATURES, node_features
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.encoder_output import D_GLOBAL, D_NODE, EncoderOutput

HIDDEN_DIM = 256
NUM_ROUNDS = 2
AggregationType = Literal["sum", "attention_weighted_sum"]


def build_incidence(graph: CircuitGraph) -> tuple[torch.Tensor, torch.Tensor, int]:
    """Returns (node_idx, edge_idx, num_edges): parallel long tensors where
    (node_idx[i], edge_idx[i]) is one (node, hyperedge) membership pair, for
    every driver+sink member of every hyperedge in the graph. A hyperedge
    with no members (shouldn't happen per the schema, but defensively
    possible with driver_node=None and empty sink_nodes) contributes no
    pairs and is left as an isolated all-zero hyperedge embedding."""
    node_idx: list[int] = []
    edge_idx: list[int] = []
    for hyperedge in graph.hyperedges:
        members = list(hyperedge.sink_nodes)
        if hyperedge.driver_node is not None:
            members.append(hyperedge.driver_node)
        for node_id in members:
            node_idx.append(node_id)
            edge_idx.append(hyperedge.net_id)

    num_edges = graph.num_hyperedges
    if not node_idx:
        return torch.empty(0, dtype=torch.long), torch.empty(0, dtype=torch.long), num_edges
    return torch.tensor(node_idx, dtype=torch.long), torch.tensor(edge_idx, dtype=torch.long), num_edges


class DEHNNLayer(nn.Module):
    """One round of node -> hyperedge -> node updates."""

    def __init__(self, dim: int = HIDDEN_DIM, aggregation: AggregationType = "attention_weighted_sum"):
        super().__init__()
        self.aggregation = aggregation

        self.msg_node_to_edge = nn.Linear(dim, dim)
        self.attn_node_to_edge = nn.Linear(dim, 1)
        self.edge_update = nn.Sequential(nn.Linear(dim, dim), nn.ReLU(), nn.Linear(dim, dim))

        self.msg_edge_to_node = nn.Linear(dim, dim)
        self.attn_edge_to_node = nn.Linear(dim, 1)
        self.node_update = nn.Sequential(nn.Linear(2 * dim, dim), nn.ReLU(), nn.Linear(dim, dim))

    def _aggregate(
        self,
        messages: torch.Tensor,
        scores: torch.Tensor,
        group_index: torch.Tensor,
        num_groups: int,
    ) -> torch.Tensor:
        if self.aggregation == "sum":
            return scatter(messages, group_index, dim=0, dim_size=num_groups, reduce="sum")
        # attention_weighted_sum: softmax normalizes scores within each group
        # (each hyperedge's members, or each node's incident hyperedges), so
        # the aggregation stays permutation-equivariant in member order.
        alpha = softmax(scores, group_index, num_nodes=num_groups)
        return scatter(alpha.unsqueeze(-1) * messages, group_index, dim=0, dim_size=num_groups, reduce="sum")

    def forward(
        self,
        node_repr: torch.Tensor,
        edge_repr: torch.Tensor,
        node_idx: torch.Tensor,
        edge_idx: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        num_nodes = node_repr.shape[0]
        num_edges = edge_repr.shape[0]

        if node_idx.numel() == 0:
            # No hyperedge memberships at all (degenerate/empty graph): nothing
            # to pass, representations stay as-is.
            return node_repr, edge_repr

        gathered_nodes = node_repr[node_idx]
        edge_scores = self.attn_node_to_edge(gathered_nodes).squeeze(-1)
        edge_messages = self.msg_node_to_edge(gathered_nodes)
        edge_agg = self._aggregate(edge_messages, edge_scores, edge_idx, num_edges)
        new_edge_repr = self.edge_update(edge_agg) + edge_repr  # residual

        gathered_edges = new_edge_repr[edge_idx]
        node_scores = self.attn_edge_to_node(gathered_edges).squeeze(-1)
        node_messages = self.msg_edge_to_node(gathered_edges)
        node_agg = self._aggregate(node_messages, node_scores, node_idx, num_nodes)
        new_node_repr = self.node_update(torch.cat([node_repr, node_agg], dim=-1)) + node_repr  # residual

        return new_node_repr, new_edge_repr


class DEHNNModel(nn.Module):
    def __init__(
        self,
        in_dim: int = NUM_NODE_FEATURES,
        hidden_dim: int = HIDDEN_DIM,
        out_dim: int = D_NODE,
        num_rounds: int = NUM_ROUNDS,
        aggregation: AggregationType = "attention_weighted_sum",
    ):
        super().__init__()
        self.input_proj = nn.Linear(in_dim, hidden_dim)
        self.edge_init = nn.Parameter(torch.zeros(hidden_dim))
        self.layers = nn.ModuleList(DEHNNLayer(hidden_dim, aggregation) for _ in range(num_rounds))
        self.output_proj = nn.Linear(hidden_dim, out_dim)
        self.global_proj = nn.Sequential(
            nn.Linear(out_dim, D_GLOBAL),
            nn.ReLU(),
            nn.Linear(D_GLOBAL, D_GLOBAL),
        )

    def forward(
        self,
        x: torch.Tensor,
        node_idx: torch.Tensor,
        edge_idx: torch.Tensor,
        num_edges: int,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        node_repr = F.relu(self.input_proj(x))
        edge_repr = self.edge_init.unsqueeze(0).expand(num_edges, -1).contiguous()

        for layer in self.layers:
            node_repr, edge_repr = layer(node_repr, edge_repr, node_idx, edge_idx)

        node_embeddings = self.output_proj(node_repr)
        pooled = node_embeddings.mean(dim=0, keepdim=True)
        global_embedding = self.global_proj(pooled).squeeze(0)
        return node_embeddings, global_embedding


class DEHNNEncoder(NetlistEncoder):
    """Wraps DEHNNModel to implement the NetlistEncoder / EncoderOutput contract."""

    def __init__(self, model: DEHNNModel | None = None):
        self.model = model if model is not None else DEHNNModel()

    def encode(self, graph: CircuitGraph) -> EncoderOutput:
        # Move inputs to whatever device self.model's parameters are on --
        # without this, a model moved to GPU (e.g. backend/main.py serving
        # inference on GPU) would crash on the first call: the same class of
        # CPU/GPU tensor-mismatch bug found and fixed in
        # modules/generator/network.py's sinusoidal_time_embedding.
        device = next(self.model.parameters()).device
        x = node_features(graph).to(device)
        node_idx, edge_idx, num_edges = build_incidence(graph)
        node_idx, edge_idx = node_idx.to(device), edge_idx.to(device)

        self.model.eval()
        with torch.no_grad():
            node_embeddings, global_embedding = self.model(x, node_idx, edge_idx, num_edges)

        return EncoderOutput(
            node_embeddings=node_embeddings,
            global_embedding=global_embedding,
            node_id_order=[n.node_id for n in graph.nodes],
        )
