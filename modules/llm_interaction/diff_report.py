"""Placement Diff Reporting — TECHNICAL.md Section 3.6 / Section 4.D.

Owned by Person D.
Compares BEFORE and AFTER PlacementJSON objects, computes coordinate displacements,
detects unexpected moves for frozen nodes, and calculates metric deltas.
"""

import math
from typing import Dict, List, Optional

from shared.schemas.constraint import ConstraintObject
from shared.schemas.diff_report import DiffReport, MovedNode
from shared.schemas.metrics import MetricsObject
from shared.schemas.placement import PlacementEntry, PlacementJSON


def generate_diff_report(
    before: PlacementJSON,
    after: PlacementJSON,
    constraint: ConstraintObject,
    metrics_before: Optional[MetricsObject] = None,
    metrics_after: Optional[MetricsObject] = None,
    tolerance: float = 1e-4,
) -> DiffReport:
    """Compares before and after placements to generate a Section 3.6 DiffReport.

    Args:
        before: Original placement before edit.
        after: Regenerated placement after edit.
        constraint: ConstraintObject that triggered the edit.
        metrics_before: Optional metrics for before placement.
        metrics_after: Optional metrics for after placement.
        tolerance: Coordinate displacement tolerance threshold.

    Returns:
        Schema-valid DiffReport instance.
    """
    before_by_id: Dict[int, PlacementEntry] = {p.node_id: p for p in before.placements}
    after_by_id: Dict[int, PlacementEntry] = {p.node_id: p for p in after.placements}

    moved_nodes: List[MovedNode] = []
    unexpected_moves: List[int] = []

    frozen_set = set(constraint.frozen_node_ids)

    for node_id, before_entry in before_by_id.items():
        after_entry = after_by_id.get(node_id)
        if after_entry is None:
            continue

        dx = after_entry.x - before_entry.x
        dy = after_entry.y - before_entry.y
        dist = math.hypot(dx, dy)

        if dist > tolerance:
            moved_nodes.append(MovedNode(node_id=node_id, delta_x=dx, delta_y=dy))

            # Flag as unexpected move if this node was marked frozen
            if node_id in frozen_set:
                unexpected_moves.append(node_id)

    hpwl_delta = 0.0
    congestion_delta = 0.0

    if metrics_before is not None and metrics_after is not None:
        hpwl_delta = metrics_after.hpwl - metrics_before.hpwl
        congestion_delta = metrics_after.congestion_overflow - metrics_before.congestion_overflow

    return DiffReport(
        constraint_id=constraint.constraint_id,
        moved_nodes=moved_nodes,
        unexpected_moves=unexpected_moves,
        hpwl_delta=hpwl_delta,
        congestion_delta=congestion_delta,
    )


def format_diff_summary(diff_report: DiffReport, constraint: ConstraintObject) -> str:
    """Formats a human-readable markdown text summary of a DiffReport."""
    lines = [
        "## Placement Change Diff Report",
        f"**Constraint ID:** `{diff_report.constraint_id}`",
        f"**Original Request:** \"{constraint.source_request}\"",
        f"**Constraint Type:** {constraint.constraint_type.value}",
        f"**Total Moved Macros/Cells:** {len(diff_report.moved_nodes)}",
        "",
    ]

    if diff_report.unexpected_moves:
        lines.append(
            f"**WARNING:** {len(diff_report.unexpected_moves)} frozen nodes unexpectedly moved! "
            f"(IDs: {diff_report.unexpected_moves})"
        )

    lines.append("### Moved Components")
    if not diff_report.moved_nodes:
        lines.append("- No macro or cell coordinates changed.")
    else:
        for m in diff_report.moved_nodes:
            dist = math.hypot(m.delta_x, m.delta_y)
            lines.append(
                f"- **Node {m.node_id}**: ΔX = {m.delta_x:+.2f}, ΔY = {m.delta_y:+.2f} (Displacement: {dist:.2f} die units)"
            )

    lines.append("")
    lines.append("### Metric Deltas")
    lines.append(f"- **HPWL Delta:** {diff_report.hpwl_delta:+.2f}")
    lines.append(f"- **Congestion Overflow Delta:** {diff_report.congestion_delta:+.2f}")

    return "\n".join(lines)
