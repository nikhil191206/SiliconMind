"""Unit tests for Placement Diff Reporting (Person D)."""

import pytest

from modules.llm_interaction.diff_report import format_diff_summary, generate_diff_report
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_constraint import make_mock_move_away_constraint
from shared.mocks.mock_placement import make_mock_placement
from shared.schemas.metrics import MetricsObject


def test_diff_report_no_movement():
    graph = make_mock_circuit_graph()
    before = make_mock_placement(graph)
    after = before.model_copy(deep=True)
    constraint = make_mock_move_away_constraint()

    report = generate_diff_report(before, after, constraint)
    assert len(report.moved_nodes) == 0
    assert len(report.unexpected_moves) == 0


def test_diff_report_moved_node_and_unexpected_move():
    graph = make_mock_circuit_graph()
    before = make_mock_placement(graph)
    after = before.model_copy(deep=True)

    # Move node 0 (affected) and node 1 (frozen)
    after.placements[0].x += 25.0
    after.placements[1].y += 15.0

    constraint = make_mock_move_away_constraint()
    constraint.affected_node_ids = [0]
    constraint.frozen_node_ids = [1, 2, 3, 4]

    report = generate_diff_report(before, after, constraint)
    assert len(report.moved_nodes) == 2
    assert 1 in report.unexpected_moves
    assert 0 not in report.unexpected_moves


def test_diff_report_metric_deltas():
    graph = make_mock_circuit_graph()
    before = make_mock_placement(graph)
    after = before.model_copy(deep=True)
    constraint = make_mock_move_away_constraint()

    mb = MetricsObject(hpwl=100.0, congestion_overflow=10.0, legality_violations=0, runtime_seconds=1.0)
    ma = MetricsObject(hpwl=90.0, congestion_overflow=8.0, legality_violations=0, runtime_seconds=1.0)

    report = generate_diff_report(before, after, constraint, metrics_before=mb, metrics_after=ma)
    assert report.hpwl_delta == pytest.approx(-10.0)
    assert report.congestion_delta == pytest.approx(-2.0)

    summary = format_diff_summary(report, constraint)
    assert "Placement Change Diff Report" in summary
