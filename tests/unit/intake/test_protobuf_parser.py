"""Tests for the Circuit Training protobuf -> CircuitGraph parser, against
the REAL downloaded Ariane netlist (data/raw/ariane_circuit_training/) —
not a synthetic fixture. Skips (does not fake-pass) if that real file isn't
present on a given machine."""

from pathlib import Path

import pytest

from modules.intake.parsers.protobuf_parser import parse_protobuf_netlist
from shared.schemas.circuit_graph import NodeType

ARIANE_PB = Path("data/raw/ariane_circuit_training/netlist.pb.txt")

pytestmark = pytest.mark.skipif(
    not ARIANE_PB.exists(),
    reason="real Ariane circuit_training netlist not present in data/raw/ — see data/README.md",
)


def test_parse_real_ariane_netlist_produces_schema_valid_graph():
    graph = parse_protobuf_netlist(ARIANE_PB, design_name="ariane")

    assert graph.design_name == "ariane"
    assert [n.node_id for n in graph.nodes] == list(range(graph.num_nodes))
    assert graph.die.width > 0 and graph.die.height > 0


def test_parse_real_ariane_netlist_finds_all_133_real_macros():
    graph = parse_protobuf_netlist(ARIANE_PB)
    macros = [n for n in graph.nodes if n.type == NodeType.MACRO]
    assert len(macros) == 133
    # every real hard macro must carry real positive geometry from the file
    assert all(m.width > 0 and m.height > 0 for m in macros)
    assert all(m.pin_count > 0 for m in macros)


def test_parse_real_ariane_netlist_hyperedges_reference_valid_nodes():
    graph = parse_protobuf_netlist(ARIANE_PB)
    valid_ids = {n.node_id for n in graph.nodes}
    for h in graph.hyperedges:
        assert h.driver_node in valid_ids
        for sink in h.sink_nodes:
            assert sink in valid_ids
        # driver must never appear among its own sinks (would be a self-loop)
        assert h.driver_node not in h.sink_nodes


def test_parse_real_ariane_netlist_no_stdcell_type_present():
    """This specific netlist is Circuit Training's macro-placement
    abstraction (Mirhoseini et al.) — real hard macros plus clustered
    soft-logic aggregates, zero individually-modeled standard cells. Every
    non-MACRO node here is a real PORT or a real cluster, mapped to
    STD_CELL only because Section 3.1 has no third category — see this
    parser's module docstring."""
    graph = parse_protobuf_netlist(ARIANE_PB)
    assert all(n.type in (NodeType.MACRO, NodeType.STD_CELL) for n in graph.nodes)


def test_parse_protobuf_netlist_on_hand_written_toy_fixture(tmp_path):
    """A tiny hand-written fixture isolating the driver/sink direction
    convention (module docstring: `input:` = fanout, not fan-in) — a
    code-correctness check, not training data."""
    # One field per line, matching the real file's actual layout exactly
    # (this parser is line-based, same as the official MacroPlacement
    # FormatTranslators reference it was cross-checked against).
    pb = tmp_path / "toy.pb.txt"
    pb.write_text(
        "node {\n"
        '  name: "driver_port"\n'
        '  input: "sink_macro/pin_a"\n'
        "  attr {\n"
        '    key: "type"\n'
        "    value {\n"
        '      placeholder: "PORT"\n'
        "    }\n"
        "  }\n"
        "  attr {\n"
        '    key: "x"\n'
        "    value {\n"
        "      f: 0.0\n"
        "    }\n"
        "  }\n"
        "  attr {\n"
        '    key: "y"\n'
        "    value {\n"
        "      f: 0.0\n"
        "    }\n"
        "  }\n"
        "}\n"
        "node {\n"
        '  name: "sink_macro"\n'
        "  attr {\n"
        '    key: "type"\n'
        "    value {\n"
        '      placeholder: "MACRO"\n'
        "    }\n"
        "  }\n"
        "  attr {\n"
        '    key: "width"\n'
        "    value {\n"
        "      f: 10.0\n"
        "    }\n"
        "  }\n"
        "  attr {\n"
        '    key: "height"\n'
        "    value {\n"
        "      f: 5.0\n"
        "    }\n"
        "  }\n"
        "  attr {\n"
        '    key: "x"\n'
        "    value {\n"
        "      f: 20.0\n"
        "    }\n"
        "  }\n"
        "  attr {\n"
        '    key: "y"\n'
        "    value {\n"
        "      f: 10.0\n"
        "    }\n"
        "  }\n"
        "}\n"
        "node {\n"
        '  name: "sink_macro/pin_a"\n'
        "  attr {\n"
        '    key: "macro_name"\n'
        "    value {\n"
        '      placeholder: "sink_macro"\n'
        "    }\n"
        "  }\n"
        "  attr {\n"
        '    key: "type"\n'
        "    value {\n"
        '      placeholder: "MACRO_PIN"\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    graph = parse_protobuf_netlist(pb, design_name="toy")

    assert graph.num_nodes == 2
    port = next(n for n in graph.nodes if n.type == NodeType.STD_CELL)
    macro = next(n for n in graph.nodes if n.type == NodeType.MACRO)
    assert macro.width == 10.0 and macro.height == 5.0

    assert len(graph.hyperedges) == 1
    hyperedge = graph.hyperedges[0]
    assert hyperedge.driver_node == port.node_id
    assert hyperedge.sink_nodes == [macro.node_id]
