# Person B — Generator: Notes for the team

Status: `PlacementGenerator` + flow-matching (primary) and diffusion
(fallback) strategies, freeze-mask enforcement, the D→B constraint
bridge, differentiable guidance, NaN-safety validation (Section 7), and
the training loop are all implemented and unit-tested against mock data
(`tests/unit/generator/`, 29/29 green — run `pytest tests/unit/generator/`).
Also verified against real cross-module code in
`tests/integration/`: real DE-HNN/GCN encoder → generator (A→B), real
generator → real `legalize_and_score` up to the DREAMPlace/OpenROAD
external-tool boundary (B→C), and real `parse_constraint` → generator
(D→B) all pass. This covers everything INSTRUCTIONS.md Section 1.1 asks
Person B to build before real data arrives, including the required
freeze-enforcement test. What follows is current status on every item
this file used to flag as open, plus what's still genuinely blocked.

## 1. Interface gaps found while implementing

### 1.1 `generate()` needed more than Section 4.B's literal signature gives it — RESOLVED, ratified 2026-09-18

Originally flagged here as "proposed, not yet applied." **Now settled:**
Person A (joint owner of `EncoderOutput`/Section 3.2) signed off on
adopting the `graph: CircuitGraph` parameter project-wide rather than
growing `EncoderOutput` to duplicate data `CircuitGraph` already carries.
TECHNICAL.md Sections 4.B and 4.C now show the amended signatures
directly, with a full ruling note after 4.C; `shared/schemas/CHANGELOG.md`
logs the decision and approval. No action remaining on this one.

### 1.2 `GuidanceConfig`'s `spatial_directives` extension — confirmed compatible with D's real parser

Originally flagged as "worth Person D reviewing once the real LLM parser
exists." D's real `parse_constraint` now exists
(`modules/llm_interaction/constraint_parser.py`), and
`tests/integration/test_person_d_end_to_end.py::test_person_d_full_python_pipeline_integration`
exercises the full real path — D's parser output straight into this
module's `constraint_to_generation_inputs()` and `generate()` — and
passes. Functionally confirmed; still worth D formally reviewing the
`spatial_directives` field itself as part of Section 3.4's documentation
if that hasn't happened as a named review step yet.

### 1.3 No optimizer/schedule specified for B — RESOLVED

`config/shared_config.yaml` now has a `generator_defaults.optimizer` block
(Adam, initial LR 1e-3, cosine decay), mirroring `encoder_defaults.optimizer`
exactly. `modules/generator/training.py`'s `TrainerConfig.from_shared_config()`
reads it, following the same pattern as
`modules/encoders/graph_utils.py`'s `NodeFeatureNormalization.from_shared_config()`
(explicit `KeyError` if the block is missing, no silent fallback). Tested
in `tests/unit/generator/test_training_sanity.py`.

## 2. Cross-module dependency status (all three items below have moved since this was last written)

- **Person C's `shared/metrics/` now exists** — real HPWL/congestion/legality
  formulas, DREAMPlace/OpenROAD wiring, Bookshelf/DEF I/O. This module's
  guidance surrogates (`modules/generator/guidance.py`) remain intentionally
  separate (Section 1.4: C's formulas are the only reportable numbers;
  guidance needs a *differentiable* surrogate, which C's real legalizer,
  wrapping non-differentiable external tools, isn't). B→C is verified up to
  the external-tool boundary (`tests/integration/test_b_to_c_generator_to_legalizer.py`);
  DREAMPlace/OpenROAD themselves aren't installed in this dev environment
  by design (`modules/evaluation/NOTES.md`), so `legalize_and_score` itself
  is still blocked there, not on anything in this module.
- **Person D's real LLM constraint parser now exists** and is integration-
  tested end to end with this module's real code (§1.2 above) — no changes
  needed on this side.
- **Person A's encoders are used directly in real integration tests**
  (DE-HNN, GCN) — still architecturally-tested rather than trained on real
  data, same as this module (see §3).

## 3. Blocked until real data is available in this environment

- **Real chip data has actually landed on the team's side**, per
  `data/README.md` (all seven sources checked as downloaded) and
  `config/shared_config.yaml`'s `dataset_split` (filled in 2026-09-21 from
  35 real, currently-parseable designs; `encoder_defaults.node_feature_normalization`
  computed from 3.1M real nodes the same day). `data/raw/` and
  `data/processed/` are gitignored by design, so none of that is present in
  this checkout — training the generator on real data is no longer blocked
  on the data existing, only on this specific environment having a copy of
  `data/processed/*.json` (and, still, on real target placements to
  supervise against — worth clarifying with the team whether that's the
  ISPD/ISPD2015 benchmarks' own reference placements, a DREAMPlace baseline
  run, or something else, before wiring up a real `Dataset`/`DataLoader`).
- Tuning guidance weights, ODE step count, or the flow-matching-vs-diffusion
  choice against real quality numbers — needs DREAMPlace/OpenROAD installed
  (Person C's environment blocker, not this module's).
- The consistency/drift benchmark (Section 1.9.6) — the freeze mechanism
  itself is built and unit-tested (bit-identical, not just "low drift"),
  but the benchmark needs real chips + a working `legalize_and_score` to
  run meaningfully.

## 4. Design choices worth a second pair of eyes (not spec violations, just judgment calls)

- The backbone (`modules/generator/network.py`) is a single self-attention
  block over all N nodes (no PyTorch Geometric, no message passing) — since
  A's embeddings already encode graph structure, this network's job is
  relative-geometry reasoning, not re-deriving connectivity. This is O(N²);
  Person C's runtime/scalability benchmark (Section 1.9.8) is the place
  that will surface whether this matters in practice on the larger real
  designs now available (e.g. `mgc_superblue11_a`/`12`/`16a`).
- Guidance terms are differentiable *surrogates* by design (see §2 above),
  not literal reimplementations of Section 1.4's formulas.

## 5. Bug found and fixed during A/B/C/D integration (2026-09-18)

**`SpatialGuidance`'s "away_from"/"avoid_region" objective was unbounded and
produced NaN.** It minimized a raw `-dist_sq`, which has no minimum — 50
Euler steps of gradient descent on it diverge toward +/-infinity, and once
`z` hits `inf` the backbone network (attention/softmax over `z`) turns that
into `NaN`. This was invisible in `tests/unit/generator/test_guidance.py`'s
single-gradient-call checks (one call doesn't diverge) and only surfaced
once Person D's real end-to-end edit loop exercised a full `generate()` call
with an "away from" constraint.

**Fix:** repulsion now minimizes a bounded, saturating potential
(`exp(-dist_sq / die_diag_sq)`, scaled to the graph's own die size) instead
of the unbounded quadratic — already at its minimum-desirable value near
zero distance, and its gradient vanishes as distance grows, so descent
can't diverge. Attraction (`toward`/`prefer_region`) was already bounded
below by 0 and is unchanged. Two regression tests cover this
(`tests/unit/generator/test_guidance.py`), plus a real-encoder end-to-end
reproduction (`tests/unit/generator/test_nan_safety.py`).

**Defense in depth added per Section 7's explicit requirement** (spec'd,
but unimplemented until this bug motivated it): `generate()` validates its
sampled coordinates for NaN/Inf before building a `PlacementJSON`, retries
once with `seed + 1`, and raises `GenerationProducedInvalidCoordinatesError`
if the retry also fails — see `PlacementGenerator._sample_with_retry`.

## 6. Housekeeping worth flagging to the team

`HANDOFF_FOR_PERSON_D.md`'s "Person B" section still describes §1.1 as
"proposed, not yet applied" and says "22/22 green" — both stale as of this
update (§1.1 is ratified; the real count is 29/29, now including the NaN
fix's tests and the `tests/integration/` cross-module passes). Not edited
here since that doc also covers Persons A and C and isn't solely this
module's file — flagging it for whoever owns updating it next.
