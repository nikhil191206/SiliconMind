"""Congestion overflow — TECHNICAL.md Section 1.4.

    overflow(g) = max(0, routing_demand(g) - routing_capacity(g))
                  for each routing grid cell g
    Total overflow = sum over all grid cells g

`routing_demand` and `routing_capacity` are computed by DREAMPlace/OpenROAD's
global router estimate (`modules/evaluation/legalizer.py`) — this project
never reimplements routing estimation from scratch. This module implements
only the aggregation formula on top of whatever the router produced.
"""

from typing import Dict, Hashable


def compute_congestion_overflow(
    routing_demand: Dict[Hashable, float],
    routing_capacity: Dict[Hashable, float],
) -> float:
    """Both maps are keyed by the same grid-cell identifier (e.g. an
    (x_index, y_index) tuple), as produced by the router estimate. A cell
    absent from `routing_capacity` is treated as zero capacity, and one
    absent from `routing_demand` as zero demand — so overflow is never
    silently under-reported just because a cell was omitted."""
    cells = set(routing_demand) | set(routing_capacity)
    total = 0.0
    for cell in cells:
        demand = routing_demand.get(cell, 0.0)
        capacity = routing_capacity.get(cell, 0.0)
        total += max(0.0, demand - capacity)
    return total
