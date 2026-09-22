"""Tests for the CircuitNet netlist+feature -> PretrainingGraph parser,
against the REAL downloaded design 0_jt12_amp (data/raw/circuitnet/) — not
a synthetic fixture. Skips (does not fake-pass) if the real data isn't
present on a given machine."""

from pathlib import Path

import pytest

from modules.intake.parsers.circuitnet_parser import parse_circuitnet_design

DESIGN_DIR = Path("data/raw/circuitnet/circuitNetv3/dataset/Final/0_jt12_amp")

pytestmark = pytest.mark.skipif(
    not DESIGN_DIR.exists(), reason="real CircuitNet data not present in data/raw/ — see data/README.md"
)


def test_parse_real_design_covers_every_instance_with_real_features():
    graph, raw_features = parse_circuitnet_design(DESIGN_DIR)
    assert graph.design_name == "0_jt12_amp"
    assert graph.num_nodes == 357
    assert graph.num_nodes == len(raw_features)  # every real instance got a node, none skipped/fabricated


def test_parse_real_design_hyperedges_reference_valid_nodes():
    graph, _ = parse_circuitnet_design(DESIGN_DIR)
    valid_ids = {n.node_id for n in graph.nodes}
    for h in graph.hyperedges:
        if h.driver_node is not None:
            assert h.driver_node in valid_ids
            assert h.driver_node not in h.sink_nodes  # no self-loop
        for sink in h.sink_nodes:
            assert sink in valid_ids


def test_parse_real_design_finds_real_sequential_nodes_with_real_slack():
    graph, _ = parse_circuitnet_design(DESIGN_DIR)
    sequential = [n for n in graph.nodes if n.is_sequential]
    assert len(sequential) == 16  # real count for this design, per STA report
    assert all(n.slack is not None for n in sequential)
    # combinational cells have no setup-slack entry in a real STA report
    combinational = [n for n in graph.nodes if not n.is_sequential]
    assert any(n.slack is None for n in combinational)


def test_parse_real_design_electrical_features_are_real_positive_values():
    graph, _ = parse_circuitnet_design(DESIGN_DIR)
    node0 = graph.nodes[0]
    assert node0.cell_name == "BUFX12"
    assert node0.drive_strength == pytest.approx(12.0)
    assert node0.fanout_load is not None and node0.fanout_load > 0
    assert node0.fanout_res is not None and node0.fanout_res > 0


def test_parse_circuitnet_design_on_hand_written_toy_fixture(tmp_path):
    """A tiny hand-written fixture isolating the driver/sink resolution via
    outputPin/inputPins -- a code-correctness check, not training data."""
    design_dir = tmp_path / "toy_design"
    design_dir.mkdir()
    (design_dir / "final_netlist.v").write_text(
        "module toy (clk, d, q);\n"
        "   input clk;\n"
        "   input d;\n"
        "   output q;\n"
        "   wire mid;\n"
        "   BUFX1 u_buf (.A(d),\n"
        "	.Y(mid));\n"
        "   DFFX1 u_dff (.CK(clk),\n"
        "	.D(mid),\n"
        "	.Q(q));\n"
        "endmodule\n"
    )
    import json

    (design_dir / "feature.json").write_text(
        json.dumps(
            {
                "u_buf": {
                    "InstName": "u_buf",
                    "cellName": "BUFX1",
                    "inputPins": "A",
                    "outputPin": "Y",
                    "driveStrength": "1",
                },
                "u_dff": {
                    "InstName": "u_dff",
                    "cellName": "DFFX1",
                    "inputPins": "CK D",
                    "outputPin": "Q",
                    "driveStrength": "1",
                    "slack": "-0.5",
                    "AT": "0.9",
                },
            }
        )
    )

    graph, raw = parse_circuitnet_design(design_dir)
    assert graph.num_nodes == 2
    buf_node = next(n for n in graph.nodes if n.cell_name == "BUFX1")
    dff_node = next(n for n in graph.nodes if n.cell_name == "DFFX1")

    assert dff_node.is_sequential is True
    assert dff_node.slack == pytest.approx(-0.5)
    assert buf_node.is_sequential is False
    assert buf_node.slack is None

    # net "mid" is driven by u_buf's Y pin and sinks u_dff's D pin
    mid_edge = next(h for h in graph.hyperedges if h.driver_node == buf_node.node_id)
    assert mid_edge.sink_nodes == [dff_node.node_id]
