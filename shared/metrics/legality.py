"""Legality violation count — TECHNICAL.md Section 1.4.

Number of macro pairs with overlapping bounding boxes + number of macros
with any portion outside the die boundary. Must be zero after the
legalization step (Section 4.C) before a placement is ever shown or
exported — a non-zero count is an internal error, not a reportable result.

Section 1.4's formula is stated in terms of macros specifically (not
standard cells), so that is exactly what's implemented here — never
silently widened to "all nodes" without a spec change.
"""

from itertools import combinations

from shared.metrics.geometry import node_bbox
from shared.schemas.circuit_graph import CircuitGraph, NodeType
from shared.schemas.placement import PlacementJSON

BoundingBox = tuple[float, float, float, float]


def _boxes_overlap(a: BoundingBox, b: BoundingBox) -> bool:
    ax_min, ay_min, ax_max, ay_max = a
    bx_min, by_min, bx_max, by_max = b
    # Strict inequalities: boxes that merely touch along an edge (zero
    # overlap area) are legal, matching standard placement-legality
    # convention (cells are allowed to abut).
    return ax_min < bx_max and bx_min < ax_max and ay_min < by_max and by_min < ay_max


def compute_legality_violations(placement: PlacementJSON, graph: CircuitGraph) -> int:
    node_by_id = {n.node_id: n for n in graph.nodes}
    placement_by_id = {p.node_id: p for p in placement.placements}

    macro_boxes: list[BoundingBox] = []
    for node_id, node in node_by_id.items():
        if node.type != NodeType.MACRO:
            continue
        entry = placement_by_id[node_id]
        macro_boxes.append(node_bbox(entry.x, entry.y, node.width, node.height, entry.orientation))

    violations = 0
    for x_min, y_min, x_max, y_max in macro_boxes:
        if x_min < 0 or y_min < 0 or x_max > graph.die.width or y_max > graph.die.height:
            violations += 1

    for box_a, box_b in combinations(macro_boxes, 2):
        if _boxes_overlap(box_a, box_b):
            violations += 1

    return violations
