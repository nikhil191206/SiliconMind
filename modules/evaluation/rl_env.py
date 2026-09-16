"""MacroPlacementEnv — the environment behind `run_rl_baseline`
(TECHNICAL.md Section 4.C's "adapt an open MaskPlace/EfficientPlace-style
implementation ... rather than reimplementing from the paper text alone").

Only macros (Section 3.1's `NodeType.MACRO`) are RL-placed, one per step
onto a discretized grid, mirroring the published MaskPlace/EfficientPlace
formulation. Standard cells are filled in afterward by a simple
deterministic packer (`baselines.py`'s `_pack_remaining_std_cells`) so
`run_rl_baseline`'s output still covers every node_id, as Section 3.3
requires.

This environment does not hard-enforce legality (no action masking inside
`step` itself — `action_masks()` is provided as an opt-in for a masked-
action algorithm, but plain PPO can ignore it): an agent may choose an
overlapping or off-die cell, which is penalized in the reward, not
blocked. This matches the project's architecture principle (Section 1.7 /
AI-VLSI-Placement-System.pdf Section 2.4): every generator's raw output —
RL baseline included — is re-legalized by Person C's `legalize_and_score`
before it is ever scored or shown, so this environment's job is to produce
a good *starting point*, not to guarantee legality on its own.
"""

from typing import Optional

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from shared.schemas.circuit_graph import CircuitGraph, NodeType


class MacroPlacementEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, graph: CircuitGraph, grid_size: int = 32, overlap_penalty: float = 50.0):
        super().__init__()
        self.graph = graph
        self.grid_size = grid_size
        self.overlap_penalty = overlap_penalty
        self.cell_w = graph.die.width / grid_size
        self.cell_h = graph.die.height / grid_size
        self._node_by_id = {n.node_id: n for n in graph.nodes}

        # Highest-connectivity macros first -- a standard MaskPlace-style
        # heuristic, so the earliest (most constrained) decisions have the
        # most free grid to choose from.
        self.macro_ids = sorted(
            (n.node_id for n in graph.nodes if n.type == NodeType.MACRO),
            key=lambda nid: -self._node_by_id[nid].pin_count,
        )
        if not self.macro_ids:
            raise ValueError("MacroPlacementEnv requires at least one MACRO node in the graph")

        macro_id_set = set(self.macro_ids)
        self._macro_nets: list[list[int]] = []
        for hyperedge in graph.hyperedges:
            pins = list(hyperedge.sink_nodes)
            if hyperedge.driver_node is not None:
                pins.append(hyperedge.driver_node)
            macro_pins = [p for p in pins if p in macro_id_set]
            if len(macro_pins) >= 2:
                self._macro_nets.append(macro_pins)

        self.action_space = spaces.Discrete(grid_size * grid_size)
        self.observation_space = spaces.Dict(
            {
                "occupancy": spaces.Box(low=0.0, high=1.0, shape=(grid_size, grid_size), dtype=np.float32),
                "next_macro_wh": spaces.Box(low=0.0, high=1.0, shape=(2,), dtype=np.float32),
            }
        )

        self._occupancy = np.zeros((grid_size, grid_size), dtype=np.float32)
        self._coords: dict[int, tuple[float, float]] = {}
        self._step_idx = 0

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)
        self._occupancy = np.zeros((self.grid_size, self.grid_size), dtype=np.float32)
        self._coords = {}
        self._step_idx = 0
        return self._observation(), {}

    def _footprint_cells(self, node_id: int, gx: int, gy: int) -> tuple[int, int, int, int]:
        node = self._node_by_id[node_id]
        cells_w = max(1, min(self.grid_size, int(np.ceil(node.width / self.cell_w))))
        cells_h = max(1, min(self.grid_size, int(np.ceil(node.height / self.cell_h))))
        return gx, gy, gx + cells_w, gy + cells_h

    def _observation(self) -> dict:
        if self._step_idx < len(self.macro_ids):
            node = self._node_by_id[self.macro_ids[self._step_idx]]
            next_wh = np.array(
                [node.width / self.graph.die.width, node.height / self.graph.die.height], dtype=np.float32
            )
        else:
            next_wh = np.zeros(2, dtype=np.float32)
        return {"occupancy": self._occupancy.copy(), "next_macro_wh": next_wh}

    def action_masks(self) -> np.ndarray:
        """Optional helper for a masked-action algorithm (e.g. sb3-contrib's
        MaskablePPO); `step` does not require it (see module docstring)."""
        mask = np.zeros(self.grid_size * self.grid_size, dtype=bool)
        if self._step_idx >= len(self.macro_ids):
            return mask
        node_id = self.macro_ids[self._step_idx]
        for gy in range(self.grid_size):
            for gx in range(self.grid_size):
                x0, y0, x1, y1 = self._footprint_cells(node_id, gx, gy)
                if x1 > self.grid_size or y1 > self.grid_size:
                    continue
                if not self._occupancy[y0:y1, x0:x1].any():
                    mask[gy * self.grid_size + gx] = True
        return mask

    def _incremental_macro_hpwl(self, just_placed: int) -> float:
        """Sum of HPWL over macro-macro nets where every pin is already
        placed as of this step — a proxy reward usable before std cells
        exist, not a claimed final-quality number (that's
        shared/metrics/hpwl.py, run on the full, legalized placement)."""
        total = 0.0
        for pins in self._macro_nets:
            if just_placed not in pins or not all(p in self._coords for p in pins):
                continue
            xs = [self._coords[p][0] for p in pins]
            ys = [self._coords[p][1] for p in pins]
            total += (max(xs) - min(xs)) + (max(ys) - min(ys))
        return total

    def step(self, action: int):
        if self._step_idx >= len(self.macro_ids):
            raise RuntimeError("step() called after all macros have been placed; call reset() first")

        node_id = self.macro_ids[self._step_idx]
        gy, gx = divmod(int(action), self.grid_size)
        x0, y0, x1, y1 = self._footprint_cells(node_id, gx, gy)

        out_of_bounds = x1 > self.grid_size or y1 > self.grid_size
        overlap = out_of_bounds or bool(self._occupancy[y0:y1, x0:x1].any())

        self._coords[node_id] = (gx * self.cell_w, gy * self.cell_h)
        if not out_of_bounds:
            self._occupancy[y0:y1, x0:x1] = 1.0

        reward = -self._incremental_macro_hpwl(node_id)
        if overlap:
            reward -= self.overlap_penalty

        self._step_idx += 1
        terminated = self._step_idx >= len(self.macro_ids)
        return self._observation(), reward, terminated, False, {"overlap": overlap, "out_of_bounds": out_of_bounds}

    def placements_so_far(self) -> dict[int, tuple[float, float]]:
        return dict(self._coords)
