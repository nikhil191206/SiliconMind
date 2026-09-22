# Person B — Generator: Notes for the team

Status: `PlacementGenerator` + flow-matching (primary) and diffusion
(fallback) strategies are implemented and unit-tested against mock data
(`tests/unit/generator/`, 22/22 green — run `pytest tests/unit/generator/`).
This covers everything INSTRUCTIONS.md Section 1.1 asks Person B to build
before real data arrives, including the required freeze-enforcement test.
What follows is what still needs a human/team decision, and what's
genuinely blocked.

## 1. Interface gaps found while implementing (need team sign-off)

### 1.1 `generate()` needed more than Section 4.B's literal signature gives it

Section 4.B's signature is:

```python
def generate(self, encoder_output, frozen_placements=None,
             guidance_terms=None, seed=0) -> PlacementJSON
```

`EncoderOutput` (Section 3.2) is only `node_embeddings`, `global_embedding`,
`node_id_order` — no `design_name`, no die dimensions, no raw node
geometry, no net connectivity. But:

- `PlacementJSON.design_name` (Section 3.3) is a required field.
- Turning the model's native normalized-[0,1] output into real placement
  coordinates needs the die's width/height.
- Legality guidance needs real node widths/heights; wirelength guidance
  needs real hyperedge connectivity. Neither is derivable from embeddings
  alone (they're baked in nonlinearly by A's encoder, not recoverable).

**What I did:** added `graph: CircuitGraph` as an extra required parameter
to `generate()`. This is implemented and tested (see
`tests/unit/generator/test_generator_schema.py`,
`test_freeze_enforcement.py`), but it's a deviation from the literal
Section 4.B text, so I logged it in `shared/schemas/CHANGELOG.md` as
proposed-not-applied rather than silently changing the spec. The
alternative fix — extending `EncoderOutput` itself with `design_name`
and `die` — is jointly owned by A and B (Section 3.2) and needs Person
A's sign-off, which is why I didn't do that unilaterally.

**Action needed:** whoever integrates B with A's real encoder (and with
the backend later) should pick one of these two and update TECHNICAL.md
Section 4.B / 3.2 accordingly — right now the *code* has the fix, the
*spec doc* doesn't yet reflect it.

### 1.2 `GuidanceConfig` needed a fourth channel beyond the fixed 3 weights

Section 4.B only describes guidance as three fixed weights (legality /
wirelength / congestion). But the D → B "editing" interface (Section 3.4)
has directional constraint types — MOVE_AWAY_FROM a specific node,
FORBID_REGION, etc. — that three scalar weights can't express ("push
harder on legality" isn't the same as "push node 3 specifically away from
node 5 specifically").

**What I did:** `modules/generator/types.py`'s `GuidanceConfig` adds a
`spatial_directives: List[SpatialGuidanceDirective]` field, and
`modules/generator/freeze.py`'s `constraint_to_generation_inputs()`
builds one from each directional `ConstraintObject`. This is entirely
inside Person B's own module (not a `shared/schemas/` change), tested in
`tests/unit/generator/test_constraint_bridge.py` and
`test_guidance.py`. Still worth Person D reviewing once the real LLM
constraint parser exists, since D is the other owner of the 3.4 interface.

### 1.3 No optimizer/schedule specified for B in Section 4.B or shared_config.yaml

Section 4.A pins Adam + initial LR 1e-3 + cosine decay for the encoders.
`config/shared_config.yaml`'s `generator_defaults` has flow-matching and
guidance-weight defaults but no `optimizer` block. `modules/generator/training.py`'s
`Trainer` reuses A's Adam/1e-3/cosine convention rather than inventing an
unrelated one — reasonable as a placeholder, but worth an explicit team
decision (and then adding a `generator_defaults.optimizer` block to
`shared_config.yaml` to match how A's is specified) rather than leaving it
implicit in code.

## 2. Cross-module dependencies (not gaps in my code — just flagging status)

- **Person C's `shared/metrics/` doesn't exist yet** (C's track hasn't
  started — `modules/evaluation/` is still just a `.gitkeep`). Section 1.4
  says HPWL/congestion/legality formulas are owned by C and must never be
  reimplemented locally. My sampling-time guidance terms
  (`modules/generator/guidance.py`) are NOT that — they're differentiable
  surrogates for steering the ODE, clearly labeled as never-reportable, and
  they don't block on C. But once C's real metrics exist, tuning the
  guidance weights against *real* HPWL/legality numbers (rather than just
  the surrogate's own internal consistency) is blocked until then.
- **Person D's real LLM constraint parser doesn't exist yet** — `freeze.py`
  is built and tested against `shared/mocks/mock_constraint.py`'s three
  examples, exactly per INSTRUCTIONS.md's mock-driven parallel-development
  plan (Section 1.1/1.2). Second-wave integration (a *real* `ConstraintObject`
  from D's parser into `constraint_to_generation_inputs()`) is D's real code
  meeting B's real code — expected to need no changes on my side if D's
  parser actually emits Section 3.4-conformant objects, but untested until
  D's module exists.
- **Person A's encoders are architecturally done (27/27 green) but not
  actually trained** — same as my situation, both blocked on real data
  (Section 2). Today's integration is real generator + real encoder
  architecture + mock/random encoder weights, which is exactly the "A → B"
  second-wave check INSTRUCTIONS.md 1.2 describes.

## 3. Blocked until real data arrives (INSTRUCTIONS.md Section 2 — did not attempt to fake around these)

- Actually training the generator to produce good placements. Everything
  built here proves the training loop *runs* and the loss *goes down* on
  data it can see (`tests/unit/generator/test_training_sanity.py` — an
  explicit overfit sanity check, not a claimed result). No real chip
  datasets exist in `data/raw/` yet.
- Tuning guidance weights, ODE step count, or the flow-matching-vs-
  diffusion choice against real quality numbers — all of that needs C's
  real legalizer and real chips, neither of which exist yet.
- The consistency/drift benchmark (Section 1.9.6: ≥10 sequential edit
  rounds, measure unfrozen-but-unrelated drift) — the freeze mechanism
  itself is built and unit-tested (bit-identical, not just "low drift"),
  but the *benchmark* needs real chips and Person C's real metrics
  pipeline to run meaningfully.

## 4. Design choices worth a second pair of eyes (not spec violations, just judgment calls)

- The backbone (`modules/generator/network.py`) is a single self-attention
  block over all N nodes (no PyTorch Geometric, no message passing) —
  since A's embeddings already encode graph structure, this network's job
  is relative-geometry reasoning, not re-deriving connectivity. This is
  O(N²); Person C's runtime/scalability benchmark (Section 1.9.8) will be
  the place that surfaces whether this matters in practice on the larger
  benchmark chips.
- Guidance terms are differentiable *surrogates* by design (see §2 above),
  not literal reimplementations of Section 1.4's formulas — necessarily so,
  since gradient-based guidance needs something differentiable and C's
  real legalizer wraps external non-differentiable tools.

## 5. Bug found and fixed during A/B/C/D integration (2026-09-18)

**`SpatialGuidance`'s "away_from"/"avoid_region" objective was unbounded and
produced NaN.** It minimized a raw `-dist_sq`, which has no minimum — 50
Euler steps of gradient descent on it diverge toward +/-infinity, and once
`z` hits `inf` the backbone network (attention/softmax over `z`) turns that
into `NaN`. This was invisible in `tests/unit/generator/test_guidance.py`'s
single-gradient-call checks (one call doesn't diverge) and only surfaced
once Person D's real end-to-end edit loop exercised a full `generate()` call
with an "away from" constraint — see `tests/unit/generator/test_guidance.py`'s
NaN-regression test and `tests/integration/`.

**Fix:** repulsion now minimizes a bounded, saturating potential
(`exp(-dist_sq / die_diag_sq)`, scaled to the graph's own die size) instead
of the unbounded quadratic — it's already at its minimum-desirable value
near zero distance and its gradient vanishes as distance grows, so descent
can't diverge. Attraction (`toward`/`prefer_region`) was already bounded
below by 0 and is unchanged.

**Defense in depth added per Section 7's explicit requirement** (which
existed in the spec but had no implementation until now): `generate()`
validates its sampled coordinates for NaN/Inf before building a
`PlacementJSON`, retries once with `seed + 1`, and raises
`GenerationProducedInvalidCoordinatesError` (not a silent pass-through) if
the retry also fails — see `PlacementGenerator._sample_with_retry`.

## 6. Real GPU scalability bugs found and fixed (2026-09-23)

Testing `PlacementBackbone` on the actual target GPU (RTX 3050, 6GB) for
the first time — every prior test/run had stayed on CPU or used tiny
mock-scale graphs — surfaced two real, previously-invisible bugs.

**Bug 1 (crash on any GPU call):** `sinusoidal_time_embedding`'s `freqs`
tensor was built with no `device` argument, defaulting to CPU. The moment
`t` was a CUDA tensor, `t[:, None] * freqs[None, :]` mixed CPU and GPU
tensors and raised immediately. This means `PlacementBackbone` had
**never actually run on GPU before this investigation**, despite GPU being
the whole point of a 6GB laptop card. Fixed: `freqs` is now built on
`t.device`.

**Bug 2 (real scalability ceiling, not a crash — a silent hang):** once
GPU calls worked, measuring peak memory across real chip sizes found:

| N (nodes) | time (fwd+bwd) | peak memory |
|---|---|---|
| 12,752 (ibm01) | 2.5s | 1.05 GB |
| 30,000 | 13.1s | 2.4 GB |
| 70,000 | 71s | 5.5 GB |
| 150,000 | **hung indefinitely** | pinned at ~6GB |

At N=150,000 the process didn't crash with a clean CUDA OOM — it hung at
100% GPU utilization with memory pinned at the ceiling for 3+ minutes with
zero progress, consistent with Windows/WDDM silently falling back to slow
shared-system-memory swapping right at the VRAM limit instead of raising.
This matters because **roughly half of the real 30-design training corpus**
(`config/shared_config.yaml`'s `train_chips` — ibm12 through ibm16, most
ISPD2015 designs, and `mgc_superblue11_a` at 925,010 nodes) exceeds this
ceiling. Training the generator as originally written would have silently
hung on over a dozen real designs rather than erroring clearly.

**Fix applied:** gradient checkpointing (`torch.utils.checkpoint`) on each
`TransformerEncoderLayer`, applied via a manual per-layer loop
(`PlacementBackbone.attn_layers`) instead of `nn.TransformerEncoder`'s own
forward, which doesn't support checkpointing per layer. Verified
output-identical and gradient-identical to the non-checkpointed path
(`tests/unit/generator/test_network_scalability.py` — with dropout forced
to 0 specifically to avoid confounding checkpointing's effect with
dropout's own train/eval difference, a mistake caught while writing the
test). Re-measured: N=150,000 no longer hangs — memory drops to ~4.5GB —
but takes ~8-9 minutes for a single forward+backward pass, since
checkpointing trades memory for recompute, not for less underlying O(N²)
compute.

**Second-order fix (checkpointing isn't free, so it shouldn't always run):**
first shipped with `use_checkpointing=True` unconditionally. Measuring
N=70,000 *with* checkpointing found it actually got SLOWER overall (95.7s,
89s of that in backward) than the original unchecked path (71s) — 70K
already fits in 5.5GB comfortably, so checkpointing's recompute tax bought
nothing there. Fixed: `use_checkpointing` now defaults to `None` (auto),
deciding per forward call from the real node count against
`AUTO_CHECKPOINT_NODE_THRESHOLD = 80,000` — chosen because it sits between
the two measured points (70K needs no help; 150K hangs without it).
Re-verified: N=70,000 with the auto default is back to 70.5s/5.5GB, matching
the pre-checkpointing baseline exactly. Pass `True`/`False` explicitly to
override the automatic choice.

**What checkpointing does NOT fix, flagged rather than absorbed silently:**
the fundamental O(N²) attention cost. `mgc_superblue11_a` (925,010 nodes)
and the held-out test chips `mgc_superblue12` (1,285,615) and
`mgc_superblue16_a` (680,538) would each take a genuinely impractical
amount of time per training step even with checkpointing — minutes to
likely tens of minutes per step, at a scale where real training (thousands
of steps) is not feasible on this hardware. A real fix for chips at this
scale needs an actual architecture change (sparse/windowed attention, or a
hierarchical/clustering approach — notably, Google's own Circuit Training
data we already have, per `modules/intake/parsers/protobuf_parser.py`'s
notes, uses exactly this kind of clustering to keep its own RL placement
problem tractable at scale). This is real, substantial, unstarted work,
not something to route around quietly — flagging it here for the team/
whoever picks up large-chip generator training next, rather than silently
excluding the largest real chips from training and calling the corpus
complete.
