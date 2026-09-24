"""TEMPORARY DEMO FALLBACK tests. Run from the repo root:

    py -3.14 -m pytest fallback -q

Pins the honesty guarantees FALLBACK.md promises, so a last-minute tweak
before the demo can't silently break them.
"""
from collections import defaultdict

import pytest
from fastapi.testclient import TestClient

from fallback.server import app
from shared.metrics.geometry import node_bbox

client = TestClient(app)


@pytest.fixture(scope="module")
def small():
    graph = client.get("/api/fallback/samples/small").json()
    res = client.post("/api/placement/generate", json={"graph": graph, "seed": 0})
    assert res.status_code == 200
    return graph, res.json()


def _overlapping_pairs(graph, placement) -> int:
    nodes = {n["node_id"]: n for n in graph["nodes"]}
    boxes = {}
    for p in placement["placements"]:
        n = nodes[p["node_id"]]
        boxes[p["node_id"]] = node_bbox(p["x"], p["y"], n["width"], n["height"], p["orientation"])
    buckets = defaultdict(list)
    for i, (x0, y0, x1, y1) in boxes.items():
        for gx in range(int(x0 // 8), int(x1 // 8) + 1):
            for gy in range(int(y0 // 8), int(y1 // 8) + 1):
                buckets[gx, gy].append(i)
    bad = set()
    for ids in buckets.values():
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                p, q = boxes[ids[a]], boxes[ids[b]]
                if p[0] < q[2] - 1e-6 and q[0] < p[2] - 1e-6 and p[1] < q[3] - 1e-6 and q[1] < p[3] - 1e-6:
                    bad.add((min(ids[a], ids[b]), max(ids[a], ids[b])))
    return len(bad)


def test_generate_is_never_reported_as_verified(small):
    _, body = small
    assert body["verification_status"].startswith("unavailable:")
    assert body["metrics"] is None
    assert body["placement"]["generation_metadata"]["model_variant"].startswith("FALLBACK")
    assert body["fallback_report"]["congestion_overflow"] is None


def test_generate_is_legal_and_beats_grid_pack(small):
    graph, body = small
    W, H = graph["die"]["width"], graph["die"]["height"]
    assert _overlapping_pairs(graph, body["placement"]) == 0
    nodes = {n["node_id"]: n for n in graph["nodes"]}
    for p in body["placement"]["placements"]:
        x0, y0, x1, y1 = node_bbox(p["x"], p["y"], nodes[p["node_id"]]["width"], nodes[p["node_id"]]["height"], p["orientation"])
        assert x0 >= -1e-6 and y0 >= -1e-6 and x1 <= W + 1e-6 and y1 <= H + 1e-6
    r = body["fallback_report"]
    assert r["legality_violations"] == 0
    assert r["hpwl"] < r["baseline"]["hpwl"]


@pytest.mark.parametrize(
    "instruction",
    ["move macro 3 away from macro 0", "move macros 2, 5 to the left edge", "move macro 1 toward macro 7", "keep m4 out of the center"],
)
def test_edit_keeps_frozen_macros_bit_identical(small, instruction):
    graph, body = small
    res = client.post(
        "/api/placement/edit",
        json={"instruction": instruction, "graph": graph, "previous_placement": body["placement"], "seed": 0},
    ).json()
    assert res["requires_clarification"] is False
    assert res["diff_report"]["unexpected_moves"] == []
    before = {p["node_id"]: p for p in body["placement"]["placements"]}
    after = {p["node_id"]: p for p in res["new_placement"]["placements"]}
    for i in res["constraint"]["frozen_node_ids"]:
        assert after[i] == before[i]
    assert _overlapping_pairs(graph, res["new_placement"]) == 0
    assert res["verification_status"].startswith("unavailable:")


def test_vague_instruction_asks_instead_of_placing(small):
    graph, body = small
    res = client.post(
        "/api/placement/edit",
        json={"instruction": "make it better", "graph": graph, "previous_placement": body["placement"], "seed": 0},
    ).json()
    assert res["requires_clarification"] is True
    assert res["new_placement"] is None


def test_rtl_draft_synthesize_generate_roundtrip():
    rtl = client.post("/api/intake/draft-rtl", json={"description": "a fifo buffer"}).json()["rtl_code"]
    graph = client.post("/api/intake/synthesize", json={"design_name": "fifo", "rtl_code": rtl}).json()
    assert any(n["type"] == "MACRO" for n in graph["nodes"])
    res = client.post("/api/placement/generate", json={"graph": graph, "seed": 1})
    assert res.status_code == 200


def test_bad_rtl_is_a_422_with_a_real_message():
    res = client.post("/api/intake/synthesize", json={"design_name": "x", "rtl_code": "module broken("})
    assert res.status_code == 422
    assert "endmodule" in res.json()["detail"]
