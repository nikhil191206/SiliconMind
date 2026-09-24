# SiliconMind Frontend Specification

**Status:** Product/UX specification for the shared frontend (Section 1.8 of TECHNICAL.md: "Visualization... built once backend is stable, shared work"). This document defines *what* the frontend must do and *how* it must behave — not visual design (colors/typography/pixel layout), which is a separate design pass. Every data field referenced here is taken verbatim from the real, already-implemented schemas in `shared/schemas/` and the real endpoints in `backend/main.py` — nothing here invents a field that doesn't exist in the backend today. Anywhere the frontend needs something the backend doesn't yet provide, that gap is called out explicitly in Section 14 rather than silently assumed.

---

## 0. Purpose and Non-Negotiable Constraints

The frontend is the only thing a human ever looks at. Every architectural decision below exists to protect one rule, stated in TECHNICAL.md Section 1.8:

> "Visualization reads only the verified Placement JSON and renders it geometrically. No generative image model is used in visualization under any circumstance, no toggle, no exception."

Three consequences follow directly, and they override convenience or polish anywhere they conflict:

1. **The UI must never present an unverified placement as if it were final.** `verification_status` (returned by every placement-producing endpoint) is not a debug field — it is load-bearing. If it is anything other than `"verified"`, the UI must visibly say so, every time, with no way to dismiss it permanently.
2. **The UI must never fabricate progress, metrics, or geometry.** No animated "estimated progress" bars invented client-side, no placeholder chip renders before real data arrives, no smoothing/interpolating metrics that weren't actually computed. If the backend hasn't returned a number, the UI shows an honest empty/loading state, not a guess.
3. **`legality_violations` must be 0 in anything labeled verified, and `unexpected_moves` must be empty in any diff.** Per TECHNICAL.md Section 1.4 and the `DiffReport` schema's own docstring, a non-zero value here is not "a slightly worse result" — it's a bug in an upstream module. The frontend must treat this case as an error state (loud, red, unmissable), never as normal output with a bad number in it.

---

## 1. Personas

The system explicitly serves two different people (TECHNICAL.md Section 1.2, step 1: "direct upload, or beginner description"). The frontend is one codebase with a **persona switch**, not two separate apps — both personas hit the same backend endpoints, the difference is entirely in what's shown, hidden, and defaulted.

### 1.1 Beginner
Has a design idea in plain English, no synthesizable RTL, no netlist. Does not know what HPWL, congestion overflow, or a hyperedge is. Needs the system to draft RTL for them (`/api/intake/draft-rtl`), synthesize it (`/api/intake/synthesize`), generate a placement, and explain results in plain language. Every technical term shown to this persona needs an inline plain-English gloss (tooltip or subtext), not just a label.

### 1.2 Expert
Already has a post-synthesis Verilog netlist or a LEF/DEF pair. Wants direct upload, full metrics, the ability to inspect the raw `CircuitGraph` / `PlacementJSON` / `ConstraintObject` payloads, seed control, and comparison against the DREAMPlace and RL baselines (TECHNICAL.md Section 1.9). Does not want hand-holding or gloss text getting in the way.

### 1.3 The switch itself
A visible, persistent toggle (not buried in settings) — "Beginner" / "Expert" — in the global header. Switching does not lose state: if a beginner drafts RTL, switches to Expert, they should see the same session's `CircuitGraph`, not have to start over. This means persona is a **view-layer setting** over one shared session/data model (Section 12), never a separate data path.

---

## 2. Information Architecture

Four top-level areas, visited roughly in this order for a first-time flow, but each independently revisitable once a `CircuitGraph` exists in session:

1. **Intake** (Section 3) — get a netlist into the system.
2. **Generate** (Section 4) — turn that netlist into a placement.
3. **Review** (Section 5) — look at the placement, its metrics, verification status.
4. **Refine** (Section 6) — issue natural-language edits, see diffs, iterate.

These are not necessarily four separate routes/pages — Review and Refine in particular should live on the same screen (you look at a placement and talk to it in the same view) — but they are four distinct *states* the frontend must track and render distinctly.

---

## 3. Section A — Intake / Upload

### 3.1 Expert path: direct upload

Inputs accepted, matching `SynthesizeRTLRequest` and the parser boundary described in TECHNICAL.md Section 1.3 ("structural Verilog netlist... OR LEF/DEF pair"):

- **Verilog file** (`.v`) — post-synthesis structural netlist. Maps to `rtl_code` (if pasted/read into a string client-side) or `rtl_path` on `SynthesizeRTLRequest`.
- **Pre-synthesized Yosys JSON** (`.json`) — maps to `yosys_json_data`. This is the fast path: skips the synthesis step entirely, calls straight into `parse_yosys_json`.
- **LEF/DEF pair** — the spec and parsers (`modules/intake/parsers/lefdef_parser.py`) support this at the parser layer, but `backend/main.py`'s `/api/intake/synthesize` endpoint today only wires up the RTL/Yosys path, not LEF/DEF upload. **This is a real backend gap** (Section 14.1) — the UI should have the upload affordance and the file-type detection ready, but must show "not yet available via this endpoint" rather than silently accepting a LEF/DEF pair and failing deep in a stack trace.

UI requirements:
- Drag-and-drop zone + explicit file picker, accepting `.v`, `.json` (LEF/DEF `.lef`/`.def` shown but disabled with the gap explanation above, until the backend endpoint exists).
- A required **design name** field — every downstream schema (`CircuitGraph.design_name`, `PlacementJSON.design_name`) is keyed by this string; it cannot default silently to something like `"untitled"` without the user seeing that choice, since it becomes part of permanent output artifacts (DEF export, W&B run names, etc. elsewhere in the system).
- Client-side pre-validation before the network call: is it plausibly Verilog/JSON text (not a binary or a placement file uploaded by mistake)? This is a UX nicety, not a substitute for backend validation — the backend's own `422`/`400` responses are still the source of truth for "was this actually valid," and their messages must be surfaced verbatim, not replaced with a generic "upload failed."

### 3.2 Beginner path: natural-language description → drafted RTL

1. A single large text area: "Describe what you want to build." Optional `template` dropdown (maps to `DraftRTLRequest.template`) if the backend exposes a fixed template list — if it doesn't yet, omit the dropdown rather than hardcoding fake template names client-side.
2. Submit calls `/api/intake/draft-rtl`. Response is `{ rtl_code: string }`.
3. **The drafted RTL is shown to the user before synthesis, not auto-submitted.** A beginner should never watch a design get built from RTL they never saw, even if they can't read it fluently — show it in a read-only, syntax-highlighted code block with a one-line plain-English disclaimer ("This code was generated by an AI model from your description — review it, or an expert on your team can, before continuing"). This matters because `synthesize_from_description` is LLM output; presenting it as ground truth without a visible review step would be exactly the kind of silent-trust failure this project's own conventions (no unexplained fallbacks) exist to prevent.
4. Two actions from here: **"Looks good, synthesize"** (proceeds to `/api/intake/synthesize` with `rtl_code` set to the drafted text) or **"Edit"** (makes the code block editable in place — this is the moment a beginner becomes a de facto expert-path user for this one file, and that's fine, the same textbox feeds the same endpoint).

### 3.3 API key handling (BYOK)

Several endpoints accept an optional `api_key` (`DraftRTLRequest.api_key`, `EditPlacementRequest.api_key`) — this project uses bring-your-own-key for LLM calls (Groq/OpenAI-compatible, per `shared/llm_client.py`), it does not embed a shared project key in the frontend bundle. Required UI:

- A **Settings** panel (accessible from the global header, not nested three menus deep — this is needed before *any* LLM-touching action works) where the user pastes their own API key.
- The key is stored **only** in browser storage (e.g. `localStorage`), attached to requests, never logged to any analytics/console output, and the input field is masked like a password field with a show/hide toggle.
- If an LLM-touching action is attempted with no key set, the UI intercepts client-side and opens the Settings panel with an explanation, rather than firing the request and letting the backend's `LLMConfigurationError` → `400` be the first the user hears of it. (The backend error must still be handled and shown if it somehow occurs anyway — e.g. a saved key that's since been revoked.)

### 3.4 Intake states

| State | Trigger | UI |
|---|---|---|
| Idle | initial | Upload zone / description box, empty |
| Validating | file selected, pre-checks running | Spinner over the drop zone only |
| Submitting | request in flight | Full-section disabled, spinner + "Drafting RTL..." / "Synthesizing..." label — labels must match which endpoint is actually in flight, not a generic "Loading" |
| Drafted (beginner only) | `/draft-rtl` succeeded | Read-only RTL preview + Edit/Synthesize actions (3.2.4) |
| Error | any 4xx/5xx | Inline error banner showing the backend's actual `detail` message; a "Try again" action that returns to Idle without losing the user's typed description/selected file |
| Success | `CircuitGraph` received | Transitions to Generate (Section 4) automatically, but the `CircuitGraph` remains inspectable (Expert: raw JSON viewer; both personas: a plain summary — "142 macros, 8,203 standard cells, 3,401 nets") |

---

## 4. Section B — Processing / Generation Pipeline

This is the highest-risk section for accidentally violating the "no fabricated progress" rule (Section 0.2), because the natural UI instinct is a progress bar, and the backend's real pipeline (encode → generate → legalize, inside a single synchronous `/api/placement/generate` call) gives the frontend **no real intermediate progress events today**.

### 4.1 What actually happens, in order (per `backend/main.py`)

1. `DEHNNEncoder().encode(graph)` — netlist → conditioning embeddings.
2. `PlacementGenerator().generate(...)` — flow-matching generation.
3. `_legalize(placement, graph)` — best-effort call into DREAMPlace/OpenROAD; returns one of `"verified"` or `"unavailable: <reason>"`.

All three happen inside one HTTP request/response cycle. There is no server-sent-events/WebSocket channel and no job-polling endpoint in the current backend (Section 14.2 — flagged as a real gap, not assumed away).

### 4.2 Honest loading UI (works today, without backend changes)

Given the constraint above, the loading state must be **honest about its own resolution**: a single indeterminate progress indicator (spinner or indeterminate bar — never a determinate percentage the frontend has no basis for) with a static label: *"Generating placement — this can take from seconds to several minutes depending on design size."* This label itself is calibrated to something real: the generator's own measured numbers (12,752 nodes ≈ 2.5s, 70,000 nodes ≈ 71s–96s, per `modules/generator/network.py`'s docstring) — the frontend should use the `CircuitGraph`'s known node count to pick a realistic qualitative estimate ("a few seconds" / "under two minutes" / "several minutes — this is a large design") rather than a fake numeric ETA.

- **Timeout handling:** the frontend must have a client-side request timeout well above the largest realistic case (the generator's known scalability ceiling means some designs may take a very long time or, at the extreme documented in `modules/generator/NOTES.md`, may not currently complete at all on constrained hardware) — and when a timeout is hit, the message must say exactly that ("This design may be too large for the current backend to place in a reasonable time — see known scalability limits") rather than a generic "network error."
- **Cancellation:** a visible Cancel action during generation. Since the backend call is synchronous, "cancel" client-side means aborting the fetch/request — the UI must not pretend this stopped server-side computation (it likely hasn't) and should say so if the user re-submits immediately after ("a previous request may still be running server-side").

### 4.3 If/when the backend gains real progress events (Section 14.2)

Design the loading component now with a pluggable progress source so this isn't a rewrite later: a `stage: "parsing" | "encoding" | "generating" | "legalizing" | "done"` enum drives a real 4-step stepper UI, filled in incrementally as each stage actually reports completion — never interpolated between known points.

### 4.4 Result of processing

Every generate/edit call resolves to a `verification_status` string. This single field is the gate for everything in Section 5:

- `"verified"` → proceed to Review with full confidence framing.
- `"unavailable: <reason>"` → proceed to Review but with a **persistent, non-dismissible banner**: "Placement not verified — DREAMPlace/OpenROAD unavailable ({reason}). Coordinates shown are unverified and may overlap or be illegal." This is not an error state (the request succeeded, per `_legalize`'s own docstring design), but it must never look identical to a verified result.

---

## 5. Section C — Design Display / Preview (the Visualizer)

### 5.1 Rendering contract

Reads **only** `PlacementJSON` (`design_name`, `placements: [{node_id, x, y, orientation}]`, `generation_metadata: {model_variant, seed, is_legalized}`) plus the originating `CircuitGraph` for node geometry (`width`, `height`, `type`) and the `die` bounding box. Per TECHNICAL.md 1.8, no generative image model, no stock/decorative chip photography, ever — geometry is drawn as geometry (rectangles), full stop.

### 5.2 Canvas / rendering technology

At small-to-medium scale (tens of thousands of nodes) an SVG or Canvas2D approach is fine. But this project's own real measurements (generator NOTES.md) show designs up to **925,010 nodes** (`mgc_superblue11_a`) in the actual training corpus — a naive one-DOM-node-per-macro SVG approach will not render that responsively. Required approach:

- **Canvas2D or WebGL (instanced rendering)**, not per-node SVG/DOM elements, for anything beyond ~5,000 nodes — pick the threshold empirically once real designs are on screen, don't guess a number and ship it unverified.
- **Level-of-detail:** at high zoom-out, standard cells (the vast majority of nodes on any real design) can render as density-shaded regions rather than individually outlined rectangles; only macros (`NodeType.MACRO`) need always-individual rendering, since there are orders of magnitude fewer of them and they're the ones a user actually reasons about and edits.
- **Viewport culling:** only nodes intersecting the current visible canvas region are drawn per frame, recomputed on pan/zoom.

### 5.3 Visual encoding

- Die boundary: drawn from `CircuitGraph.die.{width,height}`, always visible, always the outermost reference frame — canvas scale is derived from it, never guessed from placement bounds (a placement could theoretically have legality violations pushing nodes outside the die, and that must be visible as "outside the drawn die boundary," not hidden by auto-fitting the canvas to whatever coordinates came back).
- `NodeType.MACRO` vs `NodeType.STD_CELL`: visually distinct (macros larger, outlined, labeled on hover/click; standard cells smaller, can be unlabeled/aggregated per 5.2).
- `orientation` (`N/S/E/W/FN/FS/FE/FW`): reflected in the actual drawn rectangle orientation (rotation/mirroring), not just shown as a text badge — this is real placement information a mis-render would misrepresent.
- Nets (`CircuitHyperedge`): off by default at scale (rendering hundreds of thousands of hyperedges is both visually useless and a real performance cost) — an explicit, opt-in "Show nets" toggle, ideally scoped to "nets touching the currently selected node(s)" rather than "all nets," since that's both more useful and far cheaper to draw.

### 5.4 Interaction

- Pan (drag) and zoom (scroll/pinch), standard.
- Click/tap a macro → selection, shows a detail panel: `node_id`, type, width/height, pin_count, current `(x, y)`, orientation.
- Multi-select (shift-click or drag-box) — feeds directly into the edit flow (Section 6): "selected macros" is exactly the kind of thing a user then says "move these away from the edge" about, and the UI should let a NL instruction reference a selection rather than requiring the user to type exact macro names every time (this is a frontend-side convenience — it still ultimately produces a plain-English `source_request` string for `/api/placement/edit`, since that endpoint takes free text, not a structured selection).

### 5.5 Metrics panel

Always visible alongside the canvas once any placement is loaded, sourced directly from `MetricsObject`:

| Field | Label shown | Beginner gloss |
|---|---|---|
| `hpwl` | Total Wirelength (HPWL) | "Lower is better — roughly how much wire the chip needs" |
| `congestion_overflow` | Routing Congestion | "Lower is better — how crowded the wiring gets in tight areas" |
| `legality_violations` | Legality Violations | "Must be 0 in a finished design — overlapping or out-of-bounds components" |
| `runtime_seconds` | Generation Time | (no gloss needed) |

If `metrics` is `null` (which it is whenever `verification_status != "verified"`, per `_legalize`'s contract), the panel shows **"Not available — placement unverified"** in place of numbers, never a `0` or a blank that could be misread as "zero congestion."

**Hard rule enforced in the UI layer:** if `metrics.legality_violations > 0` is ever received alongside `verification_status == "verified"`, this is a contradiction of the system's own invariant (Section 1.4: "must be zero after legalization... non-zero legality violations are an internal error, not a reportable result"). The UI must render this as a distinct, red, "Internal inconsistency detected" error state — not as a normal metrics display with a nonzero number in it — and should make this state easy to screenshot/report (e.g. a "Copy diagnostic info" button dumping the raw JSON) since it indicates an upstream bug.

---

## 6. Section D — Refine / Natural-Language Edit Loop

### 6.1 The instruction box

A persistent text input near the visualizer (not a separate page — editing and looking are one motion): "Tell it what to change." Submits `instruction` (free text) to `/api/placement/edit` along with the current `graph` and `previous_placement`.

### 6.2 Clarification flow

`EditPlacementResponse.requires_clarification` is a first-class UI state, not an error:

- If `true`: show `clarification_message` directly (it's already a formatted, specific string per the backend's construction — "Instruction '...' was ambiguous or low confidence (0.42). Please specify target macro names or direction explicitly..."). The instruction box stays populated with the user's original text so they can amend it rather than retype from scratch.
- The returned `constraint` (even when clarification is required) is available for Expert-mode inspection — showing *why* it was low-confidence (its `confidence` float, `constraint_type` — often `UNCLEAR`) helps a technical user understand what to say differently. Beginners don't need this raw object; the plain message is enough for them.

### 6.3 Successful edit — showing the diff

On `requires_clarification: false`, the response carries `new_placement`, `metrics_before`/`metrics_after`, `verification_status`, `diff_report`, and `diff_summary`:

- **`diff_summary`** (a pre-formatted string from `format_diff_summary`) is the primary thing beginners see — a plain-language one-liner.
- **Before/after toggle** on the canvas itself: a slider or two-state switch that re-renders the same view with `previous_placement` vs `new_placement`, so the user sees the actual geometric change, not just reads about it.
- **`diff_report.moved_nodes`** (`[{node_id, delta_x, delta_y}]`): highlight these specific macros on the canvas (e.g. an outline or motion-trail arrow from old to new position) — this is the concrete, inspectable evidence behind the summary string, and Expert users especially should be able to get from "the summary says 3 macros moved" to "here exactly are those 3 macros" in one click.
- **`diff_report.unexpected_moves`**: per the schema's own docstring ("must be empty; non-empty means a bug in B's freeze enforcement, not a reportable result"), if this list is ever non-empty the UI must show the same class of loud "internal inconsistency" error banner described in Section 5.5, not fold these into `moved_nodes` as if they were expected.
- **Metrics delta**: show `metrics_before` → `metrics_after` as a before/after pair with a visible delta (+/− and color), for each of the four `MetricsObject` fields, when both are available (i.e. `verification_status` indicates both sides were actually verified — see the backend's `before_status`/`after_status` combination logic, which the frontend should surface directly if they differ, e.g. "before: verified; after: unavailable: ...").

### 6.4 Edit history

A chronological list (sidebar or collapsible panel) of every instruction issued this session, each entry showing: the instruction text, its `diff_summary`, timestamp, and a "View this state" action that lets the user jump the canvas back to any prior `PlacementJSON` in the session's history (client-side state, Section 12 — this needs the frontend to retain every intermediate placement, not just the latest one, precisely so this history/undo experience is possible without re-calling the backend).

### 6.5 Undo

Since every edit's `previous_placement` is already known client-side (it's what was sent in the request), "undo" is simply: set current placement back to the previous one in the client-side history stack, re-render. No backend call is needed for undo itself — but the UI should make clear that undo is a *view* operation restoring a prior state, and if the user then issues a new instruction from an undone state, that state (not whatever was "ahead" of it) becomes `previous_placement` for the new request — a normal branching-history model, not a strict linear one.

---

## 7. Section E — Expert-Only Surfaces

These exist only in Expert persona (Section 1.2), hidden entirely (not just collapsed) from Beginner:

1. **Raw JSON inspector** for the current `CircuitGraph`, `PlacementJSON`, and (after an edit) `ConstraintObject` / `DiffReport` — a formatted, syntax-highlighted, collapsible tree view, with a copy-to-clipboard action per object. This is the direct debugging surface for someone who understands the schemas.
2. **Seed control**: both `/api/placement/generate` and `/api/placement/edit` accept a `seed` (defaulting to `0`). Expose an editable seed field so an expert can regenerate deterministically or explore variation — with the current seed value always visible next to any rendered placement (`generation_metadata.seed`), so it's traceable which seed produced what's on screen.
3. **`model_variant`** (from `generation_metadata`): displayed read-only — which generator variant produced this placement. If the backend ever exposes a choice of variant (flow-matching vs diffusion, per TECHNICAL.md Section 1.5's "diffusion as fallback"), this becomes a selector; today it's informational only (Section 14.3).
4. **Baseline comparison tab**: TECHNICAL.md Section 1.9 requires every result to be reported against DREAMPlace and the RL baseline. If/when the backend exposes baseline run results (currently a training/evaluation-script concern per `modules/evaluation/baselines.py`, `experiments/train_rl_baseline.py` — not yet a live API endpoint, Section 14.4), the Expert view should have a dedicated comparison table: this system's metrics vs. DREAMPlace vs. RL baseline, side by side, for the same design. Until that endpoint exists, this tab should say plainly "Baseline comparison requires backend support not yet available" rather than being silently omitted (an expert user who knows this project's own evaluation protocol will look for it).

---

## 8. Global Layout

- **Header** (persistent across all states): SiliconMind wordmark, current `design_name` (once one exists), Beginner/Expert toggle, Settings (API key) access.
- **Primary workspace**: Intake (Section 3) *or* the combined Review+Refine canvas (Sections 5–6), depending on pipeline state — these are mutually exclusive views of one session, not separate tabs a user must remember to navigate between manually. Automatic transition on state completion (Section 3.4), with a manual "Start over / new design" action always available to return to Intake deliberately.
- **Persistent verification banner** (Section 4.4): rendered above the workspace, not inside it, so it can never be scrolled out of view or missed while a user is focused on the canvas.

---

## 9. Error and Empty States (exhaustive, mapped to real backend error paths)

| Backend condition | HTTP | Frontend treatment |
|---|---|---|
| `LLMConfigurationError` (no/invalid API key) | 400 | Intercepted pre-flight where possible (3.3); otherwise inline error directing to Settings |
| `YosysNotInstalledError` | 503 | "Synthesis unavailable — the backend's Yosys toolchain isn't installed" — an environment/deployment problem, framed as such, not "your file is invalid" |
| `YosysSynthesisError` | 422 | Show the backend's message verbatim — this is a real error in the user's RTL |
| `GenerationProducedInvalidCoordinatesError` | 500 | "Placement generation failed internally" + a report/copy-diagnostics action; this indicates a real generator bug (per the class's own name/purpose — a safety-net that still failed), not a user-fixable input problem |
| Generic exception during generate/edit | 500 | Show whatever `detail` the backend returned; never replace a specific backend message with a generic "Something went wrong" if a real message is available |
| `verification_status` starts with `"unavailable:"` | 200 (success) | **Not an error** — the persistent banner (Section 4.4), not a toast/error card |
| `requires_clarification: true` | 200 (success) | **Not an error** — the clarification flow (Section 6.2) |
| `legality_violations > 0` with `verification_status == "verified"` | 200 (success, contradictory) | Treated as an error regardless of HTTP status (Section 5.5) |
| `diff_report.unexpected_moves` non-empty | 200 (success, contradictory) | Treated as an error regardless of HTTP status (Section 6.3) |

Empty states: an Intake screen with nothing uploaded yet is not "loading" or "error" — it's a clear, inviting call to action distinguishing the two entry paths (Section 3.1 vs 3.2), not a blank page.

---

## 10. Accessibility

- All status communicated by color (verification banner, error states, metric deltas) must **also** be communicated by text/icon — color alone is not an acceptable channel for "this placement is unverified" or "legality violations detected," given how load-bearing those signals are (Section 0).
- Canvas interactions (Section 5.4) need a keyboard-accessible equivalent for node selection/inspection (e.g. a searchable/filterable list of macros by `node_id`, alongside the visual canvas) — a purely mouse-driven canvas excludes keyboard-only and screen-reader users from a core feature, not a peripheral one.
- The RTL preview (3.2.3) and raw JSON inspectors (Section 7.1) must use a monospace font and proper code-block semantics (`<pre><code>` or equivalent), not styled `<div>`s, for assistive-tech compatibility.

---

## 11. Performance Targets (tied to real, measured numbers — not aspirational guesses)

- Canvas must stay interactive (pan/zoom at ≥30fps) for the documented small/medium real designs (ibm01 at 12,752 nodes) without any special-casing.
- For designs in the 70,000–150,000 node range (the documented real ceiling zone for the *generator* on the target GPU — not directly a frontend concern, but the same node counts hit the *renderer*), the level-of-detail strategy (5.2) must keep initial render under a few seconds; if it can't, that's a real finding to document (per this project's own "measure, don't assume" convention throughout the codebase), not something to paper over with a lower target picked to look good.
- Network payload size: a `PlacementJSON` for a 925K-node design is a non-trivial JSON payload. The frontend should support streaming/chunked parsing or at minimum a clear "Loading large placement (N nodes)..." indicator scaled to payload size, rather than a UI that appears frozen during a multi-second JSON parse.

---

## 12. State Management / Data Model (frontend-side)

A single client-side session store, shape mirroring the backend contracts directly (no invented intermediate representation that could drift from the schemas):

```
Session {
  persona: "beginner" | "expert"
  apiKey: string | null                    // Section 3.3, never sent anywhere but the backend's own requests
  designName: string | null
  circuitGraph: CircuitGraph | null
  placementHistory: Array<{
    placement: PlacementJSON
    metrics: MetricsObject | null
    verificationStatus: string
    triggeringInstruction: string | null    // null for the initial /generate call
    constraint: ConstraintObject | null
    diffReport: DiffReport | null
    diffSummary: string | null
    timestamp: string
  }>
  currentIndex: number                      // pointer into placementHistory, for undo (6.5)
  pipelineState: "idle" | "intake" | "generating" | "review" | "editing" | "error"
}
```

Every field above traces to a real schema or a real endpoint response field named in Sections 3–7 — this table is the contract between whoever builds the components and whoever wires up the API calls, the same way `shared/schemas/` is the contract between the backend modules.

---

## 13. Component Inventory (concrete, buildable list)

| Component | Owns | Key props (schema-traced) |
|---|---|---|
| `PersonaToggle` | Section 1.3 | `persona`, `onChange` |
| `ApiKeySettings` | Section 3.3 | `apiKey`, `onSave` |
| `NetlistUploader` | Section 3.1 | `onSubmit(rtl_code \| rtl_path \| yosys_json_data, design_name)` |
| `RtlDraftAssistant` | Section 3.2 | `description`, `onDrafted(rtl_code)` |
| `RtlPreview` | Section 3.2.3 | `rtlCode`, `editable`, `onConfirm`, `onEdit` |
| `IntakeStatus` | Section 3.4 | `state`, `errorDetail` |
| `GenerationProgress` | Section 4.2–4.3 | `nodeCount`, `stage?` (optional, future) |
| `VerificationBanner` | Section 4.4, 9 | `verificationStatus` |
| `PlacementCanvas` | Section 5 | `circuitGraph`, `placement`, `showNets`, `selection`, `onSelect` |
| `MetricsPanel` | Section 5.5 | `metrics`, `persona` |
| `InternalErrorBanner` | Section 5.5, 6.3, 9 | `diagnosticPayload` |
| `EditInstructionBox` | Section 6.1 | `selection`, `onSubmit(instructionText)` |
| `ClarificationPrompt` | Section 6.2 | `clarificationMessage`, `constraint`, `persona` |
| `DiffViewer` | Section 6.3 | `before`, `after`, `diffReport`, `diffSummary` |
| `EditHistoryPanel` | Section 6.4 | `history`, `currentIndex`, `onJumpTo` |
| `ExpertInspector` | Section 7.1 | `circuitGraph`, `placement`, `constraint`, `diffReport` |
| `SeedControl` | Section 7.2 | `seed`, `onChange` |
| `BaselineComparisonTab` | Section 7.4 | *(gap — Section 14.4)* |

---

## 14. Known Gaps — Backend Support Not Yet Built

Stated explicitly rather than assumed away, per this project's standing rule against silent fallbacks:

1. **LEF/DEF direct upload has no live endpoint.** The parser exists (`modules/intake/parsers/lefdef_parser.py`), but `/api/intake/synthesize` doesn't accept LEF/DEF today. The frontend upload affordance can exist ahead of this, disabled with an honest message.
2. **No progress/streaming channel for generation.** `/api/placement/generate` and `/api/placement/edit` are single synchronous calls with no intermediate stage events. Section 4.2's honest indeterminate-loading design is the correct approach *until* this exists; Section 4.3 describes the upgrade path.
3. **`model_variant` is not currently selectable via the API** — it's reported in `generation_metadata`, but nothing in `GeneratePlacementRequest`/`EditPlacementRequest` lets a caller choose flow-matching vs. diffusion. Expert UI should show it read-only until a selector is meaningful.
4. **No live baseline-comparison endpoint.** DREAMPlace/RL-baseline results currently come out of training/evaluation scripts (`experiments/`, `modules/evaluation/baselines.py`), not a queryable API. Section 7.4's comparison tab is speculative until this exists.
5. **No job-status/history endpoint server-side** — the entire `placementHistory` in Section 12 lives only in the browser session today. Refreshing the page loses it. If persistent history across sessions/devices is wanted, that's a new backend surface (likely a `sessions`/`runs` store), not a frontend-only addition.

None of these gaps block starting frontend work — Sections 3–13 describe a complete, honest product against the *current* real backend. They're listed here so nobody building against this spec mistakes a documented gap for an oversight.
