"""FlowMatchingGenerationStrategy — TECHNICAL.md Section 4.B (primary model).

"Flow matching: conditional flow matching objective, linear interpolation
path between noise and data, ODE solver with 50 sampling steps as the
default." Implements the standard conditional flow matching (CFM)
recipe: source z0 ~ N(0,I), data z1 (ground-truth normalized placement),
straight-line path z_t = (1-t) z0 + t z1, regress the constant velocity
z1 - z0 with the backbone, then Euler-integrate the learned field at
inference from fresh noise to a placement.

Section 1.7's freeze guarantee is enforced here at the tensor-indexing
level in `sample()`: frozen rows are re-pinned to their exact given value
after every single Euler step, not merely initialized once and hoped to
stay put under the ODE's own dynamics.
"""

from typing import Callable, Optional

import torch

from modules.generator.base import GenerationStrategy
from modules.generator.network import PlacementBackbone

DEFAULT_ODE_STEPS = 50


class FlowMatchingGenerationStrategy(GenerationStrategy):
    def __init__(self, backbone: Optional[PlacementBackbone] = None):
        self.backbone = backbone if backbone is not None else PlacementBackbone()

    def training_loss(
        self,
        node_embeddings: torch.Tensor,
        global_embedding: torch.Tensor,
        z1: torch.Tensor,
        frozen_mask: Optional[torch.Tensor] = None,
        generator: Optional[torch.Generator] = None,
    ) -> torch.Tensor:
        device = z1.device
        if generator is not None:
            # generator (a torch.Generator) is CPU-only in this codebase's
            # callers (see PlacementGenerator._sample_with_retry) -- sample
            # on CPU with it, then move to z1's device, rather than passing
            # a CPU generator directly to a CUDA randn call, which torch
            # rejects.
            z0 = torch.randn(z1.shape, generator=generator).to(device)
            t = torch.rand((), generator=generator).to(device)
        else:
            z0 = torch.randn_like(z1)
            t = torch.rand((), device=device)
        z_t = (1 - t) * z0 + t * z1
        target_v = z1 - z0
        pred_v = self.backbone(z_t, node_embeddings, global_embedding, t)

        if frozen_mask is not None:
            keep = (~frozen_mask).unsqueeze(-1).float()
            sq_err = (pred_v - target_v) ** 2 * keep
            denom = keep.sum().clamp(min=1.0)
            return sq_err.sum() / denom
        return torch.mean((pred_v - target_v) ** 2)

    @torch.no_grad()
    def sample(
        self,
        node_embeddings: torch.Tensor,
        global_embedding: torch.Tensor,
        num_nodes: int,
        frozen_mask: Optional[torch.Tensor] = None,
        frozen_values: Optional[torch.Tensor] = None,
        guidance_fn: Optional[Callable[[torch.Tensor, torch.Tensor], torch.Tensor]] = None,
        num_steps: int = DEFAULT_ODE_STEPS,
        generator: Optional[torch.Generator] = None,
    ) -> torch.Tensor:
        self.backbone.eval()  # disable dropout: without this, sampling isn't
        # reproducible from `generator` alone, since dropout draws from
        # torch's global RNG rather than the generator threaded through here.
        device = node_embeddings.device
        if generator is not None:
            z = torch.randn((num_nodes, 2), generator=generator, device=device)
        else:
            z = torch.randn((num_nodes, 2), device=device)

        if frozen_mask is not None:
            assert frozen_values is not None, "frozen_values required when frozen_mask is given"
            z = z.clone()
            z[frozen_mask] = frozen_values[frozen_mask]

        dt = 1.0 / num_steps
        for step in range(num_steps):
            t = torch.tensor(step * dt, device=device)
            v = self.backbone(z, node_embeddings, global_embedding, t)
            if guidance_fn is not None:
                v = v + guidance_fn(z, t)
            if frozen_mask is not None:
                v = v.clone()
                v[frozen_mask] = 0.0  # frozen rows: zero velocity, full stop
            z = z + dt * v
            if frozen_mask is not None:
                # Re-pin to the exact given value after every step — this is
                # what makes the guarantee independent of anything the
                # backbone or guidance_fn computed (Section 1.7).
                z = z.clone()
                z[frozen_mask] = frozen_values[frozen_mask]
        return z
