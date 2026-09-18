"""Yosys Synthesis Integration — TECHNICAL.md Section 4.D / Section 3.1.

Owned by Person D.
Runs Yosys synthesis on Verilog RTL to produce standard Netlist JSON,
and parses it into Section 3.1's CircuitGraph schema.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from shared.schemas.circuit_graph import CircuitGraph, CircuitHyperedge, CircuitNode, Die, NodeType


class YosysNotInstalledError(Exception):
    """Raised when Yosys binary is not found in PATH or configured location."""

    def __init__(self, message: Optional[str] = None):
        msg = message or (
            "Yosys installation is required for RTL synthesis.\n"
            "Why it is required: Converts Verilog HDL into a gate-level netlist for physical placement.\n"
            "How to install:\n"
            "  - Windows: Download binaries from YosysHQ or install via MSYS2 / conda: `conda install -c conda-forge yosys`\n"
            "  - Linux (Ubuntu/Debian): `sudo apt-get install yosys`\n"
            "  - macOS: `brew install yosys`\n"
            "Verification command: `yosys --version`\n"
            "Environment configuration: Set YOSYS_PATH environment variable to yosys binary location."
        )
        super().__init__(msg)


class YosysSynthesisError(Exception):
    """Raised when Yosys execution fails (exit code != 0 or syntax error in RTL)."""


def find_yosys_executable(yosys_cmd: Optional[str] = None) -> str:
    """Finds the Yosys executable command or path.

    Checks:
    1. Explicit `yosys_cmd` argument
    2. YOSYS_PATH environment variable
    3. `yosys` in system PATH via `shutil.which`
    """
    if yosys_cmd:
        if shutil.which(yosys_cmd) or Path(yosys_cmd).exists():
            return yosys_cmd

    env_path = os.environ.get("YOSYS_PATH")
    if env_path and (shutil.which(env_path) or Path(env_path).exists()):
        return env_path

    system_yosys = shutil.which("yosys")
    if system_yosys:
        return system_yosys

    raise YosysNotInstalledError()


def parse_yosys_json(
    yosys_json_input: Union[str, dict, Path],
    design_name: Optional[str] = None,
    die_size: Tuple[float, float] = (1000.0, 1000.0),
) -> CircuitGraph:
    """Parses a Yosys JSON netlist structure into Section 3.1's CircuitGraph schema.

    Args:
        yosys_json_input: JSON dict, JSON string, or path to Yosys JSON file.
        design_name: Name of top-level design module.
        die_size: Tuple of (die_width, die_height).

    Returns:
        Schema-valid CircuitGraph object.
    """
    if isinstance(yosys_json_input, (str, Path)):
        path_obj = Path(yosys_json_input)
        if path_obj.is_file():
            with open(path_obj, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(str(yosys_json_input))
    else:
        data = yosys_json_input

    modules = data.get("modules", {})
    if not modules:
        raise YosysSynthesisError("Yosys JSON netlist contains no modules.")

    # Select top module or first module
    top_module_name = design_name
    if not top_module_name or top_module_name not in modules:
        top_module_name = next(iter(modules))

    module_data = modules[top_module_name]

    cells = module_data.get("cells", {})
    ports = module_data.get("ports", {})

    cell_name_to_id: Dict[str, int] = {}
    nodes: List[CircuitNode] = []

    # Map cells to contiguous 0-indexed CircuitNode objects
    node_id_counter = 0
    for cell_name, cell_info in cells.items():
        cell_type_str = str(cell_info.get("type", "")).upper()

        # Determine node type: MACRO vs STD_CELL
        # Macros usually have RAM, SRAM, DSP, or custom module names
        is_macro = any(m in cell_type_str for m in ["SRAM", "RAM", "DSP", "MACRO", "MEM", "BLOCK"])
        node_type = NodeType.MACRO if is_macro else NodeType.STD_CELL

        # Assign heuristic sizes for macros/cells in die units
        width = 100.0 if node_type == NodeType.MACRO else 10.0
        height = 100.0 if node_type == NodeType.MACRO else 10.0

        connections = cell_info.get("connections", {})
        pin_count = sum(len(bits) for bits in connections.values())

        cell_name_to_id[cell_name] = node_id_counter
        nodes.append(
            CircuitNode(
                node_id=node_id_counter,
                type=node_type,
                width=width,
                height=height,
                pin_count=pin_count,
            )
        )
        node_id_counter += 1

    # Map nets (bit signals) to hyperedges
    net_to_driver: Dict[int, Optional[int]] = {}
    net_to_sinks: Dict[int, List[int]] = {}

    for cell_name, cell_info in cells.items():
        node_id = cell_name_to_id[cell_name]
        port_directions = cell_info.get("port_directions", {})
        connections = cell_info.get("connections", {})

        for port_name, bits in connections.items():
            direction = port_directions.get(port_name, "input")
            for bit in bits:
                if isinstance(bit, int):
                    if bit not in net_to_sinks:
                        net_to_sinks[bit] = []
                    if direction in ("output", "out"):
                        net_to_driver[bit] = node_id
                    else:
                        if node_id not in net_to_sinks[bit]:
                            net_to_sinks[bit].append(node_id)

    # Convert to contiguous 0-indexed hyperedges
    hyperedges: List[CircuitHyperedge] = []
    net_id_counter = 0

    all_nets = sorted(list(set(list(net_to_driver.keys()) + list(net_to_sinks.keys()))))
    for net in all_nets:
        driver = net_to_driver.get(net)
        sinks = net_to_sinks.get(net, [])
        # Only create hyperedge if it connects at least two endpoints or driver+sink
        if driver is not None or sinks:
            hyperedges.append(
                CircuitHyperedge(
                    net_id=net_id_counter,
                    driver_node=driver,
                    sink_nodes=sinks,
                )
            )
            net_id_counter += 1

    # Fallback if netlist has no hyperedges (isolated nodes)
    if not hyperedges:
        hyperedges.append(
            CircuitHyperedge(
                net_id=0,
                driver_node=0 if nodes else None,
                sink_nodes=[n.node_id for n in nodes[1:]] if len(nodes) > 1 else [],
            )
        )

    die = Die(width=die_size[0], height=die_size[1])

    return CircuitGraph(
        design_name=top_module_name,
        nodes=nodes,
        hyperedges=hyperedges,
        die=die,
    )


def run_yosys_synthesis(
    rtl_path: str,
    yosys_cmd: Optional[str] = None,
    output_dir: Optional[str] = None,
    top_module: Optional[str] = None,
) -> CircuitGraph:
    """Wraps Yosys CLI safely, synthesizes Verilog RTL, and parses into CircuitGraph.

    Args:
        rtl_path: Path to input Verilog file.
        yosys_cmd: Optional path to yosys binary.
        output_dir: Optional directory to store synthesis artifacts.
        top_module: Optional top module name.

    Returns:
        CircuitGraph object.

    Raises:
        YosysNotInstalledError: If Yosys is unavailable.
        YosysSynthesisError: If synthesis fails.
    """
    executable = find_yosys_executable(yosys_cmd)

    rtl_file = Path(rtl_path)
    if not rtl_file.is_file():
        raise FileNotFoundError(f"Input RTL file not found at '{rtl_path}'")

    temp_dir_obj = None
    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir_obj = tempfile.TemporaryDirectory(prefix="yosys_synth_")
        out_path = Path(temp_dir_obj.name)

    try:
        json_out_path = out_path / f"{rtl_file.stem}_synth.json"
        script_path = out_path / f"{rtl_file.stem}_synth.ys"

        # Construct Yosys script
        yosys_script = f"read_verilog {rtl_file.resolve().as_posix()}\n"
        if top_module:
            yosys_script += f"synth -top {top_module}\n"
        else:
            yosys_script += "synth\n"
        yosys_script += f"write_json {json_out_path.resolve().as_posix()}\n"

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(yosys_script)

        # Run Yosys safely with subprocess argument array (shell=False)
        cmd = [executable, "-s", str(script_path)]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise YosysSynthesisError(
                f"Yosys synthesis failed with exit code {result.returncode}.\n"
                f"Stderr:\n{result.stderr}\n"
                f"Stdout:\n{result.stdout}"
            )

        if not json_out_path.is_file():
            raise YosysSynthesisError(
                f"Yosys synthesis completed but output JSON was not generated at {json_out_path}"
            )

        return parse_yosys_json(json_out_path, design_name=top_module or rtl_file.stem)

    finally:
        if temp_dir_obj:
            temp_dir_obj.cleanup()
