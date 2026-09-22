"""Google Circuit Training `.pb.txt` -> Circuit Graph JSON (Section 3.1) parser.

Owned by Person D's intake track (TECHNICAL.md Section 1.13 source 4: "the
netlist ships in Protocol Buffer (.pb.txt) format... use [a converter] to
bring this into the same Circuit Graph JSON pipeline as every other
source"). Verified against the real downloaded
`data/raw/ariane_circuit_training/netlist.pb.txt` (the actual Ariane
RISC-V netlist from Google's circuit_training repo) — not a synthetic
fixture. See `tests/unit/intake/test_protobuf_parser.py`.

Format, verified directly against the real file (not assumed from
documentation, which disagreed with itself in places during review):

- Each `node { name: "..." input: "..." ... attr { key: "type" value {
  placeholder: "X" } } ... }` block is one object. `type` is one of PORT,
  MACRO, MACRO_PIN, or (lowercase) macro / macro_pin.
- **`input:` lists the nodes this node DRIVES (fanout), not what drives
  it** — despite the name. Verified directly: the real-input port `rst_ni`
  (a chip-level reset signal, which must be a driver, not a receiver) lists
  9 `input:` entries, and a pin literally named ".../Poutput_multi_0"
  lists two `input:` entries pointing at OTHER nodes' ".../Pinput" pins —
  an output driving inputs elsewhere is exactly the right direction, a
  reset receiving from 9 sources would be nonsensical. So for hyperedge
  construction: `driver = node`, `sinks = node.input` (after resolving
  pins to their owning macro, see below).
- **Two abstraction layers are both present and both real**: 133 uppercase
  `MACRO` nodes are the actual physical SRAM macros (real width/height/x/y/
  orientation) with 11,970 uppercase `MACRO_PIN` children; 799 lowercase
  `macro` nodes are Circuit Training's own clustering of the surrounding
  standard-cell logic into soft aggregate blocks (also real width/height/
  position, just derived from real clustering, not fabricated) with 10,832
  lowercase `macro_pin` children. There are zero individual standard-cell
  nodes in this file at all — this specific netlist is the macro-placement
  abstraction Circuit Training's own RL problem is defined over (Mirhoseini
  et al., cited in TECHNICAL.md Section 1.12), not a full gate-level
  netlist.
- A `MACRO_PIN`/`macro_pin` node is not its own CircuitGraph node — its
  `macro_name` attr says which macro/cluster owns it, and its `input:`
  edges are attributed to that owning node (CircuitGraph connects
  MACRO/STD_CELL nodes, not individual pins).
- Node type mapping to Section 3.1's MACRO | STD_CELL: uppercase `MACRO` ->
  MACRO (real hard macros). Lowercase `macro` (a clustered-logic
  aggregate, not a real physical macro) and `PORT` (a primary I/O
  terminal) -> STD_CELL, since the schema has no third category — the same
  real gap already documented in lefdef_parser.py for DEF terminals.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from shared.schemas.circuit_graph import CircuitGraph, CircuitHyperedge, CircuitNode, Die, NodeType

_NAME_RE = re.compile(r'^\s*name:\s*"([^"]+)"')
_INPUT_RE = re.compile(r'^\s*input:\s*"([^"]+)"')
_KEY_RE = re.compile(r'^\s*key:\s*"([^"]+)"')
_FLOAT_RE = re.compile(r'^\s*f:\s*(-?[\d.eE+-]+)')
_PLACEHOLDER_RE = re.compile(r'^\s*placeholder:\s*"([^"]+)"')

_HARD_MACRO_TYPES = {"MACRO"}
_CLUSTER_MACRO_TYPES = {"macro"}
_PORT_TYPES = {"PORT"}
_MACRO_LIKE_TYPES = _HARD_MACRO_TYPES | _CLUSTER_MACRO_TYPES
_PIN_TYPES = {"MACRO_PIN", "macro_pin"}


@dataclass
class _RawNode:
    name: str
    inputs: List[str] = field(default_factory=list)
    attrs: Dict[str, object] = field(default_factory=dict)


def _parse_nodes(pb_path: Path) -> List[_RawNode]:
    """Single-pass line-based parser (this file's own `attr { key: ... value
    { ... } }` grammar is simple enough not to need a real protobuf
    library/compiled schema — TECHNICAL.md Section 1.13 source 4 only ships
    the text form, and the official MacroPlacement FormatTranslators
    reference (data/raw/macroplacement/.../ProtobufToLEFDEF.py) parses it
    the same way)."""
    nodes: List[_RawNode] = []
    current: Optional[_RawNode] = None
    current_key: Optional[str] = None

    with pb_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("node {"):
                current = _RawNode(name="")
                nodes.append(current)
                continue
            if current is None:
                continue

            m = _NAME_RE.match(line)
            if m:
                current.name = m.group(1)
                continue
            m = _INPUT_RE.match(line)
            if m:
                current.inputs.append(m.group(1))
                continue
            m = _KEY_RE.match(line)
            if m:
                current_key = m.group(1)
                continue
            m = _FLOAT_RE.match(line)
            if m and current_key is not None:
                current.attrs[current_key] = float(m.group(1))
                continue
            m = _PLACEHOLDER_RE.match(line)
            if m and current_key is not None:
                current.attrs[current_key] = m.group(1)
                continue
    return nodes


def parse_protobuf_netlist(pb_path: Path, design_name: Optional[str] = None) -> CircuitGraph:
    raw_nodes = _parse_nodes(pb_path)
    by_name: Dict[str, _RawNode] = {n.name: n for n in raw_nodes}

    # Pass 1: identify graph nodes (macro-like + port) and pins, and count
    # each macro-like node's pins for CircuitNode.pin_count.
    graph_node_names: List[str] = []
    pin_count: Dict[str, int] = {}
    for n in raw_nodes:
        node_type = n.attrs.get("type")
        if node_type in _MACRO_LIKE_TYPES or node_type in _PORT_TYPES:
            graph_node_names.append(n.name)
            pin_count.setdefault(n.name, 0)
        elif node_type in _PIN_TYPES:
            owner = n.attrs.get("macro_name")
            if isinstance(owner, str):
                pin_count[owner] = pin_count.get(owner, 0) + 1

    name_to_id = {name: i for i, name in enumerate(graph_node_names)}

    def resolve_owner(node_name: str) -> Optional[int]:
        """A connectivity endpoint is either already a graph node (macro/
        port) or a *_PIN belonging to one via macro_name — resolve either
        case to a CircuitGraph node_id."""
        if node_name in name_to_id:
            return name_to_id[node_name]
        raw = by_name.get(node_name)
        if raw is None:
            return None
        owner_name = raw.attrs.get("macro_name")
        if isinstance(owner_name, str):
            return name_to_id.get(owner_name)
        return None

    nodes: List[CircuitNode] = []
    for name in graph_node_names:
        raw = by_name[name]
        node_type_str = raw.attrs.get("type")
        node_type = NodeType.MACRO if node_type_str in _HARD_MACRO_TYPES else NodeType.STD_CELL
        width = float(raw.attrs.get("width", 0.0)) or 1e-3  # PORT nodes carry no width/height; schema requires > 0
        height = float(raw.attrs.get("height", 0.0)) or 1e-3
        nodes.append(
            CircuitNode(
                node_id=name_to_id[name],
                type=node_type,
                width=width,
                height=height,
                pin_count=max(pin_count.get(name, 0), 1),
            )
        )

    # Pass 2: build hyperedges. Every node (graph node OR pin) with a
    # non-empty `input` list is a driver; its inputs are the sinks it
    # fans out to (see module docstring for how this direction was
    # verified against the real file).
    hyperedges: List[CircuitHyperedge] = []
    net_id = 0
    for n in raw_nodes:
        if not n.inputs:
            continue
        driver_id = resolve_owner(n.name)
        if driver_id is None:
            continue
        sink_ids = sorted({resolve_owner(target) for target in n.inputs} - {None, driver_id})
        if not sink_ids:
            continue
        hyperedges.append(CircuitHyperedge(net_id=net_id, driver_node=driver_id, sink_nodes=sink_ids))
        net_id += 1

    xs = [raw.attrs.get("x") for raw in by_name.values() if isinstance(raw.attrs.get("x"), float)]
    ys = [raw.attrs.get("y") for raw in by_name.values() if isinstance(raw.attrs.get("y"), float)]
    die_width = (max(xs) - min(xs)) if xs else 1.0
    die_height = (max(ys) - min(ys)) if ys else 1.0

    return CircuitGraph(
        design_name=design_name or pb_path.stem,
        nodes=nodes,
        hyperedges=hyperedges,
        die=Die(width=die_width, height=die_height),
    )
