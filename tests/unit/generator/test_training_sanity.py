"""Sanity check ONLY: proves the training loop runs end to end and the
loss goes down on data the model can currently see. This is NOT a claim
that the model learns to place real chips well — that requires the real
datasets (TECHNICAL.md Section 1.13 / INSTRUCTIONS.md Section 2), which
are blocked until they're downloaded. Never treat these numbers as a
reportable result.
"""

import torch

from modules.generator.flow_matching import FlowMatchingGenerationStrategy
from modules.generator.training import Trainer, TrainerConfig
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_encoder_output import make_mock_encoder_output
from shared.mocks.mock_placement import make_mock_placement


def test_training_loss_decreases_on_a_single_overfit_example():
    torch.manual_seed(0)
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)
    placement = make_mock_placement(graph)

    strategy = FlowMatchingGenerationStrategy()
    trainer = Trainer(strategy, TrainerConfig(initial_lr=1e-2, num_epochs=1))

    examples = [(graph, encoder_output, placement)] * 300
    losses = trainer.fit(examples)

    early = sum(losses[:15]) / 15
    late = sum(losses[-15:]) / 15
    assert late < early


def test_train_step_runs_with_frozen_mask_excluded_from_loss():
    """Training-time frozen exclusion (base.py docstring) — separate from
    the sampling-time freeze guarantee tested in test_freeze_enforcement.py."""
    torch.manual_seed(0)
    graph = make_mock_circuit_graph()
    encoder_output = make_mock_encoder_output(graph, seed=0)

    strategy = FlowMatchingGenerationStrategy()
    z1 = torch.rand(graph.num_nodes, 2)
    frozen_mask = torch.zeros(graph.num_nodes, dtype=torch.bool)
    frozen_mask[0] = True

    loss = strategy.training_loss(
        node_embeddings=encoder_output.node_embeddings,
        global_embedding=encoder_output.global_embedding,
        z1=z1,
        frozen_mask=frozen_mask,
    )
    assert torch.isfinite(loss)
