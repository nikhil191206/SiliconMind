import numpy as np
import pytest

from modules.evaluation.rl_env import MacroPlacementEnv
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph

# mock_toy_design (shared/mocks/mock_circuit_graph.py): 2 macros --
# node 0 (20x15, pin_count=8), node 1 (18x12, pin_count=6) -- on a 100x100
# die, connected by hyperedge net_id=3 (driver=None, sinks=[0, 1]), the
# only macro-macro net.


def test_reset_orders_macros_by_descending_pin_count():
    env = MacroPlacementEnv(make_mock_circuit_graph(), grid_size=32)
    assert env.macro_ids == [0, 1]  # node 0 has pin_count 8 > node 1's 6


def test_reset_observation_shapes_and_next_macro_dims():
    env = MacroPlacementEnv(make_mock_circuit_graph(), grid_size=32)
    obs, info = env.reset(seed=0)
    assert obs["occupancy"].shape == (32, 32)
    assert not obs["occupancy"].any()
    assert obs["next_macro_wh"] == pytest.approx(np.array([0.2, 0.15]), abs=1e-6)  # 20/100, 15/100
    assert info == {}


def test_first_step_no_overlap_zero_reward_before_second_macro_placed():
    env = MacroPlacementEnv(make_mock_circuit_graph(), grid_size=32)
    env.reset(seed=0)
    obs, reward, terminated, truncated, info = env.step(0)  # gx=gy=0
    assert reward == 0.0  # net incomplete: only macro 0 placed so far
    assert info["overlap"] is False
    assert terminated is False
    assert obs["occupancy"].sum() > 0


def test_second_step_completes_macro_net_and_computes_hpwl_reward():
    env = MacroPlacementEnv(make_mock_circuit_graph(), grid_size=32)
    env.reset(seed=0)
    env.step(0)  # macro 0 at grid (0, 0) -> real (0.0, 0.0)
    action = 20  # gy=0, gx=20 -> real x = 20 * (100/32) = 62.5, y = 0.0
    obs, reward, terminated, truncated, info = env.step(action)

    assert info["overlap"] is False
    assert terminated is True
    # HPWL of net [0, 1] with coords (0,0) and (62.5, 0): dx=62.5, dy=0.
    assert reward == pytest.approx(-62.5)


def test_overlapping_placement_is_penalized_not_blocked():
    env = MacroPlacementEnv(make_mock_circuit_graph(), grid_size=32, overlap_penalty=50.0)
    env.reset(seed=0)
    env.step(0)  # macro 0 occupies grid x:[0,7), y:[0,5)
    obs, reward, terminated, truncated, info = env.step(3 * 32 + 3)  # gx=3, gy=3 -> overlaps macro 0's footprint
    assert info["overlap"] is True
    assert reward <= -50.0


def test_action_masks_true_count_matches_hand_computed_valid_positions():
    env = MacroPlacementEnv(make_mock_circuit_graph(), grid_size=32)
    env.reset(seed=0)
    mask = env.action_masks()
    # Macro 0 is 20x15 on a 100x100 die at grid_size=32 -> cell_w=cell_h=3.125.
    # cells_w = ceil(20/3.125) = 7, cells_h = ceil(15/3.125) = 5.
    # Valid gx: 0..32-7=25 (26 values); valid gy: 0..32-5=27 (28 values).
    assert mask.sum() == 26 * 28


def test_action_masks_excludes_occupied_region_after_a_placement():
    env = MacroPlacementEnv(make_mock_circuit_graph(), grid_size=32)
    env.reset(seed=0)
    env.step(0)  # macro 0 now occupies x:[0,7), y:[0,5)
    mask = env.action_masks()
    assert mask[0 * 32 + 0] == False  # gx=0, gy=0 would overlap macro 0
    assert mask[20 * 32 + 20] == True  # far away, no overlap


def test_step_after_all_macros_placed_raises():
    env = MacroPlacementEnv(make_mock_circuit_graph(), grid_size=32)
    env.reset(seed=0)
    env.step(0)
    env.step(20)
    with pytest.raises(RuntimeError):
        env.step(0)
