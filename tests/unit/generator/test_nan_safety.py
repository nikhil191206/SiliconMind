"""TECHNICAL.md Section 7: "Generator produces NaN/invalid coordinates:
B's generate() must validate its own output before returning; on failure,
retry once with a new seed, then raise an explicit error rather than
silently passing invalid data to C." This was spec'd but unimplemented
until the A/B/C/D integration pass found a real NaN-producing bug in
SpatialGuidance (see modules/generator/NOTES.md §5) — these tests cover
both the general safety net and the specific regression that motivated it.
"""

import pytest
import torch

from modules.encoders.de_hnn import DEHNNEncoder
from modules.generator.base import GenerationStrategy
from modules.generator.generator import GenerationProducedInvalidCoordinatesError, PlacementGenerator
from modules.generator.types import GuidanceConfig, SpatialGuidanceDirective
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_encoder_output import make_mock_encoder_output


class _AlwaysNaNStrategy(GenerationStrategy):
    """Deterministically pathological strategy: always samples NaN,
    regardless of seed — used to test the "retry once, then raise" path
    without depending on ever actually reproducing a real divergence."""

    def __init__(self):
        self.backbone = torch.nn.Identity()

    def training_loss(self, *args, **kwargs):
        raise NotImplementedError

    def sample(self, node_embeddings, global_embedding, num_nodes, **kwargs):
        return torch.full((num_nodes, 2), float("nan"))


class _NaNOnFirstSeedOnlyStrategy(GenerationStrategy):
    """Fails only for a specific seed value, to prove the retry actually
    uses a different (seed + 1) generator rather than just calling the same
    thing twice."""

    def __init__(self, poisoned_seed_value: int):
        self.backbone = torch.nn.Identity()
        self._poisoned_seed_value = poisoned_seed_value

    def training_loss(self, *args, **kwargs):
        raise NotImplementedError

    def sample(self, node_embeddings, global_embedding, num_nodes, generator=None, **kwargs):
        # torch.Generator has no public "seed value" getter, so we detect
        # which call this is by drawing one number from it deterministically.
        marker = torch.randint(0, 2**31 - 1, (1,), generator=generator).item()
        if marker == self._poisoned_seed_value:
            return torch.full((num_nodes, 2), float("nan"))
        return torch.rand((num_nodes, 2), generator=generator)


def test_generate_raises_explicit_error_when_sampling_always_produces_nan():
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)
    generator = PlacementGenerator(strategy=_AlwaysNaNStrategy())

    with pytest.raises(GenerationProducedInvalidCoordinatesError):
        generator.generate(encoder_output, graph, seed=0)


def test_generate_retries_once_with_a_different_seed_before_giving_up():
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)

    # Find what the first draw from seed=0's generator looks like, so the
    # fake strategy can poison exactly that one and let seed=1's retry
    # (a different draw) succeed.
    poisoned_marker = torch.randint(0, 2**31 - 1, (1,), generator=torch.Generator().manual_seed(0)).item()

    generator = PlacementGenerator(strategy=_NaNOnFirstSeedOnlyStrategy(poisoned_marker))
    result = generator.generate(encoder_output, graph, seed=0)

    for p in result.placements:
        assert p.x == p.x  # NaN != NaN; this fails fast and readably if it regresses
        assert p.y == p.y


def test_generate_with_real_encoder_and_away_from_guidance_produces_finite_coordinates():
    """The exact end-to-end scenario that originally produced NaN: a real
    DE-HNN encoder, a real flow-matching generator, and a MOVE_AWAY_FROM
    spatial guidance directive on an unfrozen node. Must now be finite."""
    graph = make_mock_circuit_graph()
    encoder_output = DEHNNEncoder().encode(graph)
    generator = PlacementGenerator()

    initial = generator.generate(encoder_output, graph, seed=42)
    frozen = [p for p in initial.placements if p.node_id != 0]
    guidance = GuidanceConfig(
        spatial_directives=[SpatialGuidanceDirective(node_ids=[0], mode="away_from", reference_point=(80.0, 20.0), weight=1.0)]
    )

    edited = generator.generate(encoder_output, graph, frozen_placements=frozen, guidance_terms=guidance, seed=42)

    for p in edited.placements:
        assert p.x == p.x and p.y == p.y  # not NaN
        assert 0.0 <= p.x <= graph.die.width
        assert 0.0 <= p.y <= graph.die.height
