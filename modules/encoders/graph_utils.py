"""Shared conversion from Circuit Graph JSON (Section 3.1) to tensor form.

CircuitGraph is a directed hypergraph (each hyperedge has one optional driver
and many sinks). GCN/GAT are pairwise message-passing nets, so they consume a
star-expansion of each hyperedge: driver -> sink and sink -> driver directed
edges (undirected connectivity, direction-tagged) for every driver/sink pair
in the net. Primary-input nets (driver_node is None) contribute no edges but
their sink nodes still exist as graph nodes.

DE-HNN and DeepGate4 consume the hypergraph structure directly (see de_hnn.py
/ deepgate4.py) and do NOT use this star expansion — this module is only for
the two pairwise-message-passing baselines.
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import torch
import yaml

from shared.schemas.circuit_graph import CircuitGraph, NodeType

NUM_NODE_FEATURES = 4  # [width, height, pin_count, is_macro]


@dataclass
class NodeFeatureNormalization:
    """log1p(mean/std) for width/height/pin_count, computed once from the
    real training corpus by data/processed/compute_normalization_stats.py
    and stored in config/shared_config.yaml's encoder_defaults.

    Why this exists: raw width/height/pin_count span orders of magnitude
    across real designs (ISPD02 standard cells ~0.01-0.5 microns, ISPD2015
    up to ~77 microns, Ariane's real macros up to ~30 microns) -- feeding
    that straight into a GNN's input layer is the same class of problem as
    the unnormalized-reward bug found in experiments/train_rl_baseline.py
    (see its module docstring): numerically unstable training, not a
    correctness bug you'd catch from a shape/schema test."""

    log_width_mean: float
    log_width_std: float
    log_height_mean: float
    log_height_std: float
    log_pin_count_mean: float
    log_pin_count_std: float

    @classmethod
    def from_shared_config(cls, config_path: Optional[Path] = None) -> "NodeFeatureNormalization":
        path = config_path or Path(__file__).resolve().parents[2] / "config" / "shared_config.yaml"
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        try:
            stats = config["encoder_defaults"]["node_feature_normalization"]
        except KeyError as exc:
            raise KeyError(
                "config/shared_config.yaml has no encoder_defaults.node_feature_normalization block yet -- "
                "run data/processed/compute_normalization_stats.py and paste its output in before "
                "training any encoder on real data."
            ) from exc
        return cls(
            log_width_mean=stats["log_width_mean"],
            log_width_std=stats["log_width_std"],
            log_height_mean=stats["log_height_mean"],
            log_height_std=stats["log_height_std"],
            log_pin_count_mean=stats["log_pin_count_mean"],
            log_pin_count_std=stats["log_pin_count_std"],
        )


def node_features(graph: CircuitGraph, normalization: Optional[NodeFeatureNormalization] = None) -> torch.Tensor:
    """[num_nodes, NUM_NODE_FEATURES] float tensor: width, height, pin_count, is_macro.

    Without `normalization`, features are raw (die/library units) -- fine
    for schema/shape unit tests against small mock/toy graphs, where
    absolute scale doesn't matter and no cross-design comparison happens.
    Real training on real designs MUST pass real stats (see
    NodeFeatureNormalization.from_shared_config) -- there is no silent
    fallback to raw features for a real training run; the caller has to
    explicitly choose not to normalize, which should never happen outside
    a toy/test context."""
    rows = []
    for node in graph.nodes:
        is_macro = 1.0 if node.type == NodeType.MACRO else 0.0
        if normalization is None:
            width, height, pin_count = node.width, node.height, float(node.pin_count)
        else:
            width = (math.log1p(node.width) - normalization.log_width_mean) / normalization.log_width_std
            height = (math.log1p(node.height) - normalization.log_height_mean) / normalization.log_height_std
            pin_count = (
                math.log1p(node.pin_count) - normalization.log_pin_count_mean
            ) / normalization.log_pin_count_std
        rows.append([width, height, pin_count, is_macro])
    return torch.tensor(rows, dtype=torch.float32)


def star_expansion_edge_index(graph: CircuitGraph) -> torch.Tensor:
    """[2, num_edges] long tensor of directed driver<->sink pairs, one pair
    per (driver, sink) combination in each hyperedge, both directions."""
    src, dst = [], []
    for hyperedge in graph.hyperedges:
        if hyperedge.driver_node is None:
            continue
        for sink in hyperedge.sink_nodes:
            src.append(hyperedge.driver_node)
            dst.append(sink)
            src.append(sink)
            dst.append(hyperedge.driver_node)

    if not src:
        # No edges (e.g. all-primary-input mock graph fragment): PyG conv
        # layers accept an empty [2, 0] edge_index.
        return torch.empty((2, 0), dtype=torch.long)

    return torch.tensor([src, dst], dtype=torch.long)
