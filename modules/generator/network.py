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

*** Real scalability numbers, measured 2026-09-23 on the actual target
GPU (RTX 3050, 6GB), not estimated ***
| N (nodes) | time (fwd+bwd) | peak memory |
|---|---|---|
| 12,752  (ibm01)             | 2.5s  | 1.05 GB |
| 30,000                      | 13.1s | 2.4 GB  |
| 70,000                      | 71s   | 5.5 GB  |
| 150,000                     | hangs -- pinned at ~6GB, Windows silently
  falls back to slow shared-memory swapping rather than a clean OOM error |

Roughly half of the real 30-design training corpus (config/shared_config.yaml's
train_chips) exceeds 70,000 nodes, and `mgc_superblue11_a` alone has
925,010 -- full O(N^2) attention cannot train on those designs on this
GPU as originally written. Gradient checkpointing (below) trades compute
for memory and measurably raises the safe ceiling (memory stops being the
limiter well past 150K; see NOTES.md for the re-measured numbers), but does
NOT fix the underlying O(N^2) *compute* cost -- a chip like
mgc_superblue11_a (925K nodes) would still take a genuinely long time per
step even with checkpointing, since checkpointing recomputes rather than
skips the attention FLOPs. That remaining gap (a real architecture change
-- sparse/windowed or hierarchical attention -- for the largest few real
chips) is flagged in NOTES.md as still open, not silently absorbed here.
"""

import math
from typing import Optional

import torch
from torch import nn
from torch.utils.checkpoint import checkpoint

from shared.schemas.encoder_output import D_GLOBAL, D_NODE

HIDDEN_DIM = 256
NUM_ATTN_LAYERS = 4
NUM_HEADS = 8
TIME_EMBED_DIM = 128

# Measured (2026-09-23, real RTX 3050 6GB): N=70,000 needs 5.5GB WITHOUT
# checkpointing and runs in 71s; the SAME size WITH checkpointing takes
# ~96s (checkpointing's recompute cost isn't free, and isn't needed yet at
# this size -- 5.5GB comfortably fits). N=150,000 hangs without
# checkpointing (pinned at the ~6GB ceiling) but only needs ~4.5GB and
# completes with it. So checkpointing should turn on only once it's
# actually needed, not unconditionally -- 80,000 sits between the two
# measured points, safely past where 70K worked fine unassisted and
# comfortably before 150K's failure point.
AUTO_CHECKPOINT_NODE_THRESHOLD = 80_000


def sinusoidal_time_embedding(t: torch.Tensor, dim: int = TIME_EMBED_DIM) -> torch.Tensor:
    """t: scalar tensor (0-d or [1]) in [0, 1]. Returns [1, dim].

    Bug found during real GPU scalability testing (2026-09-23): `freqs` was
    built with no device argument, defaulting to CPU -- on any GPU run,
    `t[:, None] * freqs[None, :]` mixed a CUDA tensor with a CPU tensor and
    raised immediately. This means this backbone had never actually been
    exercised end-to-end on GPU before now (every prior test/run either
    stayed on CPU or never reached this line with `t` already on a GPU
    device). Fixed by building `freqs` on `t`'s own device."""
    t = t.reshape(1).float()
    half = dim // 2
    freqs = torch.exp(
        -math.log(10000.0) * torch.arange(half, dtype=torch.float32, device=t.device) / max(half - 1, 1)
    )
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
        use_checkpointing: Optional[bool] = None,
    ):
        """`use_checkpointing=None` (the default) auto-decides per call
        based on node count (see AUTO_CHECKPOINT_NODE_THRESHOLD above) --
        checkpointing has a real recompute cost that isn't worth paying on
        graphs small enough to fit comfortably without it. Pass True/False
        explicitly to override the automatic choice."""
        super().__init__()
        self.use_checkpointing = use_checkpointing
        self.coord_proj = nn.Linear(2, hidden_dim)
        self.node_cond_proj = nn.Linear(D_NODE, hidden_dim)
        self.global_cond_proj = nn.Linear(D_GLOBAL, hidden_dim)
        self.time_proj = nn.Sequential(
            nn.Linear(TIME_EMBED_DIM, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        # Individual layers, applied in a manual loop below (rather than via
        # nn.TransformerEncoder's own forward) specifically so each layer can
        # be wrapped in torch.utils.checkpoint -- see module docstring for
        # why this matters (memory measured, not assumed).
        self.attn_layers = nn.ModuleList(
            nn.TransformerEncoderLayer(
                d_model=hidden_dim,
                nhead=num_heads,
                dim_feedforward=hidden_dim * 4,
                dropout=dropout,
                batch_first=True,
                activation="gelu",
            )
            for _ in range(num_layers)
        )
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

        if self.use_checkpointing is None:
            should_checkpoint = coords.shape[0] >= AUTO_CHECKPOINT_NODE_THRESHOLD
        else:
            should_checkpoint = self.use_checkpointing

        for layer in self.attn_layers:
            if should_checkpoint and self.training:
                # Recomputes this layer's activations during backward instead
                # of storing them -- trades compute for memory. Does not
                # change the output value at all (verified in
                # tests/unit/generator/test_network_scalability.py: checkpointed
                # and non-checkpointed forward passes agree exactly).
                h = checkpoint(layer, h, use_reentrant=False)
            else:
                h = layer(h)

        h = h.squeeze(0)  # [N, hidden]
        return self.out_head(h)
