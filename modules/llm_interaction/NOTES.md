# Person D — LLM Interaction: Notes

Status: `parse_constraint` (LLM-backed with a deterministic offline/no-API-key
heuristic fallback) and `generate_diff_report`/`format_diff_summary` are
implemented and unit-tested (`tests/unit/llm_interaction/`).

## Bug found and fixed during A/B/C/D integration (2026-09-18)

**The heuristic fallback parser's digit-extraction regex, `\b(\d+)\b`, could
not match a digit following an underscore** (`_` counts as a word character
in Python's `re`, so there is no `\b` boundary between `node_` and `0`).
Every example in this file's own docstring — `"Move SRAM_0 away from..."`,
`"Move MACRO_0 closer to MACRO_1"` — uses exactly that underscore-joined
form. In practice this meant `"Move node_0 away from node_1"` extracted zero
digits, silently fell back to "first placed node" for both the moved node
*and* its own reference, and produced a self-referential
`MOVE_AWAY_FROM(node, itself)` constraint at high confidence (0.85) —
never flagged as unclear, and instrumental in producing a NaN placement
once it reached `PlacementGenerator.generate()` (see
`modules/generator/NOTES.md` §5 for the other half of that bug).

**Fix:** digit extraction now matches any run of digits **not immediately
preceded by a letter or digit** (`(?<![a-zA-Z0-9])(\d+)`), so `_`, `#`,
whitespace, and start-of-string all count as valid separators —
`"node_0"`, `"SRAM_0"`, `"macro#1"`, and a bare `"10"` (as in the region
phrasing `"region 10 10 50 50"`) all extract correctly.

**A second, related bug in the same function:** every digit that matched a
valid node id was added to `affected_node_ids` — including a second node
mentioned purely as the *reference point* (e.g. the `node_1` in "away from
node_1"). That reference node should stay frozen like everything else it
isn't the one being moved. Fixed: only the first valid node id becomes
`affected_node_ids`; a second one is used only as `ref_val`, as the
`digits[1]`-based reference logic below it already intended.

Neither bug affected the LLM-backed path (used whenever an API key is
configured) — only the deterministic fallback used in tests and in offline/
no-API-key operation.

## Real LLM credentials configured, provider wiring fixed (2026-09-21)

Real `GROQ_API_KEY` and `WANDB_API_KEY` were provided and are stored in the
repo-root `.env` (gitignored, never committed — see `shared/env.py`, loaded
automatically via `import shared.env`'s side effect, and by `tests/conftest.py`
for the test session).

**Bug found while wiring this in:** this module (and `modules/intake/llm_rtl.py`)
only ever checked `OPENAI_API_KEY`/`LLM_API_KEY` and hardcoded a plain
`openai.OpenAI(api_key=...)` client pointed at OpenAI's own endpoint — a
Groq key would have been silently rejected (wrong host entirely) had this
not been caught before ever running for real. Fixed via a shared resolver,
`shared/llm_client.py`, that prefers `GROQ_API_KEY` (via Groq's
OpenAI-compatible endpoint, `https://api.groq.com/openai/v1`) and falls
back to `OPENAI_API_KEY`/`LLM_API_KEY` against the real OpenAI endpoint.
Both modules now import this instead of constructing their own client.

**Model ID verified live, not assumed:** initial research suggested
`llama-3.3-70b-versatile`, but Groq's own docs contradicted each other on
whether it's still active. Queried the real `/v1/models` endpoint with the
real key — confirmed `llama-3.3-70b-versatile` and `llama-3.1-8b-instant`
are both actually gone (deprecated), and `openai/gpt-oss-120b` is live;
confirmed with a real completion call before hardcoding it in
`shared/llm_client.py`.

**A third, previously-undiscovered bug found once the real LLM path was
actually exercised** (not just the heuristic fallback): the LLM-backed
`parse_constraint` branch always parsed `reference_node_id` as an int, even
when `reference_type` was `REGION` — it never constructed a real
`RegionBoundingBox` for `FORBID_REGION`/`PREFER_REGION` results. Fixed:
the prompt now asks for an explicit `reference_region` object
(`x_min`/`y_min`/`x_max`/`y_max`), and the code branches on `reference_type`
to build the correct `ConstraintReference` value. Verified against the live
API (`tests/unit/llm_interaction/test_constraint_parser_live_llm.py`) —
this bug would never have been caught by the heuristic-only test suite,
since the heuristic path already built region boxes correctly (hardcoded
placeholder bounds) and no test had ever actually called the LLM branch.

**Live-LLM test note:** the existing heuristic-path tests
(`test_constraint_parser.py`) now explicitly clear `GROQ_API_KEY`/
`OPENAI_API_KEY`/`LLM_API_KEY` via a fixture — without that, they would
silently start hitting the live API now that real credentials exist,
turning deterministic regression tests into flaky network-dependent ones.
A separate `test_constraint_parser_live_llm.py` exists specifically to
exercise the real path, skipped (not faked) when no credentials are
present. One live-model behavior worth knowing: exact classification of
ambiguous-but-not-UNCLEAR phrasing (e.g. "keep out of" vs. "must never be
placed in" for a region constraint) was observed to vary run-to-run even at
temperature=0 — this is the live model's own judgment call, not a parsing
bug, and the tests are written to check structural correctness (a real,
valid bounding box) rather than pin down the model's exact phrasing
preference.
