# Person C — Verification, Baselines, Evaluation: Notes for the team

Status: `shared/metrics/` (HPWL, congestion, legality — Section 1.4),
`modules/evaluation/`'s DREAMPlace/OpenROAD wiring, Bookshelf/DEF I/O, the
`compare_methods` statistical utility, and the RL-baseline environment are
implemented and unit-tested against mocks/fakes/toy data
(`tests/unit/evaluation/`, 52/52 green, +1 skipped without
stable-baselines3/torch installed — run `pytest tests/unit/evaluation/`).
This covers everything INSTRUCTIONS.md Section 1.1 asks Person C to build
before real data and real tool installs arrive. What follows is what's
genuinely blocked, what needed a judgment call, and what the team should
weigh in on.

## 1. Genuinely blocked (did not attempt to fake around these)

### 1.1 DREAMPlace and OpenROAD are not installed in this dev environment

Neither has a pip/conda package — both are built from source and need a
Linux (or WSL2/Docker) environment; see `environment_setup.md`'s new
DREAMPlace/OpenROAD sections. `dreamplace_runner.find_dreamplace_placer()`
and `openroad_runner.find_openroad_binary()` raise clear, typed errors
(`DreamplaceNotInstalledError`, `OpenroadNotInstalledError`) rather than
silently returning a fake result — this is by design (INSTRUCTIONS.md
Section 4), not an oversight. Everything *around* that boundary — Bookshelf
I/O (`bookshelf_io.py`), DEF export (`def_io.py`), config generation, output
parsing, and `legalize_and_score`'s orchestration — is fully implemented and
tested by injecting fakes at exactly that boundary
(`tests/unit/evaluation/test_legalizer.py`). Whoever sets up a Linux/WSL2
box first should build both tools and confirm the real subprocess calls
actually work — the JSON config keys and Tcl commands used here are based on
each tool's public documentation but have not been run against the real
binaries yet.

### 1.2 OpenROAD's congestion estimate needs a real tech LEF this repo has no source for

`shared/metrics/congestion.py` only implements the aggregation formula
(Section 1.4 is explicit that routing estimation itself is out of scope).
Producing `routing_demand`/`routing_capacity` needs OpenROAD's global router,
which needs a technology LEF (routing layers, track pitch) — Circuit Graph
JSON (Section 3.1) carries none of that, and nothing in TECHNICAL.md assigns
an owner for synthesizing one. The real tech LEF is expected to come from a
real PDK (Section 1.13 source 3, ASAP7) once that's wired into the intake
side. Until then, `openroad_runner.estimate_congestion` is wired but not
runnable for a real number — flagging this explicitly rather than inventing
a placeholder tech LEF that would make every downstream congestion number
meaningless.

### 1.3 Actually reproducing the RL baseline (real training on real chips)

`run_rl_baseline` only runs *inference* against an existing Stable-Baselines3
checkpoint — it raises `FileNotFoundError` if the checkpoint doesn't exist,
and never trains one itself. `tests/unit/evaluation/test_rl_baseline_smoke.py`
trains a toy PPO for 16 timesteps purely to prove the
env → SB3 → checkpoint → `run_rl_baseline` plumbing works (mirrors Person
B's `test_training_sanity.py`) — this is explicitly not a baseline result.
Real RL baseline reproduction needs real benchmark chips (INSTRUCTIONS.md
Section 2).

### 1.4 `run_dreamplace_baseline` and `legalize_and_score` on real chips

Both are blocked on 1.1 above, and on real benchmark data existing in
`data/raw/` (currently empty in this environment — `data/README.md`'s
checklist is checked off, but no `data/raw/*` folder exists here; whoever
has the real downloads should confirm that checklist still reflects reality
on their machine).

## 2. Design/interface decisions made while implementing (flagging for review)

### 2.1 `legalize_and_score` and `run_dreamplace_baseline` take an extra `graph: CircuitGraph` parameter

Section 4.C's literal signature is `legalize_and_score(placement: PlacementJSON) -> Tuple[...]`
and `run_dreamplace_baseline(graph: CircuitGraph) -> PlacementJSON` (this one
already takes `graph`). But scoring a placement needs the *nodes'*
width/height/type and the *hyperedges* — none of which `PlacementJSON`
(Section 3.3) carries, only `node_id`/`x`/`y`/`orientation`. This is the same
category of gap Person B flagged in `modules/generator/NOTES.md` §1.1 for
`generate()` needing `graph` too. **What I did:** `legalize_and_score` takes
`graph` as a second required parameter, consistent with Person B's precedent
(same fix, same reasoning, applied at the next stage of the same pipeline).
Logged here rather than re-litigated in `shared/schemas/CHANGELOG.md` since
it's the same underlying gap B already logged.

### 2.2 `compare_methods`' return type (`StatTestResult`) lives in `modules/evaluation/stats.py`, not `shared/schemas/`

Section 3 defines schemas for the pipeline's data *contracts* (netlist →
encoder → generator → verifier → diff report). `StatTestResult` isn't one of
those — it is Section 4.C's own interface, used for reporting, not for
handing data to another module's pipeline stage. Keeping it in
`modules/evaluation/` avoids implying it needs the same cross-review gate as
`shared/schemas/`/`shared/metrics/` (CONTRIBUTING.md) when nothing about it
is a cross-module data contract. Anyone reporting a comparison imports it
directly from here.

### 2.3 `MacroPlacementEnv` places macros only, not standard cells

Matches the published MaskPlace/EfficientPlace formulation this project
reproduces (Section 4.C explicitly says to adapt one of those rather than
reimplement from scratch) — both place macros via RL and leave standard
cells to a separate, cheaper method. `run_rl_baseline` fills remaining
standard cells with `packing.grid_pack` (a simple deterministic packer, also
reused as DREAMPlace's required initial placement in
`run_dreamplace_baseline`) so the returned `PlacementJSON` still covers every
`node_id`, per Section 3.3. Neither of those two steps is "the RL result" —
`legalize_and_score` is what actually scores the final layout.

### 2.4 `MacroPlacementEnv` does not hard-enforce legality via action masking

`step()` accepts any action, including one that overlaps or goes off-die,
and penalizes it in the reward rather than blocking it (an `action_masks()`
method is provided for anyone wanting to bolt on `sb3-contrib`'s
`MaskablePPO` later, but plain `stable_baselines3.PPO` doesn't need it).
Rationale: Section 1.7 / the project's own architecture principle
(AI-VLSI-Placement-System.pdf §2.4) is that *every* generator's raw output —
RL baseline included — is re-legalized by `legalize_and_score` before it's
ever scored or shown, so this environment's job is a good starting point,
not a legality guarantee. Worth a second look if the team wants a stricter
baseline (hard masking is a small change to `step()` if so).

### 2.5 Orientation's effect on bounding boxes (`shared/metrics/geometry.py`)

Neither Section 3.1 nor 3.3 states whether `(x, y)` is a corner or center,
or how `orientation` changes a node's effective width/height. Fixed both
conventions once, in one shared place, so `hpwl.py` and `legality.py` (and
`bookshelf_io.py`/`def_io.py`) can't silently disagree: `(x, y)` is the
lower-left corner (matching `shared/mocks/mock_placement.py`'s existing grid
layout and Bookshelf's own `.pl` convention), and `E`/`W`/`FE`/`FW` swap
effective width/height (standard LEF/DEF/Bookshelf rotation convention).
Not stated as a schema change since it doesn't touch the schemas themselves
— just documents an assumption every consumer of `(x, y, orientation)`
needs to share.

## 3. Cross-module dependencies (status, not gaps in this code)

- **Person A's encoders** and **Person B's generator** are both
  architecturally complete per their own NOTES.md — nothing here blocks on
  either; `legalize_and_score`'s only real input dependency is a
  schema-valid `PlacementJSON` + `CircuitGraph`, which the existing mocks
  already provide for testing.
- **Person D's intake/LLM layer** doesn't exist yet — no dependency from
  this module either way; the diff-report freeze-violation check (Section
  3.6) is D's responsibility, downstream of this module's metrics.
- Once Person A/D's real netlist parsers produce a real `CircuitGraph` from
  an actual ISPD02/ISPD2015/Ariane design, `bookshelf_io.write_bookshelf`
  and `def_io.write_def` should work unchanged — they're schema-driven, not
  mock-driven — but the synthesized `.scl` row geometry in
  `bookshelf_io._write_scl_file` is a documented approximation for graphs
  that don't ship their own row file; the real ISPD-format benchmarks come
  with authentic `.scl` files that should be used directly instead once
  Person A/D's parser has access to them.
