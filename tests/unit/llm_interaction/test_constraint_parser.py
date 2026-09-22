"""Unit tests for Natural-Language Constraint Parser (Person D).

These specifically test the deterministic heuristic fallback path
(`_fallback_parse_heuristic`, exercised via `parse_constraint` when no LLM
credentials are available) — several are regression tests for bugs found in
that exact function. Real credentials (GROQ_API_KEY) are genuinely
configured in this project's .env now, so every test here explicitly clears
them via `_no_llm_credentials`; without that, `parse_constraint` would
silently start hitting the live Groq API instead of the function under
test, making these tests non-deterministic and network-dependent for no
reason. The real LLM path itself is exercised separately and manually
against live data (see modules/llm_interaction/NOTES.md), not here.
"""

import pytest

from modules.llm_interaction.constraint_parser import parse_constraint
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_placement import make_mock_placement
from shared.schemas.constraint import ConstraintType


@pytest.fixture
def _no_llm_credentials(monkeypatch):
    for var in ("GROQ_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_parse_constraint_valid_move_away(_no_llm_credentials):
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    constraint = parse_constraint("Move node_0 away from node_1", placement)

    assert not constraint.requires_clarification()
    assert 0 in constraint.affected_node_ids
    assert 0 not in constraint.frozen_node_ids
    assert 1 in constraint.frozen_node_ids
    assert constraint.constraint_type == ConstraintType.MOVE_AWAY_FROM


def test_parse_constraint_ambiguous_requires_clarification(_no_llm_credentials):
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    constraint = parse_constraint("Move that block away", placement)

    assert constraint.requires_clarification()
    assert constraint.constraint_type == ConstraintType.UNCLEAR or constraint.confidence < 0.6


def test_parse_constraint_distinguishes_underscore_joined_node_ids(_no_llm_credentials):
    """Regression test for the digit-extraction bug found during A/B/C/D
    integration (2026-09-18, see modules/llm_interaction/NOTES.md): a plain
    `\\b(\\d+)\\b` cannot match the "0" in "node_0" (underscore is a word
    character, so there's no boundary), which silently turned this exact
    phrase into a self-referential "move node 0 away from node 0" — a
    degenerate constraint that reached high confidence and, downstream,
    produced NaN in the generator (modules/generator/NOTES.md §5)."""
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    constraint = parse_constraint("Move node_0 away from node_1", placement)

    assert constraint.affected_node_ids == [0]
    assert constraint.reference.value == 1
    assert 1 not in constraint.affected_node_ids


def test_parse_constraint_frozen_node_ids_complement(_no_llm_credentials):
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    constraint = parse_constraint("Move node_0 closer to node_1", placement)

    all_node_ids = {p.node_id for p in placement.placements}
    affected_set = set(constraint.affected_node_ids)
    frozen_set = set(constraint.frozen_node_ids)

    assert affected_set.isdisjoint(frozen_set)
    assert affected_set | frozen_set == all_node_ids
