"""Trains Person B's flow-matching PlacementBackbone (modules/generator/
network.py + flow_matching.py) on REAL supervised targets for the first
time — until this script, the generator's `training_loss` existed
(flow_matching.py) but nothing ever called it in a loop, so every
`/api/placement/generate` call was producing placements from a freshly
random-initialized, never-trained network.

Real supervised targets: ISPD02's ibm01-ibm18 DEF files ship the actual
published reference placement (real PLACED/FIXED x/y/orientation per
component, not a synthetic or unplaced floorplan — verified per-design via
modules/intake/parsers/lefdef_parser.def_has_real_reference_placement,
which rejects e.g. ISPD2015's floorplan.def for being mostly UNPLACED).
`lefdef_to_real_placement` extracts these into a schema-valid PlacementJSON
aligned node-for-node with the corresponding CircuitGraph.

Scope decision (explicit, not silent): trains on ibm01-ibm12 (12,752-
71,076 nodes each) from config/shared_config.yaml's own train_chips list,
under real time pressure ahead of a project review deadline. ibm13-ibm16
(also real train_chips with real targets, up to 183K nodes) are real,
valid future training data, just excluded tonight to keep iteration time
bounded — not because they're any less real. ibm17/ibm18 remain held out
as the project's own test_chips and are never touched here.

Encoder scope decision (explicit, not silent): uses ONE encoder (DE-HNN —
TECHNICAL.md Section 1.5's designated final-system encoder, and already
the default in backend/main.py) with FROZEN, randomly-initialized weights
as a fixed structural feature extractor — only the generator (PlacementBackbone)
is trained here. The full TECHNICAL.md Section 1.9.3 comparison (GCN vs
GAT vs DE-HNN vs DeepGate4, each properly pretrained/fine-tuned) is real,
separate, larger future work (modules/encoders/pretraining_model.py already
has all four real variants ready for that comparison) — not something this
script pretends to already cover.

Because the encoder is frozen and randomly initialized, its exact weights
must be checkpointed ALONGSIDE the trained generator — reloading a fresh
DEHNNEncoder() at inference would have different random weights and make
the trained generator's learned mapping meaningless.

Usage:
    python -m experiments.train_generator --epochs 200 --device cuda
"""

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import shared.env  # noqa: E402,F401 -- loads .env (WANDB_API_KEY) as a side effect
import torch  # noqa: E402
import wandb  # noqa: E402
import yaml  # noqa: E402

from modules.encoders.de_hnn import DEHNNEncoder  # noqa: E402
from modules.generator.flow_matching import FlowMatchingGenerationStrategy  # noqa: E402
from modules.intake.parsers.lefdef_parser import def_has_real_reference_placement, lefdef_to_real_placement  # noqa: E402
from shared.schemas.circuit_graph import CircuitGraph  # noqa: E402
from shared.schemas.placement import PlacementJSON  # noqa: E402

ISPD02_RAW_ROOT = REPO_ROOT / "data" / "raw" / "ispd02" / "ibmISPD02Bench_LEFDEF"
ISPD02_CACHE_ROOT = REPO_ROOT / "data" / "processed" / "ispd02"
RESULTS_ROOT = REPO_ROOT / "experiments" / "results"

# See module docstring "Scope decision" -- real subset of the real
# train_chips list, bounded for tonight's iteration-time budget.
TRAIN_DESIGNS = [f"ibm{i:02d}" for i in range(1, 13)]


def load_design(name: str) -> tuple[CircuitGraph, PlacementJSON]:
    import json

    graph = CircuitGraph(**json.load(open(ISPD02_CACHE_ROOT / f"{name}.json", encoding="utf-8")))
    def_path = ISPD02_RAW_ROOT / name / f"{name}.def"
    if not def_has_real_reference_placement(def_path):
        raise ValueError(f"{name}: DEF at {def_path} is not a real reference placement -- refusing to use as a target")
    placement = lefdef_to_real_placement(def_path)
    if len(placement.placements) != graph.num_nodes:
        raise ValueError(f"{name}: placement/graph node count mismatch ({len(placement.placements)} vs {graph.num_nodes})")
    return graph, placement


def target_tensor(graph: CircuitGraph, placement: PlacementJSON) -> torch.Tensor:
    """[N, 2] die-normalized target coordinates, in graph.nodes node_id
    order (guaranteed aligned to placement.placements by load_design's
    node-count check plus lefdef_to_real_placement's shared component
    ordering with lefdef_to_circuit_graph). Clipped to [0,1] -- a handful
    of real I/O pin components sit exactly on/fractionally outside the die
    edge (verified: e.g. ibm01 has entries at x=-0.33 against a 23.61-wide
    die, real DEF data, not a bug) -- clipped to match the valid range the
    generator itself is constrained to at inference (generator.py's own
    min/max clamp), not because the raw value is wrong."""
    by_id = {p.node_id: p for p in placement.placements}
    coords = []
    for node in graph.nodes:
        p = by_id[node.node_id]
        x_norm = min(max(p.x / graph.die.width, 0.0), 1.0)
        y_norm = min(max(p.y / graph.die.height, 0.0), 1.0)
        coords.append([x_norm, y_norm])
    return torch.tensor(coords, dtype=torch.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--no-wandb", action="store_true")
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=5,
        help="save a checkpoint every N epochs, not just at the end -- a background training run can be killed "
        "by a session/environment restart, and losing all progress because only the final checkpoint was ever "
        "written is a real failure mode this project hit once already (see experiments/pretrain_encoder_circuitnet.py's "
        "run history), not a hypothetical one.",
    )
    args = parser.parse_args()

    with open(REPO_ROOT / "config" / "shared_config.yaml", encoding="utf-8") as f:
        shared_cfg = yaml.safe_load(f)
    seed = shared_cfg["seeds"]["project_seeds"][0]
    wandb_project = shared_cfg["wandb"]["project"]
    torch.manual_seed(seed)

    print(f"Loading {len(TRAIN_DESIGNS)} real ISPD02 designs with real reference placements...")
    t0 = time.time()
    designs = []
    for name in TRAIN_DESIGNS:
        graph, placement = load_design(name)
        designs.append((name, graph, placement))
        print(f"  {name}: {graph.num_nodes} nodes, {graph.num_hyperedges} nets")
    print(f"Loaded {len(designs)} designs in {time.time()-t0:.1f}s")

    # Frozen, randomly-initialized structural encoder (module docstring
    # "Encoder scope decision") -- built ONCE so its weights stay fixed and
    # consistent across the whole run and are checkpointed alongside the
    # generator afterward.
    encoder = DEHNNEncoder()

    print("Pre-computing frozen encoder embeddings for all designs (encoder runs on CPU; it's frozen/no_grad so this is cheap and keeps the GPU free for the actual trainable backbone)...")
    t0 = time.time()
    cached_encodings = {}
    for name, graph, _ in designs:
        cached_encodings[name] = encoder.encode(graph)
    print(f"Encoded {len(designs)} designs in {time.time()-t0:.1f}s")

    device = torch.device(args.device)
    strategy = FlowMatchingGenerationStrategy()
    strategy.backbone.to(device)
    optimizer = torch.optim.Adam(strategy.backbone.parameters(), lr=args.lr)

    targets = {name: target_tensor(graph, placement).to(device) for name, graph, placement in designs}

    experiment_name = "train_generator_dehnn_flowmatching_seed0"
    run = None
    if not args.no_wandb:
        run = wandb.init(
            project=wandb_project,
            name=experiment_name,
            tags=["person-b", "generator", "flow-matching", "ispd02"],
            config={
                "encoder": "DE-HNN (frozen, random-init)",
                "train_designs": TRAIN_DESIGNS,
                "epochs": args.epochs,
                "lr": args.lr,
                "seed": seed,
                "device": args.device,
            },
        )

    results_dir = RESULTS_ROOT / experiment_name
    results_dir.mkdir(parents=True, exist_ok=True)

    print(f"Training on {args.device} for {args.epochs} epochs over {len(designs)} real designs...", flush=True)
    # Encoder outputs moved to `device` ONCE here, outside the epoch loop --
    # the earlier version re-did `.to(device)` for every design on every
    # epoch, a real (if minor) inefficiency caught while diagnosing this
    # run's much-slower-than-expected per-epoch time.
    cached_encodings_on_device = {
        name: (enc_out.node_embeddings.to(device), enc_out.global_embedding.to(device))
        for name, enc_out in cached_encodings.items()
    }
    t_start = time.time()
    for epoch in range(args.epochs):
        strategy.backbone.train()
        epoch_loss, count = 0.0, 0
        for name, graph, _ in designs:
            t_design = time.time()
            node_embeddings, global_embedding = cached_encodings_on_device[name]
            z1 = targets[name]

            loss = strategy.training_loss(node_embeddings, global_embedding, z1)
            optimizer.zero_grad()
            loss.backward()
            if epoch == 0:
                torch.cuda.synchronize() if device.type == "cuda" else None
                print(f"    [diag] {name} ({graph.num_nodes} nodes): {time.time()-t_design:.2f}s", flush=True)
            optimizer.step()
            epoch_loss += loss.item()
            count += 1

        avg_loss = epoch_loss / max(count, 1)
        elapsed = time.time() - t_start
        print(f"epoch {epoch}: avg_loss={avg_loss:.6f} elapsed={elapsed:.1f}s")
        if run is not None:
            wandb.log({"epoch": epoch, "train_loss": avg_loss, "elapsed_seconds": elapsed})

        is_last = epoch == args.epochs - 1
        if args.checkpoint_every > 0 and ((epoch + 1) % args.checkpoint_every == 0 or is_last):
            checkpoint_path = results_dir / "checkpoint.pt"
            torch.save(
                {
                    "backbone_state_dict": strategy.backbone.state_dict(),
                    "encoder_state_dict": encoder.model.state_dict(),
                    "encoder_type": "DEHNNEncoder",
                    "train_designs": TRAIN_DESIGNS,
                    "epochs_completed": epoch + 1,
                    "epochs_target": args.epochs,
                    "train_loss": avg_loss,
                    "seed": seed,
                },
                checkpoint_path,
            )
            print(f"  saved checkpoint at epoch {epoch+1}/{args.epochs} to {checkpoint_path}")

    if run is not None:
        run.finish()


if __name__ == "__main__":
    main()
