"""FALLBACK ONLY: stands in for Person D's intake track.

* draft_rtl: keyword-picked Verilog templates in place of the LLM
  (/api/intake/draft-rtl). The templates are real, synthesizable Verilog.
* synthesize:
    - yosys_json_data  -> converted to CircuitGraph (real netlist, real nets).
    - RTL + `yosys` on PATH -> real Yosys run, then the same converter.
    - RTL, no Yosys    -> ESTIMATED netlist: memories become macros sized by
      bit count, registers/operators become a cell count, wired as a
      clustered synthetic graph. Not a synthesized netlist, and every
      response says so (see `last_synthesis_note`).
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np

from shared.schemas.circuit_graph import CircuitGraph, CircuitHyperedge, CircuitNode, Die, NodeType


class IntakeError(Exception):
    """Maps to HTTP 422 with this message as `detail`."""


# ---------------------------------------------------------------------------
# drafting (LLM stand-in)


def _ident(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")[:32]
    return s if re.match(r"^[a-z]", s) else f"design_{s or 'top'}"


_FIFO = """module {name} #(
  parameter WIDTH = 32,
  parameter DEPTH = 64
) (
  input  wire             clk,
  input  wire             rst_n,
  input  wire             wr_en,
  input  wire             rd_en,
  input  wire [WIDTH-1:0] din,
  output reg  [WIDTH-1:0] dout,
  output wire             full,
  output wire             empty
);
  localparam AW = $clog2(DEPTH);
  reg [WIDTH-1:0] mem [0:DEPTH-1];
  reg [AW:0] wptr, rptr;

  assign full  = (wptr[AW] != rptr[AW]) && (wptr[AW-1:0] == rptr[AW-1:0]);
  assign empty = (wptr == rptr);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wptr <= 0;
      rptr <= 0;
    end else begin
      if (wr_en && !full) begin
        mem[wptr[AW-1:0]] <= din;
        wptr <= wptr + 1'b1;
      end
      if (rd_en && !empty) begin
        dout <= mem[rptr[AW-1:0]];
        rptr <= rptr + 1'b1;
      end
    end
  end
endmodule
"""

_ALU = """module {name} #(
  parameter WIDTH = 32
) (
  input  wire [WIDTH-1:0] a,
  input  wire [WIDTH-1:0] b,
  input  wire [2:0]       op,
  output reg  [WIDTH-1:0] y,
  output wire             zero
);
  always @(*) begin
    case (op)
      3'b000: y = a + b;
      3'b001: y = a - b;
      3'b010: y = a & b;
      3'b011: y = a | b;
      3'b100: y = a ^ b;
      3'b101: y = a << 1;
      3'b110: y = a >> 1;
      default: y = {{WIDTH{{1'b0}}}};
    endcase
  end
  assign zero = (y == {{WIDTH{{1'b0}}}});
endmodule
"""

_CACHE = """module {name} #(
  parameter WIDTH = 32,
  parameter LINES = 256,
  parameter TAGW  = 20
) (
  input  wire             clk,
  input  wire             rst_n,
  input  wire             req,
  input  wire             we,
  input  wire [31:0]      addr,
  input  wire [WIDTH-1:0] wdata,
  output reg  [WIDTH-1:0] rdata,
  output reg              hit
);
  localparam IW = $clog2(LINES);
  // Four memories -> four macros after synthesis.
  reg [WIDTH-1:0] data0 [0:LINES-1];
  reg [WIDTH-1:0] data1 [0:LINES-1];
  reg [TAGW-1:0]  tag0  [0:LINES-1];
  reg [TAGW-1:0]  tag1  [0:LINES-1];
  reg [LINES-1:0] lru;

  wire [IW-1:0]   idx = addr[IW+1:2];
  wire [TAGW-1:0] tag = addr[31:32-TAGW];
  wire h0 = (tag0[idx] == tag);
  wire h1 = (tag1[idx] == tag);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      hit <= 1'b0;
      lru <= {{LINES{{1'b0}}}};
    end else if (req) begin
      hit <= h0 | h1;
      if (we) begin
        if (lru[idx]) begin data1[idx] <= wdata; tag1[idx] <= tag; end
        else          begin data0[idx] <= wdata; tag0[idx] <= tag; end
        lru[idx] <= ~lru[idx];
      end else begin
        rdata <= h1 ? data1[idx] : data0[idx];
      end
    end
  end
endmodule
"""

_COUNTER = """module {name} #(
  parameter WIDTH = 16
) (
  input  wire             clk,
  input  wire             rst_n,
  input  wire             en,
  input  wire             clear,
  output reg  [WIDTH-1:0] count,
  output wire             wrap
);
  assign wrap = en && (count == {{WIDTH{{1'b1}}}});

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      count <= {{WIDTH{{1'b0}}}};
    else if (clear)
      count <= {{WIDTH{{1'b0}}}};
    else if (en)
      count <= count + 1'b1;
  end
endmodule
"""


def draft_rtl(description: str, design_name: Optional[str] = None) -> str:
    d = description.lower()
    name = _ident(design_name or "top")
    header = (
        f'// Drafted from description: "{description.strip()[:120]}"\n'
        "// FALLBACK MODE: template-based draft, not LLM output. Review before synthesis.\n"
    )
    if re.search(r"cache|cpu|processor|core|soc|memory controller|accelerator", d):
        body = _CACHE
    elif re.search(r"fifo|queue|buffer", d):
        body = _FIFO
    elif re.search(r"alu|arithmetic|adder|multipl", d):
        body = _ALU
    else:
        body = _COUNTER
    return header + body.format(name=name)


# ---------------------------------------------------------------------------
# Yosys JSON -> CircuitGraph

_MACRO_TYPE = re.compile(r"^\$mem|sram|ram|rom|macro", re.I)


def _macro_dims(bits: int) -> tuple[float, float]:
    area = 40.0 + 0.25 * bits
    w = math.sqrt(area * 1.4)
    return float(round(w, 1)), float(round(area / w, 1))


def _yosys_param(v: Any, default: int) -> int:
    """Yosys writes parameters as binary strings ("00..0100000") or ints."""
    if isinstance(v, int):
        return v
    s = str(v or "")
    try:
        return int(s, 2) if s and set(s) <= {"0", "1"} else int(s)
    except ValueError:
        return default


def yosys_json_to_graph(data: dict[str, Any], design_name: str) -> CircuitGraph:
    modules = (data or {}).get("modules") or {}
    if not modules:
        raise IntakeError("Yosys JSON has no modules.")
    top = None
    for mname, mod in modules.items():
        if str((mod.get("attributes") or {}).get("top", "0")).strip("0") != "":
            top = mname
    if top is None:
        used = {c.get("type") for m in modules.values() for c in (m.get("cells") or {}).values()}
        roots = [m for m in modules if m not in used]
        top = roots[0] if roots else next(iter(modules))
    mod = modules[top]
    cells = mod.get("cells") or {}
    if not cells:
        raise IntakeError(f"Top module '{top}' has no cells after synthesis (was it flattened?).")

    nodes: list[CircuitNode] = []
    drivers: dict[Any, int] = {}
    sinks: dict[Any, list[int]] = {}
    for i, (cname, cell) in enumerate(cells.items()):
        ctype = str(cell.get("type", ""))
        conns = cell.get("connections") or {}
        dirs = cell.get("port_directions") or {}
        pins = sum(len(v) for v in conns.values())
        if _MACRO_TYPE.search(ctype):
            params = cell.get("parameters") or {}
            bits = _yosys_param(params.get("WIDTH"), 32) * _yosys_param(params.get("SIZE"), 32)
            w, h = _macro_dims(max(bits, 64))
            nodes.append(CircuitNode(node_id=i, type=NodeType.MACRO, width=w, height=h, pin_count=pins))
        else:
            width = 2.0 if "DFF" in ctype.upper() else 1.0
            nodes.append(CircuitNode(node_id=i, type=NodeType.STD_CELL, width=width, height=1.0, pin_count=pins))
        for port, bits in conns.items():
            for b in bits:
                if isinstance(b, str):  # constant "0"/"1"/"x"/"z"
                    continue
                if dirs.get(port) == "output":
                    drivers[b] = i
                else:
                    sinks.setdefault(b, []).append(i)

    edges = []
    for b, s in sinks.items():
        d = drivers.get(b)
        s = sorted(set(x for x in s if x != d))
        if s:
            edges.append((d, s))
    hyperedges = [CircuitHyperedge(net_id=k, driver_node=d, sink_nodes=s) for k, (d, s) in enumerate(edges)]

    std_area = sum(n.width * n.height for n in nodes if n.type == NodeType.STD_CELL)
    mac_area = sum(n.width * n.height for n in nodes if n.type == NodeType.MACRO)
    side = math.ceil(math.sqrt(std_area / 0.6 + mac_area / 0.45 + 16))
    max_mac = max([max(n.width, n.height) for n in nodes if n.type == NodeType.MACRO] or [0])
    side = max(side, math.ceil(max_mac * 1.3))
    return CircuitGraph(design_name=design_name, nodes=nodes, hyperedges=hyperedges, die=Die(width=side, height=side))


# ---------------------------------------------------------------------------
# RTL -> CircuitGraph


def yosys_available() -> Optional[str]:
    return shutil.which("yosys")


def _run_yosys(rtl: str, design_name: str) -> dict[str, Any]:
    exe = yosys_available()
    assert exe
    with tempfile.TemporaryDirectory() as td:
        src, out = Path(td) / "design.v", Path(td) / "out.json"
        src.write_text(rtl, encoding="utf-8")
        script = (
            f"read_verilog {src.as_posix()}; hierarchy -auto-top; proc; flatten; opt; "
            "memory -nomap; opt; techmap; opt; abc -g AND,NAND,OR,NOR,XOR,XNOR,MUX; opt_clean; "
            f"write_json {out.as_posix()}"
        )
        proc = subprocess.run([exe, "-q", "-p", script], capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise IntakeError("Yosys synthesis failed: " + (msg[-1] if msg else f"exit code {proc.returncode}"))
        return json.loads(out.read_text(encoding="utf-8"))


def _eval_int(expr: str, params: dict[str, int], default: int) -> int:
    e = expr
    for k, v in sorted(params.items(), key=lambda kv: -len(kv[0])):
        e = re.sub(rf"\b{k}\b", str(v), e)
    e = re.sub(r"\$clog2\(([^()]*)\)", lambda m: str(max(1, math.ceil(math.log2(max(2, _eval_int(m.group(1), {}, 2)))))), e)
    if not re.fullmatch(r"[\d\s+\-*/()]+", e):
        return default
    try:
        return int(eval(e, {"__builtins__": {}}, {}))  # digits and + - * / ( ) only, checked above
    except Exception:
        return default


def estimate_graph_from_rtl(rtl: str, design_name: str) -> CircuitGraph:
    """Size estimate only. Used when Yosys is not installed."""
    if not re.search(r"\bmodule\b", rtl) or not re.search(r"\bendmodule\b", rtl):
        raise IntakeError("No complete `module ... endmodule` found in the RTL.")
    code = re.sub(r"//.*|/\*[\s\S]*?\*/", "", rtl)
    params: dict[str, int] = {}
    for k, v in re.findall(r"(?:parameter|localparam)\s+(?:integer\s+)?(\w+)\s*=\s*([^,;)\n]+)", code):
        params[k] = _eval_int(v, params, 8)

    def width(msb: str, lsb: str) -> int:
        return abs(_eval_int(msb, params, 7) - _eval_int(lsb, params, 0)) + 1

    memories = []
    for msb, lsb, names, a, b in re.findall(r"\breg\s*\[([^:\]]+):([^\]]+)\]\s*(\w+)\s*\[([^:\]]+):([^\]]+)\]", code):
        memories.append(width(msb, lsb) * width(a, b))
    reg_bits = 0
    for m in re.finditer(r"\breg\s*(?:\[([^:\]]+):([^\]]+)\])?\s*([\w\s,]+?)\s*(\[[^\]]*\])?\s*;", code):
        if m.group(4):
            continue  # memory, counted above
        w = width(m.group(1), m.group(2)) if m.group(1) else 1
        reg_bits += w * len([n for n in m.group(3).split(",") if n.strip()])
    for m in re.finditer(r"\boutput\s+reg\s*(?:\[([^:\]]+):([^\]]+)\])?", code):
        reg_bits += width(m.group(1), m.group(2)) if m.group(1) else 1
    data_w = max([width(a, b) for a, b in re.findall(r"\[([^:\]]+):([^\]]+)\]", code)] or [8])
    arith = len(re.findall(r"[^+]\+[^+=]|[^-]-[^->=]", code))
    compare = len(re.findall(r"==|!=|<=(?=[^=])|>=|<(?!=)|>(?!=)", code))
    bitwise = len(re.findall(r"[&|^~](?![&|])", code))
    muxes = len(re.findall(r"\?|\bcase\b|\bif\b", code))
    std_cells = int(reg_bits * 2 + arith * data_w * 4 + compare * data_w + bitwise * data_w + muxes * data_w)
    std_cells = max(24, min(std_cells, 40_000))

    rng = np.random.default_rng(len(code))
    nodes: list[CircuitNode] = []
    for i, bits in enumerate(memories):
        w, h = _macro_dims(bits)
        nodes.append(CircuitNode(node_id=i, type=NodeType.MACRO, width=w, height=h, pin_count=min(512, 16 + bits // 16)))
    nm = len(nodes)
    for j in range(std_cells):
        nodes.append(CircuitNode(node_id=nm + j, type=NodeType.STD_CELL, width=1.0, height=1.0, pin_count=int(2 + rng.integers(0, 3))))

    edges: list[tuple[Optional[int], list[int]]] = []
    k = max(1, nm)
    for j in range(std_cells):
        me = nm + j
        if rng.random() < 0.3:
            continue
        sinks = sorted({nm + min(std_cells - 1, j + 1 + int(rng.integers(0, 16))) for _ in range(1 + int(rng.integers(0, 3)))} - {me})
        if not sinks:
            continue
        drv = (j % k) if (nm and j < 8 * nm) else me
        edges.append((drv, sinks))
    for i in range(nm - 1):
        edges.append((i, [i + 1]))
    hyperedges = [CircuitHyperedge(net_id=q, driver_node=d, sink_nodes=s) for q, (d, s) in enumerate(edges)]

    mac_area = sum(n.width * n.height for n in nodes[:nm])
    side = math.ceil(math.sqrt(std_cells / 0.6 + mac_area / 0.45 + 16))
    side = max(side, math.ceil(max([max(n.width, n.height) for n in nodes[:nm]] or [0]) * 1.3))
    return CircuitGraph(design_name=design_name, nodes=nodes, hyperedges=hyperedges, die=Die(width=side, height=side))


def synthesize(
    design_name: str, rtl_code: Optional[str], rtl_path: Optional[str], yosys_json_data: Any
) -> tuple[CircuitGraph, str]:
    """Returns (graph, note). `note` says exactly how the graph was produced."""
    name = _ident(design_name or "top")
    if yosys_json_data is not None:
        data = yosys_json_data if isinstance(yosys_json_data, dict) else json.loads(yosys_json_data)
        if "nodes" in data and "hyperedges" in data and "die" in data:
            return CircuitGraph.model_validate(data), "CircuitGraph JSON accepted as-is (schema-validated)."
        return yosys_json_to_graph(data, name), "Converted from uploaded Yosys JSON (real netlist connectivity)."
    if rtl_path:
        p = Path(rtl_path)
        if not p.is_file():
            raise IntakeError(f"rtl_path '{rtl_path}' does not exist on the server.")
        rtl_code = p.read_text(encoding="utf-8", errors="replace")
    if not rtl_code or not rtl_code.strip():
        raise IntakeError("Exactly one of rtl_code, rtl_path, or yosys_json_data must be provided.")
    if yosys_available():
        return yosys_json_to_graph(_run_yosys(rtl_code, name), name), "Synthesized with the local Yosys install."
    return (
        estimate_graph_from_rtl(rtl_code, name),
        "Yosys not installed: netlist SIZE ESTIMATED from the RTL (memories -> macros, registers/operators -> cell count). "
        "Connectivity is synthetic. Not a synthesized netlist.",
    )
