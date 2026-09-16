"""Comparison baselines — TECHNICAL.md Section 4.C.

    def run_dreamplace_baseline(graph: CircuitGraph) -> PlacementJSON: ...
    def run_rl_baseline(graph: CircuitGraph, checkpoint_path: str) -> PlacementJSON: ...

`run_dreamplace_baseline` needs DREAMPlace installed (see
`dreamplace_runner.py`, not available in this environment — raises
`DreamplaceNotInstalledError`, never a fabricated placement).
`run_rl_baseline` needs a real trained checkpoint (training the RL baseline
on real chips is blocked per INSTRUCTIONS.md Section 2) — it only runs
inference against a checkpoint that must already exist; it never trains one
itself and never fabricates a result when one is missing.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Optional

from modules.evaluation import bookshelf_io, dreamplace_runner
from modules.evaluation.packing import grid_pack
from modules.evaluation.rl_env import MacroPlacementEnv
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.placement import GenerationMetadata, Orientation, PlacementEntry, PlacementJSON


def _naive_initial_placement(graph: CircuitGraph) -> PlacementJSON:
    return PlacementJSON(
        design_name=graph.design_name,
        placements=grid_pack(graph.nodes, graph.die),
        generation_metadata=GenerationMetadata(model_variant="naive_grid_init", seed=0, is_legalized=False),
    )


def _pack_remaining_std_cells(graph: CircuitGraph, placed_node_ids: set) -> list[PlacementEntry]:
    remaining_nodes = [n for n in graph.nodes if n.node_id not in placed_node_ids]
    return grid_pack(remaining_nodes, graph.die)


def run_dreamplace_baseline(graph: CircuitGraph, work_dir: Optional[Path] = None) -> PlacementJSON:
    """Runs DREAMPlace end to end (global + legalize + detailed placement)
    as an independent classical baseline (Section 1.5) — unlike
    `legalizer.legalize_and_score`, which only legalizes an
    already-globally-placed layout handed to it by Person B's generator,
    this starts from a naive grid initialization and lets DREAMPlace do
    the actual placement."""
    owns_work_dir = work_dir is None
    work_dir = Path(work_dir) if work_dir is not None else Path(tempfile.mkdtemp(prefix="dreamplace_baseline_"))
    try:
        initial_placement = _naive_initial_placement(graph)
        aux_path = bookshelf_io.write_bookshelf(graph, initial_placement, work_dir)
        config = dreamplace_runner.build_dreamplace_config(
            aux_path,
            work_dir,
            global_place_flag=1,
            legalize_flag=1,
            detailed_place_flag=1,
            random_seed=0,
        )
        config_path = dreamplace_runner.write_config(config, work_dir / f"{graph.design_name}.baseline.json")
        result = dreamplace_runner.run_dreamplace(config_path)
        if result.returncode != 0:
            raise dreamplace_runner.DreamplaceRunError(
                f"DREAMPlace baseline run failed (exit {result.returncode}):\n{result.stderr}"
            )
        output_pl = work_dir / f"{graph.design_name}.pl"
        placement = bookshelf_io.read_bookshelf_placement(
            output_pl, design_name=graph.design_name, model_variant="dreamplace_baseline", seed=0
        )
        placement.generation_metadata.is_legalized = True
        return placement
    finally:
        if owns_work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)


def run_rl_baseline(graph: CircuitGraph, checkpoint_path: str, grid_size: int = 32, seed: int = 0) -> PlacementJSON:
    """Loads a trained Stable-Baselines3 PPO checkpoint (Section 1.11's
    frozen RL-baseline library) and runs a deterministic
    `MacroPlacementEnv` (`rl_env.py`) rollout to place every macro, then
    fills remaining standard cells with `packing.grid_pack` so the returned
    PlacementJSON covers every node_id (Section 3.3). Output is
    `is_legalized: False` — like every other raw generator/baseline output,
    it still needs to go through `legalizer.legalize_and_score`."""
    if not Path(checkpoint_path).is_file():
        raise FileNotFoundError(
            f"RL baseline checkpoint not found at {checkpoint_path!r}. Training the RL "
            "baseline on real chips is blocked until real datasets arrive (INSTRUCTIONS.md "
            "Section 2) — run_rl_baseline only runs inference against an existing checkpoint, "
            "it never trains or fabricates one."
        )
    try:
        from stable_baselines3 import PPO
    except ImportError as exc:
        raise ImportError(
            "stable-baselines3 is required for run_rl_baseline (see modules/evaluation/requirements.txt)"
        ) from exc

    env = MacroPlacementEnv(graph, grid_size=grid_size)
    model = PPO.load(checkpoint_path)
    obs, _ = env.reset(seed=seed)
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, _ = env.step(int(action))
        done = terminated or truncated

    macro_coords = env.placements_so_far()
    entries = [
        PlacementEntry(node_id=node_id, x=x, y=y, orientation=Orientation.N) for node_id, (x, y) in macro_coords.items()
    ]
    entries += _pack_remaining_std_cells(graph, placed_node_ids=set(macro_coords))

    return PlacementJSON(
        design_name=graph.design_name,
        placements=sorted(entries, key=lambda e: e.node_id),
        generation_metadata=GenerationMetadata(model_variant="rl_baseline_ppo", seed=seed, is_legalized=False),
    )
