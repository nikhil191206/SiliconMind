"""Hand-written example ConstraintObjects, one per major constraint_type.

Lets Person B and D jointly test the freeze/regenerate interface before the
real LLM parser exists.
"""

from shared.schemas.constraint import (
    ConstraintObject,
    ConstraintReference,
    ConstraintType,
    ReferenceType,
    RegionBoundingBox,
    Strength,
)


def make_mock_move_away_constraint() -> ConstraintObject:
    return ConstraintObject(
        source_request="move node 3 away from node 5",
        frozen_node_ids=[0, 1, 2, 4, 6, 7],
        affected_node_ids=[3, 5],
        constraint_type=ConstraintType.MOVE_AWAY_FROM,
        reference=ConstraintReference(type=ReferenceType.NODE, value=5),
        strength=Strength.HARD,
        confidence=0.92,
    )


def make_mock_forbid_region_constraint() -> ConstraintObject:
    return ConstraintObject(
        source_request="keep node 2 out of the top-left corner",
        frozen_node_ids=[0, 1, 3, 4, 5, 6, 7],
        affected_node_ids=[2],
        constraint_type=ConstraintType.FORBID_REGION,
        reference=ConstraintReference(
            type=ReferenceType.REGION, value=RegionBoundingBox(x_min=0, y_min=70, x_max=30, y_max=100)
        ),
        strength=Strength.SOFT,
        confidence=0.81,
    )


def make_mock_unclear_constraint() -> ConstraintObject:
    return ConstraintObject(
        source_request="make it better",
        frozen_node_ids=[0, 1, 2, 3, 4, 5, 6, 7],
        affected_node_ids=[],
        constraint_type=ConstraintType.UNCLEAR,
        reference=ConstraintReference(type=ReferenceType.NODE, value=0),
        strength=Strength.SOFT,
        confidence=0.2,
    )
