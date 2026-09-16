<div align="center">

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0f172a,50:6d28d9,100:06b6d4&height=200&section=header&text=SiliconMind&fontSize=64&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Generative%20AI%20for%20Chip%20Placement&descAlignY=58&descSize=20" alt="SiliconMind banner" />

<a href="https://github.com/nikhil191206/SiliconMind">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&duration=2800&pause=900&color=8B5CF6&center=true&vCenter=true&width=800&lines=Netlist+%E2%86%92+Encoder+%E2%86%92+Flow-Matching+Generator;Verified+against+DREAMPlace+%2B+OpenROAD+%2B+RL;Natural-Language+Edits%2C+Frozen+Regions%2C+Live+Diffs;No+synthetic+data.+No+shortcuts.+Real+chips+only." alt="Typing SVG" />
</a>

<br/>

![Status](https://img.shields.io/badge/status-active--development-8B5CF6?style=for-the-badge&labelColor=0f172a)
![Python](https://img.shields.io/badge/python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=0f172a)
![PyTorch](https://img.shields.io/badge/PyTorch-2.x%20%2F%20CUDA%2012.1-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white&labelColor=0f172a)
![License](https://img.shields.io/badge/license-TBD-06b6d4?style=for-the-badge&labelColor=0f172a)

</div>

<br/>

## What this is

Given a synthesized netlist, **SiliconMind** produces a physically valid, optimized
placement — the `(x, y)` of every macro and standard cell — using a generative deep
learning pipeline, benchmarked honestly against classical and RL-based placers, with
a **natural-language iterative refinement loop** layered on top so a chip designer can
say *"move this block away from the clock tree"* and get a re-legalized layout back
with a diff report, not a black box.

Full binding spec: **[TECHNICAL.md](TECHNICAL.md)**. If anything below ever
disagrees with it, TECHNICAL.md wins.

<br/>

## Pipeline

```mermaid
flowchart LR
    subgraph intake["Intake — Person D"]
        A1["Netlist upload\nLEF/DEF or Verilog"]
        A2["Beginner: NL description\n→ LLM RTL draft → Yosys"]
        A1 --> A3
        A2 --> A3
        A3["Circuit Graph JSON"]
    end

    subgraph encode["Encoders — Person A"]
        B1["GCN / GAT / DE-HNN / DeepGate4"]
        B2["node_embeddings + global_embedding"]
        B1 --> B2
    end

    subgraph generate["Generator — Person B"]
        C1["Flow-matching / diffusion"]
        C2["frozen_mask enforced\nat tensor level"]
        C1 --> C2
    end

    subgraph verify["Verification — Person C"]
        D1["DREAMPlace / OpenROAD\nlegalize + score"]
        D2["HPWL · congestion · legality\n=0 or it never ships"]
        D1 --> D2
    end

    subgraph edit["NL Edit Loop — Person D"]
        E1["\"move X away from Y\""]
        E2["Structured constraint\nconfidence < 0.6 → ask, don't guess"]
        E3["Diff report:\nunexpected_moves must be empty"]
        E1 --> E2 --> E3
    end

    A3 --> B1
    B2 --> C1
    C2 --> D1
    D2 --> E2
    E2 -.freeze + guidance.-> C1
    E3 -.regenerated region.-> D1
    D2 --> F["Visualizer\ngeometry only, never generative"]

    style intake fill:#0f172a,stroke:#6d28d9,color:#fff
    style encode fill:#0f172a,stroke:#8b5cf6,color:#fff
    style generate fill:#0f172a,stroke:#a855f7,color:#fff
    style verify fill:#0f172a,stroke:#06b6d4,color:#fff
    style edit fill:#0f172a,stroke:#22d3ee,color:#fff
```

<br/>

## Why generative, not RL

> Independent replication has repeatedly shown classical simulated annealing beating
> RL-based placement (the Circuit Training/AlphaChip lineage) on standard benchmarks.
> Flow-matching placers currently outperform diffusion, RL, and DREAMPlace on multiple
> metrics — generating full layouts in seconds via zero-shot inference.

RL is reproduced here **only as an honest baseline**, never as the shipped approach.
Full reasoning: [TECHNICAL.md §1.6](TECHNICAL.md#16-why-generative-over-rl-do-not-silently-revert).

<br/>

## Four tracks, one system

<table>
<tr><td width="25%" align="center"><b>A — Encoders</b></td><td>Reproduces GCN, GAT, DE-HNN, and DeepGate4 from their papers and runs the comparative benchmark that justifies the final DE-HNN+DeepGate4 hybrid.</td></tr>
<tr><td align="center"><b>B — Generator</b></td><td>The flow-matching/diffusion engine itself, plus the hard-freezing mechanism that makes editing possible without unintended drift.</td></tr>
<tr><td align="center"><b>C — Verification</b></td><td>DREAMPlace/OpenROAD integration, the RL baseline reproduction, and the metrics/statistics pipeline everyone else's results depend on.</td></tr>
<tr><td align="center"><b>D — LLM & Intake</b></td><td>Yosys synthesis, LLM-assisted RTL drafting, NL→constraint parsing, and the diff-report that shows exactly what changed.</td></tr>
</table>

Frontend is picked up by all four together once the backend works end-to-end — split
by feature, not handed off as "just UI." Full detail: **[workDistribution.md](workDistribution.md)**.

<br/>

## Real data only

No Kaggle, no synthetic/crowd-sourced datasets, anywhere in this project.

| Source | Used for |
|---|---|
| [ISPD 2005](https://archive.sigda.org/ispd2005/contest.htm) · [ISPD 2015](http://www.ispd.cc/contests/15/web/downloads.html) | Core placement benchmarks |
| [Circuit Training (Ariane, Google)](https://github.com/google-research/circuit_training) | Real RISC-V netlist + baseline placement |
| [TILOS-AI MacroPlacement](https://github.com/TILOS-AI-Institute/MacroPlacement) | Ariane / BlackParrot / MemPool + SA baseline reference |
| [CircuitNet](https://circuitnet.github.io/) | Encoder pretraining (10K–20K real EDA tool runs) |
| [ASAP7 PDK](https://github.com/The-OpenROAD-Project/asap7) | 7nm-class synthesis/placement enablement |
| [OpenHW CORE-V](https://github.com/openhwgroup/core-v-cores) | Beginner-path RTL + generalization split |

Full fetch instructions and live checklist: **[data/README.md](data/README.md)**.

<br/>

## Build status

<!-- Update the checkmarks as each module lands real (non-mock) code. -->

- [x] Repo skeleton, shared schemas (`shared/schemas/`), mocks (`shared/mocks/`), config
- [x] **Person A — Encoders**: `NetlistEncoder` interface + GCN, GAT, DE-HNN, DeepGate4, all passing their schema/shape/determinism/non-mutation unit tests against mock data (`tests/unit/encoders/`, 27/27 green)
- [ ] **Person B — Generator**: flow-matching engine + freeze-mask enforcement
- [x] **Person C — Verification**: `shared/metrics/` (HPWL, congestion, legality) + DREAMPlace/OpenROAD subprocess wrapper + Bookshelf/DEF I/O + RL-baseline environment + `compare_methods` stats utility, all unit-tested against mocks/fakes/hand-computed toy data (`tests/unit/evaluation/`, 52/52 green, +1 skipped without stable-baselines3/torch installed). Real DREAMPlace/OpenROAD runs and RL-baseline training are blocked on tool installation and real datasets — see `modules/evaluation/NOTES.md`.
- [ ] **Person D — Intake/LLM**: Yosys pipeline, Bookshelf/LEF-DEF/protobuf parsers, NL constraint parser
- [ ] Real-data training (blocked on D's raw-format → Circuit Graph JSON parsers)
- [ ] Backend (FastAPI) wiring
- [ ] Frontend (shared, once backend is stable end-to-end)

<br/>

## Getting started

```bash
git clone https://github.com/nikhil191206/SiliconMind.git
cd SiliconMind

pip install -r requirements-shared.txt --index-url https://download.pytorch.org/whl/cu121
pip install -r modules/encoders/requirements.txt   # + other modules as needed

pytest tests/unit/encoders/   # 27 passing
```

Full setup, GPU/CUDA notes, and per-module test commands: **[environment_setup.md](environment_setup.md)**.

<br/>

## Repository map

```
SiliconMind/
├── TECHNICAL.md          ← binding spec: architecture, schemas, formulas, hyperparameters
├── workDistribution.md   ← who owns what
├── INSTRUCTIONS.md       ← execution order / what can build ahead of real data
├── config/               ← shared_config.yaml — single source of truth for seeds/splits/paths
├── data/                 ← raw (gitignored) + processed Circuit Graph JSON cache
├── modules/
│   ├── encoders/         ← Person A (done)
│   ├── generator/        ← Person B
│   ├── evaluation/       ← Person C
│   ├── intake/           ← Person D
│   └── llm_interaction/  ← Person D
├── shared/
│   ├── schemas/          ← the Section 3 data contracts, pydantic, imported everywhere
│   ├── metrics/          ← HPWL / congestion / legality — one source of truth (Person C)
│   └── mocks/            ← lets every track build in parallel before the others exist
├── backend/              ← FastAPI, wires modules together
├── frontend/             ← React, shared final layer
└── tests/
    ├── unit/             ← one folder per module
    └── integration/      ← cross-module, once two tracks are wired
```

<br/>

## Contributing

Branch naming, ownership boundaries, and the schema-change/mock-update rule:
**[CONTRIBUTING.md](CONTRIBUTING.md)**. Short version: own your `modules/<you>/`,
get review on anything in `shared/`.

Starting Person D's track? **[HANDOFF_FOR_PERSON_D.md](HANDOFF_FOR_PERSON_D.md)**
summarizes what A, B, and C actually built — interfaces, flagged deviations,
and what's still blocked — so you don't have to reverse-engineer three
modules before starting your own.

<br/>

<div align="center">
<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:06b6d4,50:6d28d9,100:0f172a&height=100&section=footer" alt="footer" />
</div>
