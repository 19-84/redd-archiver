# Feature 10: Activate Pre-Commit Hooks

**Status:** ✅ Done (2026-06-11) — .pre-commit-config.yaml with ruff check+format hooks pinned to v0.15.10
**Last updated:** 2026-06-09

**Goal:** Create a `.pre-commit-config.yaml` and activate pre-commit hooks for local development, providing faster feedback than CI-only enforcement.

**Problem:** The `pre-commit` package is already in dev dependencies and the Makefile has `install-hooks` and `setup` targets that call `uv run pre-commit install`, but no `.pre-commit-config.yaml` exists. Developers currently only discover lint/format issues when CI runs, not at commit time.

---

## Tasks

- Create `.pre-commit-config.yaml` with ruff hooks:
  ```yaml
  repos:
    - repo: https://github.com/astral-sh/ruff-pre-commit
      rev: v0.15.10  # Match version in pyproject.toml
      hooks:
        - id: ruff
          args: [--fix]
        - id: ruff-format
  ```
- Verify `make setup` / `uv run pre-commit install` works
- Test that hooks run correctly on `git commit`
- Ensure hook configuration matches CI lint workflow (`.github/workflows/lint.yml`)
- Update Deviations table in `CLAUDE.md` to reflect completion

---

## Notes

- Hook versions should stay pinned to match the ruff version in `pyproject.toml` (currently `0.15.10`)
- Ruff bumps now arrive via the `uv` Dependabot ecosystem (updating `pyproject.toml` + `uv.lock`) and **auto-merge on green CI without touching `.pre-commit-config.yaml`** — so the pre-commit `rev` will drift unless kept in sync separately. Options: add a `pre-commit` entry to a CI `pre-commit autoupdate` step, or treat CI `ruff` as the source of truth and refresh the hook `rev` periodically. (Dependabot has no native pre-commit ecosystem.)

## Acceptance Criteria

- `.pre-commit-config.yaml` exists with ruff check + format hooks
- `make setup` successfully installs hooks
- Hooks catch lint/format issues before commit
- Hook ruff version matches `pyproject.toml` ruff version
