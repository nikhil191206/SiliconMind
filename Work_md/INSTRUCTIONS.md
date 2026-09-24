# INSTRUCTIONS.md — Execution Plan for Claude Code

You are being given three documents: this file (INSTRUCTIONS.md), TECHNICAL.md, and workDistribution.md. Read them in this order:

1. **workDistribution.md** — who (Person A/B/C/D) owns what, in plain language.
2. **TECHNICAL.md** — the binding technical specification: architecture, models, exact data schemas, formulas, hyperparameters, repo layout, and non-negotiable rules. Every contract in this file is authoritative. If your own reasoning ever conflicts with something stated in TECHNICAL.md, TECHNICAL.md wins — flag the conflict to the human rather than silently deviating.
3. **This file** — the concrete, ordered execution plan: what to actually build, in what order, and how to make progress *right now* even though the real training datasets have not been downloaded yet.

This document exists to solve one specific problem: **the human is gathering the real datasets (Section 1.13–1.16 of TECHNICAL.md) in parallel, and you should not sit idle waiting for them.** The vast majority of this project's engineering work — schemas, mocks, model architectures, training loops, the verification pipeline, the LLM layer, tests — can be built and validated *before* a single real dataset file exists, using the mock system defined below. Real datasets are only required for the final step of each module: actually training on real data and reporting real numbers. Everything before that step starts now.

---

## 0. FIRST SESSION — DO THESE STEPS IN THIS EXACT ORDER

Do not skip ahead to model code before this section is complete. This is the foundation everything else depends on, and doing it out of order is exactly how the four people's work ends up conflicting later.

### Step 0.1 — Initialize the repository

Create the exact folder structure specified in TECHNICAL.md Section 2, reproduced here for direct execution:

```
chip-placement-system/
├── README.md
├── TECHNICAL.md
├── workDistribution.md
├── INSTRUCTIONS.md
├── config/
│   └── shared_config.yaml
├── data/
│   ├── raw/
│   │   ├── ispd02/
│   │   ├── ispd2015/
│   │   ├── ariane_circuit_training/
│   │   ├── macroplacement/
│   │   ├── circuitnet/
│   │   ├── asap7/
│   │   └── corev/
│   ├── processed/
│   └── README.md
├── modules/
│   ├── intake/
│   ├── encoders/
│   ├── generator/
│   ├── evaluation/
│   └── llm_interaction/
├── shared/
│   ├── schemas/
│   ├── metrics/
│   └── mocks/
├── backend/
├── frontend/
├── experiments/
│   ├── configs/
│   └── results/
└── tests/
    ├── unit/
    │   ├── intake/
    │   ├── encoders/
    │   ├── generator/
    │   ├── evaluation/
    │   └── llm_interaction/
    └── integration/
```

Create every folder above now, even the ones that will stay empty until datasets arrive (`data/raw/*`) — this gives the human a clear, obvious place to drop each downloaded dataset without needing to ask where it goes.

Populate `data/README.md` with a checklist of the 7 official sources from TECHNICAL.md Section 1.13, each with: source name, the exact folder it goes in (per Section 1.16), and a checkbox. This becomes the human's literal download checklist — update the checkboxes as datasets arrive, don't leave this file static.

### Step 0.2 — Git setup

- `git init`, initial commit with the folder skeleton and the three markdown docs at root.
- Add a `.gitignore` that excludes `data/raw/*` and `data/processed/*` (these are large binary datasets — never commit them; the folder structure itself, via `.gitkeep` files in each empty `data/raw/<source>/` folder, is what's committed instead) and standard Python/Node ignores (`__pycache__/`, `*.pyc`, `.venv/`, `node_modules/`, `experiments/results/*` model checkpoints).
- Create the branch-naming convention described in TECHNICAL.md Section 6 as a short `CONTRIBUTING.md` note at root, so it's visible immediately, not buried only in TECHNICAL.md.

### Step 0.3 — Shared schemas (build this before any model code, in any module)

In `shared/schemas/`, implement every JSON contract from TECHNICAL.md Section 3 as actual Python code (pydantic models are strongly preferred over plain dataclasses here, since pydantic gives you free runtime validation — which matters a lot for catching schema-mismatch bugs early, exactly the kind of conflict this whole document structure is trying to prevent):

- `circuit_graph.py` → `CircuitGraph`, `CircuitNode`, `CircuitHyperedge` (Section 3.1)
- `encoder_output.py` → `EncoderOutput` (Section 3.2)
- `placement.py` → `PlacementJSON`, `PlacementEntry`, `GenerationMetadata` (Section 3.3)
- `constraint.py` → `ConstraintObject`, `ConstraintReference` (Section 3.4)
- `metrics.py` → `MetricsObject` (Section 3.5)
- `diff_report.py` → `DiffReport`, `MovedNode` (Section 3.6)

Every field name, type, and enum value must match TECHNICAL.md Section 3 exactly — do not paraphrase or "improve" a field name here, since every module's code will import directly from these files. Add a `shared/schemas/CHANGELOG.md` (empty for now, per TECHNICAL.md Section 3.2's instruction) that will log any future changes to these schemas.

### Step 0.4 — Mocks (build these immediately after schemas, before real module code)

In `shared/mocks/`, implement one mock generator per contract, each returning a syntactically valid, schema-correct, but obviously-fake instance:

- `mock_circuit_graph.py` → generates a small toy `CircuitGraph` (e.g., 5–10 nodes, 3–5 hyperedges) with hand-chosen values, deterministic (fixed seed), for other modules to develop against before real netlist parsing exists.
- `mock_encoder_output.py` → generates a random tensor matching `EncoderOutput`'s shape (`D_node=256`, `D_global=512` per TECHNICAL.md Section 3.2's defaults) for a given mock `CircuitGraph`'s node count, so Person B can build the generator against this before Person A's real encoders are done.
- `mock_placement.py` → generates a fixed, valid `PlacementJSON` for the mock circuit graph (simple grid layout is fine — it doesn't need to be good, only schema-valid and legal) for Person C and D to develop against before Person B's real generator is done.
- `mock_legalizer.py` → a pass-through function matching `legalize_and_score`'s signature that just checks input shape and returns `is_legalized: True` with placeholder metrics, so Person B can test the freeze-mask logic without waiting on Person C's real DREAMPlace/OpenROAD integration.
- `mock_constraint.py` → 2–3 hand-written example `ConstraintObject` instances (one per major `constraint_type`) for Person B and D to jointly test the freeze/regenerate interface before the real LLM parser exists.

This is the single most important step for enabling all four people to work in parallel starting today, without any of them blocking on another's progress. Every mock above should have a matching real implementation later that produces the exact same schema — swapping a mock for the real thing should never require changing the calling code.

### Step 0.5 — Metrics functions (build and unit-test before any real chip data exists)

In `shared/metrics/`, implement the three formulas from TECHNICAL.md Section 1.4 (`hpwl.py`, `congestion.py`, `legality.py`). These do not need real datasets to build or test — write unit tests using small, hand-computed toy placements (e.g., a 3-node placement where you compute HPWL by hand on paper first, then assert the function matches). This is Person C's responsibility per TECHNICAL.md Section 4.C, and should be done early since every other module's evaluation depends on it being correct and stable.

Important distinction, stated explicitly so it's never a point of confusion later: these hand-computed toy unit-test fixtures are **not** the "synthetic training data" that TECHNICAL.md prohibits (Section 1.14, 1.16's "no AI-generated dataset" rule). That rule is about what the *models are trained on* — a 3-node arithmetic check for a formula is ordinary unit-testing practice, not a training dataset, and does not violate the no-synthetic-data rule. Do not confuse the two anywhere in this project.

### Step 0.6 — Config skeleton

Create `config/shared_config.yaml` now, even with placeholder/empty values for anything dataset-dependent (the train/test chip split can't be finalized until real chips are downloaded — leave it as an empty list with a comment marking it `# TODO: fill once datasets in 1.16 are downloaded`). Include from day one: the list of project-wide random seeds (TECHNICAL.md Section 1.9.5 — pick 5 fixed seeds now, e.g. `[0, 1, 2, 3, 4]`, and never change them later), paths matching Section 1.16's directory convention, and the default hyperparameters from Section 4.

### Step 0.7 — Per-module requirements files

Create an empty `requirements.txt` in each `modules/<name>/` folder and one `requirements-shared.txt` at root listing the frozen core libraries from TECHNICAL.md Section 1.11 with the version pins specified there. Fill in each module's specific requirements as that module's code starts needing specific packages — don't guess/pre-fill packages not yet used.

---

## 1. WORK ORDER — WHAT TO BUILD, AND IN WHAT SEQUENCE

Everything in this section can proceed **without waiting for real datasets**, using the mocks from Step 0.4. Real-dataset-dependent tasks are explicitly marked as blocked and listed separately in Section 2.

### 1.1 Can start immediately, fully parallel across all four modules

- **Person A (`modules/encoders/`):** implement the `NetlistEncoder` abstract interface (TECHNICAL.md Section 4.A) and all four concrete encoders (`gcn.py`, `gat.py`, `de_hnn.py`, `deepgate4.py`) with their architectures per the specified hyperparameters. Test each against `mock_circuit_graph.py` → assert output matches `EncoderOutput`'s schema exactly (shape, dtype). This is real, substantial model-architecture code — none of it requires real chip data to write or to unit-test for correctness of shape/plumbing.
- **Person B (`modules/generator/`):** implement the `PlacementGenerator` class and the flow-matching (primary) generation logic per TECHNICAL.md Section 4.B's defaults. Test against `mock_encoder_output.py` for the conditioning input and `mock_legalizer.py` downstream. **Build and pass the freeze-enforcement unit test now** (TECHNICAL.md Section 4.B: call `generate()` with non-empty `frozen_placements`, assert bit-identical output for frozen nodes) — this is achievable entirely with mock data and is one of the most important correctness guarantees in the whole system, so do not defer it.
- **Person C (`modules/evaluation/`):** implement `legalize_and_score`'s function signature and wiring to DREAMPlace/OpenROAD (installing and getting these tools running is itself a real, non-trivial task worth starting immediately, independent of any dataset). Build `compare_methods` (the statistical testing utility) and unit-test it with synthetic *numeric* test data (e.g., two known lists of numbers with a known significance result) — again, not training data, just a numerical-correctness check on a stats function.
- **Person D (`modules/intake/` and `modules/llm_interaction/`):** implement `run_yosys_synthesis` and get Yosys installed/runnable end to end on a trivial hand-written toy RTL file (a 2-gate AND/OR circuit is enough to prove the pipeline works) — this validates the whole Yosys → Circuit Graph JSON path without needing any of the real benchmark designs yet. In parallel, implement `parse_constraint` against `mock_placement.py`, and start building the ≥100-example labeled constraint test set (TECHNICAL.md Section 4.D) — this is pure human/LLM-prompt work, entirely dataset-independent, and should start early since it takes real time to do well.

### 1.2 Second wave — cross-module integration using mocks (still no real data needed)

Once each person's module passes its own unit tests against mocks, wire two modules together directly (still no real training):
- A → B: feed a real (not mock) `EncoderOutput` from Person A's actual trained-on-mock-data encoder into Person B's actual generator, confirm the schema handoff works with two real implementations instead of one real + one mock.
- B → C: feed Person B's real generator output into Person C's real `legalize_and_score`, on the mock circuit graph — confirm the full pipeline runs end to end, even though the "chip" is a toy 5-node mock.
- D → B: feed a real parsed `ConstraintObject` from Person D's actual LLM parser into Person B's freeze-mask logic, confirm the interface holds with two real implementations.

This integration work is what turns four separate modules into one working system, and it's exactly the layer TECHNICAL.md Section 3 was written to make conflict-free — if any handoff breaks here, it's a schema violation, not a logic disagreement, and should be easy to pinpoint and fix.

### 1.3 Backend and frontend

Per workDistribution.md: backend (FastAPI, wiring all four modules together via the real, non-mock schemas) starts once the modules in 1.1/1.2 are individually stable. Frontend does not start until backend is functional end to end — this is a shared, non-negotiable rule already agreed in workDistribution.md, and applies regardless of dataset availability.

---

## 2. WHAT IS BLOCKED UNTIL REAL DATASETS ARRIVE (do not attempt to fake around these)

These tasks genuinely cannot proceed correctly without the real data from TECHNICAL.md Section 1.13, and must wait:

- Actually training any of the four encoders on real circuit structure (mock-based unit tests only prove the code runs, not that the model learns anything real).
- Actually training Person B's generator to produce good placements (same reasoning).
- Reproducing the RL baseline's real training runs.
- Running the real DREAMPlace/RL baselines on real benchmark chips for comparison numbers.
- The generalization train/held-out split (TECHNICAL.md Section 1.9.4) — this cannot be defined until the real chip designs are downloaded and counted.
- CircuitNet-based pretraining of Person A's encoders (Section 1.14).
- Any number that will appear in the final report — no result may be reported from mock data, ever, under any circumstance. Mock-derived numbers exist only to prove code correctness during development and must never be mistaken for or presented as a real experimental result.

As each dataset from TECHNICAL.md Section 1.13/1.16 lands in `data/raw/<source>/`, the corresponding ingestion script (built during Section 1's work, tested against mocks) should need little more than pointing it at the new real files — that's the entire payoff of building against mocks first.

---

## 3. INGESTION SCRIPTS TO PREPARE NOW (so real data is a one-command import, not new coding, once it lands)

Write these now, tested against `mock_circuit_graph.py`'s format expectations, so each is genuinely ready the moment its real data folder in `data/raw/` is populated:

- `modules/intake/parsers/bookshelf_parser.py` and `lefdef_parser.py` → both output `CircuitGraph` (Section 3.1). Test with a tiny hand-written 3-node Bookshelf/LEF-DEF fixture you write yourself (again: a unit-test fixture, not training data) before real ISPD02/ISPD2015 files exist.
- `modules/intake/parsers/protobuf_parser.py` → parses Google's `.pb.txt` netlist format (for the Ariane netlist specifically) into `CircuitGraph`.
- `data/processed/build_cache.py` → a single script that, once run, walks `data/raw/`, calls the appropriate parser per source, and populates `data/processed/` with cached `CircuitGraph` JSON files — this is the script the human runs once datasets are downloaded, and it should already exist and be tested (against mocks/fixtures) before that day arrives.

---

## 4. STANDING RULES DURING THIS DATASET-GATHERING PERIOD (do not violate any of these while working ahead of the data)

- Never substitute a placeholder/mock dataset for a real one in anything that will be reported as a result — mocks are for proving code correctness only, stated in Section 2 above, repeated here because it is the single most important rule in this document.
- Never invent a fake "real-looking" chip design to work around not having the actual data yet — if a task genuinely needs real data and none is available, stop and mark it blocked (Section 2), don't approximate around it.
- Do not change any schema in `shared/schemas/` without updating the matching mock in `shared/mocks/` in the same commit (TECHNICAL.md Section 6).
- Do not change the tech stack, model list, or any of TECHNICAL.md's frozen decisions to make early progress easier — if something in TECHNICAL.md seems to be blocking easy progress, that's a signal to flag it to the human, not to quietly substitute something else.
- Keep every module's work inside its own `modules/<name>/` folder (TECHNICAL.md Section 2's rule) even during this early, mock-driven phase — the ownership boundaries matter from day one, not just once real integration starts.

---

## 5. WHAT TO REPORT BACK TO THE HUMAN, AND WHEN

- After Step 0 (repository bootstrap) is complete: confirm the folder structure and `data/README.md` checklist are ready, so the human knows exactly where each dataset they're downloading should go.
- After each module's Section 1.1 work is functionally complete (passing its own unit tests against mocks): report which module, what was built, and what its next step is once real data lands.
- Immediately, if any conflict is found between TECHNICAL.md and what's actually feasible to build — do not silently resolve it by guessing; surface it.
- The moment any real dataset from TECHNICAL.md Section 1.13 lands in `data/raw/`: run the matching ingestion script from Section 3 above, confirm it produces valid `CircuitGraph` JSON, and report success/failure back before proceeding to real training on it.
