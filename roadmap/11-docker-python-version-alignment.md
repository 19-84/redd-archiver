# Feature 11: Align Docker Python Versions

**Status:** Planned
**Last updated:** 2026-02-11

**Goal:** Align all Dockerfiles to use the same Python version, eliminating a known version mismatch.

**Problem:** The search-server Dockerfile uses `python:3.14-alpine` while the builder Dockerfile and CI both use Python 3.12. Python 3.14 is not yet stable, and the search-server does not require any 3.14-specific features.

| Component | Python Version |
|-----------|---------------|
| `Dockerfile` (builder) | 3.12-alpine |
| `docker/search-server/Dockerfile` | **3.14-alpine** (mismatch) |
| CI (`test.yml`) | 3.12 |
| `pyproject.toml` requires-python | >=3.10 |

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

## Acceptance Criteria

- All Dockerfiles use Python 3.12-alpine
- `docker compose up -d --build` succeeds
- Search-server health endpoint responds correctly
- CI Docker workflow passes
