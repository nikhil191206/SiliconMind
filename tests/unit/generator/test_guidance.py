import torch

from modules.generator.guidance import CongestionGuidance, LegalityGuidance, SpatialGuidance, WirelengthGuidance
from modules.generator.types import SpatialGuidanceDirective
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph


def test_legality_guidance_pushes_overlapping_nodes_apart():
    graph = make_mock_circuit_graph()
    # Overlap node 0 and node 1 (both macros) with a small offset — exactly
    # coincident centers would sit at abs()'s non-differentiable kink and
    # get a zero subgradient by convention, which isn't the case this test
    # is after (a clearly non-degenerate overlap).
    z = torch.zeros(graph.num_nodes, 2)
    z[0] = torch.tensor([50.0, 50.0])
    z[1] = torch.tensor([52.0, 51.0])

    grad = LegalityGuidance().gradient(z, graph)
    # Descent direction is -grad; nodes 0 and 1 should be pushed toward
    # opposite sides of the die on at least one axis, i.e. non-zero and
    # opposite-signed movement between the two overlapping nodes.
    movement = -grad[0] - (-grad[1])
    assert torch.any(movement.abs() > 1e-6)


def test_legality_guidance_is_zero_for_well_separated_nodes():
    graph = make_mock_circuit_graph()
    z = torch.zeros(graph.num_nodes, 2)
    z[0] = torch.tensor([5.0, 5.0])
    z[1] = torch.tensor([95.0, 95.0])
    for i in range(2, graph.num_nodes):
        z[i] = torch.tensor([50.0 + i, 50.0 + i])

    grad = LegalityGuidance().gradient(z, graph)
    assert torch.allclose(grad[0], torch.zeros(2), atol=1e-6)
    assert torch.allclose(grad[1], torch.zeros(2), atol=1e-6)


def test_wirelength_guidance_nonzero_for_spread_out_net():
    graph = make_mock_circuit_graph()
    z = torch.zeros(graph.num_nodes, 2)
    for i in range(graph.num_nodes):
        z[i] = torch.tensor([float(i) * 10.0, float(i) * 5.0])

    grad = WirelengthGuidance().gradient(z, graph)
    assert torch.any(grad.abs() > 0)


def test_spatial_guidance_away_from_increases_distance_direction():
    graph = make_mock_circuit_graph()
    node_id_to_index = {n.node_id: i for i, n in enumerate(graph.nodes)}
    z = torch.zeros(graph.num_nodes, 2)
    z[3] = torch.tensor([50.0, 50.0])  # affected node
    reference = (10.0, 10.0)

    directive = SpatialGuidanceDirective(node_ids=[3], mode="away_from", reference_point=reference, weight=1.0)
    grad = SpatialGuidance([directive], node_id_to_index).gradient(z, graph)

    # Descent direction (-grad) should point away from the reference point.
    descent = -grad[3]
    away_vector = torch.tensor([50.0 - 10.0, 50.0 - 10.0])
    assert torch.dot(descent, away_vector) > 0


def test_congestion_guidance_penalizes_dense_cluster():
    graph = make_mock_circuit_graph()
    # Piled in a corner rather than the exact die center: a perfectly
    # symmetric cluster at the center can have canceling gradient
    # contributions across grid cells; an off-center cluster does not.
    z = torch.zeros(graph.num_nodes, 2)
    for i in range(graph.num_nodes):
        z[i] = torch.tensor([15.0 + i * 0.3, 12.0 + i * 0.2])
    grad = CongestionGuidance(grid_size=4).gradient(z, graph)
    assert torch.any(grad.abs() > 1e-6)
