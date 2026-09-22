"""Deterministic row-major grid packer.

Used as (a) DREAMPlace's required initial placement for
`run_dreamplace_baseline` (any legal-ish starting point is fine — DREAMPlace's
own global-placement step moves everything anyway), and (b) to fill in
standard cells after `run_rl_baseline`'s RL rollout has placed only the
macros (the RL baseline reproduces macro placement only, matching
MaskPlace/EfficientPlace's own scope — TECHNICAL.md Section 4.C). This is
not a claimed *good* placement either way — `legalize_and_score` is what
actually judges quality (Section 3.5); this only guarantees every node_id
gets *some* schema-valid, non-overlapping-by-construction coordinate.

Mirrors `shared/mocks/mock_placement.py`'s algorithm (same idea: pack nodes
left-to-right, wrap rows), but lives here rather than in `shared/mocks/`
since it is real baseline-support code, not a mock fixture.
"""

from shared.schemas.circuit_graph import CircuitNode, Die
from shared.schemas.placement import Orientation, PlacementEntry


def grid_pack(nodes: list[CircuitNode], die: Die) -> list[PlacementEntry]:
    entries = []
    cursor_x, cursor_y, row_height = 0.0, 0.0, 0.0
    for node in nodes:
        if cursor_x + node.width > die.width:
            cursor_x = 0.0
            cursor_y += row_height
            row_height = 0.0
        entries.append(PlacementEntry(node_id=node.node_id, x=cursor_x, y=cursor_y, orientation=Orientation.N))
        cursor_x += node.width
        row_height = max(row_height, node.height)
    return entries
