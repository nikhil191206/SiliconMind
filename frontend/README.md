# SiliconMind Frontend

The web app for SiliconMind: a **landing site** (`/`) with a live 3D hero, and the
**workspace** (`/app`) that implements [`FRONTEND_SPEC.md`](../FRONTEND_SPEC.md)
end to end: intake → generate → review → refine.

Stack: **React 18 + TypeScript + Vite + Three.js** (as frozen in TECHNICAL.md §1.11),
plain CSS with design tokens. No UI framework, no chart/icon/highlighter
dependencies. Everything is in this folder and readable.

---

## Run it

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
npm run build        # typecheck + production build → dist/
npm run preview      # serve dist/ locally
npm run typecheck    # tsc only
```

`/api/*` is proxied to `http://localhost:8000` in dev (the FastAPI backend).
Override with `VITE_API_PROXY=http://host:port npm run dev`.

### Demo mode (on by default)

`backend/main.py` doesn't exist in the repo yet (spec §14), so the app ships an
**in-browser mock backend** that implements the same four endpoints. While it's
on, a purple **"Demo mode"** strip is always visible, and every placement's
`model_variant` says it's a mock. Nothing it produces can be mistaken for a real
result.

- Turn it off in **Settings → Backend connection** (or set `VITE_DEMO_MODE=false`
  in `.env`, see `.env.example`) once the backend is running.
- **Settings → Demo scenario** forces each §9 path: legalizer unavailable,
  "verified + violations", unexpected moves, generator crash (500), Yosys
  missing (503) / syntax error (422), rejected LLM key (400).

Demo-only URL shortcuts, handy for demos and QA (ignored in live mode):

| URL | Does |
|---|---|
| `/app?sample=toy` | loads `mock_toy_design` (identical to `shared/mocks`) and generates |
| `/app?sample=small` · `ibm01` · `stress` | 3k / 12,752 / 120k-node synthetic designs |
| `&persona=expert` | start in Expert |
| `&scenario=unverified` | force a demo scenario |
| `&edit=move%20macro%203%20toward%20the%20left%20edge` | run one NL edit after generating |

---

## Design

Modelled on [rerun.io](https://rerun.io) (with their permission), rebuilt from
its actual source:

- **Type:** the system sans stack (`-apple-system, Segoe UI, Roboto…`) for all
  text, and **JetBrains Mono** (self-hosted via `@fontsource-variable`) for code
  and labels. Heading scale, weights (450-550) and tracking are Rerun's tokens.
  See `src/styles/tokens.css`.
- **Theme:** white canvas, near-black ink, hairline neutral borders. Colour is
  reserved for the rainbow accent and for status. Status is always icon + text
  too, never colour alone (spec §10).
- **3D hero (`src/three/`):** Rerun's recipe of beveled slabs, an orthographic
  camera, RoomEnvironment lighting, staggered 90° turns with an expo ease, a
  rotating "rainbow light" shader, and a film-grain post pass. Our twist is
  that the top slab is a die, and its macros and cells dissolve into noise and
  then travel **straight lines** into a new legal layout, which is the flow-matching
  idea. It also has soft shadows, a pointer tilt, and layers that separate on
  scroll. It pauses off-screen, shows a still frame for `prefers-reduced-motion`,
  and falls back to CSS without WebGL.

---

## The rules this UI enforces (spec §0)

| Rule | Where |
|---|---|
| Unverified never looks final: a banner you can't dismiss, pinned above the workspace | `VerificationBanner.tsx`, `WorkspacePage.tsx` |
| `metrics: null` shows "Not available: placement unverified", never `0` | `MetricsPanel.tsx` |
| "verified" + `legality_violations > 0` is a loud internal error with copyable diagnostics | `state/selectors.ts` → `InternalErrorBanner.tsx` |
| Non-empty `unexpected_moves` gets the same treatment | same |
| No fake progress: indeterminate bar, a qualitative estimate from real node counts, honest Cancel | `GenerationProgress.tsx`, `lib/estimate.ts` |
| Backend `detail` shown verbatim, framed by error kind | `lib/api/errors.ts`, `ApiErrorBanner.tsx` |
| Drafted RTL is always reviewed before synthesis | `RtlPreview.tsx` |
| The canvas draws only PlacementJSON geometry, framed by the **die**, never auto-fit | `review/canvas/*` |

---

## Folder map

```
frontend/
├─ index.html · vite.config.ts · tsconfig.json · .env.example
├─ public/favicon.svg
└─ src/
   ├─ main.tsx · App.tsx               routes: / (landing), /app (workspace, lazy)
   ├─ styles/
   │  ├─ tokens.css                    design tokens (type scale, neutrals, rainbow, status)
   │  └─ base.css                      reset + buttons, inputs, badges, panels, code
   ├─ three/                           the 3D hero engine (framework-free Three.js)
   │  ├─ SlabScene.ts                  scene, animation timeline, shadows, grain, lifecycle
   │  ├─ shaders.ts                    rainbow light-sweep + film grain GLSL
   │  ├─ geometry.ts                   beveled slab + macro block geometry
   │  └─ layouts.ts                    legal die layouts + noise states for the flow animation
   ├─ pages/
   │  ├─ LandingPage.tsx
   │  └─ WorkspacePage.tsx (+ .css)    header, banners, view switch (spec §8)
   ├─ components/
   │  ├─ common/                       Icon, Logo, Modal, CopyButton, CodeBlock, JsonTree, useReveal
   │  ├─ landing/                      Hero, SceneCanvas, StatsStrip, PipelineSection (+Art),
   │  │                                FlowSection (interactive x_t explainer), VerificationSection,
   │  │                                RefineSection, BenchmarksSection, CtaSection, TiltCard, header/footer
   │  └─ workspace/
   │     ├─ WorkspaceHeader, PersonaToggle, SettingsModal (BYOK key, connection, demo scenario)
   │     ├─ VerificationBanner, InternalErrorBanner, ApiErrorBanner, DemoStrip, Gloss
   │     ├─ intake/     IntakeView, NetlistUploader, RtlDraftAssistant, RtlPreview,
   │     │              DesignNameField, IntakeStatus                        (spec §3)
   │     ├─ generate/   GenerateView, GraphSummary, GenerationProgress       (spec §4)
   │     ├─ review/     ReviewView, PlacementCanvas, CanvasToolbar, MetricsPanel,
   │     │              NodeDetailPanel, MacroList                           (spec §5)
   │     │   └─ canvas/ prepare.ts (typed arrays + spatial index), renderer.ts
   │     │              (LOD, culling, orientation, diff, nets), viewport.ts
   │     ├─ refine/     EditInstructionBox, ClarificationPrompt, DiffViewer,
   │     │              EditHistoryPanel                                     (spec §6)
   │     └─ expert/     ExpertInspector, SeedControl, BaselineComparisonTab  (spec §7)
   ├─ state/
   │  ├─ sessionTypes.ts               Session shape: spec §12, field for field
   │  ├─ sessionReducer.ts             every pipelineState transition
   │  ├─ SessionProvider.tsx           context + async actions (abort, errors, BYOK pre-flight)
   │  ├─ selectors.ts                  current/parent entry, invariant checks
   │  └─ useDemoUrlHooks.ts            demo-only URL shortcuts
   └─ lib/
      ├─ schemas.ts                    TS mirrors of shared/schemas/*.py
      ├─ api/                          types (endpoint contracts), httpClient, errors (§9 mapping)
      ├─ geometry/                     geometry.ts (= shared/metrics/geometry.py), spatialIndex.ts
      ├─ mock/                         DEMO ONLY: backend, placer, editor, metrics, graphs, RTL
      └─ estimate · format · highlight · random · storage · validation
```

---

## Placement canvas notes (spec §5.2, §11)

- Canvas2D with no per-node DOM. `prepare.ts` flattens the placement into typed
  arrays and builds uniform-grid spatial indexes once per placement. Each frame
  only touches nodes inside the viewport.
- **Level of detail:** std cells draw individually up to 25k visible cells at
  ≥ 1.2 px each, and as a coverage density map beyond that. Macros are always
  drawn individually. Thresholds are in `LOD` in `renderer.ts`. They were
  checked on the 12,752-node and 120k-node synthetic samples and should be
  re-measured on real designs.
- **Orientation** is drawn geometrically: E/W swap the footprint, and a pin-1
  corner marker shows rotation *and* mirroring (`geometry.ts → pinOneCorner`).
- Interaction: drag to pan, wheel to zoom at the cursor, click / shift-click /
  shift-drag to select, and keys `← ↑ → ↓` `+` `−` `0` `Esc`. `MacroList` is the
  keyboard and screen-reader route to selection.
- In Expert mode, the toolbar shows live render stats (mode, visible counts,
  ms per frame).

---

## Wiring the real backend

1. Implement the endpoints in `backend/main.py`, then reconcile
   `src/lib/api/types.ts` with the real Pydantic request/response models. That
   file is the only place endpoint shapes are defined.
2. `httpClient.ts` accepts a bare `CircuitGraph` or `{circuit_graph}` / `{graph}`
   from `/api/intake/synthesize`. Remove whichever shapes you don't use.
3. Error mapping (`errors.ts → classifyHttpError`) keys off status plus the
   exception name appearing in `detail`, so keep exception names in FastAPI's
   `detail` strings.
4. Turn off Demo mode.

Known gaps that stay visible in the UI on purpose (spec §14): LEF/DEF upload is
disabled with an explanation, there are no stage-progress events (the stepper
is ready: pass `stage` to `GenerationProgress`), `model_variant` is read-only,
the baselines tab says the endpoint doesn't exist, and history is per-tab only.
