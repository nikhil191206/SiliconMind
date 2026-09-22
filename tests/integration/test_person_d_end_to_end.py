"""End-to-end integration tests for Person D intake, constraint parsing, edit flow, and diff reporting."""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from modules.encoders.de_hnn import DEHNNEncoder
from modules.generator.freeze import constraint_to_generation_inputs
from modules.generator.generator import PlacementGenerator
from modules.intake.llm_rtl import synthesize_from_description
from modules.intake.yosys_synthesis import parse_yosys_json
from modules.llm_interaction.constraint_parser import parse_constraint
from modules.llm_interaction.diff_report import generate_diff_report
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.schemas.circuit_graph import CircuitGraph
from shared.schemas.placement import PlacementJSON

client = TestClient(app)

SAMPLE_YOSYS_NETLIST = {
    "modules": {
        "counter": {
            "cells": {
                "SRAM_0": {
                    "type": "SRAM_128x32",
                    "port_directions": {"clk": "input", "q": "output"},
                    "connections": {"clk": [1], "q": [2, 3]},
                },
                "REG_0": {
                    "type": "DFF",
                    "port_directions": {"d": "input", "q": "output"},
                    "connections": {"d": [2], "q": [4]},
                },
                "GATE_0": {
                    "type": "$_AND_",
                    "port_directions": {"A": "input", "B": "input", "Y": "output"},
                    "connections": {"A": [3], "B": [4], "Y": [5]},
                },
            },
            "ports": {
                "clk": {"direction": "input", "bits": [1]},
                "out": {"direction": "output", "bits": [5]},
            },
        }
    }
}


def test_person_d_full_python_pipeline_integration():
    # 1. Beginner intake: RTL draft + Yosys netlist parse -> CircuitGraph
    rtl = synthesize_from_description("8-bit counter design", template="counter")
    assert "module counter" in rtl

    graph = parse_yosys_json(SAMPLE_YOSYS_NETLIST, design_name="counter")
    assert isinstance(graph, CircuitGraph)
    assert len(graph.nodes) == 3

    # 2. Encode netlist (Person A) and generate initial placement (Person B)
    encoder = DEHNNEncoder()
    encoder_output = encoder.encode(graph)

    generator = PlacementGenerator()
    initial_placement = generator.generate(encoder_output=encoder_output, graph=graph, seed=42)
    assert isinstance(initial_placement, PlacementJSON)
    assert len(initial_placement.placements) == 3

    # 3. Natural-language constraint parsing (Person D)
    constraint = parse_constraint("Move node_0 away from node_1", initial_placement, graph=graph)
    assert not constraint.requires_clarification()
    assert 0 in constraint.affected_node_ids
    assert 0 not in constraint.frozen_node_ids

    # 4. Partial regeneration with hard-freezing (Person B integration)
    frozen_placements, guidance = constraint_to_generation_inputs(constraint, initial_placement, graph=graph)

    edited_placement = generator.generate(
        encoder_output=encoder_output,
        graph=graph,
        frozen_placements=frozen_placements,
        guidance_terms=guidance,
        seed=43,
    )
    assert isinstance(edited_placement, PlacementJSON)

    # Assert bit-identical freeze guarantee for frozen nodes (Section 1.7)
    for frozen_id in constraint.frozen_node_ids:
        orig = next(p for p in initial_placement.placements if p.node_id == frozen_id)
        new_entry = next(p for p in edited_placement.placements if p.node_id == frozen_id)
        assert orig.x == new_entry.x
        assert orig.y == new_entry.y

    # 5. Placement diff report (Person D)
    diff = generate_diff_report(initial_placement, edited_placement, constraint)
    assert len(diff.unexpected_moves) == 0  # Zero unexpected moves!


def test_fastapi_backend_health_and_intake_endpoints():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    res_draft = client.post("/api/intake/draft-rtl", json={"description": "counter design", "template": "counter"})
    assert res_draft.status_code == 200
    assert "module counter" in res_draft.json()["rtl_code"]

    res_synth = client.post("/api/intake/synthesize", json={"yosys_json_data": str(SAMPLE_YOSYS_NETLIST).replace("'", '"'), "design_name": "counter"})
    assert res_synth.status_code == 200
    assert res_synth.json()["design_name"] == "counter"


def test_fastapi_backend_edit_placement_endpoint():
    graph = make_mock_circuit_graph()
    encoder = DEHNNEncoder()
    encoder_output = encoder.encode(graph)

    generator = PlacementGenerator()
    initial_placement = generator.generate(encoder_output=encoder_output, graph=graph, seed=42)

    res_edit = client.post(
        "/api/placement/edit",
        json={
            "graph": graph.model_dump(),
            "previous_placement": initial_placement.model_dump(),
            "instruction": "Move node_0 away from node_1",
            "seed": 42,
        },
    )

    assert res_edit.status_code == 200
    data = res_edit.json()
    assert not data["requires_clarification"]
    assert data["constraint"] is not None
    assert data["new_placement"] is not None
    assert data["diff_report"] is not None
    assert len(data["diff_report"]["unexpected_moves"]) == 0
