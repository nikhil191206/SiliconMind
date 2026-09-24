"""DeepGate4 netlist encoder — TECHNICAL.md Section 4.A, reproducing the
*DeepGate4* (2025) approach: a GAT-based sparse transformer with a
sub-linear-memory update strategy (historical embedding reuse across
iterations) and global + local structural positional encodings.

Two things distinguish this from GCN/GAT/DE-HNN here:

1. **Sparse attention via TransformerConv** over the star-expansion graph
   (graph_utils.star_expansion_edge_index) instead of dense N x N attention —
   each node only attends to nodes it shares a net with, which is what makes
   this "sparse" rather than a full transformer.
2. **Historical embedding reuse**: `HistoricalEmbeddingCache` remembers each
   node's last-computed embedding, keyed by (design_name, node_id). A caller
   doing an incremental re-encode (e.g. after a small NL edit touches only a
   few nodes, per Section 1.7/3.4) can pass `active_node_ids` — nodes outside
   that set reuse their cached embedding bit-for-bit instead of being
   recomputed, and the sparse-attention layers only pass messages into nodes
   inside the active set, so per-call compute scales with the active set
   size rather than the whole chip. This is a simplified reproduction of the
   paper's historical-embedding idea (GNNAutoScale-style), not literal
   paper-scale KV memory management, and is flagged as such here rather than
   presented as more than it is.
"""

from dataclasses import dataclass, field

import torch
import torch.nn.functional as F
from torch import nn
from torch_geometric.nn import TransformerConv

from modules.encoders.base import NetlistEncoder
from modules.encoders.graph_utils import NUM_NODE_FEATURES, node_features, star_expansion_edge_index
from modules.encoders.positional_encoding import LOCAL_PE_DIM, compute_global_pe, compute_local_pe
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.encoder_output import D_GLOBAL, D_NODE, EncoderOutput

HIDDEN_DIM = D_NODE  # kept equal to D_NODE so cached historical embeddings can be spliced back in directly
NUM_LAYERS = 3
NUM_HEADS = 4
GLOBAL_PE_DIM = 8
DROPOUT = 0.1


@dataclass
class HistoricalEmbeddingCache:
    """Per-design, per-node embedding cache enabling the sub-linear-memory
    incremental-encode path. Not thread-safe; one instance per encoder."""

    _store: dict[tuple[str, int], torch.Tensor] = field(default_factory=dict)

    def get(self, design_name: str, node_id: int) -> torch.Tensor | None:
        return self._store.get((design_name, node_id))

    def update(self, design_name: str, node_id: int, embedding: torch.Tensor) -> None:
        self._store[(design_name, node_id)] = embedding.detach().clone()

    def clear(self, design_name: str | None = None) -> None:
        if design_name is None:
            self._store.clear()
        else:
            for key in [k for k in self._store if k[0] == design_name]:
                del self._store[key]


class DeepGate4Model(nn.Module):
    def __init__(
        self,
        in_dim: int = NUM_NODE_FEATURES,
        hidden_dim: int = HIDDEN_DIM,
        num_layers: int = NUM_LAYERS,
        heads: int = NUM_HEADS,
        dropout: float = DROPOUT,
    ):
        super().__init__()
        assert hidden_dim % heads == 0
        self.hidden_dim = hidden_dim

        self.feature_proj = nn.Linear(in_dim, hidden_dim)
        self.local_pe_proj = nn.Linear(LOCAL_PE_DIM, hidden_dim)
        self.global_pe_proj = nn.Linear(GLOBAL_PE_DIM, hidden_dim)

        self.layers = nn.ModuleList(
            TransformerConv(hidden_dim, hidden_dim // heads, heads=heads, dropout=dropout, concat=True)
            for _ in range(num_layers)
        )
        self.norms = nn.ModuleList(nn.LayerNorm(hidden_dim) for _ in range(num_layers))

        self.global_proj = nn.Sequential(
            nn.Linear(hidden_dim, D_GLOBAL),
            nn.ReLU(),
            nn.Linear(D_GLOBAL, D_GLOBAL),
        )

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        local_pe: torch.Tensor,
        global_pe: torch.Tensor,
        active_mask: torch.Tensor,
        historical: torch.Tensor | None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.feature_proj(x) + self.local_pe_proj(local_pe) + self.global_pe_proj(global_pe)

        if historical is not None:
            # Pin inactive nodes to their historical embedding as the starting
            # representation; active nodes still get a fresh input projection.
            h = torch.where(active_mask.unsqueeze(-1), h, historical)

        # Restrict message passing so only active destinations get updated —
        # this is what makes per-call compute scale with the active set, not
        # the full node count, when active_mask is sparse.
        dest_active = active_mask[edge_index[1]] if edge_index.numel() > 0 else torch.empty(0, dtype=torch.bool)
        edge_index_active = edge_index[:, dest_active] if edge_index.numel() > 0 else edge_index

        for conv, norm in zip(self.layers, self.norms):
            h_conv = conv(h, edge_index_active)
            h_conv = norm(h_conv)
            h_conv = F.relu(h_conv)
            # Non-active rows keep their previous (historical or just-pinned)
            # value across every layer — they are never updated.
            h = torch.where(active_mask.unsqueeze(-1), h_conv, h)

        pooled = h.mean(dim=0, keepdim=True)
        global_embedding = self.global_proj(pooled).squeeze(0)
        return h, global_embedding


class DeepGate4Encoder(NetlistEncoder):
    """Wraps DeepGate4Model to implement the NetlistEncoder / EncoderOutput contract."""

    def __init__(self, model: DeepGate4Model | None = None, cache: HistoricalEmbeddingCache | None = None):
        self.model = model if model is not None else DeepGate4Model()
        self.cache = cache if cache is not None else HistoricalEmbeddingCache()

    def encode(self, graph: CircuitGraph, active_node_ids: set[int] | None = None) -> EncoderOutput:
        """If active_node_ids is None, every node is (re)computed and cached
        (a full pass, as required by the NetlistEncoder interface / Section
        3.2's contract for a first-time encode). If given, nodes outside the
        set reuse their cached historical embedding bit-for-bit; nodes with
        no cache entry yet are always treated as active regardless of the
        set passed in, since there is nothing to reuse for them."""
        device = next(self.model.parameters()).device
        x = node_features(graph).to(device)
        edge_index = star_expansion_edge_index(graph).to(device)
        # compute_local_pe/compute_global_pe build plain CPU tensors internally
        # (see positional_encoding.py) -- moved here, same device-mismatch
        # class as every other encoder fix made tonight.
        local_pe = compute_local_pe(graph, edge_index.cpu()).to(device)
        global_pe = compute_global_pe(graph, edge_index.cpu(), k=GLOBAL_PE_DIM).to(device)

        node_ids = [n.node_id for n in graph.nodes]
        num_nodes = graph.num_nodes

        active_mask = torch.ones(num_nodes, dtype=torch.bool, device=device)
        historical = None
        if active_node_ids is not None:
            cached = [self.cache.get(graph.design_name, nid) for nid in node_ids]
            if all(c is not None for c in cached):
                historical = torch.stack(cached, dim=0).to(device)
                active_mask = torch.tensor([nid in active_node_ids for nid in node_ids], dtype=torch.bool, device=device)
            # else: no full cache yet for this design — fall back to a full pass.

        self.model.eval()
        with torch.no_grad():
            node_embeddings, global_embedding = self.model(
                x, edge_index, local_pe, global_pe, active_mask, historical
            )

        for i, nid in enumerate(node_ids):
            self.cache.update(graph.design_name, nid, node_embeddings[i])

        return EncoderOutput(
            node_embeddings=node_embeddings,
            global_embedding=global_embedding,
            node_id_order=node_ids,
        )
