# Environment Setup

Frozen tech stack: TECHNICAL.md Section 1.11. Do not deviate without flagging it.

## Requirements

- Python 3.11.x (this machine currently has 3.12.7 — fine for schema/mock work now,
  but re-verify against 3.11.x before real training runs, since the pin is 3.11.x).
- PyTorch 2.x, CUDA 12.1 build.
- NVIDIA GPU + driver compatible with CUDA 12.1 for any real training.
- Yosys (latest stable) — external CLI, Person D's synthesis path.
- OpenROAD, DREAMPlace (latest stable of each) — external tools, Person C's
  legalization/baseline path.

## Install

```bash
# Root shared dependencies
pip install -r requirements-shared.txt --index-url https://download.pytorch.org/whl/cu121

# Then each module's own dependencies, as needed:
pip install -r modules/encoders/requirements.txt
pip install -r modules/generator/requirements.txt
pip install -r modules/evaluation/requirements.txt
pip install -r modules/intake/requirements.txt
pip install -r modules/llm_interaction/requirements.txt
```

## Running tests

From the repo root (pytest config in `pyproject.toml` sets `pythonpath = ["."]`,
so `shared.*` and `modules.*` imports resolve without installing the project):

```bash
pytest tests/unit/encoders/       # Person A
pytest tests/unit/generator/      # Person B
pytest tests/unit/evaluation/     # Person C
pytest tests/unit/intake/ tests/unit/llm_interaction/   # Person D
pytest tests/integration/         # cross-module, once two modules are wired
pytest                            # everything
```

## Data

See `data/README.md` for the dataset download checklist and exact target folders.
`data/raw/` is gitignored — real datasets are never committed.
