"""Freeze/Constraint Object — the D -> B interface for editing.

TECHNICAL.md Section 3.4. Owned jointly by Person D and Person B.

Hard rule (Section 3.4 / 1.7): if constraint_type == UNCLEAR or
confidence < 0.6, B's generator must NOT be called — D returns a
clarification request to the user instead.
"""

from enum import Enum
from typing import Union
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ConstraintType(str, Enum):
    MOVE_AWAY_FROM = "MOVE_AWAY_FROM"
    MOVE_TOWARD = "MOVE_TOWARD"
    FORBID_ADJACENT = "FORBID_ADJACENT"
    FORBID_REGION = "FORBID_REGION"
    PREFER_REGION = "PREFER_REGION"
    UNCLEAR = "UNCLEAR"


class ReferenceType(str, Enum):
    NODE = "NODE"
    REGION = "REGION"
    EDGE = "EDGE"


class RegionBoundingBox(BaseModel):
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class ConstraintReference(BaseModel):
    type: ReferenceType
    value: Union[int, RegionBoundingBox]


class Strength(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"


class ConstraintObject(BaseModel):
    constraint_id: str = Field(default_factory=lambda: str(uuid4()))
    source_request: str
    frozen_node_ids: list[int]
    affected_node_ids: list[int]
    constraint_type: ConstraintType
    reference: ConstraintReference
    strength: Strength
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("confidence")
    @classmethod
    def _flag_low_confidence(cls, v: float) -> float:
        # Validation only checks range; the "route to clarification instead of
        # calling B" rule is enforced by the caller (Section 3.4), not here.
        return v

    def requires_clarification(self) -> bool:
        return self.constraint_type == ConstraintType.UNCLEAR or self.confidence < 0.6
