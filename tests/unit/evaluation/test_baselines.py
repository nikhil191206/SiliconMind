import pytest

from modules.evaluation.baselines import _pack_remaining_std_cells, run_dreamplace_baseline, run_rl_baseline
from modules.evaluation.dreamplace_runner import DreamplaceNotInstalledError
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.schemas.circuit_graph import NodeType


def test_run_dreamplace_baseline_raises_when_not_installed(monkeypatch, tmp_path):
    monkeypatch.delenv("DREAMPLACE_ROOT", raising=False)
    graph = make_mock_circuit_graph()
    with pytest.raises(DreamplaceNotInstalledError):
        run_dreamplace_baseline(graph, work_dir=tmp_path)


def test_run_rl_baseline_raises_when_checkpoint_missing(tmp_path):
    graph = make_mock_circuit_graph()
    missing_checkpoint = tmp_path / "does_not_exist.zip"
    with pytest.raises(FileNotFoundError):
        run_rl_baseline(graph, str(missing_checkpoint))


def test_pack_remaining_std_cells_excludes_already_placed_nodes():
    graph = make_mock_circuit_graph()
    macro_ids = {n.node_id for n in graph.nodes if n.type == NodeType.MACRO}
    remaining = _pack_remaining_std_cells(graph, placed_node_ids=macro_ids)
    std_cell_ids = {n.node_id for n in graph.nodes if n.type == NodeType.STD_CELL}
    assert {e.node_id for e in remaining} == std_cell_ids
