import pytest

from modules.evaluation.def_io import write_def
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_placement import make_mock_placement


def test_write_def_produces_expected_structure(tmp_path):
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)

    def_path = write_def(graph, placement, tmp_path / "design.def")
    text = def_path.read_text()

    assert f"DESIGN {graph.design_name} ;" in text
    assert f"DIEAREA ( 0 0 ) ( {int(graph.die.width * 1000)} {int(graph.die.height * 1000)} ) ;" in text
    assert f"COMPONENTS {graph.num_nodes} ;" in text
    assert "END COMPONENTS" in text
    assert f"NETS {graph.num_hyperedges} ;" in text
    assert "END NETS" in text
    assert text.strip().endswith("END DESIGN")

    for node_id in range(graph.num_nodes):
        assert f"- o{node_id} " in text
    for hyperedge in graph.hyperedges:
        assert f"- net{hyperedge.net_id} " in text


def test_write_def_scales_coordinates_to_database_units(tmp_path):
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    entry = placement.placements[0]

    def_path = write_def(graph, placement, tmp_path / "design.def")
    text = def_path.read_text()

    expected_x, expected_y = round(entry.x * 1000), round(entry.y * 1000)
    assert f"( {expected_x} {expected_y} )" in text


def test_write_def_rejects_design_name_mismatch(tmp_path):
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    placement.design_name = "other_design"
    with pytest.raises(ValueError, match="design_name"):
        write_def(graph, placement, tmp_path / "design.def")
