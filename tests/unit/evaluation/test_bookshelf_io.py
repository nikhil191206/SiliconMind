import pytest

from modules.evaluation.bookshelf_io import read_bookshelf_placement, write_bookshelf
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_placement import make_mock_placement
from shared.schemas.placement import GenerationMetadata, Orientation, PlacementEntry, PlacementJSON


def test_write_then_read_round_trips_coordinates_and_orientation(tmp_path):
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph, seed=3)

    aux_path = write_bookshelf(graph, placement, tmp_path)
    assert aux_path.exists()
    for ext in ("nodes", "nets", "wts", "pl", "scl"):
        assert (tmp_path / f"{graph.design_name}.{ext}").exists()

    round_tripped = read_bookshelf_placement(
        tmp_path / f"{graph.design_name}.pl", design_name=graph.design_name, model_variant="roundtrip_test", seed=3
    )

    original_by_id = {e.node_id: e for e in placement.placements}
    round_tripped_by_id = {e.node_id: e for e in round_tripped.placements}
    assert set(original_by_id) == set(round_tripped_by_id)
    for node_id, original in original_by_id.items():
        rt = round_tripped_by_id[node_id]
        assert rt.x == pytest.approx(original.x)
        assert rt.y == pytest.approx(original.y)
        assert rt.orientation == original.orientation


def test_write_rejects_design_name_mismatch(tmp_path):
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    placement.design_name = "some_other_design"
    with pytest.raises(ValueError, match="design_name"):
        write_bookshelf(graph, placement, tmp_path)


def test_write_rejects_placement_covering_wrong_node_set(tmp_path):
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    placement = PlacementJSON(
        design_name=graph.design_name,
        placements=placement.placements[:-1],  # drop one node's entry
        generation_metadata=GenerationMetadata(model_variant="incomplete", seed=0, is_legalized=False),
    )
    with pytest.raises(ValueError, match="node_ids"):
        write_bookshelf(graph, placement, tmp_path)


def test_rotated_orientation_round_trips():
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    placement.placements[0] = PlacementEntry(
        node_id=placement.placements[0].node_id, x=1.5, y=2.5, orientation=Orientation.FE
    )

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        write_bookshelf(graph, placement, Path(tmp))
        round_tripped = read_bookshelf_placement(
            Path(tmp) / f"{graph.design_name}.pl", design_name=graph.design_name, model_variant="rt", seed=0
        )
    entry = next(e for e in round_tripped.placements if e.node_id == placement.placements[0].node_id)
    assert entry.orientation == Orientation.FE
    assert entry.x == pytest.approx(1.5)
    assert entry.y == pytest.approx(2.5)
