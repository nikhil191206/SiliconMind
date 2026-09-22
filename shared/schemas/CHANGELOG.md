# Schema Changelog

Every change to a file in `shared/schemas/` after initial creation must be logged
here: date, schema file, what changed, who approved it (per TECHNICAL.md Section 6,
changes to `shared/schemas/` require cross-review from the adjacent-interface owner).

No changes to the schema files themselves (`shared/schemas/*.py` still exactly
match Section 3 as created 2026-09-12). One cross-module interface decision is
logged here per TECHNICAL.md Section 6, since it directly concerns the adjacent
interfaces around `EncoderOutput`:

## 2026-09-18 — `graph: CircuitGraph` added to `generate()` and `legalize_and_score()`

**What:** TECHNICAL.md Section 4.B's `generate()` and Section 4.C's
`legalize_and_score()` now take an explicit `graph: CircuitGraph` parameter,
in addition to their original arguments. `EncoderOutput` (this file's
`encoder_output.py`) is unchanged.

**Why:** `EncoderOutput` carries only embeddings + `node_id_order`; neither
`generate()` nor `legalize_and_score()` can produce a schema-valid result
(design_name, die-scaled coordinates, node geometry, hyperedge connectivity)
from embeddings alone. Two fixes existed — extend `EncoderOutput` itself, or
pass `CircuitGraph` explicitly. Persons B and C each independently hit this
gap and implemented the latter; see `modules/generator/NOTES.md` §1.1 and
`modules/evaluation/NOTES.md` §2.1 for their reasoning.

**Approved by:** Person A (joint owner of `EncoderOutput`/Section 3.2),
2026-09-18 — ratifying B and C's already-implemented-and-tested fix rather
than growing `EncoderOutput` to duplicate data `CircuitGraph` already
carries. See TECHNICAL.md Sections 4.B/4.C for the amended interfaces and
the full ruling note.

**Impact:** none on `shared/schemas/` itself. `shared/mocks/mock_encoder_output.py`
and `shared/mocks/mock_placement.py` are unaffected since they don't
construct calls to `generate()`/`legalize_and_score()` themselves.
