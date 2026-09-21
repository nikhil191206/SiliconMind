"""Tests for the LEF/DEF -> CircuitGraph parser, against the REAL downloaded
ISPD02 IBM01 benchmark (data/raw/ispd02/) — not a synthetic fixture. If
data/raw/ispd02 isn't present on a given machine, these tests skip rather
than silently passing against a fake substitute (INSTRUCTIONS.md's standing
rule: never substitute a placeholder for real data)."""

from pathlib import Path

import pytest

from modules.intake.parsers.lefdef_parser import lefdef_to_circuit_graph, parse_def, parse_lef
from shared.schemas.circuit_graph import NodeType

IBM01_DIR = Path("data/raw/ispd02/ibmISPD02Bench_LEFDEF/ibm01")
IBM01_LEF = IBM01_DIR / "ibm01.lef"
IBM01_DEF = IBM01_DIR / "ibm01.def"

pytestmark = pytest.mark.skipif(
    not (IBM01_LEF.exists() and IBM01_DEF.exists()),
    reason="real ISPD02 ibm01 benchmark not present in data/raw/ — see data/README.md",
)


def test_parse_lef_extracts_real_macro_catalog():
    macros = parse_lef(IBM01_LEF)
    assert "MAS0" in macros
    mas0 = macros["MAS0"]
    assert mas0.width == pytest.approx(0.01)
    assert mas0.height == pytest.approx(0.01)
    assert mas0.pin_count == 1

    mas2 = macros["MAS2"]
    assert mas2.pin_count == 2  # MAS2 has PIN P1 and PIN P2 in the real LEF


def test_parse_def_extracts_real_die_area_and_counts():
    parsed = parse_def(IBM01_DEF)
    assert parsed.design_name == "ibm01"
    assert len(parsed.components) == 12752
    assert len(parsed.nets) == 14111
    # DIEAREA ( -33 -33 ) ( 2328 2337 ) at 100 units/micron
    assert parsed.die_width == pytest.approx((2328 - (-33)) / 100)
    assert parsed.die_height == pytest.approx((2337 - (-33)) / 100)


def test_parse_def_first_component_and_net_match_the_real_file():
    parsed = parse_def(IBM01_DEF)
    first = parsed.components[0]
    assert first.name == "p1"
    assert first.macro == "MAS0"
    assert first.is_fixed is True
    assert (first.x, first.y) == (0.0, 2336.0)

    first_net = parsed.nets[0]
    assert first_net.net_name == "net0"
    assert first_net.pins == [("p198", "P1"), ("a8117", "P1")]


def test_lefdef_to_circuit_graph_produces_schema_valid_real_graph():
    graph = lefdef_to_circuit_graph(IBM01_LEF, IBM01_DEF)

    assert graph.design_name == "ibm01"
    assert graph.num_nodes == 12752
    assert graph.num_hyperedges == 14111
    assert [n.node_id for n in graph.nodes] == list(range(12752))
    assert all(n.type == NodeType.STD_CELL for n in graph.nodes)
    assert all(n.width > 0 and n.height > 0 for n in graph.nodes)

    # net0: ( p198 P1 ) ( a8117 P1 ) -> driver is the first-listed pin's node (p198)
    first_hyperedge = graph.hyperedges[0]
    parsed = parse_def(IBM01_DEF)
    name_to_id = {c.name: i for i, c in enumerate(parsed.components)}
    assert first_hyperedge.driver_node == name_to_id["p198"]
    assert first_hyperedge.sink_nodes == [name_to_id["a8117"]]


def test_lefdef_parser_raises_on_missing_macro_reference(tmp_path):
    lef = tmp_path / "toy.lef"
    lef.write_text("MACRO M1\n\tSIZE 1 BY 1 ;\n\tPIN P1\n\tEND P1\nEND M1\n")
    def_file = tmp_path / "toy.def"
    def_file.write_text(
        "DESIGN toy ;\n"
        "UNITS DISTANCE MICRONS 100 ;\n"
        "DIEAREA ( 0 0 ) ( 100 100 ) ;\n"
        "COMPONENTS 1 ;\n"
        "  -  c1  UNDEFINED_MACRO  +  PLACED ( 0 0 )  N  ;\n"
        "END COMPONENTS\n"
        "NETS 0 ;\n"
        "END NETS\n"
    )
    with pytest.raises(ValueError, match="UNDEFINED_MACRO"):
        lefdef_to_circuit_graph(lef, def_file)
