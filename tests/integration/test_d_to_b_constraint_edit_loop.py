"""D -> B second-wave integration (INSTRUCTIONS.md Section 1.2, third
bullet): feed a parsed ConstraintObject into Person B's REAL freeze-mask
logic, confirming the interface holds. Person D's real LLM constraint
parser doesn't exist yet, so this uses shared/mocks/mock_constraint.py's
examples as the stand-in for "a parsed ConstraintObject" — exactly the
mock-first pattern INSTRUCTIONS.md prescribes, applied one level up from
B's own unit tests (test_constraint_bridge.py tests freeze.py in isolation;
this test drives a full generate -> edit -> regenerate cycle through the
REAL PlacementGenerator, twice).

This is also the direct, code-level check on TECHNICAL.md Section 1.7's
drift guarantee end-to-end: a full edit cycle, not just a unit test on
build_frozen_mask in isolation.
"""

import pytest

from modules.encoders.gcn import GCNEncoder
from modules.generator.freeze import ConstraintRequiresClarificationError, constraint_to_generation_inputs
from modules.generator.generator import PlacementGenerator
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_constraint import (
    make_mock_forbid_region_constraint,
    make_mock_move_away_constraint,
    make_mock_unclear_constraint,
)


def _placements_by_id(placement):
    return {p.node_id: (p.x, p.y, p.orientation) for p in placement.placements}


@pytest.mark.parametrize(
    "make_constraint", [make_mock_move_away_constraint, make_mock_forbid_region_constraint]
)
def test_full_edit_cycle_leaves_frozen_nodes_bit_identical(make_constraint):
    graph = make_mock_circuit_graph()
    encoder_output = GCNEncoder().encode(graph)
    generator = PlacementGenerator()

    initial = generator.generate(encoder_output, graph, seed=0)

    constraint = make_constraint()
    frozen_placements, guidance = constraint_to_generation_inputs(constraint, initial, graph=graph)
    edited = generator.generate(
        encoder_output, graph, frozen_placements=frozen_placements, guidance_terms=guidance, seed=1
    )

    initial_by_id = _placements_by_id(initial)
    edited_by_id = _placements_by_id(edited)

    # Section 1.7 / Section 3.6's unexpected_moves check: every frozen node
    # must be exactly unchanged, not just "close."
    for node_id in constraint.frozen_node_ids:
        assert edited_by_id[node_id] == initial_by_id[node_id], (
            f"node {node_id} was supposed to be frozen but moved during the edit"
        )


def test_unclear_constraint_never_reaches_the_generator():
    """Section 3.4's hard gate: constraint_type == UNCLEAR (or confidence
    < 0.6) must raise before B's generate() is ever called, never silently
    regenerate on a guess."""
    graph = make_mock_circuit_graph()
    encoder_output = GCNEncoder().encode(graph)
    generator = PlacementGenerator()
    initial = generator.generate(encoder_output, graph, seed=0)

    constraint = make_mock_unclear_constraint()
    with pytest.raises(ConstraintRequiresClarificationError):
        constraint_to_generation_inputs(constraint, initial, graph=graph)
