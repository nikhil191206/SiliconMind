"""Differentiable sampling-time guidance surrogates — TECHNICAL.md Section 4.B:
"Guidance weight for legality/wirelength/congestion terms: start at equal
weighting, tune via ablation."

*** Scope boundary vs. Person C (Section 1.4) ***
The HPWL / congestion-overflow / legality-violation numbers that get
REPORTED anywhere in this project are owned by Person C (`shared/metrics/`)
and must never be reimplemented locally. The classes below are NOT that.
They are differentiable *surrogates* used only to steer the flow-
matching/diffusion ODE during sampling (classifier-guidance style) — a
different job with a different requirement (needs a gradient; C's real
legalizer wraps external, non-differentiable tools: DREAMPlace/OpenROAD).
No number produced here is ever reported as a result — only C's
shared/metrics output can be. `shared/metrics/` does not exist in the repo
yet (Person C's track hasn't started); see NOTES.md.

All three geometry-aware terms (legality, wirelength, congestion) take
`z` already in REAL die units (not the [0,1]-normalized space the sampler
works in internally) — `combined_guidance_fn` below owns that unit
conversion in one place via the chain rule, so no individual term has to
know about normalization.
"""

from abc import ABC, abstractmethod
from typing import Callable, Dict, List

import torch

from modules.generator.types import GuidanceConfig, SpatialGuidanceDirective
from shared.schemas.circuit_graph import CircuitGraph


class GuidanceTerm(ABC):
    @abstractmethod
    def gradient(self, z: torch.Tensor, graph: CircuitGraph) -> torch.Tensor:
        """z: [N,2], REAL die-unit coordinates. Returns [N,2]: the gradient
        of this term's penalty (or, for SpatialGuidance, its directional
        objective) w.r.t. z. The caller descends this (subtracts it) to
        reduce the penalty / pursue the objective."""
        raise NotImplementedError


class LegalityGuidance(GuidanceTerm):
    """Differentiable pairwise soft-overlap penalty between node bounding
    boxes — a surrogate for the hard legality-violation COUNT in Section
    1.4, which is itself not differentiable."""

    def gradient(self, z: torch.Tensor, graph: CircuitGraph) -> torch.Tensor:
        with torch.enable_grad():  # guidance is called from inside sample()'s @torch.no_grad()
            z = z.detach().requires_grad_(True)
            half_extents = torch.tensor([[n.width / 2, n.height / 2] for n in graph.nodes], dtype=z.dtype)
            delta = z.unsqueeze(0) - z.unsqueeze(1)  # [N,N,2]
            overlap = torch.relu((half_extents.unsqueeze(0) + half_extents.unsqueeze(1)) - delta.abs())
            pair_penalty = overlap[..., 0] * overlap[..., 1]  # [N,N] area-like overlap
            n = z.shape[0]
            pair_penalty = pair_penalty.masked_fill(torch.eye(n, dtype=torch.bool), 0.0)
            loss = pair_penalty.sum() / 2  # each pair counted twice
            (grad,) = torch.autograd.grad(loss, z)
        return grad.detach()


class WirelengthGuidance(GuidanceTerm):
    """Differentiable soft-HPWL-shaped surrogate: per-hyperedge bounding-box
    span, summed over driver + sink nodes, using the CircuitGraph's real
    connectivity (Section 3.1) — same formula *shape* as Section 1.4's
    HPWL, recomputed here only as a guidance gradient, never as a reported
    number."""

    def gradient(self, z: torch.Tensor, graph: CircuitGraph) -> torch.Tensor:
        with torch.enable_grad():
            z = z.detach().requires_grad_(True)
            loss = torch.zeros((), dtype=z.dtype)
            for hyperedge in graph.hyperedges:
                node_ids = list(hyperedge.sink_nodes)
                if hyperedge.driver_node is not None:
                    node_ids.append(hyperedge.driver_node)
                if len(node_ids) < 2:
                    continue
                pts = z[node_ids]
                span = pts.max(dim=0).values - pts.min(dim=0).values
                loss = loss + span.sum()
            if not loss.requires_grad:
                return torch.zeros_like(z)
            (grad,) = torch.autograd.grad(loss, z)
        return grad.detach()


class CongestionGuidance(GuidanceTerm):
    """Coarse kernel-density congestion surrogate: penalizes node density
    per grid cell exceeding a uniform target occupancy — a proxy for the
    real routing-demand/capacity overflow in Section 1.4, which needs an
    actual global-router estimate from DREAMPlace/OpenROAD and cannot be
    approximated exactly here."""

    def __init__(self, grid_size: int = 8):
        self.grid_size = grid_size

    def gradient(self, z: torch.Tensor, graph: CircuitGraph) -> torch.Tensor:
        with torch.enable_grad():
            z = z.detach().requires_grad_(True)
            g = self.grid_size
            die_w, die_h = graph.die.width, graph.die.height
            xs = torch.linspace(0, die_w, g)
            ys = torch.linspace(0, die_h, g)
            grid = torch.stack(torch.meshgrid(xs, ys, indexing="ij"), dim=-1).reshape(-1, 2)  # [g*g,2]
            sigma_x, sigma_y = die_w / g, die_h / g
            diff = z.unsqueeze(1) - grid.unsqueeze(0)  # [N,g*g,2]
            density = torch.exp(-(((diff[..., 0] / sigma_x) ** 2) + ((diff[..., 1] / sigma_y) ** 2)) / 2)
            occupancy = density.sum(dim=0)  # [g*g]
            target = z.shape[0] / (g * g)
            overflow = torch.relu(occupancy - target)
            loss = (overflow**2).sum()
            (grad,) = torch.autograd.grad(loss, z)
        return grad.detach()


class SpatialGuidance(GuidanceTerm):
    """Attraction/repulsion guidance implementing the D -> B directional
    constraint types (MOVE_AWAY_FROM, MOVE_TOWARD, FORBID_REGION,
    PREFER_REGION) that Section 4.B's fixed 3-term GuidanceConfig has no
    channel for on its own — see types.py's module docstring."""

    def __init__(self, directives: List[SpatialGuidanceDirective], node_id_to_index: Dict[int, int]):
        self.directives = directives
        self.node_id_to_index = node_id_to_index

    def gradient(self, z: torch.Tensor, graph: CircuitGraph) -> torch.Tensor:
        with torch.enable_grad():
            z = z.detach().requires_grad_(True)
            loss = torch.zeros((), dtype=z.dtype)
            touched = False
            for directive in self.directives:
                idx = [self.node_id_to_index[nid] for nid in directive.node_ids if nid in self.node_id_to_index]
                if not idx:
                    continue
                pts = z[idx]
                if directive.reference_point is not None:
                    ref = torch.tensor(directive.reference_point, dtype=z.dtype)
                elif directive.reference_region is not None:
                    r = directive.reference_region
                    ref = torch.tensor([(r.x_min + r.x_max) / 2, (r.y_min + r.y_max) / 2], dtype=z.dtype)
                else:
                    continue
                dist_sq = ((pts - ref) ** 2).sum(dim=-1)
                sign = -1.0 if directive.mode in ("away_from", "avoid_region") else 1.0
                loss = loss + sign * directive.weight * dist_sq.sum()
                touched = True
            if not touched:
                return torch.zeros_like(z)
            (grad,) = torch.autograd.grad(loss, z)
        return grad.detach()


def combined_guidance_fn(
    graph: CircuitGraph, config: GuidanceConfig, node_id_to_index: Dict[int, int]
) -> Callable[[torch.Tensor, torch.Tensor], torch.Tensor]:
    """Returns guidance_fn(z_normalized, t) -> [N,2] additive velocity term,
    combining every configured guidance surrogate. `z_normalized` is the
    sampler's internal [0,1] die-relative representation; this function
    owns the one-place conversion to real die units (legality needs real
    node widths/heights, wirelength needs real spans) and back, via the
    chain rule: d(loss)/dz_normalized = d(loss)/dz_real * die_scale."""
    legality = LegalityGuidance()
    wirelength = WirelengthGuidance()
    congestion = CongestionGuidance()
    spatial = SpatialGuidance(config.spatial_directives, node_id_to_index) if config.spatial_directives else None
    die_scale = torch.tensor([graph.die.width, graph.die.height])

    def guidance_fn(z_normalized: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
        z_real = z_normalized * die_scale
        total_real = torch.zeros_like(z_real)
        if config.legality_weight:
            total_real = total_real - config.legality_weight * legality.gradient(z_real, graph)
        if config.wirelength_weight:
            total_real = total_real - config.wirelength_weight * wirelength.gradient(z_real, graph)
        if config.congestion_weight:
            total_real = total_real - config.congestion_weight * congestion.gradient(z_real, graph)
        if spatial is not None:
            total_real = total_real - spatial.gradient(z_real, graph)
        return total_real * die_scale  # chain rule back to normalized-z gradient

    return guidance_fn
