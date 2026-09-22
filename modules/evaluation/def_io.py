"""Placement JSON -> DEF export — TECHNICAL.md Section 1.2 step 10 ("Final
DEF export") and Section 1.3 ("Placement output: DEF file, plus the
internal Placement JSON").

Caveat, stated up front because it matters: Circuit Graph JSON (Section
3.1) carries no real standard-cell-library names or pin names — only
generic width/height/pin_count. A real DEF consumer (OpenROAD, a real PDK
flow) expects COMPONENTS to reference real LEF cell models and NETS to
reference real pin names. This writer produces a structurally valid DEF
(correct syntax, correct DIEAREA/placement/orientation/connectivity) using
synthesized placeholder names (`MACRO`/`STDCELL` as the model, `PIN` as
every pin's name) — good enough for OpenROAD to parse and for visual/
geometric round-tripping, but not a substitute for merging in a real LEF
library, which is a Person-D/ASAP7-PDK-path concern (Section 1.13 source 3),
not something inventable here. See NOTES.md.
"""

from pathlib import Path

from shared.schemas.circuit_graph import CircuitGraph, NodeType
from shared.schemas.placement import PlacementJSON

_DISTANCE_UNITS_PER_MICRON = 1000
_PLACEHOLDER_PIN_NAME = "PIN"


def _model_name(node_type: NodeType) -> str:
    return "MACRO" if node_type == NodeType.MACRO else "STDCELL"


def _to_dbu(value: float) -> int:
    return round(value * _DISTANCE_UNITS_PER_MICRON)


def write_def(graph: CircuitGraph, placement: PlacementJSON, path: Path) -> Path:
    if placement.design_name != graph.design_name:
        raise ValueError(
            f"placement.design_name ({placement.design_name!r}) must match "
            f"graph.design_name ({graph.design_name!r})"
        )

    node_by_id = {n.node_id: n for n in graph.nodes}
    entry_by_id = {p.node_id: p for p in placement.placements}
    node_name = lambda node_id: f"o{node_id}"  # noqa: E731 - matches bookshelf_io.py's node-naming convention

    lines = [
        "VERSION 5.8 ;",
        "DIVIDERCHAR \"/\" ;",
        "BUSBITCHARS \"[]\" ;",
        f"DESIGN {graph.design_name} ;",
        f"UNITS DISTANCE MICRONS {_DISTANCE_UNITS_PER_MICRON} ;",
        "",
        f"DIEAREA ( 0 0 ) ( {_to_dbu(graph.die.width)} {_to_dbu(graph.die.height)} ) ;",
        "",
        f"COMPONENTS {len(graph.nodes)} ;",
    ]
    for node_id, node in node_by_id.items():
        entry = entry_by_id[node_id]
        name = node_name(node_id)
        lines.append(
            f"- {name} {_model_name(node.type)} + PLACED ( {_to_dbu(entry.x)} {_to_dbu(entry.y)} ) "
            f"{entry.orientation.value} ;"
        )
    lines.append("END COMPONENTS")
    lines.append("")

    lines.append(f"NETS {graph.num_hyperedges} ;")
    for hyperedge in graph.hyperedges:
        pin_node_ids = list(hyperedge.sink_nodes)
        if hyperedge.driver_node is not None:
            pin_node_ids.append(hyperedge.driver_node)
        pins = " ".join(f"( {node_name(nid)} {_PLACEHOLDER_PIN_NAME} )" for nid in pin_node_ids)
        lines.append(f"- net{hyperedge.net_id} {pins} ;")
    lines.append("END NETS")
    lines.append("")
    lines.append("END DESIGN")

    path = Path(path)
    path.write_text("\n".join(lines) + "\n")
    return path
