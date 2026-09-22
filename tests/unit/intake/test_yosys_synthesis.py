"""Unit tests for Yosys synthesis & JSON parsing (Person D)."""

import pytest

from modules.intake.yosys_synthesis import (
    YosysNotInstalledError,
    find_yosys_executable,
    parse_yosys_json,
    run_yosys_synthesis,
)
from shared.schemas.circuit_graph import CircuitGraph, NodeType

SAMPLE_YOSYS_JSON = {
    "modules": {
        "toy_design": {
            "cells": {
                "SRAM_0": {
                    "type": "SRAM_256x32",
                    "port_directions": {"clk": "input", "dout": "output"},
                    "connections": {"clk": [1], "dout": [2, 3]},
                },
                "U1": {
                    "type": "$_AND_",
                    "port_directions": {"A": "input", "B": "input", "Y": "output"},
                    "connections": {"A": [2], "B": [3], "Y": [4]},
                },
            },
            "ports": {
                "clk": {"direction": "input", "bits": [1]},
                "out": {"direction": "output", "bits": [4]},
            },
        }
    }
}


def test_find_yosys_executable_missing_raises(monkeypatch):
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("YOSYS_PATH", raising=False)
    with pytest.raises(YosysNotInstalledError):
        find_yosys_executable()


def test_parse_yosys_json_valid_schema():
    graph = parse_yosys_json(SAMPLE_YOSYS_JSON, design_name="toy_design", die_size=(500.0, 500.0))
    assert isinstance(graph, CircuitGraph)
    assert graph.design_name == "toy_design"
    assert len(graph.nodes) == 2
    assert graph.nodes[0].type == NodeType.MACRO
    assert graph.nodes[1].type == NodeType.STD_CELL
    assert graph.die.width == 500.0
    assert len(graph.hyperedges) > 0


def test_run_yosys_synthesis_missing_yosys_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("YOSYS_PATH", raising=False)
    rtl_file = tmp_path / "test.v"
    rtl_file.write_text("module test; endmodule")

    with pytest.raises(YosysNotInstalledError):
        run_yosys_synthesis(str(rtl_file))
