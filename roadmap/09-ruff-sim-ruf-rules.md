# Feature 9: Enable SIM and RUF Ruff Rules

**Status:** Planned
**Last updated:** 2026-02-11

**Goal:** Add `SIM` (flake8-simplify) and `RUF` (Ruff-specific) rule sets to the ruff configuration, aligning with the global tooling standard.

**Problem:** The global `~/.claude/docs/python.md` standard includes both `SIM` and `RUF` in the recommended rule set, but this project omits them. SIM catches code simplification opportunities (unnecessary `else` after `return`, collapsible `if` statements, etc.). RUF catches Ruff-specific improvements and modernizations.

Current select: `["E", "W", "F", "I", "N", "UP", "B", "C4", "S"]`
Target select: `["E", "W", "F", "I", "N", "UP", "B", "C4", "S", "SIM", "RUF"]`

---

## Phase 1: Assessment

- Add `"SIM"` and `"RUF"` to `[tool.ruff.lint] select` in `pyproject.toml`
- Run `uv run ruff check .` to assess the volume of new violations
- Categorize violations: auto-fixable vs manual fix vs legitimate suppression

## Phase 2: Auto-Fix & Manual Resolution

- Run `uv run ruff check . --fix` to resolve auto-fixable violations
- Manually fix straightforward violations
- Add justified per-file-ignores for violations that require larger refactors
- Document any ignored rules with inline rationale

## Phase 3: CI Verification

- Verify `uv run ruff check .` passes with the new rules
- Verify `uv run ruff format --check .` still passes
- Update Deviations table in `CLAUDE.md` to reflect completion

---

## Acceptance Criteria

- Both SIM and RUF rules are enabled in `pyproject.toml`
- `uv run ruff check .` passes in CI
- Any new per-file-ignores have documented justification
