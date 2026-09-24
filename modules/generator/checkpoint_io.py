"""Loads a trained generator + its paired frozen encoder from a checkpoint
produced by experiments/train_generator.py.

Both DEHNNEncoder and PlacementGenerator already accept an injected
model/strategy (their __init__ signatures were built for exactly this),
so this module is a thin, explicit assembly point -- not new model code.

The encoder's weights MUST come from the same checkpoint as the generator's:
DE-HNN is used frozen/randomly-initialized in the current training script
(see that module's docstring), so a fresh DEHNNEncoder() would have
different random weights than what the generator was actually trained
against, making its output meaningless. Loading them as a pair is not
optional.
"""

from pathlib import Path
from typing import Optional, Tuple

import torch

from modules.encoders.de_hnn import DEHNNEncoder, DEHNNModel
from modules.generator.flow_matching import FlowMatchingGenerationStrategy
from modules.generator.generator import PlacementGenerator
from modules.generator.network import PlacementBackbone


class GeneratorCheckpointNotFoundError(FileNotFoundError):
    """Raised when no trained checkpoint exists yet -- e.g. training is
    still running, or hasn't been launched. Callers must handle this
    explicitly (see backend/main.py) rather than silently falling back to
    an untrained network and calling it a real result."""


def load_trained_pipeline(checkpoint_path: Path, device: str = "cpu") -> Tuple[DEHNNEncoder, PlacementGenerator, dict]:
    """Returns (encoder, generator, checkpoint_metadata). Both models are
    loaded in eval mode -- generator training's own loop switches the
    backbone back to .train() each epoch, but a checkpoint consumed here is
    for inference, and PlacementGenerator's own sample() path already calls
    .eval() internally regardless (flow_matching.py), so this is
    belt-and-suspenders, not load-bearing."""
    if not checkpoint_path.exists():
        raise GeneratorCheckpointNotFoundError(
            f"no trained generator checkpoint at {checkpoint_path} -- run experiments/train_generator.py first"
        )
    ckpt = torch.load(checkpoint_path, map_location=device)

    encoder_model = DEHNNModel()
    encoder_model.load_state_dict(ckpt["encoder_state_dict"])
    encoder_model.eval()
    encoder = DEHNNEncoder(model=encoder_model)

    backbone = PlacementBackbone()
    backbone.load_state_dict(ckpt["backbone_state_dict"])
    backbone.eval()
    strategy = FlowMatchingGenerationStrategy(backbone=backbone)
    generator = PlacementGenerator(strategy=strategy)

    metadata = {
        "train_designs": ckpt.get("train_designs"),
        "epochs_completed": ckpt.get("epochs_completed"),
        "epochs_target": ckpt.get("epochs_target"),
        "train_loss": ckpt.get("train_loss"),
        "seed": ckpt.get("seed"),
    }
    return encoder, generator, metadata


def try_load_trained_pipeline(checkpoint_path: Path, device: str = "cpu") -> Optional[Tuple[DEHNNEncoder, PlacementGenerator, dict]]:
    """Same as load_trained_pipeline, but returns None instead of raising
    when the checkpoint doesn't exist -- for the backend's real, honest
    startup fallback path (serve from an untrained network AND say so via
    generation_metadata, per this project's no-silent-fallback rule) rather
    than crashing the whole API if training hasn't produced a checkpoint
    yet."""
    try:
        return load_trained_pipeline(checkpoint_path, device=device)
    except GeneratorCheckpointNotFoundError:
        return None
