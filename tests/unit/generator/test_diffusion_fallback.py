"""Diffusion is the explicit fallback strategy (TECHNICAL.md Section 4.B:
"only if flow-matching underperforms in practice"). These tests confirm
it's a real drop-in swap behind the same GenerationStrategy interface,
including the same non-negotiable freeze guarantee (Section 1.7) — not
just that flow matching alone satisfies it.
"""

import torch

from modules.generator.diffusion import DiffusionGenerationStrategy
from modules.generator.generator import PlacementGenerator
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_encoder_output import make_mock_encoder_output
from shared.schemas.placement import Orientation, PlacementEntry


def test_diffusion_strategy_is_swappable_into_placement_generator():
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)
    generator = PlacementGenerator(strategy=DiffusionGenerationStrategy(train_steps=100))

    frozen = [PlacementEntry(node_id=2, x=20.0, y=20.0, orientation=Orientation.W)]
    result = generator.generate(encoder_output, graph, frozen_placements=frozen, seed=0)

    out = next(p for p in result.placements if p.node_id == 2)
    assert out.x == 20.0
    assert out.y == 20.0
    assert out.orientation == Orientation.W
    assert {p.node_id for p in result.placements} == {n.node_id for n in graph.nodes}


def test_diffusion_training_loss_is_finite():
    torch.manual_seed(0)
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)
    strategy = DiffusionGenerationStrategy(train_steps=100)

    z1 = torch.rand(graph.num_nodes, 2)
    loss = strategy.training_loss(
        node_embeddings=encoder_output.node_embeddings,
        global_embedding=encoder_output.global_embedding,
        z1=z1,
    )
    assert torch.isfinite(loss)
