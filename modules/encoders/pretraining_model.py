"""Encoder pretraining models for CircuitNet's real (structure + timing)
data — TECHNICAL.md Section 1.14.2, adapted per the real data-availability
finding in shared/schemas/pretraining_graph.py's module docstring
(CircuitNet's public release has no real physical geometry, so this
pretrains on real timing-slack prediction rather than congestion/
wirelength, which would need geometry that doesn't exist).

This is intentionally a separate, lightweight family of models from the
four real encoders (modules/encoders/gcn.py etc.) — they operate on
PretrainingGraph, not CircuitGraph, and their node features (cell-type
embedding + real electrical scalars) have no width/height/is_macro
dimension at all. The point of pretraining is to transfer the trained
MESSAGE-PASSING WEIGHTS into a real encoder's own layers before
fine-tuning on real CircuitGraph data — see
experiments/pretrain_encoder_circuitnet.py's docstring for the transfer
step.

Four variants (PretrainingGCN/GAT/DEHNN/DeepGate4) exist for the
TECHNICAL.md Section 1.9.3 encoder comparison. Each reuses the REAL
message-passing layer class from its corresponding production encoder
(modules/encoders/{gcn,gat,de_hnn,deepgate4}.py) directly — GCNConv,
GATConv, DEHNNLayer, TransformerConv — rather than reimplementing a
stand-in, so the comparison reflects each encoder's actual architecture,
not an approximation of it.
"""

from typing import Dict, List, Optional

import torch
import torch.nn.functional as F
from torch import nn
from torch_geometric.nn import GATConv, GCNConv, TransformerConv

from modules.encoders.de_hnn import DEHNNLayer
from modules.encoders.positional_encoding import compute_global_pe, compute_local_pe
from shared.schemas.pretraining_graph import PretrainingGraph

UNKNOWN_CELL_TOKEN = "<UNK>"
NUM_SCALAR_FEATURES = 4  # [pin_count, is_sequential, drive_strength, fanout_load]


def build_cell_vocabulary(graphs: List[PretrainingGraph]) -> Dict[str, int]:
    """Real vocabulary built ONLY from the given (real training) graphs —
    never hand-specified or guessed. Index 0 is reserved for
    UNKNOWN_CELL_TOKEN, for any cell type seen only at eval/held-out time."""
    names = sorted({node.cell_name for graph in graphs for node in graph.nodes})
    vocab = {UNKNOWN_CELL_TOKEN: 0}
    for name in names:
        vocab[name] = len(vocab)
    return vocab


def pretraining_star_expansion_edge_index(graph: PretrainingGraph) -> torch.Tensor:
    """Same driver<->sink star-expansion convention as
    modules/encoders/graph_utils.star_expansion_edge_index, over
    PretrainingHyperedge instead of CircuitHyperedge."""
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
        return torch.empty((2, 0), dtype=torch.long)
    return torch.tensor([src, dst], dtype=torch.long)


def build_pretraining_incidence(graph: PretrainingGraph) -> tuple[torch.Tensor, torch.Tensor, int]:
    """Same (node_idx, edge_idx, num_edges) hypergraph-incidence convention
    as modules/encoders/de_hnn.build_incidence, over PretrainingHyperedge
    instead of CircuitHyperedge."""
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


def pretraining_inputs(graph: PretrainingGraph, vocab: Dict[str, int]) -> tuple:
    """Returns (cell_type_ids [N] long, scalar_features [N, NUM_SCALAR_FEATURES]
    float, slack_targets [N] float, has_label_mask [N] bool). Missing
    scalar values (None) are imputed with 0.0 -- real per-cell electrical
    data is present for the overwhelming majority of nodes in practice
    (see tests/unit/intake/test_circuitnet_parser.py), this only guards
    the rare/edge-case node."""
    cell_ids, scalars, targets, mask = [], [], [], []
    for node in graph.nodes:
        cell_ids.append(vocab.get(node.cell_name, vocab[UNKNOWN_CELL_TOKEN]))
        scalars.append(
            [
                float(node.pin_count),
                1.0 if node.is_sequential else 0.0,
                node.drive_strength or 0.0,
                node.fanout_load or 0.0,
            ]
        )
        if node.slack is not None:
            targets.append(node.slack)
            mask.append(True)
        else:
            targets.append(0.0)
            mask.append(False)

    return (
        torch.tensor(cell_ids, dtype=torch.long),
        torch.tensor(scalars, dtype=torch.float32),
        torch.tensor(targets, dtype=torch.float32),
        torch.tensor(mask, dtype=torch.bool),
    )


class PretrainingGCN(nn.Module):
    """3-layer GCN (matching Section 4.A's GCN/GAT baseline depth/width so
    the pretrained weights are shape-compatible with those encoders'
    message-passing layers), predicting real timing slack at nodes that
    have a real label."""

    def __init__(self, vocab_size: int, embed_dim: int = 32, hidden_dim: int = 256, num_layers: int = 3):
        super().__init__()
        self.cell_embedding = nn.Embedding(vocab_size, embed_dim)
        in_dim = embed_dim + NUM_SCALAR_FEATURES

        dims = [in_dim] + [hidden_dim] * num_layers
        self.convs = nn.ModuleList(GCNConv(dims[i], dims[i + 1]) for i in range(num_layers))
        self.regression_head = nn.Linear(hidden_dim, 1)

    def forward(self, cell_ids: torch.Tensor, scalars: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        h = torch.cat([self.cell_embedding(cell_ids), scalars], dim=-1)
        for i, conv in enumerate(self.convs):
            h = conv(h, edge_index)
            if i < len(self.convs) - 1:
                h = F.relu(h)
        return self.regression_head(h).squeeze(-1)  # [N] predicted slack

    def masked_mse_loss(
        self, cell_ids: torch.Tensor, scalars: torch.Tensor, edge_index: torch.Tensor, targets: torch.Tensor, mask: torch.Tensor
    ) -> Optional[torch.Tensor]:
        if not mask.any():
            return None  # a design with zero labeled (sequential) nodes contributes nothing
        pred = self.forward(cell_ids, scalars, edge_index)
        return F.mse_loss(pred[mask], targets[mask])


class PretrainingGAT(nn.Module):
    """Reuses GATConv (modules/encoders/gat.py's real layer choice) at the
    same depth/heads/dropout as GATEncoderModel, over the same star-expansion
    edges as PretrainingGCN."""

    def __init__(
        self,
        vocab_size: int,
        embed_dim: int = 32,
        hidden_dim: int = 256,
        num_layers: int = 3,
        heads: int = 4,
        dropout: float = 0.1,
    ):
        super().__init__()
        assert hidden_dim % heads == 0, "hidden_dim must be divisible by heads for multi-head concat"
        self.dropout = dropout
        self.cell_embedding = nn.Embedding(vocab_size, embed_dim)
        in_dim = embed_dim + NUM_SCALAR_FEATURES

        self.convs = nn.ModuleList()
        self.convs.append(GATConv(in_dim, hidden_dim // heads, heads=heads, dropout=dropout))
        for _ in range(num_layers - 2):
            self.convs.append(GATConv(hidden_dim, hidden_dim // heads, heads=heads, dropout=dropout))
        self.convs.append(GATConv(hidden_dim, hidden_dim, heads=heads, concat=False, dropout=dropout))
        self.regression_head = nn.Linear(hidden_dim, 1)

    def forward(self, cell_ids: torch.Tensor, scalars: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        h = torch.cat([self.cell_embedding(cell_ids), scalars], dim=-1)
        for i, conv in enumerate(self.convs):
            h = conv(h, edge_index)
            if i < len(self.convs) - 1:
                h = F.relu(h)
                h = F.dropout(h, p=self.dropout, training=self.training)
        return self.regression_head(h).squeeze(-1)

    def masked_mse_loss(
        self, cell_ids: torch.Tensor, scalars: torch.Tensor, edge_index: torch.Tensor, targets: torch.Tensor, mask: torch.Tensor
    ) -> Optional[torch.Tensor]:
        if not mask.any():
            return None
        pred = self.forward(cell_ids, scalars, edge_index)
        return F.mse_loss(pred[mask], targets[mask])


class PretrainingDEHNN(nn.Module):
    """Reuses DEHNNLayer (modules/encoders/de_hnn.py's real bipartite
    node<->hyperedge message-passing layer) unmodified, over the netlist's
    native hypergraph incidence rather than a star-expansion decomposition —
    the whole point of DE-HNN per that module's docstring."""

    def __init__(self, vocab_size: int, embed_dim: int = 32, hidden_dim: int = 256, num_rounds: int = 2):
        super().__init__()
        self.cell_embedding = nn.Embedding(vocab_size, embed_dim)
        in_dim = embed_dim + NUM_SCALAR_FEATURES
        self.input_proj = nn.Linear(in_dim, hidden_dim)
        self.edge_init = nn.Parameter(torch.zeros(hidden_dim))
        self.layers = nn.ModuleList(DEHNNLayer(hidden_dim) for _ in range(num_rounds))
        self.regression_head = nn.Linear(hidden_dim, 1)

    def forward(
        self,
        cell_ids: torch.Tensor,
        scalars: torch.Tensor,
        node_idx: torch.Tensor,
        edge_idx: torch.Tensor,
        num_edges: int,
    ) -> torch.Tensor:
        x = torch.cat([self.cell_embedding(cell_ids), scalars], dim=-1)
        node_repr = F.relu(self.input_proj(x))
        edge_repr = self.edge_init.unsqueeze(0).expand(num_edges, -1).contiguous()
        for layer in self.layers:
            node_repr, edge_repr = layer(node_repr, edge_repr, node_idx, edge_idx)
        return self.regression_head(node_repr).squeeze(-1)

    def masked_mse_loss(
        self,
        cell_ids: torch.Tensor,
        scalars: torch.Tensor,
        node_idx: torch.Tensor,
        edge_idx: torch.Tensor,
        num_edges: int,
        targets: torch.Tensor,
        mask: torch.Tensor,
    ) -> Optional[torch.Tensor]:
        if not mask.any():
            return None
        pred = self.forward(cell_ids, scalars, node_idx, edge_idx, num_edges)
        return F.mse_loss(pred[mask], targets[mask])


class PretrainingDeepGate4(nn.Module):
    """Reuses TransformerConv (modules/encoders/deepgate4.py's real layer
    choice) plus that module's real compute_local_pe/compute_global_pe
    structural positional encodings unmodified — both functions only touch
    fields PretrainingGraph also has (num_nodes, hyperedges, per-node
    pin_count), so they apply here despite being type-hinted for
    CircuitGraph. No incremental/historical-embedding caching here (that's
    an inference-time optimization for the real encoder, not relevant to
    this offline pretraining loop) -- every node is always "active"."""

    def __init__(
        self, vocab_size: int, embed_dim: int = 32, hidden_dim: int = 256, num_layers: int = 3, heads: int = 4, dropout: float = 0.1
    ):
        super().__init__()
        assert hidden_dim % heads == 0
        self.cell_embedding = nn.Embedding(vocab_size, embed_dim)
        in_dim = embed_dim + NUM_SCALAR_FEATURES
        self.feature_proj = nn.Linear(in_dim, hidden_dim)
        self.local_pe_proj = nn.Linear(3, hidden_dim)  # LOCAL_PE_DIM
        self.global_pe_proj = nn.Linear(8, hidden_dim)  # default global PE k
        self.layers = nn.ModuleList(
            TransformerConv(hidden_dim, hidden_dim // heads, heads=heads, dropout=dropout, concat=True) for _ in range(num_layers)
        )
        self.norms = nn.ModuleList(nn.LayerNorm(hidden_dim) for _ in range(num_layers))
        self.regression_head = nn.Linear(hidden_dim, 1)

    def forward(
        self,
        cell_ids: torch.Tensor,
        scalars: torch.Tensor,
        edge_index: torch.Tensor,
        local_pe: torch.Tensor,
        global_pe: torch.Tensor,
    ) -> torch.Tensor:
        x = torch.cat([self.cell_embedding(cell_ids), scalars], dim=-1)
        h = self.feature_proj(x) + self.local_pe_proj(local_pe) + self.global_pe_proj(global_pe)
        for conv, norm in zip(self.layers, self.norms):
            h = F.relu(norm(conv(h, edge_index)))
        return self.regression_head(h).squeeze(-1)

    def masked_mse_loss(
        self,
        cell_ids: torch.Tensor,
        scalars: torch.Tensor,
        edge_index: torch.Tensor,
        local_pe: torch.Tensor,
        global_pe: torch.Tensor,
        targets: torch.Tensor,
        mask: torch.Tensor,
    ) -> Optional[torch.Tensor]:
        if not mask.any():
            return None
        pred = self.forward(cell_ids, scalars, edge_index, local_pe, global_pe)
        return F.mse_loss(pred[mask], targets[mask])
