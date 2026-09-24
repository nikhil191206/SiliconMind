# TECHNICAL.md — AI-Driven Chip Placement System (Full Technical Specification)

This is the single, binding technical reference for this project. Every schema, function signature, folder path, and default value in this document is a **contract** between the four members' work. If any of these needs to change during development, it must be changed here first and agreed by whoever owns the adjacent module — never changed silently in one person's code, because that is exactly how integration conflicts happen four months in.

---

## 0. HOW TO USE THIS DOCUMENT

- Section 1 is mandatory reading for all four members and any AI coding agent assisting them — it is the shared mental model of the whole system.
- Section 2 defines the repository layout and environment — followed exactly, so no one's code lives in the wrong place or depends on the wrong library version.
- Section 3 defines the **exact data contracts** between the four subsystems — this is the most important section for avoiding conflicts, because it means each person can build and test their module against a mock of another person's output before that person's real code even exists.
- Section 4 is the four person-specific deep dives, now including concrete hyperparameters, function signatures, and testing contracts.
- Section 5 covers naming conventions, config, and logging.
- Section 6 covers git workflow and ownership boundaries.
- Section 7 covers failure/edge-case handling — what every module must do when something upstream goes wrong, so failures don't cascade silently.

---

## 1. OVERALL TECHNICAL DEEP DIVE

### 1.1 Problem Statement

Given a synthesized netlist, produce a physically valid, optimized placement — the (x, y) coordinate of every macro/standard cell on the die — using a generative deep learning pipeline, benchmarked honestly against classical and reinforcement-learning placement methods, with a natural-language-driven iterative refinement loop layered on top.

### 1.2 End-to-End Pipeline (component-by-component, with owning person)

| Step | Description | Owner |
|---|---|---|
| 1 | Netlist acquisition (direct upload, or beginner description → LLM-assisted RTL → Yosys synthesis) | D (intake) → A (from netlist onward) |
| 2 | Netlist parsed into directed hypergraph representation | A |
| 3 | Hypergraph encoded into conditioning embeddings (GCN / GAT / DE-HNN / DeepGate4) | A |
| 4 | Embeddings condition the flow-matching/diffusion placement generator | B |
| 5 | Candidate placement legalized and scored (DREAMPlace/OpenROAD) | C |
| 6 | Verified placement rendered deterministically | (shared frontend, later) |
| 7 | User issues NL edit → LLM parses to structured constraint | D |
| 8 | Constraint converted to freeze-mask + guidance term, fed back into generator | D → B (interface) |
| 9 | Regenerated region re-legalized, diff computed, shown to user | C → D |
| 10 | Final DEF export | — |

### 1.3 Data Formats (exact)

- **Netlist input:** structural Verilog netlist (post-synthesis) OR LEF/DEF pair. Both must be supported at the intake boundary (owned by A's parser).
- **Internal intermediate representation:** every downstream module (B, C, D) consumes the **Circuit Graph JSON** defined in Section 3.1 — not raw Verilog/LEF-DEF directly. This is the single most important rule in this document: nobody except A's parser touches raw netlist formats.
- **Placement output:** DEF file, plus the internal **Placement JSON** defined in Section 3.2, which the visualizer and diff-reporter consume (JSON is easier to render/diff than raw DEF; DEF is generated only at final export and after any legalizer run).

### 1.4 Core Formulas (must be implemented identically everywhere they're used — owned by C, imported by everyone else, never reimplemented locally)

**HPWL (half-perimeter wirelength), per net:**
```
HPWL(net) = (max(x_i) - min(x_i)) + (max(y_i) - min(y_i))
            for all pins i in net
Total HPWL = sum over all nets
```

**Congestion overflow**, computed per routing grid cell g:
```
overflow(g) = max(0, routing_demand(g) - routing_capacity(g))
Total overflow = sum over all grid cells g
```
`routing_demand` and `routing_capacity` are computed by DREAMPlace/OpenROAD's global router estimate — this project does not reimplement routing estimation from scratch.

**Legality violation count:** number of macro pairs with overlapping bounding boxes + number of macros with any portion outside die boundary. Must be zero after the legalization step (Section 4.C) before a placement is ever shown or exported; non-zero legality violations are an internal error, not a reportable result.

### 1.5 Models — Final List (see Section 4 for full hyperparameters)

| Component | Model(s) |
|---|---|
| Netlist encoder (compared) | GCN, GAT, DE-HNN, DeepGate4 |
| Netlist encoder (final system) | DE-HNN hypergraph representation + DeepGate4 sparse-attention/sub-linear-memory technique |
| Placement generator | Flow-matching (primary) / diffusion (fallback if flow-matching underperforms in practice) |
| Comparison baselines | DREAMPlace (classical), RL placer reproduction (MaskPlace/EfficientPlace-style) |
| LLM roles | (a) beginner RTL drafting assist, (b) NL → structured constraint parsing |
| Verification | DREAMPlace legalizer, OpenROAD |
| Synthesis | Yosys |

### 1.6 Why Generative Over RL (do not silently revert)

Independent replication has repeatedly shown classical simulated annealing beating RL-based placement (the Circuit Training/AlphaChip lineage) on standard benchmarks, even after every raised methodological objection was addressed. Diffusion-based placers have been shown to outperform DREAMPlace directly; flow-matching placers currently outperform diffusion, RL, and DREAMPlace on multiple metrics, generating full layouts in seconds via zero-shot inference. RL is a **baseline only**.

### 1.7 Drift/Consistency Guarantee (non-negotiable, applies to B and D jointly)

- Frozen macros are **excluded from the generative variable set** for a regeneration call, not soft-conditioned. Concretely: B's generator accepts a `frozen_mask` array; any index marked frozen is never touched by the sampling process, full stop — this must be enforced at the tensor-indexing level, not by hoping the loss function keeps it stable.
- Every regenerated layout — frozen or not — passes through C's legalizer/evaluator before being shown or exported.
- D generates a quantitative diff report after every regeneration (Section 3.4).

### 1.8 Visualization Principle

Visualization (built once backend is stable, shared work) reads only the verified Placement JSON (Section 3.2) and renders it geometrically. No generative image model is used in visualization under any circumstance, no toggle, no exception. Real photos of unrelated chips must never be used as background/overlay; only die-size/aspect-ratio conventions may inform canvas scale.

### 1.9 Evaluation Protocol (owned by C, used by everyone)

1. HPWL, congestion overflow, legality violations — via the formulas in 1.4.
2. Every result reported against DREAMPlace and the RL baseline.
3. Encoder comparison: GCN vs GAT vs DE-HNN vs DeepGate4 vs the DE-HNN+DeepGate4 hybrid — generator, training chips, and compute budget held identical across all five runs.
4. Generalization split: fixed train/test chip partition (defined once, in the shared config — Section 5.3 — never redefined per-experiment).
5. Statistical rigor: minimum 5 random seeds per configuration; report mean ± std; paired t-test or Wilcoxon (p < 0.05 threshold) before any superiority claim.
6. Consistency/drift benchmark: simulate ≥10 sequential edit rounds; measure fraction of unfrozen-but-unrelated macros that moved beyond a tolerance of 0.01 (die-normalized units).
7. LLM constraint accuracy: precision/recall on a labeled set of ≥100 (NL request → expected constraint) pairs, held out from any prompt-engineering iteration.
8. Runtime/scalability: wall-clock inference time vs. chip size (number of macros), vs. DREAMPlace and RL, on identical hardware.

### 1.10 Repository & Environment — see Section 2 (mandatory, not optional)

### 1.11 Tech Stack (frozen)

| Layer | Technology | Version pin |
|---|---|---|
| Language | Python | 3.11.x |
| Core ML framework | PyTorch | 2.x, CUDA 12.1 build |
| Graph/hypergraph learning | PyTorch Geometric | latest compatible with PyTorch pin above |
| Generative engine | Custom (PyTorch) | — |
| RL baseline | Stable-Baselines3 | latest stable |
| RTL synthesis | Yosys | latest stable release |
| Legalization/classical baseline | OpenROAD, DREAMPlace | latest stable release of each |
| LLM | API-based, function-calling capable | — |
| Visualization | Three.js | latest stable |
| Backend | FastAPI | latest stable |
| Frontend | React | latest stable (functional components + hooks only) |
| Experiment tracking | Weights & Biases | — |
| Package management | `pip` with `requirements.txt` per module (Section 2) | — |

### 1.12 Key Reference Papers (cite in report; architectures should follow these, not be reinvented from scratch)

- Mirhoseini et al., *A graph placement methodology for fast chip design* (Nature, 2021)
- Cheng et al., ISPD 2023 / 2025 RL-for-macro-placement replication assessments
- Lin et al., *DREAMPlace* (DAC 2019)
- Lai et al., *MaskPlace* (NeurIPS 2022)
- Diffusion-based chip placement (2025); *FlowPlace* (flow matching, 2026)
- Luo et al., *DE-HNN* (AISTATS 2024)
- *DeepGate4* (2025)
- *NetTAG* (reference/comparison)
- ChatEDA, ChipNeMo, *EDA Corpus*/OpenROAD-Assistant
- *The Dawn of Agentic EDA* (2025 survey)

### 1.13 Official Data Sources — Validated Links and Fetching Process

Every link below was directly opened and confirmed live before being added to this document. No Kaggle, no synthetic/crowd-sourced datasets, anywhere in this project — every source below is real chip design data released by the actual EDA research community, a real academic PDK developer, or a real hardware design organization.

**1. ISPD 2005 Placement Contest Benchmark Suite**
- Official contest page (confirmed live): `https://archive.sigda.org/ispd2005/contest.htm`
- Benchmark format reference (standard academic citation for these files, the MARCO GSRC Bookshelf): `http://vlsicad.ucsd.edu/GSRC/bookshelf/Slots/Placement/`
- Fetching process: benchmarks are distributed in Bookshelf format (`.nodes`, `.nets`, `.pl`, `.scl` files per design — 16 industrial-derived designs, e.g. `adaptec1`–`adaptec4`, `bigblue1`–`bigblue4`). Download via the contest page's linked archive, unpack, and parse `.nodes`/`.nets`/`.pl` directly into Section 3.1's Circuit Graph JSON — this Bookshelf→Circuit-Graph-JSON parser is part of Person A's intake responsibilities (Section 4.A).

**2. ISPD 2015 Blockage-Aware Detailed-Routing-Driven Placement Contest Benchmark Suite**
- Official downloads page (confirmed live): `http://www.ispd.cc/contests/15/web/downloads.html`
- Direct benchmark archive (confirmed live): `http://www.ispd.cc/contests/15/web/benchmarks/ispd_2015_contest_benchmark.tgz`
- Documentation: `http://www.ispd.cc/contests/15/web/benchmarks/ispd_2015_contest_benchmark_description.pdf`
- Fetching process: download the `.tgz` archive directly (no account/registration required), extract — files are in LEF/DEF format with fence regions and blockages. Parse via the same LEF/DEF → Circuit Graph JSON path used for direct netlist uploads (Section 3.1).

**3. ASAP7 (7nm Predictive Research PDK)**
- Official repository (confirmed live, BSD-3 licensed, released by the OpenROAD Project / Arizona State University): `https://github.com/The-OpenROAD-Project/asap7`
- Fetching process: `git clone --recurse-submodules https://github.com/The-OpenROAD-Project/asap7.git` — this pulls the technology files, standard-cell libraries (`asap7sc7p5t_28` is the current digital-flow library), and SRAM macros as submodules. Used to synthesize/place project-generated test designs at a realistic 7nm-class node via Yosys + OpenROAD, not as a source of pre-made netlists itself.

**4. Google's Open Ariane RISC-V (TSMC 7nm variant) via the Circuit Training Repository**
- Official repository (confirmed live): `https://github.com/google-research/circuit_training`
- Example netlist path within the repo: `circuit_training/environment/test_data/ariane/netlist.pb.txt` (with initial placement at `.../ariane/initial.plc`)
- Netlist format documentation: `https://github.com/google-research/circuit_training/blob/main/docs/NETLIST_FORMAT.md`
- Fetching process: clone the repository; the netlist ships in Protocol Buffer (`.pb.txt`) format, Google's own exchange format for this data. TILOS-AI-Institute provides a maintained LEF/DEF↔Protobuf converter (see source 5 below) — use it to bring this into the same Circuit Graph JSON pipeline as every other source, rather than writing a second, separate Protobuf parser.

**5. TILOS-AI-Institute `MacroPlacement` Repository**
- Official repository (confirmed live): `https://github.com/TILOS-AI-Institute/MacroPlacement`
- Test cases folder: `https://github.com/TILOS-AI-Institute/MacroPlacement/tree/main/Testcases`
- Format translators (LEF/DEF ⇄ Protobuf, used for source 4 above): `https://github.com/TILOS-AI-Institute/MacroPlacement/tree/main/CodeElements` (FormatTranslators section)
- Fetching process: clone the repository. Contains real open designs (Ariane, BlackParrot, MemPool, and updated ASAP7-based testcases as of the March 2025 update) plus official simulated-annealing baseline results and evaluator scripts — use these evaluator scripts as a cross-check against Person C's own DREAMPlace/OpenROAD-based evaluation pipeline (Section 4.C), not as a replacement for it.

**6. CircuitNet**
- Official project page (confirmed live): `https://circuitnet.github.io/`
- Official code repository (confirmed live): `https://github.com/circuitnet/CircuitNet`
- Fetching process: the repository's README links directly to the actual data hosting (Hugging Face for both CircuitNet-N14 v2.0 and CircuitNet-N45 v3.0; also mirrored on Baidu Netdisk). Download via the Hugging Face link specified in the repo README, then follow the repo's documented task-specific setup (Congestion / DRC / IR-Drop) to unpack LEF/DEF, netlist, and graph-information files. Real data: over 10K–20K samples generated from actual commercial EDA tool runs on real open-source RISC-V designs — used primarily as Person A's pretraining source for the encoders (Section 1.14 below) given its much larger sample count than the placement-only benchmarks above.

**7. Open RTL designs for beginner-path testing and augmentation diversity**
- OpenCores (confirmed live): `https://opencores.org/`
- More actively maintained modern alternative, recommended as primary: the OpenHW Group CORE-V family (confirmed live): `https://github.com/openhwgroup/core-v-cores` — real, actively developed open RISC-V cores (CVA6/Ariane's own current home, CV32E40P, and others), each in its own maintained GitHub repository.
- Fetching process: clone the specific core's repository (e.g., CVA6), run it through Yosys synthesis (Section 4.D's `run_yosys_synthesis`) to produce additional real netlists beyond the fixed benchmark set above — this is what feeds the generalization-test split (Section 1.9.4) with more distinct real designs, not just the standard ISPD/ASAP7 set everyone else in the field already trains on.

### 1.14 Data Augmentation Methodology (real data only — no synthetic generation)

Given the real constraint that the number of large, fully-benchmarked chip designs across all sources above is small (realistically a few dozen distinct designs, not thousands), the project uses two augmentation strategies — both operating on real designs and real tool output, never inventing fictional netlists or fabricated chip data:

1. **Multiple real placements per real chip.** For each real netlist, generate several different legal placements of that same design — e.g., DREAMPlace or the reproduced RL baseline run with different random seeds/initial conditions on the identical netlist. Every resulting placement is a real, physically valid layout of a real circuit, checked by Person C's real legalizer (Section 3.5) — this multiplies the number of (netlist, good-placement) training pairs available to Person B's generator without touching the netlist itself or fabricating any new circuit.
2. **Pretraining on CircuitNet before fine-tuning on placement.** CircuitNet's much larger sample count (10K–20K, from real commercial tool runs) is used to pretrain Person A's netlist encoders on a proxy task (congestion/wirelength prediction) before fine-tuning them jointly with Person B's generator on the smaller placement-benchmark set. This is a standard, legitimate way to get more effective training signal out of a small pool of real fully-benchmarked designs — the pretraining data itself is 100% real EDA tool output, not model-generated.

Additionally, source 7 above (OpenHW Group CORE-V designs run through Yosys) provides more distinct real designs specifically to strengthen the train/held-out-chip split used for the generalization test (Section 1.9.4) — more real designs to hold out, not more copies of the same few designs.

### 1.15 Dataset Ownership by Person

| Dataset | Person A (Encoders) | Person B (Generator) | Person C (Verification/Baselines) | Person D (LLM/Intake) |
|---|---|---|---|---|
| ISPD02 (IBM-MS) | Required | Required | Required | Not needed |
| ISPD 2015 | Required | Required | Required | Not needed |
| Ariane RISC-V netlist | Required | Required | Required | Not needed |
| TILOS-AI MacroPlacement repo | Required (SA baseline results used as a sanity reference) | Required | Primary owner — this is the main baseline comparison source | Not needed |
| CircuitNet | Primary owner — this is specifically the pretraining data | Not required directly (only indirectly, through A's pretrained encoder) | Not needed | Not needed |
| ASAP7 PDK | Not needed directly | Not needed directly | Needed only if benchmarking newly-synthesized designs | Required — needed to synthesize beginner-path test designs |
| OpenHW CORE-V (RTL) | Not needed directly | Not needed directly | Needed for generalization-split testing on new designs | Required — this is the raw input to the Yosys pipeline |

A, B, and C share the four core benchmark sources (ISPD02, ISPD2015, Ariane, TILOS-AI) since these flow through the entire placement pipeline end to end. CircuitNet belongs specifically to A's pretraining step. ASAP7 and OpenHW CORE-V belong specifically to D's beginner-intake/synthesis path, separate from the benchmark-placement side of the system.

### 1.16 Data Directory Convention (where downloaded data must be placed)

All downloaded, unmodified source data goes under `data/raw/<source_name>/`, using these exact folder names so every module's ingestion code can assume a fixed path:

```
data/raw/
├── ispd02/                     <- ibmISPD02Bench_LEFDEF.tar.gz, extracted
├── ispd2015/                   <- ispd_2015_contest_benchmark.tgz, extracted
├── ariane_circuit_training/    <- netlist.pb.txt + initial.plc from google-research/circuit_training
├── macroplacement/             <- full clone/zip of TILOS-AI-Institute/MacroPlacement
├── circuitnet/                 <- CircuitNet-N45 (v3.0) data from Hugging Face
├── asap7/                      <- clone of The-OpenROAD-Project/asap7 (with submodules)
└── corev/                      <- clone(s) of relevant openhwgroup/core-v-cores repositories
```
`data/processed/` (Circuit Graph JSON cache, Section 3.1) is never committed to git and is always derived from `data/raw/` by code — if it's ever out of sync, delete and regenerate it, never hand-edit it.

---

## 2. REPOSITORY STRUCTURE & ENVIRONMENT (mandatory)

```
chip-placement-system/
├── README.md
├── TECHNICAL.md                  <- this document, lives at repo root
├── workDistribution.md
├── config/
│   └── shared_config.yaml        <- Section 5.3 — single source of truth for seeds, splits, paths
├── data/
│   ├── raw/                      <- untouched official benchmark downloads
│   ├── processed/                <- Circuit Graph JSON cache (Section 3.1)
│   └── README.md                 <- exact download instructions per source
├── modules/
│   ├── intake/                   <- Person D: Yosys wrapper, LLM RTL assist, netlist parser entry point
│   ├── encoders/                 <- Person A: GCN, GAT, DE-HNN, DeepGate4 implementations
│   ├── generator/                <- Person B: flow-matching/diffusion model, freeze-mask logic
│   ├── evaluation/                <- Person C: legalizer wrapper, baselines, metrics, statistical tests
│   └── llm_interaction/          <- Person D: constraint parser, diff-report generator
├── shared/
│   ├── schemas/                  <- Python dataclasses / pydantic models for Section 3 contracts — imported, never redefined locally
│   ├── metrics/                  <- HPWL, congestion, legality formulas (Section 1.4) — owned by C, imported by all
│   └── mocks/                    <- mock generators for every module's expected input, for isolated testing (Section 6.3)
├── backend/                      <- FastAPI app wiring modules together (built once individual modules are stable)
├── frontend/                     <- React app (built in the shared final phase)
├── experiments/
│   ├── configs/                  <- one YAML per experiment run
│   └── results/                  <- raw output + W&B run IDs, never hand-edited
└── tests/
    ├── unit/                     <- one subfolder per module, owned by that module's person
    └── integration/              <- shared, added once two modules are wired together
```

**Rule:** each person commits only inside their `modules/<their_module>/` and `tests/unit/<their_module>/` folders, plus the relevant `shared/schemas/` file if they are the owner of that schema. Anyone needing to change a file inside another person's module folder must open a PR and get that person's review — no direct pushes across module boundaries.

**Environment:** one `requirements.txt` per module folder (so each person's dependencies are isolated and don't silently break someone else's environment) plus one root `requirements-shared.txt` for the common libraries in Section 1.11. A single `environment_setup.md` at repo root documents exact install steps, GPU driver/CUDA version, and how to run each module's unit tests standalone.

---

## 3. INTERFACE CONTRACTS BETWEEN MODULES (the critical section)

Every arrow in the pipeline (1.2) crosses exactly one of these contracts. Each person can build and test against a **mock** of the adjacent contract before the real implementation exists — mocks live in `shared/mocks/` and must be kept in sync with the real schema by whoever owns that schema.

### 3.1 Circuit Graph JSON (owned by Person A; produced by intake parser, consumed by A's own encoders)

```json
{
  "design_name": "string",
  "nodes": [
    {
      "node_id": "int, 0-indexed, contiguous",
      "type": "string enum: MACRO | STD_CELL",
      "width": "float, die units",
      "height": "float, die units",
      "pin_count": "int"
    }
  ],
  "hyperedges": [
    {
      "net_id": "int, 0-indexed, contiguous",
      "driver_node": "int, node_id of the driving pin's node, or null if primary input",
      "sink_nodes": ["int, node_id list of all sink pins' nodes"]
    }
  ],
  "die": {
    "width": "float",
    "height": "float"
  }
}
```
This is the ONLY format the encoders (2.A) accept as input. The intake module (2.D) is responsible for producing valid Circuit Graph JSON from either an uploaded netlist or a Yosys-synthesized one — encoder code must never parse Verilog/LEF-DEF directly.

### 3.2 Encoder Output → Generator Input (owned jointly by A and B — changes require both sign off)

```json
{
  "node_embeddings": "float tensor, shape [num_nodes, D_node]",
  "global_embedding": "float tensor, shape [D_global]",
  "node_id_order": "int list, must match Circuit Graph JSON node_id order exactly"
}
```
Default dimensionalities for the project (tunable, but must be agreed and frozen once encoder training starts): `D_node = 256`, `D_global = 512`. Changing these after B has started training breaks B's model input layer — any change must be a joint decision, logged in `shared/schemas/CHANGELOG.md`.

### 3.3 Generator Output — Placement JSON (owned by Person B; consumed by C for verification and by the visualizer)

```json
{
  "design_name": "string",
  "placements": [
    {
      "node_id": "int",
      "x": "float",
      "y": "float",
      "orientation": "string enum: N | S | E | W | FN | FS | FE | FW"
    }
  ],
  "generation_metadata": {
    "model_variant": "string, e.g. 'DE-HNN+DeepGate4_flowmatching_v1'",
    "seed": "int",
    "is_legalized": "bool, false until Section 3.5 is applied"
  }
}
```

### 3.4 Freeze/Constraint Object — the D → B interface for editing (owned jointly by D and B)

```json
{
  "constraint_id": "uuid string",
  "source_request": "string, the raw NL text, kept for audit/debugging",
  "frozen_node_ids": "int list — ALL node_ids NOT touched by this constraint; complement of affected_node_ids",
  "affected_node_ids": "int list — node_ids the constraint refers to",
  "constraint_type": "string enum: MOVE_AWAY_FROM | MOVE_TOWARD | FORBID_ADJACENT | FORBID_REGION | PREFER_REGION | UNCLEAR",
  "reference": {
    "type": "string enum: NODE | REGION | EDGE",
    "value": "node_id, or region bounding box {x_min,y_min,x_max,y_max}"
  },
  "strength": "string enum: HARD | SOFT",
  "confidence": "float 0-1, LLM's own confidence in this parse; below 0.6 must trigger a clarifying question back to the user instead of a regeneration call"
}
```
If `constraint_type` resolves to `UNCLEAR` or `confidence < 0.6`, B's generator must NOT be called — D returns a clarification request to the user instead. This is a hard rule preventing the generator from acting on a misparsed instruction.

### 3.5 Verification Contract (owned by Person C; consumed by everyone downstream)

Input: a Placement JSON with `is_legalized: false`.
Output: a Placement JSON with `is_legalized: true` and legality violations resolved, PLUS a metrics object:
```json
{
  "hpwl": "float",
  "congestion_overflow": "float",
  "legality_violations": "int, must be 0 in final output",
  "runtime_seconds": "float"
}
```
No module other than C's evaluation code may compute these three metrics independently — every reported number in the project must trace back to this one function.

### 3.6 Diff Report Contract (owned by Person D; input from two Placement JSONs via C's metrics)

```json
{
  "constraint_id": "uuid, matches the triggering constraint object",
  "moved_nodes": [
    {"node_id": "int", "delta_x": "float", "delta_y": "float"}
  ],
  "unexpected_moves": "int list of node_ids that moved despite being in frozen_node_ids — MUST be empty; non-empty means a bug in B's freeze enforcement, not a reportable result",
  "hpwl_delta": "float",
  "congestion_delta": "float"
}
```

---

## 4. PERSON-WISE DEEP DIVES (with concrete defaults, signatures, and test contracts)

### 4.A — Netlist Encoders

**Module path:** `modules/encoders/`

**Sub-implementations required:** `gcn.py`, `gat.py`, `de_hnn.py`, `deepgate4.py`, each exposing the same interface:
```python
class NetlistEncoder(ABC):
    def encode(self, graph: CircuitGraph) -> EncoderOutput:
        """Returns node_embeddings [N, D_node] and global_embedding [D_global],
        per the schema in Section 3.2. Must not mutate the input graph."""
```

**Default starting hyperparameters (tunable during experimentation, but log every change in `experiments/configs/`):**
- GCN / GAT: 3 message-passing layers, hidden dim 256, ReLU activation, dropout 0.1.
- DE-HNN: hypergraph encoder + hyperedge interaction module per Luo et al., 2 rounds of alternating node/hyperedge updates, hidden dim 256, permutation-equivariant aggregation (sum or attention-weighted sum — treat as a tunable ablation, not a fixed choice).
- DeepGate4: GAT-based sparse transformer, sub-linear-memory update strategy (historical embedding reuse across training iterations), global + local structural positional encodings.
- All four: Adam optimizer, initial LR 1e-3 with cosine decay, batch size determined by largest chip that fits in GPU memory (log actual value used).

**Testing contract:** before B's generator exists, A tests each encoder against `shared/mocks/mock_generator_consumer.py`, which simply asserts the output shape/schema matches Section 3.2 and does nothing else — this lets A finish and validate encoder work independent of B's progress.

**Deliverable:** four trained encoders + the comparative benchmark table (accuracy contribution to final placement HPWL/congestion, plus standalone runtime/memory at increasing node counts) that justifies the final DE-HNN+DeepGate4 choice.

---

### 4.B — Generative Placement Engine

**Module path:** `modules/generator/`

**Interface (amended 2026-09-18 — see the ruling note after Section 4.C for why):**
```python
class PlacementGenerator:
    def generate(
        self,
        encoder_output: EncoderOutput,
        graph: CircuitGraph,
        frozen_placements: Optional[List[FrozenNode]] = None,
        guidance_terms: Optional[GuidanceConfig] = None,
        seed: int = 0,
    ) -> PlacementJSON:
        """frozen_placements entries are EXCLUDED from the generative variable
        tensor entirely — implemented via index masking before the
        sampling loop begins, not via loss weighting. See Section 1.7.
        `graph` supplies design_name, die dimensions, node geometry, and
        hyperedge connectivity — none of which EncoderOutput (Section 3.2)
        carries, and all of which are required to produce a schema-valid
        PlacementJSON (Section 3.3) or to run legality/wirelength guidance."""
```

**Default starting hyperparameters:**
- Flow matching: conditional flow matching objective, linear interpolation path between noise and data, ODE solver with 50 sampling steps as the default (tune down for the runtime benchmark, tune up if quality is the priority for a given experiment — log which was used per run).
- Diffusion fallback (only if flow-matching underperforms in practice on the project's benchmark set): standard DDPM-style noise schedule, 1000 training steps / reduced sampling steps at inference (e.g., DDIM-style acceleration) for the zero-shot-in-seconds claim to hold.
- Guidance weight for legality/wirelength/congestion terms: start at equal weighting, tune via ablation — record every configuration tried.

**Freeze enforcement (must be unit tested explicitly):** a test in `tests/unit/generator/` that calls `generate()` with a non-empty `frozen_placements`, then asserts every frozen node's output coordinate is bit-identical to its input coordinate. This test must exist before this module is considered "done" — it is the direct code-level enforcement of Section 1.7's guarantee.

**Testing contract:** B tests against `shared/mocks/mock_encoder_output.py` (random tensors matching Section 3.2's shape) before A's real encoders are ready, and against `shared/mocks/mock_legalizer.py` (a pass-through that just checks Placement JSON shape) before C's real legalizer is ready.

**Deliverable:** trained generator, working zero-shot inference on held-out chips, working freeze-mask regeneration with the unit test above passing.

---

### 4.C — Verification, Baselines, and Evaluation

**Module path:** `modules/evaluation/`

**Interface (amended 2026-09-18 — see the ruling note below):**
```python
def legalize_and_score(
    placement: PlacementJSON, graph: CircuitGraph, work_dir: Optional[Path] = None
) -> Tuple[PlacementJSON, MetricsObject]:
    """Implements Section 3.5. The single source of truth for HPWL,
    congestion overflow, and legality violations — see Section 1.4 for
    the exact formulas. Wraps DREAMPlace/OpenROAD; does not reimplement
    routing estimation. `graph` supplies node width/height/type and
    hyperedge connectivity, neither of which PlacementJSON (Section 3.3)
    carries on its own — required to compute any of the three metrics."""

def run_dreamplace_baseline(graph: CircuitGraph) -> PlacementJSON: ...
def run_rl_baseline(graph: CircuitGraph, checkpoint_path: str) -> PlacementJSON: ...
```

**RL baseline reproduction:** adapt an open MaskPlace/EfficientPlace-style implementation (or Google's open-sourced Circuit Training repo) rather than reimplementing from the paper text alone — the goal is a faithful, fair baseline, not a novel RL contribution.

**Ruling on the `graph: CircuitGraph` parameter (logged here and in `shared/schemas/CHANGELOG.md`, 2026-09-18):** while implementing 4.B and 4.C, Persons B and C independently hit the same gap — `EncoderOutput` (3.2) carries only embeddings + `node_id_order`, and `PlacementJSON` (3.3) carries only `node_id`/`x`/`y`/`orientation`, so neither `generate()` nor `legalize_and_score()` can produce a schema-valid result, run legality/wirelength guidance, or compute HPWL/legality without also having node geometry, die dimensions, and hyperedge connectivity in hand. Two fixes were on the table: (a) extend `EncoderOutput` itself with `design_name`/`die` (jointly owned by A and B per 3.2, needing A's sign-off), or (b) pass `graph: CircuitGraph` as an explicit extra parameter at each call site. B and C both implemented and unit-tested (b) independently (`modules/generator/generator.py`, `modules/evaluation/legalizer.py`) before this was reconciled. **Ruling: (b) is adopted project-wide, formally, as of this edit** — Person A (joint owner of 3.2) signs off on leaving `EncoderOutput` unchanged rather than growing it to duplicate data `CircuitGraph` already carries; every pipeline stage past the encoder receives `graph` alongside whatever stage-specific object it's operating on. This section and 4.B above now reflect the interfaces exactly as implemented and tested, not the original literal signatures.

**Statistical testing utility (used by all four members when reporting any comparison):**
```python
def compare_methods(results_a: List[float], results_b: List[float]) -> StatTestResult:
    """Returns mean, std for each, and a paired significance test
    (Wilcoxon by default; falls back to paired t-test if explicitly
    configured). p < 0.05 required before either method may be reported
    as 'better' in any writeup."""
```

**Testing contract:** C's metrics functions are unit tested against small, hand-computed placements with known HPWL/congestion values (a 3-4 macro toy example worked out by hand) before being trusted on real benchmark chips — this catches formula bugs before they contaminate every other module's results.

**Deliverable:** working legalizer wrapper, both baselines reproduced and runnable on the shared benchmark set, the full metrics/statistics pipeline, and the consistency/drift and runtime/scalability benchmark scripts.

---

### 4.D — LLM Layer and Intake

**Module path:** `modules/intake/` (Yosys + RTL assist) and `modules/llm_interaction/` (constraint parsing + diff reporting)

**Intake interface:**
```python
def synthesize_from_description(description: str, template: Optional[str] = None) -> str:
    """Returns synthesizable RTL (HDL text). LLM-assisted drafting only —
    actual synthesis is delegated to Yosys, not modeled."""

def run_yosys_synthesis(rtl_path: str) -> CircuitGraph:
    """Wraps Yosys CLI, parses its netlist output into Section 3.1's
    Circuit Graph JSON. This function is also the ONLY legal parser for
    directly-uploaded netlists — expert path and beginner path converge
    here."""
```

**Constraint parser interface:**
```python
def parse_constraint(nl_text: str, current_placement: PlacementJSON) -> ConstraintObject:
    """Implements Section 3.4's schema exactly. Must use LLM
    function-calling / structured output mode, not free-text parsing
    with regex. Must set constraint_type=UNCLEAR and route to a
    clarifying question if confidence < 0.6 — never guess silently."""

def generate_diff_report(
    before: PlacementJSON, after: PlacementJSON,
    constraint: ConstraintObject, metrics_before: MetricsObject,
    metrics_after: MetricsObject,
) -> DiffReport:
    """Implements Section 3.6. Must flag any moved node_id present in
    constraint.frozen_node_ids as unexpected_moves — this is the
    project's direct check on B's freeze guarantee, run on every single
    edit, not just in testing."""
```

**Constraint-parsing labeled test set:** D owns building and maintaining ≥100 (NL request, expected constraint) pairs, covering all `constraint_type` values and a deliberate mix of clear and ambiguous requests (to test the confidence-threshold/clarification path). This set is held out from any prompt iteration and used only for the final precision/recall number in Section 1.9.

**Testing contract:** D tests the constraint parser against `shared/mocks/mock_placement.py` (a fixed toy placement) before C's real evaluation pipeline exists, and tests `generate_diff_report` against hand-constructed before/after pairs with a known expected diff.

**Deliverable:** working beginner intake flow (description → RTL draft → Yosys → Circuit Graph JSON), working constraint parser with the confidence/clarification path implemented, working diff-report generator, and the labeled evaluation set with reported precision/recall.

---

## 5. NAMING CONVENTIONS, CONFIG, AND LOGGING

### 5.1 Naming conventions
- Python: `snake_case` for functions/variables, `PascalCase` for classes, matching the interfaces already specified above exactly — do not rename fields in Section 3's schemas locally.
- Experiment names in W&B: `<module>_<model_variant>_<chip_name>_seed<seed>`, e.g. `encoder_de-hnn_ariane_seed3`.
- Model checkpoints: saved under `experiments/results/<experiment_name>/checkpoint_<step>.pt`.

### 5.2 Config
- `config/shared_config.yaml` is the single source of truth for: the fixed train/test chip split (Section 1.9.4), the list of random seeds to use project-wide, benchmark data paths, and default hyperparameters from Section 4. No module hardcodes any of these values independently — all four modules load this file.

### 5.3 Logging
- Every training/evaluation run logs to Weights & Biases under a shared project name, tagged with the owning module and model variant, so any member can pull up any other member's run without asking.

---

## 6. GIT WORKFLOW AND OWNERSHIP BOUNDARIES

- One branch per module per feature: `<person-initial>/<short-feature-name>`, e.g. `a/de-hnn-implementation`.
- PRs require review from the adjacent-interface owner when a schema file under `shared/schemas/` is touched (e.g., a PR changing Section 3.2's dimensions needs both A and B's approval), and are otherwise self-mergeable once tests pass.
- `shared/schemas/`, `shared/metrics/`, and `TECHNICAL.md` itself are the only paths that require cross-review by default — everything inside a person's own `modules/<name>/` folder does not.
- Mocks in `shared/mocks/` are updated by the schema owner whenever a contract changes, in the same PR as the schema change — a schema change without an updated mock is treated as an incomplete PR.

---

## 7. FAILURE AND EDGE-CASE HANDLING CONTRACTS

- **Legalizer cannot resolve overlaps within a reasonable iteration budget:** C's `legalize_and_score` returns the best-effort result with `legality_violations > 0` explicitly flagged; this result must never be shown to the user or counted in final reported metrics — it is logged as a failure case for that specific chip/seed combination instead.
- **LLM constraint parse confidence < 0.6, or `constraint_type == UNCLEAR`:** D returns a clarification prompt to the user; B's generator is never invoked on an unclear instruction (Section 3.4).
- **Freeze violation detected (`unexpected_moves` non-empty in a diff report):** this is treated as a bug report against module B, filed immediately, and the affected result is excluded from any reported benchmark numbers until fixed and re-run.
- **Generator produces NaN/invalid coordinates:** B's `generate()` must validate its own output before returning; on failure, retry once with a new seed, then raise an explicit error rather than silently passing invalid data to C.
- **Yosys synthesis failure on beginner-drafted RTL:** D's intake path surfaces the Yosys error back through the LLM layer as a plain-language explanation to the user, with an option to edit the description and retry — it must never silently fall back to a template without telling the user.
