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
pip install -r backend/requirements.txt
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

## Running the backend

```bash
uvicorn backend.main:app --reload --port 8000
```

Then `GET http://localhost:8000/health` should return `{"status": "ok", ...}`,
and interactive API docs are at `http://localhost:8000/docs` (FastAPI's
auto-generated Swagger UI — useful for exercising `/api/placement/generate`
and `/api/placement/edit` by hand before a frontend exists).

Every placement `/api/placement/generate` and `/api/placement/edit` return
has already been through Person C's `legalize_and_score` — check the
response's `verification_status` field: `"verified"` means real HPWL/
congestion/legality numbers are present in `metrics`; a string starting
with `"unavailable: ..."` means DREAMPlace/OpenROAD aren't installed in this
environment (see the DREAMPlace/OpenROAD sections below) and the returned
placement is still `is_legalized: false` — never treat it as final in that
case (TECHNICAL.md Section 1.8).

Set `OPENAI_API_KEY` (or `LLM_API_KEY`) in the environment to use the real
LLM-backed constraint parser and RTL drafting instead of their deterministic
offline fallbacks — both work correctly without it, just less flexibly (see
`modules/llm_interaction/NOTES.md`).

## DREAMPlace (Person C — legalization + classical baseline)

DREAMPlace has no PyPI package; it's built from source (CMake, Boost, Flute,
optionally CUDA) and needs a Linux environment (native Linux, or WSL2/Docker
on Windows/Mac) — it does not build on Windows directly.

```bash
git clone --recursive https://github.com/limbo018/DREAMPlace.git
cd DREAMPlace
docker build . --file Dockerfile --tag dreamplace:latest   # simplest path, per DREAMPlace's own README
# or build from source per DREAMPlace's README if not using Docker
```

Once built, point this project at it:

```bash
export DREAMPLACE_ROOT=/path/to/DREAMPlace   # must contain dreamplace/Placer.py
```

`modules/evaluation/dreamplace_runner.py` reads `DREAMPLACE_ROOT` and raises
a clear `DreamplaceNotInstalledError` (not a silent fallback) if it's unset
or the build is incomplete.

## OpenROAD (Person C — congestion estimate)

```bash
git clone --recursive https://github.com/The-OpenROAD-Project/OpenROAD.git
cd OpenROAD && ./etc/DependencyInstaller.sh && mkdir build && cd build && cmake .. && make -j$(nproc)
```

Same Linux/WSL2/Docker constraint as DREAMPlace. Once built:

```bash
export OPENROAD_BIN=/path/to/OpenROAD/build/src/openroad   # or leave unset if `openroad` is on PATH
```

**Known gap, not yet resolvable from this repo alone:** a real congestion
estimate needs a technology LEF (routing layers, track pitch) in addition
to the design DEF. Circuit Graph JSON (Section 3.1) carries no routing/
technology information — a real tech LEF has to come from a real PDK
(TECHNICAL.md Section 1.13 source 3, ASAP7). Until a real design is run
through a real PDK, `modules/evaluation/openroad_runner.py`'s
`estimate_congestion` is wired (subprocess call, Tcl script generation,
report parsing — all unit-tested against fakes) but not yet runnable
end-to-end for a real number. See `modules/evaluation/NOTES.md`.

## Data

See `data/README.md` for the dataset download checklist and exact target folders.
`data/raw/` is gitignored — real datasets are never committed.
