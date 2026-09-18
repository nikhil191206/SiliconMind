"""B -> C second-wave integration (INSTRUCTIONS.md Section 1.2, second
bullet): feed Person B's REAL generator output into Person C's REAL
legalize_and_score, on the mock circuit graph, confirming the full pipeline
runs end to end up to the external-tool boundary.

DREAMPlace/OpenROAD are not installed in this dev environment (by design,
per modules/evaluation/NOTES.md Section 1.1 — these are genuinely blocked,
not faked around). So "runs end to end" here means: the CircuitGraph ->
PlacementJSON -> Bookshelf write -> DREAMPlace-invocation handoff is
schema-correct and fails at exactly the documented external-tool boundary
(a typed DreamplaceNotInstalledError), not at some earlier schema mismatch
or crash. That distinction — the right kind of failure vs. a wrong one — is
exactly what this test proves.
"""

import pytest

from modules.encoders.de_hnn import DEHNNEncoder
from modules.evaluation.dreamplace_runner import DreamplaceNotInstalledError
from modules.evaluation.legalizer import legalize_and_score
from modules.generator.generator import PlacementGenerator
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph


def test_real_generator_output_reaches_the_dreamplace_boundary_cleanly():
    graph = make_mock_circuit_graph()
    encoder_output = DEHNNEncoder().encode(graph)
    placement = PlacementGenerator().generate(encoder_output, graph, seed=0)

    assert placement.generation_metadata.is_legalized is False

    with pytest.raises(DreamplaceNotInstalledError):
        legalize_and_score(placement, graph)


def test_bookshelf_round_trip_of_a_real_generator_placement():
    """Even without DREAMPlace installed, the Bookshelf writer (the part of
    C's pipeline that runs before the external tool call) must accept a
    real PlacementGenerator output and round-trip it losslessly — this is
    the part of the B->C handoff that doesn't need DREAMPlace at all."""
    from modules.evaluation import bookshelf_io

    graph = make_mock_circuit_graph()
    encoder_output = DEHNNEncoder().encode(graph)
    placement = PlacementGenerator().generate(encoder_output, graph, seed=0)

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        aux_path = bookshelf_io.write_bookshelf(graph, placement, Path(tmp))
        pl_path = aux_path.parent / f"{graph.design_name}.pl"
        round_tripped = bookshelf_io.read_bookshelf_placement(
            pl_path,
            design_name=graph.design_name,
            model_variant=placement.generation_metadata.model_variant,
            seed=placement.generation_metadata.seed,
        )

    original_by_id = {p.node_id: (round(p.x, 3), round(p.y, 3)) for p in placement.placements}
    round_tripped_by_id = {p.node_id: (round(p.x, 3), round(p.y, 3)) for p in round_tripped.placements}
    assert original_by_id == round_tripped_by_id
