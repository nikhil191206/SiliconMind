"""Freeze-mask construction, and the D -> B constraint bridge — the
"partial-regeneration / hard-freezing mechanism that makes natural-
language editing possible" (workDistribution.md, Person B), implementing
TECHNICAL.md Section 3.4 / 1.7.
"""

from typing import Dict, List, Optional, Tuple

import torch

from modules.generator.types import FrozenNode, GuidanceConfig, SpatialGuidanceDirective
from shared.schemas.circuit_graph import CircuitGraph, Die
from shared.schemas.constraint import ConstraintObject, ConstraintType, ReferenceType, Strength
from shared.schemas.placement import PlacementEntry, PlacementJSON


class ConstraintRequiresClarificationError(Exception):
    """Raised when a ConstraintObject fails Section 3.4's hard gate
    (constraint_type == UNCLEAR or confidence < 0.6). The generator must
    NEVER be called in this case — the caller (Person D's layer) must
    return a clarification request to the user instead, not a
    regeneration."""


def build_frozen_mask(
    num_nodes: int,
    node_id_to_index: Dict[int, int],
    die: Die,
    frozen_placements: Optional[List[FrozenNode]],
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Returns (frozen_mask [N] bool, frozen_values [N,2] float, normalized
    to [0,1] die-relative units). Unfrozen rows of frozen_values are left
    at 0.0 and must never be read — callers gate every use through
    frozen_mask. This is used only to keep the ODE/denoising trajectory
    numerically consistent during sampling; the FINAL output for frozen
    nodes is assembled directly from `frozen_placements` in generator.py,
    never derived from this tensor, so it is bit-identical independent of
    any floating-point round-trip through normalization here."""
    frozen_mask = torch.zeros(num_nodes, dtype=torch.bool)
    frozen_values = torch.zeros(num_nodes, 2, dtype=torch.float32)
    if not frozen_placements:
        return frozen_mask, frozen_values
    for fp in frozen_placements:
        idx = node_id_to_index[fp.node_id]
        frozen_mask[idx] = True
        frozen_values[idx, 0] = fp.x / die.width
        frozen_values[idx, 1] = fp.y / die.height
    return frozen_mask, frozen_values


_CONSTRAINT_MODE = {
    ConstraintType.MOVE_AWAY_FROM: "away_from",
    ConstraintType.FORBID_ADJACENT: "away_from",
    ConstraintType.MOVE_TOWARD: "toward",
    ConstraintType.FORBID_REGION: "avoid_region",
    ConstraintType.PREFER_REGION: "prefer_region",
}


def _resolve_reference_point(
    constraint: ConstraintObject,
    placement_by_id: Dict[int, PlacementEntry],
    graph: Optional[CircuitGraph],
) -> Optional[Tuple[float, float]]:
    ref = constraint.reference
    if ref.type == ReferenceType.REGION:
        return None  # handled as reference_region instead, see caller
    if ref.type == ReferenceType.NODE:
        node_id = ref.value
        entry = placement_by_id.get(node_id)
        if entry is None:
            raise ValueError(f"reference node_id {node_id} not found in previous_placement")
        return (entry.x, entry.y)
    if ref.type == ReferenceType.EDGE:
        if graph is None:
            raise ValueError(
                "constraint.reference.type == EDGE requires `graph` to resolve the net's endpoint "
                "nodes — pass the CircuitGraph to constraint_to_generation_inputs()."
            )
        net_id = ref.value
        hyperedge = next((h for h in graph.hyperedges if h.net_id == net_id), None)
        if hyperedge is None:
            raise ValueError(f"reference net_id {net_id} not found in graph.hyperedges")
        endpoint_ids = list(hyperedge.sink_nodes)
        if hyperedge.driver_node is not None:
            endpoint_ids.append(hyperedge.driver_node)
        pts = [(placement_by_id[nid].x, placement_by_id[nid].y) for nid in endpoint_ids]
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    raise ValueError(f"unexpected reference.type: {ref.type}")


def constraint_to_generation_inputs(
    constraint: ConstraintObject,
    previous_placement: PlacementJSON,
    graph: Optional[CircuitGraph] = None,
    base_guidance: Optional[GuidanceConfig] = None,
) -> Tuple[List[FrozenNode], GuidanceConfig]:
    """Converts a Section 3.4 ConstraintObject + the placement it's editing
    into `generate()`'s (frozen_placements, guidance_terms) inputs.

    `graph` is optional and only required to resolve an EDGE reference
    (needs hyperedge connectivity); NODE and REGION references resolve
    from `previous_placement` alone.
    """
    if constraint.requires_clarification():
        raise ConstraintRequiresClarificationError(
            f"constraint {constraint.constraint_id!r} is UNCLEAR or confidence "
            f"{constraint.confidence} < 0.6 — per Section 3.4 the generator must NOT be "
            "called; return a clarification request to the user instead."
        )

    placement_by_id = {p.node_id: p for p in previous_placement.placements}
    frozen_placements: List[FrozenNode] = []
    for node_id in constraint.frozen_node_ids:
        entry = placement_by_id.get(node_id)
        if entry is None:
            raise ValueError(f"frozen_node_id {node_id} not found in previous_placement")
        frozen_placements.append(entry.model_copy())

    guidance = (base_guidance or GuidanceConfig()).model_copy(deep=True)
    mode = _CONSTRAINT_MODE.get(constraint.constraint_type)
    if mode is not None:
        weight = 2.0 if constraint.strength == Strength.HARD else 1.0
        reference_region = (
            constraint.reference.value if constraint.reference.type == ReferenceType.REGION else None
        )
        reference_point = (
            None
            if reference_region is not None
            else _resolve_reference_point(constraint, placement_by_id, graph)
        )
        guidance.spatial_directives.append(
            SpatialGuidanceDirective(
                node_ids=constraint.affected_node_ids,
                mode=mode,
                reference_point=reference_point,
                reference_region=reference_region,
                weight=weight,
            )
        )

    return frozen_placements, guidance
