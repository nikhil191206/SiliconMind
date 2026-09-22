"""Trains Person C's RL baseline (`modules/evaluation/rl_env.py`'s
MacroPlacementEnv + Stable-Baselines3 PPO) for real, on a real cached
CircuitGraph — TECHNICAL.md Section 4.C's "RL placer reproduction
(MaskPlace/EfficientPlace-style)... for honest comparison."

This did not exist before: `run_rl_baseline` (modules/evaluation/baselines.py)
only ever *runs* a checkpoint someone already trained; nothing in the repo
actually produced one. Logs to Weights & Biases per TECHNICAL.md Section
5.3 (project name from config/shared_config.yaml).

*** Revision 2026-09-21: fixed two real training-quality bugs found by
inspecting the first real run's W&B curves (train/value_loss flat at
~1.3e9, no convergence) ***
1. Reward was raw HPWL-in-microns + overlap penalty over a 2000+-node
   netlist -- magnitudes in the hundreds of thousands, unnormalized. PPO's
   value function was trying to regress targets that large, which is
   numerically unstable. Fixed with VecNormalize(norm_reward=True):
   observations are already bounded [0,1] by the env itself and are left
   unnormalized.
2. Plain PPO never used the env's own `action_masks()` (grid_size=64 means
   4096 actions/step, most invalid once several macros are placed) --
   wasting most exploration on actions that were always going to be
   overlaps. Switched to sb3-contrib's MaskablePPO + ActionMasker, which
   actually uses it.

Usage:
    python -m experiments.train_rl_baseline --design ariane --timesteps 200000 --seed 0
"""

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import shared.env  # noqa: E402,F401 -- loads .env (WANDB_API_KEY) as a side effect
import wandb  # noqa: E402
import yaml  # noqa: E402
from sb3_contrib import MaskablePPO  # noqa: E402
from sb3_contrib.common.maskable.utils import get_action_masks  # noqa: E402
from sb3_contrib.common.wrappers import ActionMasker  # noqa: E402
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize  # noqa: E402
from wandb.integration.sb3 import WandbCallback  # noqa: E402

from modules.evaluation.rl_env import MacroPlacementEnv  # noqa: E402
from shared.metrics.hpwl import compute_hpwl  # noqa: E402
from shared.metrics.legality import compute_legality_violations  # noqa: E402
from shared.schemas.circuit_graph import CircuitGraph  # noqa: E402
from shared.schemas.placement import GenerationMetadata, Orientation, PlacementEntry, PlacementJSON  # noqa: E402


def _mask_fn(env: MacroPlacementEnv):
    return env.action_masks()

DATA_PROCESSED = REPO_ROOT / "data" / "processed"
RESULTS_ROOT = REPO_ROOT / "experiments" / "results"


def load_design(name: str) -> CircuitGraph:
    """Loads a cached CircuitGraph produced by data/processed/build_cache.py.
    Never falls back to a placeholder if the cache is missing -- run
    build_cache.py first."""
    for source_dir in DATA_PROCESSED.iterdir():
        if not source_dir.is_dir():
            continue
        candidate = source_dir / f"{name}.json"
        if candidate.exists():
            return CircuitGraph.model_validate_json(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        f"No cached design named {name!r} under {DATA_PROCESSED} -- run "
        "`python data/processed/build_cache.py` first (see data/README.md)."
    )


def _fill_remaining_std_cells(graph: CircuitGraph, macro_coords: dict) -> list[PlacementEntry]:
    from modules.evaluation.packing import grid_pack

    remaining = [n for n in graph.nodes if n.node_id not in macro_coords]
    return grid_pack(remaining, graph.die)


def evaluate_checkpoint(graph: CircuitGraph, model: MaskablePPO, grid_size: int, seed: int) -> dict:
    """Real, deterministic rollout + real HPWL/legality (Section 1.4) on the
    macro-only sub-placement -- congestion is intentionally not computed
    here (needs OpenROAD + a real tech LEF neither of which exist for this
    design, see modules/evaluation/NOTES.md Section 1.2). Standard cells
    (none exist in this macro-only netlist) would be packed in if present.

    Evaluated on a plain (non-normalized) env -- VecNormalize's reward
    scaling only matters for training the value function; the policy's
    observation space is unnormalized either way (see module docstring),
    and here we want the real, un-rescaled reward/HPWL/legality numbers."""
    env = MacroPlacementEnv(graph, grid_size=grid_size)
    obs, _ = env.reset(seed=seed)
    done = False
    total_reward = 0.0
    overlaps = 0
    while not done:
        action_masks = get_action_masks(env)
        action, _ = model.predict(obs, action_masks=action_masks, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(int(action))
        total_reward += reward
        overlaps += int(info["overlap"])
        done = terminated or truncated

    macro_coords = env.placements_so_far()
    entries = [
        PlacementEntry(node_id=nid, x=x, y=y, orientation=Orientation.N) for nid, (x, y) in macro_coords.items()
    ]
    entries += _fill_remaining_std_cells(graph, macro_coords)
    placement = PlacementJSON(
        design_name=graph.design_name,
        placements=sorted(entries, key=lambda e: e.node_id),
        generation_metadata=GenerationMetadata(model_variant="rl_baseline_ppo", seed=seed, is_legalized=False),
    )

    return {
        "episode_reward": total_reward,
        "overlap_steps": overlaps,
        "hpwl": compute_hpwl(placement, graph),
        "legality_violations": compute_legality_violations(placement, graph),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True, help="cached design name, e.g. 'ariane'")
    parser.add_argument("--timesteps", type=int, default=200_000)
    parser.add_argument("--grid-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--overlap-penalty", type=float, default=50.0)
    parser.add_argument("--no-wandb", action="store_true", help="disable W&B logging (debugging only)")
    args = parser.parse_args()

    with open(REPO_ROOT / "config" / "shared_config.yaml", encoding="utf-8") as f:
        shared_cfg = yaml.safe_load(f)
    wandb_project = shared_cfg["wandb"]["project"]

    graph = load_design(args.design)
    print(f"Loaded real design {graph.design_name!r}: {graph.num_nodes} nodes, {graph.num_hyperedges} hyperedges")

    probe_env = MacroPlacementEnv(graph, grid_size=args.grid_size, overlap_penalty=args.overlap_penalty)
    num_macros = len(probe_env.macro_ids)
    if num_macros == 0:
        raise ValueError(f"design {args.design!r} has no MACRO nodes -- MacroPlacementEnv needs at least one")

    def make_env():
        env = MacroPlacementEnv(graph, grid_size=args.grid_size, overlap_penalty=args.overlap_penalty)
        return ActionMasker(env, _mask_fn)

    vec_env = DummyVecEnv([make_env])
    # norm_reward=True is the actual fix for the flat value_loss seen in the
    # first real run -- see module docstring. norm_obs=False because the
    # env's own observation (occupancy grid, next_macro_wh) is already
    # bounded [0,1] by construction; re-normalizing it would just add noise.
    vec_env = VecNormalize(vec_env, norm_obs=False, norm_reward=True, clip_reward=10.0, gamma=0.99)

    experiment_name = f"rl_baseline_maskable_ppo_{args.design}_seed{args.seed}"
    run = None
    if not args.no_wandb:
        run = wandb.init(
            project=wandb_project,
            name=experiment_name,
            tags=["person-c", "rl-baseline", args.design],
            config={
                "design": args.design,
                "num_macros": num_macros,
                "grid_size": args.grid_size,
                "overlap_penalty": args.overlap_penalty,
                "timesteps": args.timesteps,
                "seed": args.seed,
                "algorithm": "MaskablePPO",
                "reward_normalization": True,
                "action_masking": True,
            },
            sync_tensorboard=True,
        )

    results_dir = RESULTS_ROOT / experiment_name
    results_dir.mkdir(parents=True, exist_ok=True)

    model = MaskablePPO(
        "MultiInputPolicy",
        vec_env,
        verbose=1,
        seed=args.seed,
        tensorboard_log=str(results_dir / "tb") if run is not None else None,
    )

    t0 = time.time()
    callback = WandbCallback(verbose=2) if run is not None else None
    model.learn(total_timesteps=args.timesteps, callback=callback, progress_bar=False)
    train_seconds = time.time() - t0

    checkpoint_path = results_dir / f"checkpoint_{args.timesteps}.zip"
    model.save(str(checkpoint_path))
    vec_env.save(str(results_dir / f"vecnormalize_{args.timesteps}.pkl"))
    print(f"Trained {args.timesteps} timesteps in {train_seconds:.1f}s -- saved to {checkpoint_path}")

    metrics = evaluate_checkpoint(graph, model, grid_size=args.grid_size, seed=args.seed)
    metrics["train_seconds"] = train_seconds
    print("Real evaluation metrics (macro-only placement, deterministic rollout):")
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    if run is not None:
        wandb.log({f"final/{k}": v for k, v in metrics.items()})
        run.finish()


if __name__ == "__main__":
    main()
