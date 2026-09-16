"""Local types for Person B's generator.

TECHNICAL.md Section 4.B's `generate()` signature references two types by
name, `FrozenNode` and `GuidanceConfig`, that are not defined anywhere in
`shared/schemas/`. Both are defined here, inside Person B's own module,
since neither is a cross-module contract in the sense Section 3 means it
(Section 3 lists exactly six contracts, 3.1-3.6; these two names appear
only in Section 4.B's code signature, not in Section 3) — see NOTES.md for
the full reasoning.

FrozenNode
----------
A frozen node needs both its identity (node_id) and its fixed, must-not-
move coordinate + orientation. That is exactly `PlacementEntry`'s shape
(Section 3.3, owned by Person B already), so `FrozenNode` is a type alias
for it rather than a redefinition of the same three fields under a new
name.

GuidanceConfig
--------------
Section 4.B says: "Guidance weight for legality/wirelength/congestion
terms: start at equal weighting, tune via ablation." `config/shared_config.yaml`
mirrors this with `generator_defaults.guidance_weights` (legality /
wirelength / congestion, default 1.0 each) — those three fields are
reproduced here exactly.

`spatial_directives` is an *addition* beyond Section 4.B's literal three
weights. It exists to carry the D -> B directional intent from a
Section 3.4 `ConstraintObject` (MOVE_AWAY_FROM / MOVE_TOWARD /
FORBID_REGION / PREFER_REGION) into the sampler's guidance function — the
three fixed weights alone have no channel for "away from *this specific
node*" vs "away from *that specific region*". See `freeze.py` for where
these get constructed from a real ConstraintObject, and NOTES.md for why
this is flagged as a designed extension pending team review rather than
silently treated as part of the frozen Section 4.B contract.
"""

from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from shared.schemas.constraint import RegionBoundingBox
from shared.schemas.placement import PlacementEntry

# Section 3.3 already defines the exact shape a frozen node needs.
FrozenNode = PlacementEntry


class SpatialGuidanceDirective(BaseModel):
    """One directional nudge for a set of (unfrozen) affected nodes, derived
    from a single ConstraintObject (Section 3.4). See freeze.py."""

    node_ids: List[int]
    mode: str  # "away_from" | "toward" | "avoid_region" | "prefer_region"
    reference_point: Optional[Tuple[float, float]] = None
    reference_region: Optional[RegionBoundingBox] = None
    weight: float = 1.0


class GuidanceConfig(BaseModel):
    """Mirrors config/shared_config.yaml's `generator_defaults.guidance_weights`
    (TECHNICAL.md Section 4.B). `spatial_directives` is Person B's own
    extension (see module docstring) for directional NL-edit guidance."""

    legality_weight: float = 1.0
    wirelength_weight: float = 1.0
    congestion_weight: float = 1.0
    spatial_directives: List[SpatialGuidanceDirective] = Field(default_factory=list)

    @classmethod
    def from_shared_config(cls, cfg: dict) -> "GuidanceConfig":
        weights = cfg["generator_defaults"]["guidance_weights"]
        return cls(
            legality_weight=weights["legality"],
            wirelength_weight=weights["wirelength"],
            congestion_weight=weights["congestion"],
        )
