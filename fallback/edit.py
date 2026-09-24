"""FALLBACK ONLY: stands in for Person D's LLM constraint parser (rule-based
regexes, the same patterns as the frontend's lib/mock/mockEditor.ts) and for
Person B's freeze-aware regeneration (the classical placer with every
non-affected macro fixed bit-identically).

Contract honoured exactly as the real system must (TECHNICAL.md 3.4 / 1.7):
  * UNCLEAR or confidence < 0.6 -> requires_clarification, placer NOT run.
  * frozen_node_ids = every macro not being edited. They are passed to the
    placer as `fixed`, so they cannot move; unexpected_moves is computed, not
    assumed, and must come out empty.
  * Standard cells are not frozen: the ones covered by a moved macro are
    re-legalized to the nearest free row spot. Every other cell stays put.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np

from fallback.placer import MacroHint, place
from shared.metrics.geometry import node_bbox
from shared.schemas.circuit_graph import CircuitGraph, NodeType
from shared.schemas.constraint import (
    ConstraintObject,
    ConstraintReference,
    ConstraintType,
    ReferenceType,
    RegionBoundingBox,
    Strength,
)
from shared.schemas.diff_report import DiffReport, MovedNode
from shared.schemas.placement import PlacementEntry, PlacementJSON

VAGUE = re.compile(r"\b(better|improve|optimi[sz]e|nicer|fix( it)?|good|clean ?up|whatever)\b", re.I)
LIST_RE = re.compile(r"\b(?:macros?|nodes?|blocks?|cells?)\s+((?:#?\d+\s*(?:,|and|&)?\s*)+)", re.I)
SHORT_RE = re.compile(r"\b[mM](\d+)\b|#(\d+)")
AWAY_RE = re.compile(r"away from\s+(?:macro|node|block)?\s*#?m?(\d+)", re.I)
TOWARD_RE = re.compile(r"(?:toward|towards|closer to|next to|near)\s+(?:macro|node|block)?\s*#?m?(\d+)", re.I)
ADJ_RE = re.compile(r"\b(not (?:be )?(?:next to|adjacent to|beside|touching)|separate)\b", re.I)
FORBID_RE = re.compile(r"\b(keep out|out of|avoid|not in|away from the)\b", re.I)


@dataclass
class Parsed:
    constraint: ConstraintObject
    direction: Optional[str]
    reference_node: Optional[int]


def _node_ids(text: str, n: int) -> list[int]:
    ids: list[int] = []
    for m in LIST_RE.finditer(text):
        ids += [int(d) for d in re.findall(r"\d+", m.group(1))]
    for a, b in SHORT_RE.findall(text):
        ids.append(int(a or b))
    seen, out = set(), []
    for i in ids:
        if 0 <= i < n and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _direction(text: str) -> Optional[str]:
    t = text.lower()
    for word, d in (
        (r"\b(left|west)\b", "left"),
        (r"\b(right|east)\b", "right"),
        (r"\b(top|up|upper|north)\b", "up"),
        (r"\b(bottom|down|lower|south)\b", "down"),
        (r"\b(cent(er|re)|middle)\b", "center"),
    ):
        if re.search(word, t):
            return d
    return None


def _region(d: Optional[str], W: float, H: float) -> RegionBoundingBox:
    return {
        "left": RegionBoundingBox(x_min=0, y_min=0, x_max=W * 0.3, y_max=H),
        "right": RegionBoundingBox(x_min=W * 0.7, y_min=0, x_max=W, y_max=H),
        "up": RegionBoundingBox(x_min=0, y_min=H * 0.7, x_max=W, y_max=H),
        "down": RegionBoundingBox(x_min=0, y_min=0, x_max=W, y_max=H * 0.3),
    }.get(d or "", RegionBoundingBox(x_min=W * 0.3, y_min=H * 0.3, x_max=W * 0.7, y_max=H * 0.7))


def parse_instruction(instruction: str, graph: CircuitGraph) -> Parsed:
    text = instruction.strip()
    n = len(graph.nodes)
    ids = _node_ids(text, n)
    direction = _direction(text)
    ctype, conf, ref_node, affected = ConstraintType.UNCLEAR, 0.2, None, []

    away, toward = AWAY_RE.search(text), TOWARD_RE.search(text)
    if VAGUE.search(text) and not ids:
        pass
    elif away or toward:
        ref_node = int((away or toward).group(1))
        affected = [i for i in ids if i != ref_node]
        if away:
            ctype = ConstraintType.FORBID_ADJACENT if ADJ_RE.search(text) else ConstraintType.MOVE_AWAY_FROM
        else:
            ctype = ConstraintType.FORBID_ADJACENT if ADJ_RE.search(text) else ConstraintType.MOVE_TOWARD
        conf = 0.9 if affected and ref_node < n else 0.42
    elif ids and direction:
        affected = ids
        ctype = ConstraintType.FORBID_REGION if FORBID_RE.search(text) else ConstraintType.PREFER_REGION
        conf = 0.86
    elif ids:
        affected, conf = ids, 0.45  # knows WHAT, not WHERE
    elif direction:
        ctype, conf = ConstraintType.PREFER_REGION, 0.38  # knows WHERE, not WHAT

    affected_set = set(affected)
    if ref_node is not None:
        reference = ConstraintReference(type=ReferenceType.NODE, value=ref_node)
    elif direction:
        reference = ConstraintReference(type=ReferenceType.REGION, value=_region(direction, graph.die.width, graph.die.height))
    else:
        reference = ConstraintReference(type=ReferenceType.NODE, value=0)

    constraint = ConstraintObject(
        source_request=text,
        frozen_node_ids=[nd.node_id for nd in graph.nodes if nd.type == NodeType.MACRO and nd.node_id not in affected_set],
        affected_node_ids=affected,
        constraint_type=ctype,
        reference=reference,
        strength=Strength.HARD if ctype in (ConstraintType.FORBID_REGION, ConstraintType.FORBID_ADJACENT) else Strength.SOFT,
        confidence=conf,
    )
    return Parsed(constraint=constraint, direction=direction, reference_node=ref_node)


def clarification_message(instruction: str, c: ConstraintObject) -> str:
    return (
        f"Instruction '{instruction}' was ambiguous or low confidence ({c.confidence:.2f}). "
        "Please name the macros and the direction explicitly, e.g. 'move macro 3 toward the left edge', "
        "'move macros 2, 5 away from macro 0', or 'keep m4 out of the center'."
    )


def _hint_for(parsed: Parsed, node: int, graph: CircuitGraph, prev: dict[int, PlacementEntry]) -> MacroHint:
    W, H = graph.die.width, graph.die.height
    diag = math.hypot(W, H)
    c = parsed.constraint
    nd = graph.nodes[node]
    p = prev[node]
    x0, y0, x1, y1 = node_bbox(p.x, p.y, nd.width, nd.height, p.orientation)
    ocx, ocy = (x0 + x1) / 2, (y0 + y1) / 2

    if parsed.reference_node is not None:
        rn, rp = graph.nodes[parsed.reference_node], prev[parsed.reference_node]
        rx0, ry0, rx1, ry1 = node_bbox(rp.x, rp.y, rn.width, rn.height, rp.orientation)
        rcx, rcy = (rx0 + rx1) / 2, (ry0 + ry1) / 2
        dx, dy = ocx - rcx, ocy - rcy
        ln = math.hypot(dx, dy) or 1.0
        ux, uy = dx / ln, dy / ln
        if c.constraint_type == ConstraintType.MOVE_TOWARD:
            gap = (max(rx1 - rx0, ry1 - ry0) + max(x1 - x0, y1 - y0)) / 2 + min(W, H) * 0.02
            tx, ty = rcx + ux * gap, rcy + uy * gap
        else:  # MOVE_AWAY_FROM / FORBID_ADJACENT
            step = min(W, H) * (0.3 if c.constraint_type == ConstraintType.MOVE_AWAY_FROM else 0.15)
            tx, ty = ocx + ux * step, ocy + uy * step

        def hint(cx: np.ndarray, cy: np.ndarray, w: float, h: float) -> np.ndarray:
            cost = np.hypot(cx - tx, cy - ty) / diag
            if c.constraint_type != ConstraintType.MOVE_TOWARD:
                # never end up closer to the reference than it started
                cost += 5.0 * (np.hypot(cx - rcx, cy - rcy) < math.hypot(ocx - rcx, ocy - rcy) * 1.05)
            return cost

        return hint

    reg = c.reference.value
    assert isinstance(reg, RegionBoundingBox)

    def region_hint(cx: np.ndarray, cy: np.ndarray, w: float, h: float) -> np.ndarray:
        bx0, by0, bx1, by1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        ov = np.clip(np.minimum(bx1, reg.x_max) - np.maximum(bx0, reg.x_min), 0, None) * np.clip(
            np.minimum(by1, reg.y_max) - np.maximum(by0, reg.y_min), 0, None
        )
        frac_in = ov / (w * h)
        stay = np.hypot(cx - ocx, cy - ocy) / diag  # otherwise move as little as possible
        if c.constraint_type == ConstraintType.FORBID_REGION:
            return 5.0 * (frac_in > 0) + stay
        return 3.0 * (1.0 - frac_in) + stay

    return region_hint


def _cell_target(parsed: Parsed, node: int, graph: CircuitGraph, prev: dict[int, PlacementEntry]) -> tuple[float, float]:
    """Desired lower-left for an explicitly edited standard cell (legalizer snaps it)."""
    W, H = graph.die.width, graph.die.height
    p = prev[node]
    if parsed.reference_node is not None:
        r = prev[parsed.reference_node]
        dx, dy = p.x - r.x, p.y - r.y
        ln = math.hypot(dx, dy) or 1.0
        if parsed.constraint.constraint_type == ConstraintType.MOVE_TOWARD:
            return r.x + dx / ln * 2, r.y + dy / ln * 2
        step = min(W, H) * 0.3
        return min(W - 1, max(0, p.x + dx / ln * step)), min(H - 1, max(0, p.y + dy / ln * step))
    reg = parsed.constraint.reference.value
    if parsed.constraint.constraint_type == ConstraintType.FORBID_REGION:
        inside = reg.x_min <= p.x <= reg.x_max and reg.y_min <= p.y <= reg.y_max
        if not inside:
            return p.x, p.y
        opts = [(reg.x_min - 1, p.y), (reg.x_max + 1, p.y), (p.x, reg.y_min - 1), (p.x, reg.y_max + 1)]
        opts = [(x, y) for x, y in opts if 0 <= x < W and 0 <= y < H] or [(p.x, p.y)]
        return min(opts, key=lambda o: abs(o[0] - p.x) + abs(o[1] - p.y))
    return min(max(p.x, reg.x_min), reg.x_max - 1), min(max(p.y, reg.y_min), reg.y_max - 1)


def apply_edit(parsed: Parsed, graph: CircuitGraph, previous: PlacementJSON, seed: int) -> PlacementJSON:
    prev = {p.node_id: p for p in previous.placements}
    c = parsed.constraint
    affected = set(c.affected_node_ids)
    hints = {i: _hint_for(parsed, i, graph, prev) for i in affected if graph.nodes[i].type == NodeType.MACRO}

    # Pass 1: move the affected macros with every other macro frozen, cells untouched.
    fixed = {i: prev[i] for i in range(len(graph.nodes)) if i not in hints}
    moved = place(graph, seed=seed, fixed=fixed, macro_hints=hints).placement
    new_pos = {p.node_id: p for p in moved.placements}

    # Pass 2: std cells under a moved macro's new footprint (or explicitly
    # affected cells) get re-legalized; everything else stays bit-identical.
    boxes = []
    for m in hints:
        nd, p = graph.nodes[m], new_pos[m]
        boxes.append(node_bbox(p.x, p.y, nd.width, nd.height, p.orientation))
    displaced, targets = [], {}
    for nd in graph.nodes:
        if nd.type != NodeType.STD_CELL:
            continue
        p = prev[nd.node_id]
        a = node_bbox(p.x, p.y, nd.width, nd.height, p.orientation)
        hit = nd.node_id in affected or any(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3] for b in boxes)
        if hit:
            displaced.append(nd.node_id)
            targets[nd.node_id] = _cell_target(parsed, nd.node_id, graph, prev) if nd.node_id in affected else (p.x, p.y)
    fixed2 = {i: (new_pos[i] if i in hints else prev[i]) for i in range(len(graph.nodes)) if i not in set(displaced)}
    result = place(graph, seed=seed, fixed=fixed2, cell_targets=targets).placement
    return result


def diff_report(
    constraint: ConstraintObject, before: PlacementJSON, after: PlacementJSON, hpwl_before: float, hpwl_after: float
) -> DiffReport:
    b = {p.node_id: p for p in before.placements}
    moved, unexpected = [], []
    frozen = set(constraint.frozen_node_ids)
    for p in after.placements:
        q = b[p.node_id]
        dx, dy = p.x - q.x, p.y - q.y
        if dx != 0 or dy != 0 or p.orientation != q.orientation:
            moved.append(MovedNode(node_id=p.node_id, delta_x=dx, delta_y=dy))
            if p.node_id in frozen:
                unexpected.append(p.node_id)
    return DiffReport(
        constraint_id=constraint.constraint_id,
        moved_nodes=moved,
        unexpected_moves=unexpected,
        hpwl_delta=hpwl_after - hpwl_before,
        # Congestion is blocked (no OpenROAD / tech LEF, see modules/evaluation/NOTES.md 1.2).
        # The schema requires a float; 0.0 here means "not measured", and the UI's
        # fallback panel says so explicitly next to it.
        congestion_delta=0.0,
    )


def summarize(parsed: Parsed, graph: CircuitGraph, report: DiffReport, hpwl_before: float, hpwl_after: float) -> str:
    c = parsed.constraint
    kinds = {n.node_id: ("macro" if n.type == NodeType.MACRO else "cell") for n in graph.nodes}
    what = ", ".join(f"{kinds[i]} {i}" for i in c.affected_node_ids[:6]) or "no nodes"
    # reference_node is None for a region-derived reference (e.g. a
    # ReferenceType.EDGE reference re-derived as a region -- see
    # fallback/server.py's _parsed_from_llm_constraint) even for a
    # node-shaped constraint_type like MOVE_TOWARD, so these fall back to
    # "the requested area" rather than the literal "node None".
    node_ref = f"node {parsed.reference_node}" if parsed.reference_node is not None else "the requested area"
    verb = {
        ConstraintType.MOVE_AWAY_FROM: f"moved away from {node_ref}",
        ConstraintType.MOVE_TOWARD: f"moved toward {node_ref}",
        ConstraintType.FORBID_ADJACENT: f"kept from being adjacent to {node_ref}",
        ConstraintType.PREFER_REGION: f"moved into the {parsed.direction or 'requested'} region",
        ConstraintType.FORBID_REGION: f"kept out of the {parsed.direction or 'requested'} region",
    }.get(c.constraint_type, "edited")
    cells = len(report.moved_nodes) - len([m for m in report.moved_nodes if m.node_id in set(c.affected_node_ids)])
    pct = (hpwl_after - hpwl_before) / hpwl_before * 100 if hpwl_before else 0.0
    return (
        f"[fallback] {what} {verb}. {cells} standard cell(s) under the new footprint were re-legalized; "
        f"{len(c.frozen_node_ids)} frozen macro(s) did not move. HPWL {'+' if pct >= 0 else ''}{pct:.1f}% "
        f"(shared/metrics). Congestion not measured in fallback mode."
    )
