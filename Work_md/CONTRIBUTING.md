# Contributing / Git Workflow

Full rules: TECHNICAL.md Section 6. Summary for quick reference:

- **Branch naming:** `<person-initial>/<short-feature-name>`, e.g. `a/de-hnn-implementation`.
- **Ownership:** each person commits only inside their own `modules/<their_module>/`
  and `tests/unit/<their_module>/` folders, plus any `shared/schemas/` file they own.
  Editing inside another person's module folder requires a PR reviewed by that person.
- **Cross-review required by default** (regardless of who's editing): `shared/schemas/`,
  `shared/metrics/`, and `TECHNICAL.md` itself. Everything else in a person's own
  module folder is self-mergeable once tests pass.
- **Schema changes:** a PR touching `shared/schemas/` must update the matching mock in
  `shared/mocks/` in the *same* PR. A schema change without an updated mock is an
  incomplete PR. Log the change in `shared/schemas/CHANGELOG.md`.
- **Module owners:**
  - Person A — `modules/encoders/`
  - Person B — `modules/generator/`
  - Person C — `modules/evaluation/`
  - Person D — `modules/intake/`, `modules/llm_interaction/`
