"""Pretrains each of the four real encoder architectures (TECHNICAL.md
Section 1.9.3's comparison: GCN/GAT/DE-HNN/DeepGate4) on real CircuitNet
structure + real timing labels (Section 1.14.2, adapted per the real
data-availability finding documented in shared/schemas/pretraining_graph.py
— CircuitNet's public release has no real physical geometry, so this
predicts real timing slack instead of congestion/wirelength, which would
need geometry that doesn't exist).

Each of the four PretrainingX models (modules/encoders/pretraining_model.py)
reuses its corresponding real production encoder's actual message-passing
layer (GCNConv/GATConv/DEHNNLayer/TransformerConv) directly -- this is the
same generator/chips/compute-budget-held-identical comparison Section 1.9.3
calls for, just at the pretraining-task level (the full CircuitGraph-level
comparison is separate, larger future work).

Real train/val split: by DESIGN (not by node) -- an 90/10 split over the
real downloaded corpus, seeded from config/shared_config.yaml's
project_seeds[0] for reproducibility, IDENTICAL across all four encoders
in one run (built once, reused) so the comparison is fair. The vocabulary
(modules/encoders/pretraining_model.build_cell_vocabulary) is built from
the TRAIN designs only, same leakage discipline as
compute_normalization_stats.py.

Output: one checkpoint per encoder. The message-passing layers are what
actually transfer -- loading them as each real encoder's initial weights
before fine-tuning on real CircuitGraph data is the next step once these
pretraining runs are done.

Usage:
    python -m experiments.pretrain_encoder_circuitnet --encoder gcn --epochs 50 --max-designs 2004
    python -m experiments.pretrain_encoder_circuitnet --encoder all --epochs 50 --max-designs 2004
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
    PretrainingDEHNN,
    PretrainingDeepGate4,
    PretrainingGAT,
    PretrainingGCN,
    build_cell_vocabulary,
    build_pretraining_incidence,
    pretraining_inputs,
    pretraining_star_expansion_edge_index,
)
from modules.encoders.positional_encoding import compute_global_pe, compute_local_pe  # noqa: E402
from modules.intake.parsers.circuitnet_parser import parse_circuitnet_design  # noqa: E402
from shared.schemas.pretraining_graph import PretrainingGraph  # noqa: E402

CIRCUITNET_ROOT = REPO_ROOT / "data" / "raw" / "circuitnet" / "circuitNetv3" / "dataset" / "Final"
RESULTS_ROOT = REPO_ROOT / "experiments" / "results"

ENCODER_NAMES = ["gcn", "gat", "de_hnn", "deepgate4"]


def build_model(encoder_name: str, vocab_size: int) -> torch.nn.Module:
    return {
        "gcn": PretrainingGCN,
        "gat": PretrainingGAT,
        "de_hnn": PretrainingDEHNN,
        "deepgate4": PretrainingDeepGate4,
    }[encoder_name](vocab_size=vocab_size)


def compute_loss(encoder_name: str, model: torch.nn.Module, graph: PretrainingGraph, vocab, device):
    cell_ids, scalars, targets, mask = pretraining_inputs(graph, vocab)
    cell_ids, scalars, targets, mask = cell_ids.to(device), scalars.to(device), targets.to(device), mask.to(device)

    if encoder_name in ("gcn", "gat"):
        edge_index = pretraining_star_expansion_edge_index(graph).to(device)
        return model.masked_mse_loss(cell_ids, scalars, edge_index, targets, mask)
    if encoder_name == "de_hnn":
        node_idx, edge_idx, num_edges = build_pretraining_incidence(graph)
        node_idx, edge_idx = node_idx.to(device), edge_idx.to(device)
        return model.masked_mse_loss(cell_ids, scalars, node_idx, edge_idx, num_edges, targets, mask)
    # deepgate4: needs star-expansion edges for its positional encodings too
    # (compute_local_pe/compute_global_pe do real CPU/numpy work internally,
    # so computed on CPU edges then moved, same pattern as
    # modules/encoders/deepgate4.py's own encode()).
    edge_index_cpu = pretraining_star_expansion_edge_index(graph)
    local_pe = compute_local_pe(graph, edge_index_cpu).to(device)
    global_pe = compute_global_pe(graph, edge_index_cpu).to(device)
    edge_index = edge_index_cpu.to(device)
    return model.masked_mse_loss(cell_ids, scalars, edge_index, local_pe, global_pe, targets, mask)


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


def run_epoch(encoder_name: str, model, optimizer, vocab, graphs, train: bool, device) -> float:
    model.train(train)
    total_loss, count = 0.0, 0
    for graph in graphs:
        if train:
            loss = compute_loss(encoder_name, model, graph, vocab, device)
            if loss is None:
                continue
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        else:
            with torch.no_grad():
                loss = compute_loss(encoder_name, model, graph, vocab, device)
            if loss is None:
                continue
        total_loss += loss.item()
        count += 1
    return total_loss / max(count, 1)


def train_one_encoder(encoder_name: str, train_graphs, val_graphs, vocab, seed: int, wandb_project: str, args) -> None:
    device = torch.device(args.device)
    model = build_model(encoder_name, vocab_size=len(vocab)).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    experiment_name = f"pretrain_{encoder_name}_circuitnet_seed{seed}"
    run = None
    if not args.no_wandb:
        run = wandb.init(
            project=wandb_project,
            name=experiment_name,
            tags=["person-a", "pretraining", "circuitnet", encoder_name],
            config={
                "encoder": encoder_name,
                "num_train_designs": len(train_graphs),
                "num_val_designs": len(val_graphs),
                "vocab_size": len(vocab),
                "epochs": args.epochs,
                "lr": args.lr,
                "seed": seed,
                "device": args.device,
                "task": "real_timing_slack_prediction",
            },
            reinit=True,
        )

    results_dir = RESULTS_ROOT / experiment_name
    results_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== {encoder_name} === training on {args.device} for {args.epochs} epochs "
          f"({len(train_graphs)} train / {len(val_graphs)} val real designs)", flush=True)
    t_start = time.time()
    for epoch in range(args.epochs):
        train_loss = run_epoch(encoder_name, model, optimizer, vocab, train_graphs, train=True, device=device)
        val_loss = run_epoch(encoder_name, model, optimizer, vocab, val_graphs, train=False, device=device)
        elapsed = time.time() - t_start
        print(f"[{encoder_name}] epoch {epoch}: train_loss={train_loss:.4f} val_loss={val_loss:.4f} elapsed={elapsed:.1f}s", flush=True)
        if run is not None:
            wandb.log({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss, "elapsed_seconds": elapsed})

        is_last = epoch == args.epochs - 1
        if args.checkpoint_every > 0 and ((epoch + 1) % args.checkpoint_every == 0 or is_last):
            checkpoint_path = results_dir / "checkpoint.pt"
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "vocab": vocab,
                    "encoder_name": encoder_name,
                    "epochs_completed": epoch + 1,
                    "epochs_target": args.epochs,
                    "train_loss": train_loss,
                    "val_loss": val_loss,
                    "seed": seed,
                },
                checkpoint_path,
            )
            print(f"[{encoder_name}]   saved checkpoint at epoch {epoch+1}/{args.epochs} to {checkpoint_path}", flush=True)

    if run is not None:
        run.finish()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-designs", type=int, default=2004)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--encoder", choices=ENCODER_NAMES + ["all"], default="all")
    parser.add_argument("--checkpoint-every", type=int, default=5)
    parser.add_argument("--no-wandb", action="store_true")
    args = parser.parse_args()

    with open(REPO_ROOT / "config" / "shared_config.yaml", encoding="utf-8") as f:
        shared_cfg = yaml.safe_load(f)
    seed = shared_cfg["seeds"]["project_seeds"][0]
    wandb_project = shared_cfg["wandb"]["project"]
    torch.manual_seed(seed)

    print(f"Loading real CircuitNet designs (max {args.max_designs})...", flush=True)
    t0 = time.time()
    graphs = load_real_designs(args.max_designs)
    print(f"Loaded {len(graphs)} real designs in {time.time()-t0:.1f}s", flush=True)

    # Same split and vocabulary reused across all four encoders in this run
    # (module docstring) so the comparison is fair -- built ONCE here, not
    # per encoder.
    train_graphs, val_graphs = split_train_val(graphs, seed=seed)
    print(f"Real split: {len(train_graphs)} train designs, {len(val_graphs)} val designs", flush=True)

    vocab = build_cell_vocabulary(train_graphs)  # train-only, no leakage from val designs
    print(f"Real cell-type vocabulary size (from train designs only): {len(vocab)}", flush=True)

    encoders_to_run = ENCODER_NAMES if args.encoder == "all" else [args.encoder]
    for encoder_name in encoders_to_run:
        train_one_encoder(encoder_name, train_graphs, val_graphs, vocab, seed, wandb_project, args)


if __name__ == "__main__":
    main()
