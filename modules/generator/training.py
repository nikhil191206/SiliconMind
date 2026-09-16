"""Training loop for the generator — TECHNICAL.md Section 4.B,
workDistribution.md Person B ("owns... its training loop").

BLOCKED per INSTRUCTIONS.md Section 2: actually training on real chip
data cannot happen until the real datasets (TECHNICAL.md Section 1.13)
are downloaded — nothing this loop produces on mock data is a result.
`Trainer` is provided so the loop's correctness (does it run end to end,
does the loss go down on data it CAN currently see) is verified now;
swapping in a real `Dataset`/`DataLoader` over `data/processed/*.json`
once real data lands is then a change to what feeds `Trainer.fit()`, not
new training-loop code.

Optimizer note: Section 4.B doesn't repeat an optimizer choice for B the
way Section 4.A pins one for the encoders (Adam, initial LR 1e-3, cosine
decay), and `config/shared_config.yaml`'s `generator_defaults` block has
no `optimizer` key either — this reuses Section 4.A's convention rather
than inventing an unrelated one; flagged in NOTES.md as worth an explicit
team decision rather than a silent default.
"""

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import torch

from modules.generator.base import GenerationStrategy
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.encoder_output import EncoderOutput
from shared.schemas.placement import PlacementJSON

TrainingExample = Tuple[CircuitGraph, EncoderOutput, PlacementJSON]


@dataclass
class TrainerConfig:
    initial_lr: float = 1e-3
    num_epochs: int = 1


def target_tensor(graph: CircuitGraph, placement: PlacementJSON) -> torch.Tensor:
    """Ground-truth placement, normalized to [0,1] die-relative units in
    graph.nodes' node_id order — the same space `PlacementGenerator`
    samples in."""
    by_id = {p.node_id: p for p in placement.placements}
    rows = []
    for node in graph.nodes:
        entry = by_id[node.node_id]
        rows.append([entry.x / graph.die.width, entry.y / graph.die.height])
    return torch.tensor(rows, dtype=torch.float32)


class Trainer:
    def __init__(self, strategy: GenerationStrategy, config: Optional[TrainerConfig] = None):
        self.strategy = strategy
        self.config = config or TrainerConfig()
        self.optimizer = torch.optim.Adam(self.strategy.backbone.parameters(), lr=self.config.initial_lr)
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=max(self.config.num_epochs, 1)
        )

    def train_step(self, graph: CircuitGraph, encoder_output: EncoderOutput, placement: PlacementJSON) -> float:
        self.optimizer.zero_grad()
        z1 = target_tensor(graph, placement)
        loss = self.strategy.training_loss(
            node_embeddings=encoder_output.node_embeddings,
            global_embedding=encoder_output.global_embedding,
            z1=z1,
        )
        loss.backward()
        self.optimizer.step()
        return loss.item()

    def fit(self, examples: Iterable[TrainingExample]) -> List[float]:
        examples = list(examples)
        losses = []
        for _ in range(self.config.num_epochs):
            for graph, encoder_output, placement in examples:
                losses.append(self.train_step(graph, encoder_output, placement))
            self.scheduler.step()
        return losses
