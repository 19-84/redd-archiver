# Feature 8: Add Pyright Type Checking

**Status:** Planned
**Last updated:** 2026-02-11

**Goal:** Add static type checking to the project using pyright in standard mode, closing the gap with the global tooling conventions.

**Problem:** The codebase uses type hints throughout but has no formal type checker configured or enforced in CI. Type errors can slip through undetected. The global `~/.claude/docs/python.md` standard requires pyright in standard mode.

---

## Phase 1: Configuration & Baseline

Add pyright configuration and assess the current violation landscape.

**Tasks:**
- Add `pyright` to dev dependencies in `pyproject.toml`
- Add `[tool.pyright]` section to `pyproject.toml`:
  ```toml
  [tool.pyright]
  pythonVersion = "3.10"
  typeCheckingMode = "standard"
  include = ["core", "api", "html_modules", "processing", "utils", "monitoring"]
  exclude = ["**/__pycache__", ".venv", "build", "tools", "tests"]
  strictListInference = true
  strictDictionaryInference = true
  strictSetInference = true
  reportMissingParameterType = "warning"
  reportDeprecated = "warning"
  reportUnnecessaryTypeIgnoreComment = "warning"
  reportUnusedImport = "none"
  reportUnusedVariable = "none"
  ```
- Run `uv run pyright` and document baseline violation count
- Add per-file `# pyright: basic` overrides for legacy files with excessive violations

## Phase 2: CI Integration

- Add `uv run pyright` step to `.github/workflows/lint.yml`
- Ensure all violations are either fixed or suppressed with documented rationale
- Update Deviations table in `CLAUDE.md` to reflect completion

## Phase 3: Gradual Strictness (ongoing)

- Enable `# pyright: strict` on mature, well-typed files
- Tighten suppressions as files are refactored
- Consider adding `tests/` to the include list once core modules are clean

---

## Acceptance Criteria

- `uv run pyright` runs without errors (or only documented suppressed warnings)
- CI lint workflow includes pyright check
- No regressions in existing functionality
