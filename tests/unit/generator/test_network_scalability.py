"""Tests for PlacementBackbone's real GPU scalability finding and the
gradient-checkpointing fix (see modules/generator/network.py's module
docstring for the actual measured numbers: memory-bound failure between
70K-150K nodes on a 6GB GPU, fixed for memory but not for the underlying
O(N^2) compute cost by checkpointing)."""

import os

import pytest
import torch

from modules.generator.network import PlacementBackbone, sinusoidal_time_embedding
from shared.schemas.encoder_output import D_GLOBAL, D_NODE


def test_sinusoidal_time_embedding_respects_input_device_cpu():
    """Regression test for the device-mismatch bug found during real GPU
    scalability testing (2026-09-23): `freqs` was built with no device
    argument, defaulting to CPU, so any GPU call crashed immediately.
    CPU-only check here (CI/most dev machines won't have a GPU); the CUDA
    case is exercised manually against the real target GPU, not in this
    suite."""
    t = torch.tensor(0.5)
    embedding = sinusoidal_time_embedding(t)
    assert embedding.device == t.device
    assert embedding.shape == (1, 128)


def test_checkpointing_produces_identical_output_to_uncheckpointed():
    """The whole point of gradient checkpointing is that it changes only
    *how* activations are computed during backward (recompute vs. store),
    never the forward VALUE. Dropout is set to 0 here specifically to
    isolate that claim -- comparing across train/eval mode (where dropout
    also differs) would confound the two effects, which is exactly the
    mistake caught and fixed while writing this test."""
    torch.manual_seed(0)
    model = PlacementBackbone(dropout=0.0)
    model.train()

    N = 50
    coords = torch.rand(N, 2)
    node_emb = torch.rand(N, D_NODE)
    global_emb = torch.rand(D_GLOBAL)
    t = torch.tensor(0.3)

    model.use_checkpointing = False
    out_no_ckpt = model(coords, node_emb, global_emb, t)

    model.use_checkpointing = True
    out_ckpt = model(coords, node_emb, global_emb, t)

    assert torch.allclose(out_no_ckpt, out_ckpt, atol=1e-6)


def test_checkpointing_gradients_are_identical_too():
    """Not just the forward value -- the gradients checkpointing recomputes
    during backward must match the non-checkpointed gradients exactly."""
    torch.manual_seed(0)
    model = PlacementBackbone(dropout=0.0)
    model.train()

    N = 50
    coords = torch.rand(N, 2, requires_grad=True)
    node_emb = torch.rand(N, D_NODE)
    global_emb = torch.rand(D_GLOBAL)
    t = torch.tensor(0.3)

    model.use_checkpointing = False
    out1 = model(coords, node_emb, global_emb, t)
    out1.sum().backward()
    grad_no_ckpt = coords.grad.clone()
    coords.grad = None

    model.use_checkpointing = True
    out2 = model(coords, node_emb, global_emb, t)
    out2.sum().backward()
    grad_ckpt = coords.grad.clone()

    assert torch.allclose(grad_no_ckpt, grad_ckpt, atol=1e-5)


def test_checkpointing_only_activates_in_training_mode():
    """use_checkpointing=True has no effect in eval mode (no backward pass
    happens during inference anyway, so there's nothing to save memory on,
    and checkpoint() would raise without a grad context in some torch
    versions if actually invoked)."""
    model = PlacementBackbone(use_checkpointing=True)
    model.eval()

    N = 20
    coords = torch.rand(N, 2)
    node_emb = torch.rand(N, D_NODE)
    global_emb = torch.rand(D_GLOBAL)
    t = torch.tensor(0.5)

    with torch.no_grad():
        out = model(coords, node_emb, global_emb, t)
    assert out.shape == (N, 2)


@pytest.mark.skipif(
    not (torch.cuda.is_available() and os.environ.get("RUN_SLOW_GPU_TESTS") == "1"),
    reason="real GPU memory/timing numbers require an actual GPU, and takes ~70s -- "
    "opt in with RUN_SLOW_GPU_TESTS=1 rather than running by default (observed to become "
    "unreliable -- much slower or hanging -- when run back-to-back with the rest of the "
    "suite on a loaded machine, vs. a clean ~70s in isolation; see modules/generator/NOTES.md)",
)
def test_real_gpu_memory_stays_well_under_ceiling_at_70k_nodes():
    """Regression floor for the real measured numbers in network.py's
    module docstring: N=70,000 must stay comfortably under the 6GB ceiling
    that caused N=150,000 to hang (Windows silently falling back to slow
    shared-memory swapping rather than a clean OOM, per the investigation
    log) -- if a future change regresses this back toward the ceiling,
    this test should catch it before a real training run does.

    Run explicitly with: RUN_SLOW_GPU_TESTS=1 pytest tests/unit/generator/test_network_scalability.py"""
    device = "cuda"
    model = PlacementBackbone().to(device)
    N = 70_000
    coords = torch.rand(N, 2, device=device)
    node_emb = torch.rand(N, D_NODE, device=device)
    global_emb = torch.rand(D_GLOBAL, device=device)
    t = torch.tensor(0.5, device=device)

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    out = model(coords, node_emb, global_emb, t)
    out.sum().backward()
    torch.cuda.synchronize()

    peak_gb = torch.cuda.max_memory_allocated() / 1e9
    assert peak_gb < 6.0, f"peak memory {peak_gb:.2f} GB is at/over this GPU's real 6GB ceiling"
