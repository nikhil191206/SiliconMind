"""Plumbing smoke test for the RL baseline's full inference path: trains a
tiny PPO for a handful of steps on the mock graph's MacroPlacementEnv,
purely to prove env -> Stable-Baselines3 -> checkpoint -> run_rl_baseline
wiring works end to end. This is NOT a claimed baseline result
(INSTRUCTIONS.md Section 2: real RL baseline training on real chips is
blocked) — mirrors modules/generator/'s test_training_sanity.py, an
explicit "does the loop run" check, not a quality claim.

Skipped automatically wherever stable-baselines3 (and its torch
dependency) aren't installed — see NOTES.md.
"""

import pytest

pytest.importorskip("stable_baselines3")

from stable_baselines3 import PPO  # noqa: E402

from modules.evaluation.baselines import run_rl_baseline  # noqa: E402
from modules.evaluation.rl_env import MacroPlacementEnv  # noqa: E402
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph  # noqa: E402


def test_run_rl_baseline_end_to_end_plumbing_smoke(tmp_path):
    graph = make_mock_circuit_graph()
    env = MacroPlacementEnv(graph, grid_size=8)
    model = PPO("MultiInputPolicy", env, seed=0, n_steps=8, batch_size=8, verbose=0)
    model.learn(total_timesteps=16)
    checkpoint_path = tmp_path / "toy_ppo.zip"
    model.save(str(checkpoint_path))

    placement = run_rl_baseline(graph, str(checkpoint_path), grid_size=8, seed=0)

    assert placement.design_name == graph.design_name
    assert {e.node_id for e in placement.placements} == {n.node_id for n in graph.nodes}
    assert placement.generation_metadata.is_legalized is False
