"""Tests against the REAL, live LLM-backed constraint-parsing path (Groq),
as opposed to test_constraint_parser.py's deterministic heuristic-fallback
tests. Skipped (not faked) on any machine without real credentials
configured — never mocked, since the whole point is proving the live path
genuinely works end-to-end."""

import os

import pytest

from modules.encoders.de_hnn import DEHNNEncoder
from modules.generator.generator import PlacementGenerator
from modules.llm_interaction.constraint_parser import parse_constraint
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.schemas.constraint import ConstraintType, ReferenceType

pytestmark = pytest.mark.skipif(
    not (os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY")),
    reason="no live LLM credentials configured (GROQ_API_KEY/OPENAI_API_KEY)",
)


@pytest.fixture(scope="module")
def real_placement():
    graph = make_mock_circuit_graph()
    encoder_output = DEHNNEncoder().encode(graph)
    placement = PlacementGenerator().generate(encoder_output, graph, seed=0)
    return graph, placement


def test_live_llm_parses_move_away_from_specific_node(real_placement):
    graph, placement = real_placement
    constraint = parse_constraint("please move node 0 far away from node 3, this is important", placement, graph=graph)

    assert constraint.constraint_type == ConstraintType.MOVE_AWAY_FROM
    assert constraint.affected_node_ids == [0]
    assert constraint.reference.type == ReferenceType.NODE
    assert constraint.reference.value == 3
    assert not constraint.requires_clarification()


def test_live_llm_parses_forbid_region_with_real_bounding_box(real_placement):
    """Regression coverage for the reference_region gap: the live LLM path
    previously never constructed a real RegionBoundingBox for FORBID_REGION/
    PREFER_REGION, only ever parsing (and mis-typing) a node id. Fixed
    2026-09-21 — see modules/llm_interaction/NOTES.md.

    Only checks that a real, valid bounding box was constructed — NOT which
    specific corner the model picked. A live model's exact interpretation of
    "top-left" (e.g. which axis direction counts as "top") is its own
    judgment call and was observed to vary run-to-run even at temperature=0;
    asserting a specific corner would be testing the model's phrasing
    preference, not this code's correctness."""
    graph, placement = real_placement
    constraint = parse_constraint(
        "Node 2 must never be placed inside the top-left corner region of the die", placement, graph=graph
    )

    assert constraint.constraint_type == ConstraintType.FORBID_REGION
    assert constraint.reference.type == ReferenceType.REGION
    region = constraint.reference.value
    assert 0.0 <= region.x_min < region.x_max <= graph.die.width
    assert 0.0 <= region.y_min < region.y_max <= graph.die.height


def test_live_llm_ambiguous_request_requires_clarification(real_placement):
    graph, placement = real_placement
    constraint = parse_constraint("make it better somehow", placement, graph=graph)

    assert constraint.requires_clarification()
