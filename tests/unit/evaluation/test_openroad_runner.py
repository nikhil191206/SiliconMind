import pytest

from modules.evaluation.openroad_runner import (
    OpenroadNotInstalledError,
    _parse_congestion_report,
    build_congestion_script,
    find_openroad_binary,
)


def test_find_openroad_binary_raises_when_not_installed(monkeypatch):
    monkeypatch.delenv("OPENROAD_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(OpenroadNotInstalledError):
        find_openroad_binary()


def test_find_openroad_binary_rejects_bad_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROAD_BIN", str(tmp_path / "does_not_exist"))
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(OpenroadNotInstalledError):
        find_openroad_binary()


def test_build_congestion_script_contains_expected_commands(tmp_path):
    script = build_congestion_script(tmp_path / "tech.lef", tmp_path / "design.def", tmp_path / "report.txt")
    assert "read_lef" in script
    assert "read_def" in script
    assert "global_route" in script
    assert "report_congestion" in script
    assert str(tmp_path / "design.def") in script


def test_parse_congestion_report_extracts_demand_and_capacity():
    report_text = (
        "GCell (3, 7) horizontal demand: 12.0 capacity: 8.0\n"
        "GCell (4, 7) horizontal demand: 5.0 capacity: 9.0\n"
        "some unrelated line with no numbers\n"
    )
    demand, capacity = _parse_congestion_report(report_text)
    assert demand == {(3, 7): 12.0, (4, 7): 5.0}
    assert capacity == {(3, 7): 8.0, (4, 7): 9.0}


def test_parse_congestion_report_skips_unrecognized_lines():
    demand, capacity = _parse_congestion_report("nothing to see here\n")
    assert demand == {}
    assert capacity == {}
