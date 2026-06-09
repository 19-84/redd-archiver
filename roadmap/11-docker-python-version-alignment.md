# Feature 11: Align Docker Python Versions

**Status:** ✅ Done (2026-06-09)
**Last updated:** 2026-06-09

**Goal:** Align all Dockerfiles to the same Python version (3.12, matching CI), eliminating the version mismatch.

**Problem (resolved):** The search-server Dockerfile used `python:3.14-alpine` while the builder Dockerfile and CI used 3.12. A brief Dependabot auto-merge episode pushed the builder and mcp_server images to 3.14 as well, widening the gap. Critically, CI's test suite runs on 3.12, so the 3.14 images ran an untested Python version — and 3.14 surfaced a `PythonFinalizationError` from psycopg's connection pool at shutdown that the 3.12 suite never showed. All images were reverted/aligned to **3.12** to match the version CI actually validates.

| Component | Python Version |
|-----------|---------------|
| `Dockerfile` (builder) | 3.12-alpine ✅ |
| `docker/search-server/Dockerfile` | 3.12-alpine ✅ (was the 3.14 outlier) |
| `docker/leaderboard/Dockerfile` | 3.12-alpine ✅ |
| `mcp_server/Dockerfile` | 3.12-slim-bookworm ✅ (Debian flavor, intentional) |
| CI (`test.yml`, `lint.yml`) | 3.12 |
| `pyproject.toml` requires-python | >=3.10 |

> **If a future move to 3.14 is desired**, do it deliberately: bump CI (`test.yml`/`lint.yml`) to 3.14 first so the suite validates it, resolve the psycopg pool `PythonFinalizationError` at interpreter shutdown, then move the images — not via auto-merged base-image bumps.

---

## Tasks

- Change `docker/search-server/Dockerfile` base image from `python:3.14-alpine` to `python:3.12-alpine`
- Verify search-server builds successfully with `docker compose build search-server`
- Verify `docker compose up -d` works end-to-end (health endpoints respond)
- Run the Docker CI workflow integration test pattern locally:
  - Start postgres + search-server
  - Verify `/health` and `/api/v1/stats` respond
- Update Deviations table in `CLAUDE.md` to reflect completion

---

## Acceptance Criteria (all met)

- ✅ All Dockerfiles target Python **3.12** (alpine for builder/search-server/leaderboard; slim-bookworm for mcp_server — the *flavor* differs intentionally, but the Python minor version is uniform and matches CI).
- ✅ `docker compose up -d --build` succeeds (Docker Compose Integration Test passes in CI)
- ✅ Search-server health endpoint responds correctly
- ✅ CI Docker workflow passes
