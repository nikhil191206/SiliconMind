# FALLBACK.md: temporary demo fallback

> **Status:** TEMPORARY. Added 2026-09-24 for the live demo.
> **Delete it** once `backend/main.py` serves the real pipeline (see [§8 Removal](#8-removal-checklist)).
> Everything it added lives in two folders (`fallback/`, `frontend/src/fallback/`) plus
> **six lines** in four files tagged `FALLBACK-REMOVE`.

---

## 1. Why this exists, and why it is honest

Persons A, B and C finished their code (encoders, flow-matching generator,
verification/metrics), but **nothing is trained yet**. That is blocked on
real benchmark data (INSTRUCTIONS.md §2), and Person D's intake/LLM track
hasn't started. `backend/` is empty. We still need to demo the product today.

We had three options:

| Option | Verdict |
|---|---|
| Run the untrained generator | Output is noise. Showing it as "our model" would be misleading. |
| Fake numbers / pre-rendered screenshots | Violates the project's own rule (TECHNICAL.md §1.4, FRONTEND_SPEC.md §0): *every reported number must trace back to `shared/metrics/`*. |
| **Fallback server that runs our real code wherever it can, swaps in a clearly labelled classical algorithm where the model isn't ready, and never claims verification** | **Chosen.** |

The fallback is built to the same contracts as the real system, so the
frontend doesn't change when the real backend lands. It follows four rules:

1. **Never "verified".** Every placement's `verification_status` is
   `"unavailable: fallback mode (...)"`, so the frontend shows its
   non-dismissable "Placement not verified" banner, as the spec requires.
2. **`metrics` is always `null`.** The spec's Metrics panel correctly says
   *"Not available: placement unverified"*. The demo numbers live in a
   separate, clearly labelled **Fallback scores** panel.
3. **Every number comes from `shared/metrics`**: Person C's real
   `compute_hpwl` and `compute_legality_violations`, nothing reimplemented.
   Congestion needs OpenROAD, so it shows **"Not measured"**, never `0`.
4. **The model name never lies.** `generation_metadata.model_variant` reads
   `FALLBACK classical placer (not the trained flow-matching model)`, and the
   frontend shows a permanent amber **Fallback mode** strip with a
   "What's real?" breakdown.

---

## 2. What is real vs substituted today

| Pipeline stage (TECHNICAL.md) | Owner | Today in fallback mode | Real code used? |
|---|---|---|---|
| Schemas: CircuitGraph, PlacementJSON, Constraint, DiffReport | A/B/C/D | Every request and response is validated by the real Pydantic models in `shared/schemas/` | **Yes** |
| HPWL + macro legality scoring | C | `shared/metrics/hpwl.py`, `shared/metrics/legality.py` | **Yes** |
| Baseline for comparison | C | `modules/evaluation/packing.py::grid_pack`, scored by the same metrics | **Yes** |
| Freeze contract (§1.7) | B/D | Frozen macros are passed through bit-identical; `unexpected_moves` is **computed** from the two placements, not assumed | Same contract, fallback implementation |
| Netlist encoder (DE-HNN / DeepGate4) | A | **Not run** (untrained, and the fallback needs no torch) | No |
| Placement generator (flow matching) | B | **Substituted** by a classical placer (§4.1) | No |
| DREAMPlace legalization | C | **Not run** (not installed on Windows) | No |
| OpenROAD congestion | C | **Not run** (no tech LEF, see `modules/evaluation/NOTES.md` §1.2) | No |
| RTL drafting (LLM) | D | **Substituted** by keyword-picked Verilog templates | No |
| Synthesis (Yosys) | D | Uses real Yosys **if it is on PATH**; otherwise a clearly labelled **size estimate** (§4.3) | Only if installed |
| NL constraint parser (LLM) | D | **Substituted** by rule-based regexes (same patterns as the frontend's demo mock) | No |
| Diff report (§3.6) | D | Built with the real `DiffReport` schema; HPWL delta from `shared/metrics` | Schema yes |

The same list is served live at `GET /api/fallback/status`, and that endpoint
is what the frontend's "What's real?" panel renders.

---

## 3. Running it for the demo

Needs Python with `fastapi uvicorn numpy scipy pydantic pyyaml`. **No torch.**
On this laptop, Python 3.14 already has everything installed.

**Terminal 1: fallback backend** (from the repo root)

```powershell
cd "C:\Users\Ragini Pawar\OneDrive\Desktop\EDI"
py -3.14 -m pip install -r fallback\requirements.txt   # first time only
py -3.14 -m uvicorn fallback.server:app --port 8000
```

**Terminal 2: frontend**

```powershell
cd "C:\Users\Ragini Pawar\OneDrive\Desktop\EDI\frontend"
npm run dev
```

**Open:** <http://localhost:5173/app?backend=live>

`?backend=live` switches off the in-browser Demo mode, which the browser
otherwise remembers. You can also flip it in **Settings → Demo mode**. You
should see the header badge say **Live backend** and the amber **Fallback
mode** strip.

**One-click links for the presentation:**

| Link | Shows |
|---|---|
| `/app?backend=live&persona=beginner` | Beginner path: describe → drafted RTL → synthesize → place |
| `/app?backend=live&persona=expert&sample=small` | Lands directly on a placed 3k-cell design |
| `/app?backend=live&persona=expert&sample=ibm01` | 12.7k nodes (ibm01's size), placed in ~2 s |

**Sanity check before presenting:**

```powershell
py -3.14 -m pytest fallback -q      # 9 tests, ~3 s
curl http://localhost:8000/api/fallback/status
```

### Plan B (if Python breaks on stage)

The frontend still has its **in-browser Demo mode** (purple strip, no server
at all). Open <http://localhost:5173/app?backend=demo&sample=small>. That
mode is also loudly labelled as mock output.

---

## 4. What the fallback actually does

### 4.1 Placement (`fallback/placer.py`), standing in for Person B's generator

A textbook, CPU-only, deterministic-per-seed placer:

1. **Macros:** a greedy floorplan over a candidate grid (48², then 96² if
   crowded). Each macro takes the cheapest candidate that doesn't overlap an
   already-placed macro (plus a small halo). The cost has four parts:
   distance to the die edge (macros go to the periphery), weighted distance
   to connected macros already placed, an optional edit directive, and seeded
   jitter so different seeds explore.
2. **Standard cells, global placement:** a quadratic-style wirelength pull
   (Jacobi averaging of net centroids, with macros as anchors), alternated
   with **capacity-aware recursive-bisection spreading**. Cells are split in
   proportion to the free (non-macro) area of each half, so they fill the die
   evenly around macros while keeping their connectivity-driven relative
   order.
3. **Standard cells, legalization:** Tetris-style row legalization into free
   row segments (rows minus macros minus fixed cells). By construction, no
   cell overlaps another cell or a macro, and nothing leaves the die. The
   tests check this independently.

Measured on this laptop (scored by `shared/metrics`):

| Design | Nodes | Place time | HPWL fallback | HPWL `grid_pack` | Macro violations |
|---|---|---|---|---|---|
| synthetic_small | 3,012 | ~0.4 s | 31,835 | 167,543 | 0 |
| synthetic_medium | 8,020 | ~0.8 s | 100,822 | 558,783 | 0 |
| synthetic_ibm01_scale | 12,752 | ~1.6 s | 178,619 | 1,033,117 | 0 |

These numbers compare **a classical heuristic against a naive packer**.
They are **not** results for our model and must not be presented as such.

### 4.2 Editing (`fallback/edit.py`), standing in for Person D's parser + Person B's regeneration

* **Parser:** regexes recognise `move macro 3 away from macro 0`,
  `move macros 2, 5 to the left edge`, `move m1 toward m7`,
  `keep m4 out of the center`, `... not next to ...`. These map to
  `MOVE_AWAY_FROM`, `MOVE_TOWARD`, `PREFER_REGION`, `FORBID_REGION` and
  `FORBID_ADJACENT` `ConstraintObject`s.
* **Clarification rule kept:** `UNCLEAR` or confidence < 0.6 (e.g. *"make it
  better"*) returns `requires_clarification: true` **and the placer is not
  called**, exactly as TECHNICAL.md §3.4 requires.
* **Freeze:** `frozen_node_ids` = every macro not being edited. They are
  handed to the placer as fixed entries and come back bit-identical. Only
  the edited macros move, plus the standard cells under their new
  footprint, which get re-legalized to the nearest free spot. All other
  cells stay put.
* **Diff report:** `moved_nodes` and `unexpected_moves` are computed by
  comparing the two placements. `hpwl_delta` comes from `shared/metrics`.
  `congestion_delta` is `0.0` only because the schema requires a float. The
  Fallback scores panel states that congestion is not measured.

### 4.3 Intake (`fallback/rtl.py`), standing in for Person D

* **Draft RTL:** a keyword picks one of four real, synthesizable templates:
  `cache|cpu|processor|soc` → a 2-way cache with 4 memories (4 macros),
  `fifo|queue|buffer` → a FIFO, `alu|adder` → an ALU, otherwise a counter.
  The header comment says it's a fallback template, not LLM output.
* **Synthesize**, in order:
  1. Yosys JSON upload → converted to a CircuitGraph (real cells, real nets).
  2. CircuitGraph JSON upload → schema-validated and accepted.
  3. RTL + `yosys` on PATH → real Yosys run, then the same converter.
  4. RTL without Yosys → a **size estimate**. Memories become macros sized
     by bit count; registers and operators become a cell count; the wiring is
     a synthetic clustered netlist. The status panel says
     *"size ESTIMATE from RTL, Yosys not installed"*.
* Bad RTL returns HTTP 422 with a specific `detail`, which the frontend shows
  verbatim.

### 4.4 Endpoints (`fallback/server.py`)

| Endpoint | Same as the spec? | Notes |
|---|---|---|
| `POST /api/intake/draft-rtl` | yes | `{ rtl_code }` |
| `POST /api/intake/synthesize` | yes | returns a bare CircuitGraph |
| `POST /api/placement/generate` | yes, **+ `fallback_report`** | `metrics: null`, status `unavailable: ...` |
| `POST /api/placement/edit` | yes, **+ `fallback_report`** | includes `before` scores |
| `GET /api/fallback/status` | fallback only | what's real / substituted / not run |
| `GET /api/fallback/samples[/{id}]` | fallback only | toy (exact `shared/mocks` fixture), small, medium, ibm01-scale (synthetic) |

`fallback_report` is an **extra** field. The spec's response types were not
changed. The frontend captures the field in a `WeakMap` keyed by the placement
object, so when the real backend doesn't send it, nothing renders.

---

## 5. What to say in the demo (suggested)

* "The encoder, generator and verification modules are implemented and
  unit-tested (27 + 22 + 52 tests). Training is blocked on benchmark data,
  so today a **classical placer stands in** for the generator. The amber
  strip says so on every screen."
* "Everything else you see is our real contract. Our real schemas validate
  each request, **Person C's real metrics code scores** every placement, and
  the UI refuses to call anything 'verified' because DREAMPlace didn't run."
* "Watch the edit loop: frozen macros are guaranteed not to move, and the
  diff report *proves* it (`unexpected_moves = []`). A vague instruction
  gets a clarification question, not a guess."
* Don't say the numbers are our model's results. Don't compare against
  published placers. Point at "What's real?" if anyone asks.

---

## 6. Files added or changed

**New, backend** (`fallback/`, delete the whole folder):

| File | Purpose |
|---|---|
| `fallback/__init__.py` | Package marker + version |
| `fallback/server.py` | FastAPI app, the spec endpoints plus `/api/fallback/*` |
| `fallback/placer.py` | Classical placer (macros → global → row legalization) |
| `fallback/edit.py` | Rule-based constraint parser, freeze-aware edit, diff report |
| `fallback/rtl.py` | RTL templates, Yosys runner, Yosys JSON converter, size estimator |
| `fallback/samples.py` | Sample CircuitGraphs |
| `fallback/test_fallback.py` | 9 pytest checks of the honesty guarantees |
| `fallback/requirements.txt` | Server deps (no torch) |

**New, frontend** (`frontend/src/fallback/`, delete the whole folder):

| File | Purpose |
|---|---|
| `fallbackApi.ts` | Status/sample fetchers, `withFallbackCapture`, `WeakMap` of reports |
| `useFallbackStatus.ts` | Hook: is the live backend the fallback server? |
| `FallbackBanner.tsx` | Amber "Fallback mode" strip + "What's real?" |
| `FallbackScores.tsx` | "Fallback scores" panel (unverified badge, baseline comparison) |
| `FallbackSamples.tsx` | Sample buttons on the intake screen (+ `?sample=` autoload) |
| `fallback.css` | Styles for the above |

**Changed** (6 lines, each tagged `FALLBACK-REMOVE`):

| File | Line(s) |
|---|---|
| `frontend/src/state/SessionProvider.tsx` | import; `withFallbackCapture(...)` around `createHttpApi(...)`; `isFallbackActive()` skip in `ensureApiKey` |
| `frontend/src/pages/WorkspacePage.tsx` | import; `<FallbackBanner />` |
| `frontend/src/components/workspace/review/ReviewView.tsx` | import; `<FallbackScores />` |
| `frontend/src/components/workspace/intake/IntakeView.tsx` | import; `<FallbackSamples />` |

**Kept permanently (not fallback):** `?backend=live|demo` in
`frontend/src/state/useDemoUrlHooks.ts`, a general switch that's also
useful with the real backend.

---

## 7. Swapping in real parts one at a time

The fallback doesn't have to go all at once. When `backend/main.py` exists,
simply **run it on :8000 instead** and the frontend uses it with zero
changes. The fallback UI disappears automatically, because the real backend
has no `/api/fallback/status`.

Until then, individual pieces can be upgraded inside the fallback. Each
needs a line changed in `fallback/server.py`:

| When this lands | Replace in the fallback |
|---|---|
| Trained generator (B) + encoder (A) | `place(...)` → `PlacementGenerator.generate(encoder.encode(graph), graph, seed=seed)`, and set `model_variant` from B |
| DREAMPlace on Linux/WSL (C) | score via `legalize_and_score(placement, graph)` and return its `MetricsObject` as `metrics` with `verification_status: "verified"`, then drop `fallback_report` |
| D's `run_yosys_synthesis` | `synthesize(...)` in `synth()` |
| D's `parse_constraint` + B's `constraint_to_generation_inputs` | `parse_instruction` / `apply_edit` in `edit()` |

Once all four rows are done, there's nothing left in the fallback. Delete it.

---

## 8. Removal checklist

```powershell
cd "C:\Users\Ragini Pawar\OneDrive\Desktop\EDI"

# 1. delete the two fallback folders and this file
Remove-Item -Recurse -Force fallback, frontend\src\fallback
Remove-Item FALLBACK.md

# 2. find the six tagged lines
git grep -n "FALLBACK-REMOVE" -- frontend/src
```

Then, for each hit:

* **Import lines:** delete the whole line.
* `SessionProvider.tsx`: change
  `withFallbackCapture(createHttpApi(state.apiBaseUrl))` back to
  `createHttpApi(state.apiBaseUrl)`, and delete the `isFallbackActive()` line.
* `WorkspacePage.tsx`, `ReviewView.tsx`, `IntakeView.tsx`: delete the
  `<Fallback... />` line.

Verify:

```powershell
git grep -n -e "FALLBACK-REMOVE" -e "src/fallback" -e "/fallback/" -- frontend/src   # expect: no hits
cd frontend; npm run build                                                           # must pass tsc + vite build
```

---

## 9. Known limitations (say so if asked)

* Congestion is never measured in fallback mode (needs OpenROAD + a tech LEF).
* Macro orientation is always `N`. The placer doesn't rotate macros.
* The RTL size estimate without Yosys is an approximation of cell count, and
  its wiring is synthetic.
* The edit parser only understands the phrasings in §4.2. Anything else
  asks for clarification, which is the correct behaviour.
* The 120k-node stress sample is not offered (it would take ~20 s and the
  macro-pair legality check is O(M²)). The in-browser Demo mode still has it
  for renderer testing.
* The fallback runs synchronously, like the spec'd endpoints. The frontend's
  indeterminate progress (no fake percentages) applies unchanged.
