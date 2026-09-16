"""Subprocess wiring to DREAMPlace — TECHNICAL.md Section 1.11/4.C.

DREAMPlace has no PyPI package; it's built from source (CMake + Boost +
Flute, optionally CUDA) per its own repository instructions, and the build
is a real, non-trivial task in its own right (INSTRUCTIONS.md Section 1.1)
that needs a Linux (or WSL2/Docker) environment — see NOTES.md and
environment_setup.md. This module never fabricates a placement when
DREAMPlace isn't reachable; it raises `DreamplaceNotInstalledError` so a
caller (`legalizer.py`, `baselines.py`) fails loudly instead of silently
returning a fake "result" (INSTRUCTIONS.md Section 4: never substitute a
placeholder for a real tool/dataset in anything that could be reported).
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Optional


class DreamplaceNotInstalledError(RuntimeError):
    pass


class DreamplaceRunError(RuntimeError):
    pass


def find_dreamplace_placer() -> Path:
    """DREAMPlace's entry point is `dreamplace/Placer.py` inside wherever
    it was built. We look it up via the `DREAMPLACE_ROOT` environment
    variable (documented in environment_setup.md) rather than guessing a
    path, since there's no standard install location for a source build."""
    root = os.environ.get("DREAMPLACE_ROOT")
    if not root:
        raise DreamplaceNotInstalledError(
            "DREAMPLACE_ROOT is not set. DREAMPlace must be built from source "
            "(see environment_setup.md's DREAMPlace section) and DREAMPLACE_ROOT "
            "pointed at the build directory containing dreamplace/Placer.py."
        )
    placer_path = Path(root) / "dreamplace" / "Placer.py"
    if not placer_path.is_file():
        raise DreamplaceNotInstalledError(
            f"DREAMPLACE_ROOT is set to {root!r} but {placer_path} does not exist. "
            "Check the build completed (see environment_setup.md)."
        )
    return placer_path


def build_dreamplace_config(
    aux_input: Path,
    result_dir: Path,
    *,
    global_place_flag: int,
    legalize_flag: int,
    detailed_place_flag: int,
    random_seed: int,
    target_density: float = 1.0,
    gpu: int = 0,
    num_bins_x: int = 512,
    num_bins_y: int = 512,
    **overrides: Any,
) -> dict:
    """DREAMPlace is driven by a JSON config (its `test/*.json` examples
    document the schema); this builds the subset of keys this project's two
    call sites need. `legalize_and_score` (Section 3.5) calls this with
    `global_place_flag=0` — the input is already globally placed by
    Person B's generator, only legalization + detailed placement should
    run. `run_dreamplace_baseline` (Section 4.C) calls this with
    `global_place_flag=1` to run DREAMPlace end to end as an independent
    baseline placer, per Section 1.5's "Comparison baselines" list."""
    config = {
        "aux_input": str(aux_input),
        "result_dir": str(result_dir),
        "gpu": gpu,
        "num_bins_x": num_bins_x,
        "num_bins_y": num_bins_y,
        "global_place_flag": global_place_flag,
        "legalize_flag": legalize_flag,
        "detailed_place_flag": detailed_place_flag,
        "target_density": target_density,
        "random_seed": random_seed,
        "scale_factor": 0,
        "num_threads": 8,
    }
    config.update(overrides)
    return config


def write_config(config: dict, path: Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(config, indent=2))
    return path


def run_dreamplace(config_path: Path, placer_path: Optional[Path] = None) -> subprocess.CompletedProcess:
    """Invokes `python <placer_path> <config_path>` and returns the
    completed process (never raises on nonzero exit — callers decide how to
    react, since e.g. `legalizer.py` wants a specific error type)."""
    if placer_path is None:
        placer_path = find_dreamplace_placer()
    return subprocess.run(
        ["python", str(placer_path), str(config_path)],
        capture_output=True,
        text=True,
        check=False,
    )
