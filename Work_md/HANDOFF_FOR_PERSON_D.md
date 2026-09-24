# Handoff for Person D — where A, B, and C left off

Person D's track (`modules/intake/`, `modules/llm_interaction/` — Yosys
synthesis, LLM-assisted RTL drafting, NL constraint parsing, diff reporting)
hasn't started yet. This document pulls together what Persons A, B, and C
actually built, in enough detail to start D's track without having to
reverse-engineer three other people's code first. It's a summary — the
binding spec is still TECHNICAL.md, and each person's own module has more
detail (linked below) than fits here.

Read this after INSTRUCTIONS.md / TECHNICAL.md / workDistribution.md, right
before starting Section 4.D.

---

## Person A — Netlist Encoders (`modules/encoders/`)

**Status:** architecturally complete, unit-tested against mock data
(`tests/unit/encoders/`, 27/27 green per README). **Not yet trained on real
data** — blocked on real benchmark chips (INSTRUCTIONS.md Section 2), same
as everyone else's "real numbers" work.

**Interface every encoder implements** (`modules/encoders/base.py`):
```python
class NetlistEncoder(ABC):
    def encode(self, graph: CircuitGraph) -> EncoderOutput: ...
```
Input is Section 3.1's `CircuitGraph` — **this is the only netlist format
downstream code ever sees**. Whatever D's Yosys/Bookshelf/LEF-DEF/protobuf
parsers produce, it must be a schema-valid `CircuitGraph`, not raw netlist
text handed to anything else.

**The four encoders, and why they differ under the hood** (this matters if
D ever needs to reason about what "the encoder" assumes about a graph):
- **`gcn.py` / `gat.py`** — standard pairwise message-passing (3 layers,
  hidden dim 256). Both consume a **star-expansion** of each hyperedge
  (`graph_utils.star_expansion_edge_index`: driver↔sink directed edges per
  net) since GCN/GAT only understand pairwise edges, not native hyperedges.
- **`de_hnn.py`** — reproduces Luo et al. (AISTATS 2024): consumes the
  **native hypergraph structure directly** (no star expansion), 2 rounds of
  alternating node↔hyperedge updates, attention-weighted-sum aggregation by
  default.
- **`deepgate4.py`** — sparse `TransformerConv` attention over the same
  star-expansion graph GCN/GAT use, plus **historical embedding reuse**: an
  `active_node_ids` parameter lets a caller re-encode only the nodes
  touched by a small edit, reusing cached embeddings for everything else —
  directly relevant to D's iterative-editing loop (Section 1.7), since it's
  what makes a post-edit re-encode cheap instead of a full re-run. Flagged
  in-code as a simplified reproduction of the paper's technique, not
  literal paper-scale memory management.
- **`positional_encoding.py`** — DeepGate4's structural PEs: cheap local
  stats (degree, hyperedge count, pin count) plus global Laplacian
  eigenvector PE (falls back to a sparse Lanczos solver above a few
  thousand nodes — a known, documented scalability limit, not hidden).

**Deliverable still open:** the four-way comparative benchmark table
(Section 1.9.3) justifying the final DE-HNN+DeepGate4 hybrid — blocked on
real training data, same as the rest of A's "real numbers" work.

No `NOTES.md` from A and no flagged interface deviations beyond the
in-code DeepGate4 note above — A's module matches Section 4.A as written.

---

## Person B — Placement Generation Engine (`modules/generator/`)

**Status:** flow-matching (primary) + diffusion (fallback) implemented,
freeze-mask enforcement implemented and unit-tested, merged via PR #1.
22/22 green (`tests/unit/generator/`). **Not yet trained on real data.**
Full detail: **`modules/generator/NOTES.md`** (read this before touching
anything that calls `generate()`).

**Interface, as actually implemented** (`modules/generator/generator.py`) —
**note this differs from TECHNICAL.md Section 4.B's literal text**:
```python
class PlacementGenerator:
    def generate(
        self,
        encoder_output: EncoderOutput,
        graph: CircuitGraph,               # <- added; not in Section 4.B's literal signature
        frozen_placements: Optional[List[FrozenNode]] = None,
        guidance_terms: Optional[GuidanceConfig] = None,
        seed: int = 0,
    ) -> PlacementJSON: ...
```
**Why this matters for D:** `EncoderOutput` (Section 3.2) only carries
embeddings + `node_id_order` — no `design_name`, no die dimensions, no node
geometry. B added `graph: CircuitGraph` as a required parameter to make a
schema-valid `PlacementJSON` possible at all. This is flagged as
"proposed, not yet applied to the spec doc" — **B's NOTES.md §1.1 asks
whoever integrates the pipeline next to pick between this fix and the
alternative (extending `EncoderOutput` itself, which needs A's sign-off)
and update TECHNICAL.md accordingly.** If D's diff-report/constraint-edit
loop ever calls `generate()` directly (rather than through a future backend
wrapper), it needs `graph` too — don't assume Section 4.B's literal
3-argument signature.

**The D↔B interface D actually owns half of (Section 3.4):** B already
built the receiving end. `modules/generator/freeze.py`'s
`constraint_to_generation_inputs()` converts a `ConstraintObject` into
`frozen_mask` + `GuidanceConfig`, tested against
`shared/mocks/mock_constraint.py`'s three examples (one per constraint type
family). **Two things to know before D's real `parse_constraint` exists:**
1. B extended `GuidanceConfig` with a `spatial_directives` field
   (`modules/generator/types.py`) to express directional constraints
   (`MOVE_AWAY_FROM` a specific node, `FORBID_REGION`, etc.) that three
   scalar weights can't — this is inside B's own module, not a
   `shared/schemas/` change, but B explicitly asks D to review it once the
   real LLM parser exists (B's NOTES.md §1.2).
2. The freeze guarantee itself (Section 1.7) is enforced at the
   tensor-indexing level and unit-tested for bit-identical output on frozen
   nodes — D's `generate_diff_report`'s `unexpected_moves` check (Section
   3.6) should never find anything from B's side, and if it ever does,
   Section 7 says that's a bug report against B, not a D-side fix.

**Blocked for B:** real training, tuning guidance weights against real
metrics, and the consistency/drift benchmark (Section 1.9.6) — the last one
specifically needs real chips *and* Person C's real metrics pipeline (see
below), so it's blocked on both B and C's real-data steps together, not
just one.

---

## Person C — Verification, Baselines, and Evaluation (`modules/evaluation/`)

**Status:** `shared/metrics/`, DREAMPlace/OpenROAD wiring, Bookshelf/DEF
I/O, the RL-baseline environment, and `compare_methods` are implemented and
unit-tested (`tests/unit/evaluation/`, 52/52 green, +1 skipped without
stable-baselines3/torch). Full detail: **`modules/evaluation/NOTES.md`**.

**What D's `generate_diff_report` actually consumes from this module**
(Section 3.6's signature needs `metrics_before`/`metrics_after`):
```python
def legalize_and_score(
    placement: PlacementJSON, graph: CircuitGraph, work_dir: Optional[Path] = None
) -> Tuple[PlacementJSON, MetricsObject]
```
Same deviation as B's `generate()`, for the same reason: `graph` was added
because scoring needs node width/height/type and hyperedge connectivity,
none of which `PlacementJSON` alone carries. **D's diff-report code will
need to pass `graph` alongside both `PlacementJSON`s it's comparing.**

`MetricsObject` (Section 3.5) is stable and fully usable today for
building/testing D's diff-report logic against hand-constructed
before/after pairs (exactly what Section 4.D's testing contract asks for) —
you do **not** need DREAMPlace/OpenROAD installed, or real chip data, to
build and test `generate_diff_report` itself. Only a call to
`legalize_and_score` *itself* is currently blocked (raises
`DreamplaceNotInstalledError`/`OpenroadNotInstalledError` — neither tool is
installed in this dev environment; see NOTES.md and `environment_setup.md`
for the Linux/WSL2/Docker install path).

**The one number `generate_diff_report` cannot get from this module yet:**
`congestion_overflow` in a real `MetricsObject` needs OpenROAD's global
router, which needs a real technology LEF — Circuit Graph JSON carries none
(`modules/evaluation/NOTES.md` §1.2). If D's diff report needs to run
end-to-end for real before that's resolved, `hpwl` and
`legality_violations` are the two metrics that work today; treat
`congestion_overflow` as blocked, not as something to approximate.

**`compare_methods`** (`modules/evaluation/stats.py`) is available for
D's own reporting needs too (e.g. constraint-parser precision/recall
comparisons across prompt-iteration rounds, Section 1.9.7) — it's a
general utility, not evaluation-pipeline-specific.

**Also relevant to D's beginner-path work:** `modules/evaluation/def_io.py`
writes the "Final DEF export" (Section 1.2 step 10) from any
`CircuitGraph`/`PlacementJSON` pair — usable as-is once D's beginner flow
produces a real placement to export, no dependency on D's own code.

---

## Quick-start checklist for Person D

1. Read `TECHNICAL.md` Section 4.D and `INSTRUCTIONS.md` Section 1.1's
   Person D bullet — the actual task list hasn't changed.
2. Build `run_yosys_synthesis` against a **hand-written toy RTL file**
   (INSTRUCTIONS.md's own suggestion: a 2-gate AND/OR circuit), output
   validated against `shared/schemas/circuit_graph.py` — same mock-first
   pattern A/B/C all used. `shared/mocks/mock_circuit_graph.py` shows the
   exact shape a valid `CircuitGraph` needs.
3. Build `parse_constraint` against `shared/mocks/mock_placement.py`,
   output validated against `shared/schemas/constraint.py` — match
   `shared/mocks/mock_constraint.py`'s three examples' shape exactly, since
   that's what B's `freeze.py` is already tested against.
4. Build `generate_diff_report` against hand-constructed before/after
   `PlacementJSON` + `MetricsObject` pairs — no external tool or real data
   needed for this part (see Person C section above).
5. Start the ≥100-example labeled constraint test set (Section 4.D) early —
   it's pure human/LLM-prompt work, doesn't block on anything above.
6. Second-wave integration once your real parser exists: feed a real
   `ConstraintObject` into B's real `constraint_to_generation_inputs()`
   (`modules/generator/freeze.py`) — expected to need no changes on B's
   side if your object is Section 3.4-conformant, but untested until then.

**Do not** commit inside `modules/encoders/`, `modules/generator/`, or
`modules/evaluation/` without a PR from that person (`CONTRIBUTING.md`) —
if something in this handoff looks wrong or out of date, flag it in a PR
comment or to the human rather than editing another person's module
directly.
