"""DiffusionGenerationStrategy — TECHNICAL.md Section 4.B (fallback).

"Diffusion fallback (only if flow-matching underperforms in practice on
the project's benchmark set): standard DDPM-style noise schedule, 1000
training steps / reduced sampling steps at inference (e.g., DDIM-style
acceleration) for the zero-shot-in-seconds claim to hold."

Shares `PlacementBackbone` with the flow-matching strategy (same network,
predicting noise instead of velocity) and implements the identical
`GenerationStrategy` interface, so `PlacementGenerator` can swap between
the two with a one-line change — see NOTES.md / base.py for why that
swappability matters here (Section 1.5 explicitly reserves the right to
fall back).

Freeze enforcement mirrors flow_matching.py exactly: re-pin frozen rows to
their exact given value after every single denoising step, never relying
on the schedule to keep them stable (Section 1.7).
"""

from typing import Callable, Optional

import torch

from modules.generator.base import GenerationStrategy
from modules.generator.network import PlacementBackbone

DEFAULT_TRAIN_STEPS = 1000
DEFAULT_INFERENCE_STEPS = 50


def linear_beta_schedule(
    num_steps: int = DEFAULT_TRAIN_STEPS, beta_start: float = 1e-4, beta_end: float = 0.02
) -> torch.Tensor:
    return torch.linspace(beta_start, beta_end, num_steps)


class DiffusionGenerationStrategy(GenerationStrategy):
    def __init__(self, backbone: Optional[PlacementBackbone] = None, train_steps: int = DEFAULT_TRAIN_STEPS):
        self.backbone = backbone if backbone is not None else PlacementBackbone()
        self.train_steps = train_steps
        betas = linear_beta_schedule(train_steps)
        alphas = 1.0 - betas
        self.alphas_cumprod = torch.cumprod(alphas, dim=0)  # [T]

    def training_loss(
        self,
        node_embeddings: torch.Tensor,
        global_embedding: torch.Tensor,
        z1: torch.Tensor,
        frozen_mask: Optional[torch.Tensor] = None,
        generator: Optional[torch.Generator] = None,
    ) -> torch.Tensor:
        T = self.train_steps
        if generator is not None:
            t_idx = torch.randint(0, T, (), generator=generator)
            noise = torch.randn(z1.shape, generator=generator)
        else:
            t_idx = torch.randint(0, T, ())
            noise = torch.randn_like(z1)

        a_bar = self.alphas_cumprod[t_idx]
        z_t = torch.sqrt(a_bar) * z1 + torch.sqrt(1 - a_bar) * noise
        t_norm = t_idx.float() / T
        pred_noise = self.backbone(z_t, node_embeddings, global_embedding, t_norm)

        if frozen_mask is not None:
            keep = (~frozen_mask).unsqueeze(-1).float()
            sq_err = (pred_noise - noise) ** 2 * keep
            denom = keep.sum().clamp(min=1.0)
            return sq_err.sum() / denom
        return torch.mean((pred_noise - noise) ** 2)

    @torch.no_grad()
    def sample(
        self,
        node_embeddings: torch.Tensor,
        global_embedding: torch.Tensor,
        num_nodes: int,
        frozen_mask: Optional[torch.Tensor] = None,
        frozen_values: Optional[torch.Tensor] = None,
        guidance_fn: Optional[Callable[[torch.Tensor, torch.Tensor], torch.Tensor]] = None,
        num_steps: int = DEFAULT_INFERENCE_STEPS,
        generator: Optional[torch.Generator] = None,
    ) -> torch.Tensor:
        """DDIM-style accelerated sampling: strides through a subsequence of
        the T training timesteps so inference stays fast (Section 1.6's
        "zero-shot in seconds" claim) even for this fallback path."""
        self.backbone.eval()  # disable dropout — see flow_matching.py's sample() for why this matters
        device = node_embeddings.device
        if generator is not None:
            z = torch.randn((num_nodes, 2), generator=generator, device=device)
        else:
            z = torch.randn((num_nodes, 2), device=device)

        if frozen_mask is not None:
            assert frozen_values is not None, "frozen_values required when frozen_mask is given"
            z = z.clone()
            z[frozen_mask] = frozen_values[frozen_mask]

        T = self.train_steps
        step_indices = torch.linspace(T - 1, 0, num_steps).round().long()
        for i, t_idx in enumerate(step_indices):
            a_bar_t = self.alphas_cumprod[t_idx]
            t_norm = t_idx.float() / T
            pred_noise = self.backbone(z, node_embeddings, global_embedding, t_norm)
            if guidance_fn is not None:
                # Classifier-guidance-style nudge on the noise estimate itself.
                pred_noise = pred_noise - guidance_fn(z, t_norm)
            pred_z1 = (z - torch.sqrt(1 - a_bar_t) * pred_noise) / torch.sqrt(a_bar_t)

            if i + 1 < len(step_indices):
                a_bar_next = self.alphas_cumprod[step_indices[i + 1]]
                z = torch.sqrt(a_bar_next) * pred_z1 + torch.sqrt(1 - a_bar_next) * pred_noise
            else:
                z = pred_z1

            if frozen_mask is not None:
                z = z.clone()
                z[frozen_mask] = frozen_values[frozen_mask]
        return z
