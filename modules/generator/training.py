"""Training loop for the generator — TECHNICAL.md Section 4.B,
workDistribution.md Person B ("owns... its training loop").

BLOCKED per INSTRUCTIONS.md Section 2: actually training on real chip
data cannot happen in this environment — `data/raw/`/`data/processed/`
are gitignored per-design, and this checkout has neither. (Elsewhere on
the team, per `data/README.md` and `config/shared_config.yaml`'s
`dataset_split`, all seven sources are now downloaded and `train_chips`/
`test_chips` are filled in from 3.1M real processed nodes — so real
training is no longer blocked on data existing, only on this environment
having a copy of it.) `Trainer` is provided so the loop's correctness
(does it run end to end, does the loss go down on data it CAN currently
see) is verified now; swapping in a real `Dataset`/`DataLoader` over
`data/processed/*.json` is then a change to what feeds `Trainer.fit()`,
not new training-loop code.

Optimizer: `config/shared_config.yaml`'s `generator_defaults.optimizer`
(Adam, initial LR 1e-3, cosine decay) is the single source of truth per
Section 5.2, formalizing what this module had been using as an unstated
Python-level default — see `TrainerConfig.from_shared_config()`, which
mirrors `modules/encoders/graph_utils.py`'s `NodeFeatureNormalization.from_shared_config()`
convention exactly (explicit error if the config block is missing, no
silent fallback).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import torch
import yaml

from modules.generator.base import GenerationStrategy
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.encoder_output import EncoderOutput
from shared.schemas.placement import PlacementJSON

TrainingExample = Tuple[CircuitGraph, EncoderOutput, PlacementJSON]


@dataclass
class TrainerConfig:
    initial_lr: float = 1e-3
    num_epochs: int = 1

    @classmethod
    def from_shared_config(cls, config_path: Optional[Path] = None, num_epochs: int = 1) -> "TrainerConfig":
        """`num_epochs` is a run-specific choice, not a project-wide
        convention (shared_config.yaml's `generator_defaults.optimizer`
        has no epoch count, same as `encoder_defaults.optimizer`), so it
        stays a plain argument here rather than being read from the file."""
        path = config_path or Path(__file__).resolve().parents[2] / "config" / "shared_config.yaml"
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        try:
            optimizer = config["generator_defaults"]["optimizer"]
        except KeyError as exc:
            raise KeyError(
                "config/shared_config.yaml has no generator_defaults.optimizer block yet — "
                "add one (mirroring encoder_defaults.optimizer) before training the generator "
                "on real data."
            ) from exc
        if optimizer["type"] != "adam" or optimizer["lr_schedule"] != "cosine_decay":
            raise NotImplementedError(
                f"generator_defaults.optimizer specifies {optimizer['type']!r}/{optimizer['lr_schedule']!r}, "
                "but Trainer only implements Adam + cosine decay — update Trainer to match before "
                "using this config for a real run."
            )
        return cls(initial_lr=optimizer["initial_lr"], num_epochs=num_epochs)


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
