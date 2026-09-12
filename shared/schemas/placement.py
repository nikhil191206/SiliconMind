"""Generator Output — Placement JSON — TECHNICAL.md Section 3.3.

Owned by Person B. Consumed by Person C (verification) and the visualizer.
"""

from enum import Enum

from pydantic import BaseModel


class Orientation(str, Enum):
    N = "N"
    S = "S"
    E = "E"
    W = "W"
    FN = "FN"
    FS = "FS"
    FE = "FE"
    FW = "FW"


class PlacementEntry(BaseModel):
    node_id: int
    x: float
    y: float
    orientation: Orientation


class GenerationMetadata(BaseModel):
    model_variant: str
    seed: int
    is_legalized: bool = False


class PlacementJSON(BaseModel):
    design_name: str
    placements: list[PlacementEntry]
    generation_metadata: GenerationMetadata
