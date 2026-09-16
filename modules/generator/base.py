"""GenerationStrategy abstract interface — TECHNICAL.md Section 4.B.

Mirrors the pattern Person A used for the four interchangeable encoders
(modules/encoders/base.py): flow matching is the primary strategy and
diffusion is an explicit fallback "if flow-matching underperforms in
practice" (Section 1.5/4.B). Building both behind one interface means that
swap is a one-line change in `PlacementGenerator.__init__`, not a rewrite.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional

import torch


class GenerationStrategy(ABC):
    backbone: torch.nn.Module

    @abstractmethod
    def training_loss(
        self,
        node_embeddings: torch.Tensor,
        global_embedding: torch.Tensor,
        z1: torch.Tensor,
        frozen_mask: Optional[torch.Tensor] = None,
        generator: Optional[torch.Generator] = None,
    ) -> torch.Tensor:
        """z1: [N, 2] ground-truth normalized (die-relative, [0,1]) target
        coordinates. Returns a scalar loss. If frozen_mask [N] bool is
        given, rows marked frozen are excluded from the loss (their target
        velocity/noise is trivially zero-information for training)."""
        raise NotImplementedError

    @abstractmethod
    def sample(
        self,
        node_embeddings: torch.Tensor,
        global_embedding: torch.Tensor,
        num_nodes: int,
        frozen_mask: Optional[torch.Tensor] = None,
        frozen_values: Optional[torch.Tensor] = None,
        guidance_fn: Optional[Callable[[torch.Tensor, torch.Tensor], torch.Tensor]] = None,
        generator: Optional[torch.Generator] = None,
    ) -> torch.Tensor:
        """Returns [N, 2] normalized (die-relative, [0,1]) sampled
        coordinates. Any row where frozen_mask is True MUST equal the
        corresponding row of frozen_values at every intermediate step and
        in the final output, enforced by index assignment — never by
        relying on the loss/guidance to keep it stable (Section 1.7)."""
        raise NotImplementedError
