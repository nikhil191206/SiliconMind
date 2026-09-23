"""CircuitNet real gate-level netlist + real timing features -> PretrainingGraph.

Owned by Person D's intake track / Person A's pretraining data prep
(TECHNICAL.md Section 1.14.2). Verified against real downloaded designs
under data/raw/circuitnet/circuitNetv3/dataset/Final/<design>/ — not a
synthetic fixture.

Two real files per design, cross-referenced:
- final_netlist.v: a real structural (post-P&R) Verilog netlist, generated
  by a real commercial EDA tool (Cadence Innovus, per its own header
  comment) -- `<CellType> <InstanceName> (.pin(net), ...);` instantiations.
- feature.json: real per-instance timing/electrical data from an actual
  static timing analysis report -- critically, `inputPins`/`outputPin`
  tell us which pin is the real driving output, which is exactly what we
  need to resolve each net's real driver/sink direction (the netlist text
  alone doesn't distinguish input from output pins without a cell
  library, which -- see shared/schemas/pretraining_graph.py's module
  docstring -- we don't have for this specific cell library).

See shared/schemas/pretraining_graph.py for why this produces a
PretrainingGraph, not a CircuitGraph: no real width/height exists in
CircuitNet's public release.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from shared.schemas.pretraining_graph import PretrainingGraph, PretrainingHyperedge, PretrainingNode

_INSTANCE_STATEMENT = re.compile(
    r"^\s{3}([A-Za-z][A-Za-z0-9_]*)\s+(\S+)\s*\((.*?)\)\s*;",
    re.MULTILINE | re.DOTALL,
)
_PIN_CONNECTION = re.compile(r"\.(\w+)\s*\(\s*([^()\s]+)\s*\)")


def _parse_instances(verilog_text: str) -> List[Tuple[str, str, Dict[str, str]]]:
    """Returns [(cell_name, instance_name, {pin_name: net_name}), ...]."""
    instances = []
    for match in _INSTANCE_STATEMENT.finditer(verilog_text):
        cell_name, instance_name, body = match.group(1), match.group(2), match.group(3)
        if cell_name in ("module", "input", "output", "wire", "inout", "assign", "endmodule"):
            continue  # not an instantiation
        pins = {pin: net for pin, net in _PIN_CONNECTION.findall(body)}
        if pins:
            instances.append((cell_name, instance_name, pins))
    return instances


def parse_circuitnet_design(design_dir: Path) -> Tuple[PretrainingGraph, Dict[str, Dict]]:
    """Returns (graph, raw_features) where raw_features maps instance name
    to its full real feature.json entry, for callers that want fields
    beyond what PretrainingNode carries (e.g. exact pin names)."""
    verilog_text = (design_dir / "final_netlist.v").read_text(encoding="utf-8", errors="replace")
    with open(design_dir / "feature.json", encoding="utf-8") as f:
        raw_features: Dict[str, Dict] = json.load(f)

    instances = _parse_instances(verilog_text)

    name_to_id: Dict[str, int] = {}
    nodes: List[PretrainingNode] = []
    # net_name -> (driver_node_id or None, [sink_node_ids])
    net_driver: Dict[str, Optional[int]] = {}
    net_sinks: Dict[str, List[int]] = {}

    def _to_float(raw: Optional[str]) -> Optional[float]:
        if raw is None:
            return None
        try:
            # Several feature.json fields are "rise fall" pairs, e.g.
            # "0.002151 0.002149" -- use their average as one real scalar.
            parts = [float(p) for p in str(raw).split()]
            return sum(parts) / len(parts) if parts else None
        except ValueError:
            return None

    for cell_name, instance_name, pins in instances:
        feat = raw_features.get(instance_name)
        if feat is None:
            continue  # no real timing data for this instance -- skip rather than fabricate it
        node_id = len(nodes)
        name_to_id[instance_name] = node_id

        input_pin_names = str(feat.get("inputPins", "")).split()
        output_pin_name = feat.get("outputPin")
        is_sequential = "CK" in input_pin_names or "clk" in [p.lower() for p in input_pin_names]

        nodes.append(
            PretrainingNode(
                node_id=node_id,
                cell_name=cell_name,
                pin_count=len(pins),
                is_sequential=is_sequential,
                drive_strength=_to_float(feat.get("driveStrength")),
                fanout_load=_to_float(feat.get("fanoutLoad (rise fall)")),
                fanout_res=_to_float(feat.get("fanoutRes")),
                slack=_to_float(feat.get("slack")),
                arrival_time=_to_float(feat.get("AT")),
            )
        )

        for pin_name, net_name in pins.items():
            net_sinks.setdefault(net_name, [])
            if pin_name == output_pin_name:
                net_driver[net_name] = node_id
            else:
                net_sinks[net_name].append(node_id)

    hyperedges: List[PretrainingHyperedge] = []
    net_id = 0
    for net_name, sinks in net_sinks.items():
        driver = net_driver.get(net_name)
        # De-dup and drop the driver from its own sink list if it ended up
        # there (e.g. a net with only one real-featured endpoint recorded).
        sink_ids = sorted({s for s in sinks if s != driver})
        if driver is None and len(sink_ids) < 2:
            continue  # not enough real connectivity to be a meaningful hyperedge
        if driver is not None and not sink_ids:
            continue  # driver with no real sinks recorded -- nothing to connect
        hyperedges.append(PretrainingHyperedge(net_id=net_id, driver_node=driver, sink_nodes=sink_ids))
        net_id += 1

    graph = PretrainingGraph(design_name=design_dir.name, nodes=nodes, hyperedges=hyperedges)
    return graph, raw_features
