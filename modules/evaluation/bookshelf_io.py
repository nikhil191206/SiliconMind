"""Circuit Graph JSON / Placement JSON <-> Bookshelf format, round-trip.

DREAMPlace (and the ISPD02/ISPD2015 benchmarks themselves, per TECHNICAL.md
Section 1.13) speak the MARCO GSRC Bookshelf format (`.nodes`/`.nets`/`.pl`/
`.scl`/`.aux`), not our internal JSON schemas. This module is the adapter:
`write_bookshelf` dumps a (CircuitGraph, PlacementJSON) pair to a Bookshelf
design for `legalizer.py` to hand to DREAMPlace, and `read_bookshelf_placement`
parses DREAMPlace's output `.pl` back into a PlacementJSON.

This is fully testable without DREAMPlace itself installed — it's a format
converter, not a call into the external tool (that's `legalizer.py`).

Row/site geometry (`.scl`) is not part of Circuit Graph JSON (Section 3.1),
which only carries die width/height, not row height or site width. This
module synthesizes a single-height-row `.scl` covering the die, using the
smallest standard-cell height in the graph as the row height (falling back
to the die height if there are no standard cells, e.g. a macro-only mock
graph) — a documented approximation, not a real row-based floorplan. Real
ISPD02/ISPD2015 benchmarks ship their own authentic `.scl` files and should
use those directly rather than a regenerated one; this synthesized version
exists only so mock/toy graphs can round-trip through DREAMPlace at all.
"""

import math
from pathlib import Path

from shared.schemas.circuit_graph import CircuitGraph, NodeType
from shared.schemas.placement import GenerationMetadata, Orientation, PlacementEntry, PlacementJSON

_NODE_NAME_PREFIX = "o"


def _node_name(node_id: int) -> str:
    return f"{_NODE_NAME_PREFIX}{node_id}"


def _node_id_from_name(name: str) -> int:
    if not name.startswith(_NODE_NAME_PREFIX):
        raise ValueError(f"unrecognized Bookshelf node name (expected '{_NODE_NAME_PREFIX}<id>'): {name!r}")
    return int(name[len(_NODE_NAME_PREFIX) :])


def _write_nodes_file(graph: CircuitGraph, path: Path) -> None:
    num_terminals = 0  # nothing is a fixed pad/pin in this project's usage; all nodes are movable.
    lines = [
        "UCLA nodes 1.0",
        f"NumNodes : {graph.num_nodes}",
        f"NumTerminals : {num_terminals}",
        "",
    ]
    for node in graph.nodes:
        lines.append(f"{_node_name(node.node_id)} {node.width:g} {node.height:g}")
    path.write_text("\n".join(lines) + "\n")


def _write_nets_file(graph: CircuitGraph, path: Path) -> None:
    num_pins = sum(1 + len(h.sink_nodes) if h.driver_node is not None else len(h.sink_nodes) for h in graph.hyperedges)
    lines = [
        "UCLA nets 1.0",
        f"NumNets : {graph.num_hyperedges}",
        f"NumPins : {num_pins}",
        "",
    ]
    for hyperedge in graph.hyperedges:
        pins: list[tuple[int, str]] = []
        if hyperedge.driver_node is not None:
            pins.append((hyperedge.driver_node, "O"))
        pins.extend((sink, "I") for sink in hyperedge.sink_nodes)

        lines.append(f"NetDegree : {len(pins)} net{hyperedge.net_id}")
        for node_id, direction in pins:
            # No per-pin offset in Circuit Graph JSON (Section 3.1) -> pin
            # placed at the node's own origin (0, 0 offset), consistent with
            # shared/metrics/hpwl.py's node-center approximation being the
            # project-wide convention for missing pin-level geometry.
            lines.append(f"\t{_node_name(node_id)} {direction} : 0 0")
    path.write_text("\n".join(lines) + "\n")


def _write_pl_file(graph: CircuitGraph, placement: PlacementJSON, path: Path) -> None:
    lines = ["UCLA pl 1.0", ""]
    for entry in placement.placements:
        lines.append(f"{_node_name(entry.node_id)} {entry.x:g} {entry.y:g} : {entry.orientation.value}")
    path.write_text("\n".join(lines) + "\n")


def _write_scl_file(graph: CircuitGraph, path: Path) -> None:
    std_cell_heights = [n.height for n in graph.nodes if n.type == NodeType.STD_CELL]
    row_height = min(std_cell_heights) if std_cell_heights else graph.die.height
    num_rows = max(1, math.floor(graph.die.height / row_height))

    lines = ["UCLA scl 1.0", f"NumRows : {num_rows}", ""]
    for row_index in range(num_rows):
        y = row_index * row_height
        lines += [
            "CoreRow Horizontal",
            f"  Coordinate : {y:g}",
            f"  Height : {row_height:g}",
            "  Sitewidth : 1",
            "  Sitespacing : 1",
            "  Siteorient : 1",
            "  Sitesymmetry : 1",
            f"  SubrowOrigin : 0  NumSites : {math.floor(graph.die.width)}",
            "End",
        ]
    path.write_text("\n".join(lines) + "\n")


def _write_aux_file(design_name: str, path: Path) -> None:
    path.write_text(
        f"RowBasedPlacement : {design_name}.nodes {design_name}.nets {design_name}.wts "
        f"{design_name}.pl {design_name}.scl\n"
    )


def _write_wts_file(graph: CircuitGraph, path: Path) -> None:
    lines = ["UCLA wts 1.0", ""]
    for node in graph.nodes:
        lines.append(f"{_node_name(node.node_id)} 1")
    path.write_text("\n".join(lines) + "\n")


def write_bookshelf(graph: CircuitGraph, placement: PlacementJSON, out_dir: Path) -> Path:
    """Writes a full Bookshelf design (`.aux` + `.nodes` + `.nets` + `.wts`
    + `.pl` + `.scl`) for `graph`/`placement` under `out_dir`, named after
    `graph.design_name`. Returns the path to the `.aux` file, which is what
    DREAMPlace's config takes as `aux_input` (see `legalizer.py`)."""
    if placement.design_name != graph.design_name:
        raise ValueError(
            f"placement.design_name ({placement.design_name!r}) must match "
            f"graph.design_name ({graph.design_name!r})"
        )
    placement_node_ids = {p.node_id for p in placement.placements}
    graph_node_ids = {n.node_id for n in graph.nodes}
    if placement_node_ids != graph_node_ids:
        raise ValueError("placement.placements must cover exactly graph.nodes' node_ids, no more, no fewer")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    design_name = graph.design_name

    _write_nodes_file(graph, out_dir / f"{design_name}.nodes")
    _write_nets_file(graph, out_dir / f"{design_name}.nets")
    _write_wts_file(graph, out_dir / f"{design_name}.wts")
    _write_pl_file(graph, placement, out_dir / f"{design_name}.pl")
    _write_scl_file(graph, out_dir / f"{design_name}.scl")
    aux_path = out_dir / f"{design_name}.aux"
    _write_aux_file(design_name, aux_path)
    return aux_path


def read_bookshelf_placement(pl_path: Path, design_name: str, model_variant: str, seed: int) -> PlacementJSON:
    """Parses a Bookshelf `.pl` file (as DREAMPlace writes for its
    global/legalized/detailed-placed output) into a schema-valid
    PlacementJSON. `is_legalized` is left False here — the caller
    (`legalizer.py`) sets it True only for output it has confirmed passed
    legalization."""
    entries = []
    for line in Path(pl_path).read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("UCLA") or stripped.startswith("#"):
            continue
        # Format: "<name> <x> <y> : <orientation>" (extra trailing flags
        # such as "/FIXED" on some Bookshelf variants are ignored).
        head, _, orientation_part = stripped.partition(":")
        parts = head.split()
        if len(parts) < 3:
            continue
        name, x_str, y_str = parts[0], parts[1], parts[2]
        orientation_token = orientation_part.split()[0] if orientation_part.split() else "N"
        entries.append(
            PlacementEntry(
                node_id=_node_id_from_name(name),
                x=float(x_str),
                y=float(y_str),
                orientation=Orientation(orientation_token),
            )
        )
    entries.sort(key=lambda e: e.node_id)
    return PlacementJSON(
        design_name=design_name,
        placements=entries,
        generation_metadata=GenerationMetadata(model_variant=model_variant, seed=seed, is_legalized=False),
    )
