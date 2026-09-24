# workDistribution.md — AI-Driven Chip Placement System

Four people, four roughly equal, technically deep tracks. Nobody is assigned "just frontend" or "just docs" — every track below is substantial, hard technical work in its own right, and frontend is picked up by everyone together once the engine and backend actually work end to end, rather than being handed to one person from the start.

---

## Person A — Netlist Encoders

Owns implementing and training all four netlist encoders — GCN, GAT, DE-HNN, and DeepGate4 — and running the comparative benchmarking between them. This is dense, research-heavy work: reproducing two fairly advanced architectures (a directed hypergraph network and a scalable graph transformer) from their published papers, not just calling a library function. The output of this track is both the trained encoders themselves and the comparison table that justifies which one the final system uses.

## Person B — Placement Generation Engine

Owns the flow-matching/diffusion model itself — its training loop, and wiring it to take Person A's encoder output as conditioning input. This is arguably the technical heart of the whole system, matching Person A's track in difficulty. Also owns the partial-regeneration / hard-freezing mechanism that makes natural-language editing possible without unintended drift elsewhere in the layout.

## Person C — Verification, Baselines, and Evaluation

Owns integrating DREAMPlace and OpenROAD for legality checking, reproducing the RL-based placement baseline (MaskPlace/EfficientPlace-style) for honest comparison, and building the actual metrics and statistics pipeline — HPWL, congestion, the generalization test, and the statistical significance testing across runs. This person effectively owns "how we prove our results are real," which is just as much genuine technical work as building a model, since none of the other three tracks' results mean anything without it.

## Person D — LLM and Intake Layer

Owns the Yosys synthesis integration for the beginner path, the LLM-assisted RTL drafting, the natural-language constraint parser that turns a user's plain-language critique into a structured edit instruction, and the diff-report logic that shows exactly what changed after every edit. This is a genuinely separate, self-contained subsystem, not a lightweight "chatbot wrapper" job.

---

## How the Four Tracks Come Together

These four tracks are largely independent at first, since each owns a separable piece of the pipeline, but they need real integration as each piece matures — whoever's piece is ready earliest helps wire things together in the backend rather than sitting idle, so no one is stuck waiting on someone else for the whole build.

Frontend work is treated as a shared final layer, not an individual assignment: once the engine and backend work end to end, all four move to frontend together, split by feature rather than by who's "better at UI" — the visualizer, the netlist-upload/beginner-wizard flow, the chat/edit interface tied to the LLM layer, and the results/benchmark dashboard. Since each person already owns the backend logic behind their assigned frontend piece, that work stays technical rather than becoming pure styling work.
