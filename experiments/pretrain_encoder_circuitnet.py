"""Pretrains a GCN-style encoder on real CircuitNet structure + real timing
labels (TECHNICAL.md Section 1.14.2, adapted per the real data-availability
finding documented in shared/schemas/pretraining_graph.py — CircuitNet's
public release has no real physical geometry, so this predicts real timing
slack instead of congestion/wirelength, which would need geometry that
doesn't exist).

Real train/val split: by DESIGN (not by node) -- an 90/10 split over the
real downloaded corpus, seeded from config/shared_config.yaml's
project_seeds[0] for reproducibility. The vocabulary (modules/encoders/
pretraining_model.build_cell_vocabulary) is built from the TRAIN designs
only, same leakage discipline as compute_normalization_stats.py.

Output: a checkpoint of PretrainingGCN's weights. The message-passing
layers (`.convs`) are what actually transfers -- loading them as GCN's
(modules/encoders/gcn.py) initial weights before fine-tuning on real
CircuitGraph data is the next step once this pretraining run itself is
approved to launch at full scale (currently held per explicit instruction
to not run further training without an explicit go-ahead).

Usage:
    python -m experiments.pretrain_encoder_circuitnet --epochs 50 --max-designs 2004
"""

import argparse
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import shared.env  # noqa: E402,F401 -- loads .env (WANDB_API_KEY) as a side effect
import torch  # noqa: E402
import wandb  # noqa: E402
import yaml  # noqa: E402

from modules.encoders.pretraining_model import (  # noqa: E402
    PretrainingGCN,
    build_cell_vocabulary,
    pretraining_inputs,
    pretraining_star_expansion_edge_index,
)
from modules.intake.parsers.circuitnet_parser import parse_circuitnet_design  # noqa: E402
from shared.schemas.pretraining_graph import PretrainingGraph  # noqa: E402

CIRCUITNET_ROOT = REPO_ROOT / "data" / "raw" / "circuitnet" / "circuitNetv3" / "dataset" / "Final"
RESULTS_ROOT = REPO_ROOT / "experiments" / "results"


def load_real_designs(max_designs: int) -> list[PretrainingGraph]:
    if not CIRCUITNET_ROOT.is_dir():
        raise FileNotFoundError(
            f"{CIRCUITNET_ROOT} not found -- real CircuitNet data required, see data/README.md. "
            "Never falls back to a placeholder."
        )
    design_dirs = sorted(d for d in CIRCUITNET_ROOT.iterdir() if d.is_dir())[:max_designs]
    graphs = []
    for d in design_dirs:
        try:
            graph, _ = parse_circuitnet_design(d)
        except Exception as exc:
            print(f"  skipping {d.name}: {exc}")
            continue
        if graph.num_nodes > 0:
            graphs.append(graph)
    return graphs


def split_train_val(graphs: list[PretrainingGraph], seed: int, val_fraction: float = 0.1):
    rng = random.Random(seed)
    shuffled = graphs.copy()
    rng.shuffle(shuffled)
    num_val = max(1, int(len(shuffled) * val_fraction))
    return shuffled[num_val:], shuffled[:num_val]


def run_epoch(model, optimizer, vocab, graphs, train: bool) -> float:
    model.train(train)
    total_loss, count = 0.0, 0
    for graph in graphs:
        cell_ids, scalars, targets, mask = pretraining_inputs(graph, vocab)
        edge_index = pretraining_star_expansion_edge_index(graph)
        if train:
            loss = model.masked_mse_loss(cell_ids, scalars, edge_index, targets, mask)
            if loss is None:
                continue
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        else:
            with torch.no_grad():
                loss = model.masked_mse_loss(cell_ids, scalars, edge_index, targets, mask)
            if loss is None:
                continue
        total_loss += loss.item()
        count += 1
    return total_loss / max(count, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-designs", type=int, default=2004)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--no-wandb", action="store_true")
    args = parser.parse_args()

    with open(REPO_ROOT / "config" / "shared_config.yaml", encoding="utf-8") as f:
        shared_cfg = yaml.safe_load(f)
    seed = shared_cfg["seeds"]["project_seeds"][0]
    wandb_project = shared_cfg["wandb"]["project"]

    print(f"Loading real CircuitNet designs (max {args.max_designs})...")
    t0 = time.time()
    graphs = load_real_designs(args.max_designs)
    print(f"Loaded {len(graphs)} real designs in {time.time()-t0:.1f}s")

    train_graphs, val_graphs = split_train_val(graphs, seed=seed)
    print(f"Real split: {len(train_graphs)} train designs, {len(val_graphs)} val designs")

    vocab = build_cell_vocabulary(train_graphs)  # train-only, no leakage from val designs
    print(f"Real cell-type vocabulary size (from train designs only): {len(vocab)}")

    model = PretrainingGCN(vocab_size=len(vocab))
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    experiment_name = f"pretrain_gcn_circuitnet_seed{seed}"
    run = None
    if not args.no_wandb:
        run = wandb.init(
            project=wandb_project,
            name=experiment_name,
            tags=["person-a", "pretraining", "circuitnet"],
            config={
                "num_train_designs": len(train_graphs),
                "num_val_designs": len(val_graphs),
                "vocab_size": len(vocab),
                "epochs": args.epochs,
                "lr": args.lr,
                "seed": seed,
                "task": "real_timing_slack_prediction",
            },
        )

    results_dir = RESULTS_ROOT / experiment_name
    results_dir.mkdir(parents=True, exist_ok=True)

    for epoch in range(args.epochs):
        train_loss = run_epoch(model, optimizer, vocab, train_graphs, train=True)
        val_loss = run_epoch(model, optimizer, vocab, val_graphs, train=False)
        print(f"epoch {epoch}: train_loss={train_loss:.4f} val_loss={val_loss:.4f}")
        if run is not None:
            wandb.log({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})

    checkpoint_path = results_dir / f"pretrained_gcn_epoch{args.epochs}.pt"
    torch.save({"model_state_dict": model.state_dict(), "vocab": vocab}, checkpoint_path)
    print(f"Saved pretrained checkpoint to {checkpoint_path}")

    if run is not None:
        run.finish()


if __name__ == "__main__":
    main()
