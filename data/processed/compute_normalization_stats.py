"""Computes real node-feature normalization statistics (log1p mean/std for
width, height, pin_count) from the TRAIN split only (config/shared_config.yaml's
dataset_split.train_chips), and writes them into shared_config.yaml under
encoder_defaults.node_feature_normalization.

Why this exists: modules/encoders/graph_utils.py's node_features() fed raw
width/height/pin_count straight into every encoder -- these span orders of
magnitude across real designs (ISPD02 standard cells ~0.01-0.5 microns,
ISPD2015 cells up to ~77 microns, Ariane's real macros up to ~30 microns).
Training a GNN across designs at that scale mismatch is the same class of
problem as the unnormalized-reward bug found and fixed in
experiments/train_rl_baseline.py (see its module docstring) -- here it
would show up as an ill-conditioned input layer instead of a broken value
function, same root cause (unnormalized real-world-scale numbers fed
straight into a neural net).

Computed ONLY from train_chips, never test_chips or the macro_designs
(ariane) group -- fitting normalization stats on held-out data would leak
information the generalization test (TECHNICAL.md Section 1.9.4) is
supposed to measure the absence of. ariane is excluded because it's a
different node-type distribution entirely (see shared_config.yaml's
comment on dataset_split) and encoder training's primary corpus here is
the standard-cell designs; if Ariane-scale training later needs its own
normalization, that's a separate, explicit decision, not silently folded
into this one.

Usage:
    python data/processed/compute_normalization_stats.py

Prints the computed stats as a ready-to-paste YAML block. Deliberately does
NOT auto-write them into shared_config.yaml: PyYAML's dump does not
round-trip comments, and that file's comments are real documentation (the
dataset_split rationale, TECHNICAL.md section references, etc.) -- silently
stripping them to save a manual paste is not a trade worth making.
"""

import sys
from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shared.schemas.circuit_graph import CircuitGraph  # noqa: E402

DATA_PROCESSED = REPO_ROOT / "data" / "processed"
CONFIG_PATH = REPO_ROOT / "config" / "shared_config.yaml"


def _find_cached_graph(name: str) -> CircuitGraph:
    for source_dir in DATA_PROCESSED.iterdir():
        if not source_dir.is_dir():
            continue
        candidate = source_dir / f"{name}.json"
        if candidate.exists():
            return CircuitGraph.model_validate_json(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        f"train_chips entry {name!r} has no cached CircuitGraph under {DATA_PROCESSED} -- "
        "run data/processed/build_cache.py first."
    )


def compute_stats(train_chips: list) -> dict:
    widths, heights, pins = [], [], []
    for name in train_chips:
        graph = _find_cached_graph(name)
        for node in graph.nodes:
            widths.append(node.width)
            heights.append(node.height)
            pins.append(node.pin_count)
        print(f"  {name}: {graph.num_nodes} real nodes")

    log_w = np.log1p(np.array(widths, dtype=np.float64))
    log_h = np.log1p(np.array(heights, dtype=np.float64))
    log_p = np.log1p(np.array(pins, dtype=np.float64))

    return {
        "log_width_mean": float(log_w.mean()),
        "log_width_std": float(log_w.std()),
        "log_height_mean": float(log_h.mean()),
        "log_height_std": float(log_h.std()),
        "log_pin_count_mean": float(log_p.mean()),
        "log_pin_count_std": float(log_p.std()),
        "computed_from_num_designs": len(train_chips),
        "computed_from_num_nodes": len(widths),
    }


def main() -> None:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    train_chips = config["dataset_split"]["train_chips"]
    if not train_chips:
        raise ValueError("dataset_split.train_chips is empty in shared_config.yaml -- define the split first")

    print(f"Computing real node-feature normalization stats from {len(train_chips)} real train_chips:")
    stats = compute_stats(train_chips)

    print("\nPaste this under encoder_defaults in config/shared_config.yaml:\n")
    print("  node_feature_normalization:")
    for k, v in stats.items():
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
