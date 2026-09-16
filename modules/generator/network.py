"""PlacementBackbone — the network both generation strategies share.

Predicts a per-node R^2 field (a flow-matching velocity, or a diffusion
noise estimate — same architecture serves both, see flow_matching.py /
diffusion.py) from: the current per-node coordinates, Person A's per-node
and global conditioning embeddings (Section 3.2), and a scalar time step.

Chips have a variable node count N, so the network must not depend on N
structurally. This uses full self-attention across the node axis (every
node attends to every other node) — a permutation-equivariant "set"
architecture, standard for point-set generative models and appropriate
here since Person A's embeddings already carry the graph structure; this
network's job is to reason about *relative geometry*, not to re-derive
netlist connectivity. Caveat: attention here is O(N^2); on very large
chips this becomes the runtime bottleneck. That tradeoff is explicitly a
target for Person C's runtime/scalability benchmark (TECHNICAL.md Section
1.9.8) to surface with real numbers, not something to guess at here.
"""

import math

import torch
from torch import nn

from shared.schemas.encoder_output import D_GLOBAL, D_NODE

HIDDEN_DIM = 256
NUM_ATTN_LAYERS = 4
NUM_HEADS = 8
TIME_EMBED_DIM = 128


def sinusoidal_time_embedding(t: torch.Tensor, dim: int = TIME_EMBED_DIM) -> torch.Tensor:
    """t: scalar tensor (0-d or [1]) in [0, 1]. Returns [1, dim]."""
    t = t.reshape(1).float()
    half = dim // 2
    freqs = torch.exp(-math.log(10000.0) * torch.arange(half, dtype=torch.float32) / max(half - 1, 1))
    args = t[:, None] * freqs[None, :] * 1000.0  # scale up since t in [0,1], not large integer steps
    embedding = torch.cat([torch.sin(args), torch.cos(args)], dim=-1)
    if embedding.shape[-1] < dim:
        embedding = torch.nn.functional.pad(embedding, (0, dim - embedding.shape[-1]))
    return embedding  # [1, dim]


class PlacementBackbone(nn.Module):
    def __init__(
        self,
        hidden_dim: int = HIDDEN_DIM,
        num_layers: int = NUM_ATTN_LAYERS,
        num_heads: int = NUM_HEADS,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.coord_proj = nn.Linear(2, hidden_dim)
        self.node_cond_proj = nn.Linear(D_NODE, hidden_dim)
        self.global_cond_proj = nn.Linear(D_GLOBAL, hidden_dim)
        self.time_proj = nn.Sequential(
            nn.Linear(TIME_EMBED_DIM, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=num_heads,
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
        )
        self.attn = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.out_head = nn.Linear(hidden_dim, 2)

    def forward(
        self,
        coords: torch.Tensor,
        node_embeddings: torch.Tensor,
        global_embedding: torch.Tensor,
        t: torch.Tensor,
    ) -> torch.Tensor:
        """coords: [N,2]. node_embeddings: [N,D_NODE]. global_embedding:
        [D_GLOBAL]. t: scalar tensor in [0,1]. Returns [N,2]."""
        h = self.coord_proj(coords) + self.node_cond_proj(node_embeddings)
        h = h + self.global_cond_proj(global_embedding).unsqueeze(0)
        h = h + self.time_proj(sinusoidal_time_embedding(t, TIME_EMBED_DIM))
        h = h.unsqueeze(0)  # [1, N, hidden] — batch size 1, one chip per call
        h = self.attn(h)
        h = h.squeeze(0)  # [N, hidden]
        return self.out_head(h)
