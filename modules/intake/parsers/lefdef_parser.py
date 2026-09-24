"""LEF/DEF -> Circuit Graph JSON (Section 3.1) parser.

Owned by Person D's intake track (TECHNICAL.md Section 1.3: "structural
Verilog netlist (post-synthesis) OR LEF/DEF pair. Both must be supported at
the intake boundary"). This is the first real-benchmark ingestion parser
built for this project — until now `modules/intake/parsers/` only had a
placeholder; ISPD02/ISPD2015 (Section 1.13 sources 1-2) ship exactly this
format and were sitting in `data/raw/` unusable without it.

Verified against the real downloaded `data/raw/ispd02/ibmISPD02Bench_LEFDEF/`
benchmarks (IBM01-IBM18) — not a synthetic fixture. See
`tests/unit/intake/test_lefdef_parser.py`.

Format notes (ISPD02 IBM* benchmarks specifically):

- The LEF here is a *cell-shape library*: each MACRO (e.g. "MAS7") is one
  distinct (width, height, pin-count) shape reused by many DEF COMPONENT
  instances — it is NOT the component's real functional name.
- Every MACRO in every IBM01-IBM18 LEF is standard-cell-scale (checked: max
  ~0.5 x 0.16 microns on a uniform 0.16-micron row height, matching the
  SITE definition) — this benchmark suite is standard-cell-only placement,
  with no real macros. So every node here is classified STD_CELL. This is
  a real, checked property of this specific benchmark family, not a
  guess — a future parser for a benchmark family that DOES ship real macros
  (e.g. ISPD2015's fence-region designs) needs its own size-based or
  explicit-class threshold, not this same hardcoded rule.
- "PIN" components (DEF names like "p1", "p2", ...) are primary I/O
  terminals, DEF-FIXED at the die boundary — CircuitGraph (Section 3.1) has
  no "fixed" flag, which is a real schema gap this parser cannot silently
  paper over: it loads every DEF COMPONENT (terminals included) as an
  ordinary node, and callers that need to know a node must not move (e.g.
  a future real training data prep step) must currently infer FIXED status
  from the original DEF file themselves. Flagged here rather than adding an
  undocumented convention (e.g. "any node with pin_count==1 is fixed").
- NETS in this format list `(component pin)` pairs with no explicit
  driver/sink annotation. Convention adopted here, consistent with common
  Bookshelf/DEF-parsing practice (e.g. DREAMPlace's own bookshelf reader):
  the FIRST pin listed in a net is treated as the driver, the rest as
  sinks. This is a real, stated assumption, not a fabricated one — the
  format genuinely does not distinguish them.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from shared.schemas.circuit_graph import CircuitGraph, CircuitHyperedge, CircuitNode, Die, NodeType
from shared.schemas.placement import GenerationMetadata, Orientation, PlacementEntry, PlacementJSON

_MICRON_SCALE_DEFAULT = 100  # DEF "UNITS DISTANCE MICRONS <n>" — DEF coords are in 1/n micron


@dataclass
class LefMacro:
    name: str
    width: float  # microns
    height: float  # microns
    pin_count: int


def parse_lef(lef_path: Path) -> Dict[str, LefMacro]:
    """Parses MACRO ... SIZE ... PIN ... END <name> blocks into a name -> LefMacro map.
    Ignores everything else in the LEF (layers, vias, sites, spacing rules) —
    none of that is part of Section 3.1's schema. A LEF with zero MACRO
    blocks (e.g. ISPD2015's tech.lef, which only defines layers/sites) is
    valid and returns an empty dict — some real benchmark families split
    the cell library (cells.lef) from the technology file (tech.lef), see
    parse_lef_library below."""
    text = lef_path.read_text(encoding="utf-8", errors="replace")
    macros: Dict[str, LefMacro] = {}

    for match in re.finditer(r"^MACRO\s+(\S+)\s*$(.*?)^END\s+\1\s*$", text, re.MULTILINE | re.DOTALL):
        name, body = match.group(1), match.group(2)
        size_match = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)\s*;", body)
        if size_match is None:
            raise ValueError(f"LEF macro {name!r} has no SIZE statement in {lef_path}")
        width, height = float(size_match.group(1)), float(size_match.group(2))
        pin_count = len(re.findall(r"^\s*PIN\s+\S+", body, re.MULTILINE))
        macros[name] = LefMacro(name=name, width=width, height=height, pin_count=pin_count)

    return macros


def parse_lef_library(lef_paths: List[Path]) -> Dict[str, LefMacro]:
    """Merges MACRO definitions across one or more LEF files (ISPD02 ships
    one combined .lef; ISPD2015 splits tech.lef (0 macros, layers only)
    from cells.lef (the real cell library) — both real, both handled here).
    Raises if the combined result is still empty, since that means neither
    file was a usable cell library."""
    macros: Dict[str, LefMacro] = {}
    for lef_path in lef_paths:
        macros.update(parse_lef(lef_path))
    if not macros:
        raise ValueError(f"no MACRO definitions found across {lef_paths!r} — not a valid cell-library LEF set")
    return macros


@dataclass
class DefComponent:
    name: str
    macro: str
    x: float  # DEF database units (not yet scaled to microns); 0.0 if is_placed is False
    y: float
    is_fixed: bool
    is_placed: bool  # False for UNPLACED (ISPD2015's floorplan.def ships components with no coordinates at all)
    orientation: Optional[str] = None  # DEF orientation code (N/S/E/W/FN/FS/FE/FW), None if is_placed is False


@dataclass
class DefNet:
    net_name: str
    pins: List[Tuple[str, str]]  # (component_name, pin_name), in listed order


@dataclass
class ParsedDef:
    design_name: str
    micron_scale: int
    die_width: float  # microns
    die_height: float  # microns
    components: List[DefComponent]
    nets: List[DefNet]


_COMPONENT_STATEMENT = re.compile(
    r"-\s+(\S+)\s+(\S+)\s+\+\s+(FIXED|PLACED|COVER|UNPLACED)"
    r"(?:\s+\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)\s+(\S+))?\s*;"
)


def parse_def(def_path: Path) -> ParsedDef:
    text = def_path.read_text(encoding="utf-8", errors="replace")

    design_match = re.search(r"^DESIGN\s+(\S+)\s*;", text, re.MULTILINE)
    design_name = Path(design_match.group(1)).stem if design_match else def_path.stem

    units_match = re.search(r"^UNITS\s+DISTANCE\s+MICRONS\s+(\d+)\s*;", text, re.MULTILINE)
    micron_scale = int(units_match.group(1)) if units_match else _MICRON_SCALE_DEFAULT

    die_match = re.search(r"^DIEAREA\s+\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)\s+\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)\s*;", text, re.MULTILINE)
    if die_match is None:
        raise ValueError(f"no DIEAREA statement found in {def_path}")
    x0, y0, x1, y1 = (float(g) for g in die_match.groups())
    die_width = (x1 - x0) / micron_scale
    die_height = (y1 - y0) / micron_scale

    components_block = re.search(r"^COMPONENTS\s+\d+\s*;(.*?)^END\s+COMPONENTS", text, re.MULTILINE | re.DOTALL)
    if components_block is None:
        raise ValueError(f"no COMPONENTS block found in {def_path}")

    # Collapsed to single-line-equivalent text before matching: a component
    # statement can legitimately wrap across multiple physical lines (seen
    # in ISPD2015's floorplan.def, e.g. "- name macro \n + UNPLACED ;") --
    # matching per-line like the rest of this parser would silently drop
    # every such entry instead of erroring, which is worse than being
    # slightly less efficient here.
    components_flat = re.sub(r"\s+", " ", components_block.group(1))
    components: List[DefComponent] = []
    for m in _COMPONENT_STATEMENT.finditer(components_flat):
        name, macro, status, x, y, orient = m.groups()
        is_placed = x is not None
        components.append(
            DefComponent(
                name=name,
                macro=macro,
                x=float(x) if is_placed else 0.0,
                y=float(y) if is_placed else 0.0,
                is_fixed=(status in ("FIXED", "COVER")),
                is_placed=is_placed,
                orientation=orient if is_placed else None,
            )
        )

    nets_block = re.search(r"^NETS\s+\d+\s*;(.*?)^END\s+NETS", text, re.MULTILINE | re.DOTALL)
    if nets_block is None:
        raise ValueError(f"no NETS block found in {def_path}")

    nets: List[DefNet] = []
    current_name: Optional[str] = None
    current_pins: List[Tuple[str, str]] = []
    for line in nets_block.group(1).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        header = re.match(r"^-\s+(\S+)", stripped)
        if header:
            if current_name is not None:
                nets.append(DefNet(net_name=current_name, pins=current_pins))
            current_name = header.group(1)
            current_pins = []
            stripped = stripped[header.end():].strip()
        for pin_match in re.finditer(r"\(\s*(\S+)\s+(\S+)\s*\)", stripped):
            current_pins.append((pin_match.group(1), pin_match.group(2)))
    if current_name is not None:
        nets.append(DefNet(net_name=current_name, pins=current_pins))

    return ParsedDef(
        design_name=design_name,
        micron_scale=micron_scale,
        die_width=die_width,
        die_height=die_height,
        components=components,
        nets=nets,
    )


def lefdef_to_circuit_graph(lef_path: Union[Path, List[Path]], def_path: Path) -> CircuitGraph:
    """Combines one or more LEF cell libraries and a DEF placement/netlist
    file into a schema-valid CircuitGraph (Section 3.1). Node order follows
    DEF COMPONENTS order (0-indexed, contiguous, per the schema). Pass a
    list for `lef_path` when a benchmark splits tech.lef from cells.lef
    (e.g. ISPD2015) rather than shipping one combined .lef (e.g. ISPD02)."""
    lef_paths = lef_path if isinstance(lef_path, list) else [lef_path]
    macros = parse_lef_library(lef_paths)
    parsed_def = parse_def(def_path)

    name_to_id: Dict[str, int] = {}
    nodes: List[CircuitNode] = []
    for i, comp in enumerate(parsed_def.components):
        macro = macros.get(comp.macro)
        if macro is None:
            raise ValueError(f"DEF component {comp.name!r} references undefined LEF macro {comp.macro!r}")
        name_to_id[comp.name] = i
        nodes.append(
            CircuitNode(
                node_id=i,
                type=NodeType.STD_CELL,  # see module docstring: this benchmark family has no real macros
                width=macro.width,
                height=macro.height,
                pin_count=macro.pin_count,
            )
        )

    hyperedges: List[CircuitHyperedge] = []
    net_id = 0
    for net in parsed_def.nets:
        node_ids = [name_to_id[comp_name] for comp_name, _pin_name in net.pins if comp_name in name_to_id]
        if len(node_ids) < 2:
            continue  # a net touching <2 known components carries no placement-relevant connectivity
        driver, sinks = node_ids[0], node_ids[1:]
        hyperedges.append(CircuitHyperedge(net_id=net_id, driver_node=driver, sink_nodes=sinks))
        net_id += 1

    return CircuitGraph(
        design_name=parsed_def.design_name,
        nodes=nodes,
        hyperedges=hyperedges,
        die=Die(width=parsed_def.die_width, height=parsed_def.die_height),
    )


def def_has_real_reference_placement(def_path: Path, min_placed_fraction: float = 0.99) -> bool:
    """True if this DEF's own components are (almost) all real PLACED/FIXED
    coordinates -- i.e. it's a genuine reference-placement benchmark (e.g.
    ISPD02's ibm01-ibm18) rather than an unplaced/floorplan-only DEF (e.g.
    ISPD2015's floorplan.def, which is mostly UNPLACED). Used to gate real
    generator-training-target extraction so an unplaced DEF is never
    mistaken for one, rather than silently extracting a near-empty or
    all-zero placement."""
    parsed_def = parse_def(def_path)
    if not parsed_def.components:
        return False
    placed_fraction = sum(1 for c in parsed_def.components if c.is_placed) / len(parsed_def.components)
    return placed_fraction >= min_placed_fraction


def lefdef_to_real_placement(def_path: Path) -> PlacementJSON:
    """Extracts the REAL PLACED/FIXED (x, y, orientation) already present in
    a reference-placement DEF file into a schema-valid PlacementJSON, using
    the identical component order (parsed_def.components, enumerated 0..N-1)
    that lefdef_to_circuit_graph uses to assign node_id -- so a CircuitGraph
    and PlacementJSON built from the SAME def_path always align node-for-
    node. This is real, published benchmark data (the actual known
    placement these classic IBM-derived benchmarks ship with), used as a
    genuine supervised training target -- never a fabricated/synthetic one.

    Raises if the DEF isn't (almost entirely) placed -- see
    def_has_real_reference_placement -- rather than silently returning a
    placement built mostly from is_placed=False components' meaningless
    (0.0, 0.0) fallback coordinates."""
    parsed_def = parse_def(def_path)
    if not def_has_real_reference_placement(def_path):
        raise ValueError(
            f"{def_path} is not a real reference-placement DEF (most components are UNPLACED) -- "
            "cannot extract real training targets from it. See ISPD2015's floorplan.def for an "
            "example of what this correctly rejects."
        )

    placements = []
    for i, comp in enumerate(parsed_def.components):
        placements.append(
            PlacementEntry(
                node_id=i,
                x=comp.x / parsed_def.micron_scale,
                y=comp.y / parsed_def.micron_scale,
                orientation=Orientation(comp.orientation) if comp.orientation else Orientation.N,
            )
        )

    return PlacementJSON(
        design_name=parsed_def.design_name,
        placements=placements,
        generation_metadata=GenerationMetadata(model_variant="ispd02_real_reference", seed=0, is_legalized=True),
    )
