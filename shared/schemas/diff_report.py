"""Diff Report Contract — TECHNICAL.md Section 3.6.

Owned by Person D. Input derived from two Placement JSONs via Person C's
metrics. `unexpected_moves` must be empty; non-empty means a bug in B's
freeze enforcement (Section 1.7), not a reportable result.
"""

from pydantic import BaseModel


class MovedNode(BaseModel):
    node_id: int
    delta_x: float
    delta_y: float


class DiffReport(BaseModel):
    constraint_id: str
    moved_nodes: list[MovedNode]
    unexpected_moves: list[int]
    hpwl_delta: float
    congestion_delta: float
