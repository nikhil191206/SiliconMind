"""Natural-Language Constraint Parser — TECHNICAL.md Section 4.D / Section 3.4.

Owned by Person D.
Translates a designer's plain-language layout critique into a structured
ConstraintObject (Section 3.4) for Person B's placement-edit mechanism.

Hard Rule (Section 3.4 / 1.7):
If constraint_type == UNCLEAR or confidence < 0.6, requires_clarification()
returns True — Person B's generator MUST NOT be called in this case.
"""

import json
import re
from typing import Dict, List, Optional, Tuple, Union

from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.constraint import (
    ConstraintObject,
    ConstraintReference,
    ConstraintType,
    ReferenceType,
    RegionBoundingBox,
    Strength,
)
from shared.schemas.placement import PlacementJSON


def _fallback_parse_heuristic(
    nl_text: str, current_placement: PlacementJSON, graph: Optional[CircuitGraph] = None
) -> ConstraintObject:
    """Deterministic heuristic parser for offline/test fallback.

    Parses natural language phrases like:
      - "Move node_0 away from node_1"
      - "Move SRAM_0 away from the left edge"
      - "Move MACRO_0 closer to MACRO_1"
      - "Move node_2 to region 10 10 50 50"
      - "Move that block" (ambiguous -> UNCLEAR)
    """
    text_lower = nl_text.lower().strip()
    all_node_ids = [p.node_id for p in current_placement.placements]

    # Check for ambiguous requests without explicit target node or macro reference.
    # Digit-extraction pattern note: a plain `\b(\d+)\b` does NOT match the "0" in
    # "node_0" — `_` counts as a word character, so there is no \b boundary between
    # "node_" and "0". That silently turned "move node_0 away from node_1" into a
    # self-referential "move node 0 away from node 0" (both digits vanished, so it
    # fell back to the first placed node for both the affected node and its own
    # reference), which produced a zero-distance guidance target end-to-end through
    # generation. Matching on "not immediately preceded by a letter or digit"
    # instead treats `_`/`#`/whitespace/start-of-string as valid separators, so
    # "node_0", "SRAM_0", "macro#1", and a bare "10" all extract correctly.
    _ID_PATTERN = r"(?<![a-zA-Z0-9])(\d+)"
    ambiguous_triggers = ["move that", "move it", "change something", "too close", "fix placement", "optimize"]
    has_explicit_id = bool(re.search(_ID_PATTERN, text_lower))

    if any(trigger in text_lower for trigger in ambiguous_triggers) and not has_explicit_id:
        return ConstraintObject(
            source_request=nl_text,
            frozen_node_ids=all_node_ids,
            affected_node_ids=[],
            constraint_type=ConstraintType.UNCLEAR,
            reference=ConstraintReference(type=ReferenceType.NODE, value=all_node_ids[0] if all_node_ids else 0),
            strength=Strength.SOFT,
            confidence=0.3,
        )

    # Extract node numbers mentioned in text. Only the FIRST valid node id is
    # the node being moved (`affected_nodes`) — a second id in phrasing like
    # "move node_0 away from node_1" is the reference point, not something
    # else being moved, and must stay out of affected_nodes so it's frozen
    # like every other untouched node (see digits[1] used as ref_val below;
    # collecting every matching digit here previously put the reference node
    # in both affected_nodes and, incorrectly, never in frozen_node_ids).
    digits = [int(m) for m in re.findall(_ID_PATTERN, text_lower)]

    affected_nodes: List[int] = []
    for d in digits:
        if d in all_node_ids:
            affected_nodes = [d]
            break

    if not affected_nodes:
        # If no digits matched node IDs, default to first node if available or mark UNCLEAR
        if all_node_ids:
            affected_nodes = [all_node_ids[0]]
        else:
            return ConstraintObject(
                source_request=nl_text,
                frozen_node_ids=[],
                affected_node_ids=[],
                constraint_type=ConstraintType.UNCLEAR,
                reference=ConstraintReference(type=ReferenceType.NODE, value=0),
                strength=Strength.SOFT,
                confidence=0.4,
            )

    # Determine constraint type and reference
    c_type = ConstraintType.MOVE_AWAY_FROM
    ref_type = ReferenceType.NODE
    ref_val: Union[int, RegionBoundingBox] = affected_nodes[0]
    confidence = 0.85

    if "toward" in text_lower or "closer" in text_lower or "near" in text_lower:
        c_type = ConstraintType.MOVE_TOWARD
        if len(digits) >= 2 and digits[1] in all_node_ids:
            ref_val = digits[1]
    elif "away" in text_lower or "far" in text_lower or "distance" in text_lower:
        c_type = ConstraintType.MOVE_AWAY_FROM
        if len(digits) >= 2 and digits[1] in all_node_ids:
            ref_val = digits[1]
    elif "forbid region" in text_lower or "avoid region" in text_lower:
        c_type = ConstraintType.FORBID_REGION
        ref_type = ReferenceType.REGION
        ref_val = RegionBoundingBox(x_min=0.0, y_min=0.0, x_max=200.0, y_max=200.0)
    elif "prefer region" in text_lower or "place in region" in text_lower:
        c_type = ConstraintType.PREFER_REGION
        ref_type = ReferenceType.REGION
        ref_val = RegionBoundingBox(x_min=100.0, y_min=100.0, x_max=500.0, y_max=500.0)
    elif "adjacent" in text_lower or "touching" in text_lower:
        c_type = ConstraintType.FORBID_ADJACENT
        if len(digits) >= 2 and digits[1] in all_node_ids:
            ref_val = digits[1]

    strength = Strength.HARD if ("must" in text_lower or "hard" in text_lower or "strict" in text_lower) else Strength.SOFT

    # Freeze every node EXCEPT the affected nodes
    frozen_nodes = [nid for nid in all_node_ids if nid not in affected_nodes]

    return ConstraintObject(
        source_request=nl_text,
        frozen_node_ids=frozen_nodes,
        affected_node_ids=affected_nodes,
        constraint_type=c_type,
        reference=ConstraintReference(type=ref_type, value=ref_val),
        strength=strength,
        confidence=confidence,
    )


def parse_constraint(
    nl_text: str,
    current_placement: PlacementJSON,
    graph: Optional[CircuitGraph] = None,
    api_key: Optional[str] = None,
) -> ConstraintObject:
    """Parses a designer's natural-language critique into a structured ConstraintObject.

    Args:
        nl_text: Designer instruction string.
        current_placement: Verified current placement.
        graph: Optional CircuitGraph for net/node metadata.
        api_key: Optional OpenAI/LLM API key.

    Returns:
        Schema-valid ConstraintObject (Section 3.4).
    """
    from shared.llm_client import NoLLMCredentialsError, resolve_llm_client

    try:
        resolved = resolve_llm_client(api_key)
    except NoLLMCredentialsError:
        return _fallback_parse_heuristic(nl_text, current_placement, graph)

    try:
        nodes_info = [{"node_id": p.node_id, "x": p.x, "y": p.y} for p in current_placement.placements[:20]]
        die_info = {"width": graph.die.width, "height": graph.die.height} if graph is not None else None

        prompt = (
            "You are a VLSI placement constraint parser. Translate the following user natural-language "
            "placement request into a structured JSON constraint object.\n"
            f"Available placement nodes (sample): {json.dumps(nodes_info)}\n"
            f"Die area: {json.dumps(die_info)}\n"
            f"User request: '{nl_text}'\n\n"
            "Output JSON with these exact keys:\n"
            "- affected_node_ids: list of int node_ids specified to move\n"
            "- constraint_type: one of ['MOVE_AWAY_FROM', 'MOVE_TOWARD', 'FORBID_ADJACENT', 'FORBID_REGION', 'PREFER_REGION', 'UNCLEAR']\n"
            "- reference_type: one of ['NODE', 'REGION', 'EDGE']\n"
            "- reference_node_id: int node_id if reference_type is NODE or EDGE, else null\n"
            "- reference_region: {\"x_min\": float, \"y_min\": float, \"x_max\": float, \"y_max\": float} if "
            "reference_type is REGION (infer sensible die-relative bounds from the request, e.g. 'top-left "
            "corner' or 'near the edge'), else null\n"
            "- strength: 'HARD' or 'SOFT'\n"
            "- confidence: float between 0.0 and 1.0 (set < 0.6 if ambiguous or unclear)\n"
        )

        response = resolved.client.chat.completions.create(
            model=resolved.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        raw_json = response.choices[0].message.content or "{}"
        parsed = json.loads(raw_json)

        affected = [int(n) for n in parsed.get("affected_node_ids", [])]
        all_node_ids = [p.node_id for p in current_placement.placements]
        frozen = [n for n in all_node_ids if n not in affected]

        c_type_str = str(parsed.get("constraint_type", "UNCLEAR")).upper()
        ref_type_str = str(parsed.get("reference_type", "NODE")).upper()

        ref_val: Union[int, RegionBoundingBox]
        if ref_type_str == "REGION" and parsed.get("reference_region"):
            region = parsed["reference_region"]
            ref_val = RegionBoundingBox(
                x_min=float(region["x_min"]),
                y_min=float(region["y_min"]),
                x_max=float(region["x_max"]),
                y_max=float(region["y_max"]),
            )
        else:
            ref_node_id = parsed.get("reference_node_id")
            ref_val = int(ref_node_id) if ref_node_id is not None else (affected[0] if affected else 0)

        confidence = float(parsed.get("confidence", 0.9))

        return ConstraintObject(
            source_request=nl_text,
            frozen_node_ids=frozen,
            affected_node_ids=affected,
            constraint_type=ConstraintType(c_type_str) if c_type_str in ConstraintType.__members__ else ConstraintType.UNCLEAR,
            reference=ConstraintReference(
                type=ReferenceType(ref_type_str) if ref_type_str in ReferenceType.__members__ else ReferenceType.NODE,
                value=ref_val,
            ),
            strength=Strength.HARD if str(parsed.get("strength")).upper() == "HARD" else Strength.SOFT,
            confidence=confidence,
        )

    except Exception:
        # Fallback to heuristic parser on API error
        return _fallback_parse_heuristic(nl_text, current_placement, graph)
