"""Encoder pretraining model for CircuitNet's real (structure + timing)
data — TECHNICAL.md Section 1.14.2, adapted per the real data-availability
finding in shared/schemas/pretraining_graph.py's module docstring
(CircuitNet's public release has no real physical geometry, so this
pretrains on real timing-slack prediction rather than congestion/
wirelength, which would need geometry that doesn't exist).

This is intentionally a separate, lightweight model from the four real
encoders (modules/encoders/gcn.py etc.) — it operates on PretrainingGraph,
not CircuitGraph, and its node features (cell-type embedding + real
electrical scalars) have no width/height/is_macro dimension at all. The
point of pretraining is to transfer the trained MESSAGE-PASSING WEIGHTS
(this model's GCNConv layers) into a real encoder's own layers before
fine-tuning on real CircuitGraph data — see
experiments/pretrain_encoder_circuitnet.py's docstring for the transfer
step.
"""

from typing import Dict, List, Optional

import torch
import torch.nn.functional as F
from torch import nn
from torch_geometric.nn import GCNConv

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
