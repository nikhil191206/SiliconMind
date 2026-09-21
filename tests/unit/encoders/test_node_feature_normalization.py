import math

import pytest

from modules.encoders.graph_utils import NodeFeatureNormalization, node_features
from shared.mocks.mock_circuit_graph import make_mock_circuit_graph


def _toy_stats() -> NodeFeatureNormalization:
    # Deliberately simple, hand-computable stats -- not real corpus stats,
    # just enough to verify the normalization arithmetic itself is correct.
    return NodeFeatureNormalization(
        log_width_mean=0.0,
        log_width_std=1.0,
        log_height_mean=0.0,
        log_height_std=1.0,
        log_pin_count_mean=0.0,
        log_pin_count_std=1.0,
    )


def test_node_features_without_normalization_is_raw_and_unchanged():
    graph = make_mock_circuit_graph()
    feats = node_features(graph)
    assert feats[0].tolist() == [20.0, 15.0, 8.0, 1.0]  # node 0: MACRO, width=20, height=15, pin_count=8


def test_node_features_with_normalization_applies_log1p_zscore():
    graph = make_mock_circuit_graph()
    stats = _toy_stats()  # mean=0, std=1 -> normalized value is just log1p(x)
    feats = node_features(graph, normalization=stats)

    node0 = graph.nodes[0]
    assert feats[0, 0].item() == pytest.approx(math.log1p(node0.width))
    assert feats[0, 1].item() == pytest.approx(math.log1p(node0.height))
    assert feats[0, 2].item() == pytest.approx(math.log1p(node0.pin_count))
    assert feats[0, 3].item() == 1.0  # is_macro unaffected by normalization


def test_node_features_normalization_shifts_and_scales_correctly():
    graph = make_mock_circuit_graph()
    node0 = graph.nodes[0]
    stats = NodeFeatureNormalization(
        log_width_mean=math.log1p(node0.width),  # center exactly on this node's own value
        log_width_std=2.0,
        log_height_mean=0.0,
        log_height_std=1.0,
        log_pin_count_mean=0.0,
        log_pin_count_std=1.0,
    )
    feats = node_features(graph, normalization=stats)
    assert feats[0, 0].item() == pytest.approx(0.0, abs=1e-6)  # (x - mean)/std with x==mean -> 0


def test_from_shared_config_raises_clearly_when_stats_not_yet_computed(tmp_path):
    config_path = tmp_path / "shared_config.yaml"
    config_path.write_text("encoder_defaults:\n  hidden_dim: 256\n", encoding="utf-8")

    with pytest.raises(KeyError, match="compute_normalization_stats"):
        NodeFeatureNormalization.from_shared_config(config_path)
