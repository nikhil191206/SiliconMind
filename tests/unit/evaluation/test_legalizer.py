"""legalize_and_score tests. DREAMPlace/OpenROAD aren't installed in this
environment (see dreamplace_runner.py/openroad_runner.py) so the "not
installed" path is tested for real; the orchestration/scoring logic is
tested by injecting fakes at the two tool-call boundaries, per
legalizer.py's module docstring.
"""

import pytest

import modules.evaluation.legalizer as legalizer
from modules.evaluation.dreamplace_runner import DreamplaceNotInstalledError
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph
from shared.mocks.mock_placement import make_mock_placement
from shared.metrics.hpwl import compute_hpwl
from shared.metrics.legality import compute_legality_violations
from shared.metrics.congestion import compute_congestion_overflow


def test_legalize_and_score_raises_when_dreamplace_not_installed(monkeypatch, tmp_path):
    monkeypatch.delenv("DREAMPLACE_ROOT", raising=False)
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)
    with pytest.raises(DreamplaceNotInstalledError):
        legalizer.legalize_and_score(placement, graph, work_dir=tmp_path)


def test_legalize_and_score_wires_tool_outputs_into_correct_metrics(monkeypatch, tmp_path):
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)

    legalized_stub = placement.model_copy(deep=True)
    legalized_stub.generation_metadata.is_legalized = True

    fake_demand = {(0, 0): 10.0, (1, 1): 3.0}
    fake_capacity = {(0, 0): 4.0, (1, 1): 5.0}

    monkeypatch.setattr(legalizer, "_run_dreamplace_legalization", lambda g, p, wd: legalized_stub)
    monkeypatch.setattr(legalizer, "_run_congestion_estimate", lambda g, lp, wd: (fake_demand, fake_capacity))

    result_placement, metrics = legalizer.legalize_and_score(placement, graph, work_dir=tmp_path)

    assert result_placement is legalized_stub
    assert result_placement.generation_metadata.is_legalized is True
    assert metrics.hpwl == pytest.approx(compute_hpwl(legalized_stub, graph))
    assert metrics.legality_violations == compute_legality_violations(legalized_stub, graph)
    assert metrics.congestion_overflow == pytest.approx(compute_congestion_overflow(fake_demand, fake_capacity))
    assert metrics.runtime_seconds >= 0.0


def test_legalize_and_score_propagates_dreamplace_run_failure(monkeypatch, tmp_path):
    graph = make_mock_circuit_graph()
    placement = make_mock_placement(graph)

    def _boom(g, p, wd):
        raise legalizer.dreamplace_runner.DreamplaceRunError("simulated DREAMPlace crash")

    monkeypatch.setattr(legalizer, "_run_dreamplace_legalization", _boom)
    with pytest.raises(legalizer.dreamplace_runner.DreamplaceRunError):
        legalizer.legalize_and_score(placement, graph, work_dir=tmp_path)
