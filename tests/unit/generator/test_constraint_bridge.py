import pytest

from modules.generator.freeze import ConstraintRequiresClarificationError, constraint_to_generation_inputs
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_constraint import (
    make_mock_forbid_region_constraint,
    make_mock_move_away_constraint,
    make_mock_unclear_constraint,
)
from shared.mocks.mock_placement import make_mock_placement


def test_unclear_constraint_raises_before_touching_generator():
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    constraint = make_mock_unclear_constraint()

    with pytest.raises(ConstraintRequiresClarificationError):
        constraint_to_generation_inputs(constraint, placement)


def test_low_confidence_constraint_also_raises_even_if_type_is_clear():
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    constraint = make_mock_move_away_constraint()
    constraint.confidence = 0.4  # below the 0.6 threshold, Section 3.4

    with pytest.raises(ConstraintRequiresClarificationError):
        constraint_to_generation_inputs(constraint, placement)


def test_move_away_constraint_freezes_the_complement_and_builds_directive():
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    constraint = make_mock_move_away_constraint()

    frozen, guidance = constraint_to_generation_inputs(constraint, placement)

    assert {fp.node_id for fp in frozen} == set(constraint.frozen_node_ids)
    assert len(guidance.spatial_directives) == 1
    directive = guidance.spatial_directives[0]
    assert directive.mode == "away_from"
    assert set(directive.node_ids) == set(constraint.affected_node_ids)
    assert directive.reference_point is not None
    assert directive.weight == 2.0  # HARD strength in the mock


def test_forbid_region_constraint_builds_region_directive():
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    constraint = make_mock_forbid_region_constraint()

    frozen, guidance = constraint_to_generation_inputs(constraint, placement)

    directive = guidance.spatial_directives[0]
    assert directive.mode == "avoid_region"
    assert directive.reference_region is not None
    assert directive.reference_point is None
    assert directive.weight == 1.0  # SOFT strength in the mock


def test_missing_frozen_node_in_previous_placement_raises():
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    constraint = make_mock_move_away_constraint()
    constraint.frozen_node_ids = constraint.frozen_node_ids + [999]

    with pytest.raises(ValueError):
        constraint_to_generation_inputs(constraint, placement)
