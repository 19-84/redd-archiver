# Feature 2: Dynamic Serving Mode

**Status:** Planned
**Last updated:** 2026-06-09

**Goal:** Expand the Flask search server into a full application server that serves all page types from PostgreSQL, enabling the dynamic serving mode described in [README.md > Serving Modes](README.md#serving-modes).

**Problem:** The current hybrid mode requires a separate export step that generates potentially millions of static HTML files. At large scale (50M+ posts), this export takes hours and consumes significant disk space. Additionally, any browsing improvement (date filtering, flair filtering, keyword search) must be pre-computed as static files — which is fundamentally worse than a database query. The hybrid mode's Flask server handles only search and the REST API; all other pages are static files served by nginx.

---

## Approach

Expand the existing Flask search server into a full application server that renders all page types on-the-fly from PostgreSQL using the existing Jinja2 templates.

**What already exists (confirmed via code analysis):**
- Flask server (`search_server.py`, ~570 lines) with 3 routes (`/`, `/search`, `/health`) plus 404/500/429/400 error handlers
- REST API (`api/routes.py`, ~5,200 lines) with 30+ endpoints — comprehensive data retrieval for posts, comments, users, subreddits
- Jinja2 environment (`html_modules/jinja_env.py`) with bytecode caching, template streaming, pre-compilation
- 11 cached Jinja2 filters (`html_modules/jinja_filters.py`) with LRU caching (10K items) — `reddit_date`, `format_number`, `truncate_smart`, `score_class`, etc.
- 19 HTML templates covering all page types (dashboard, subreddit, post, user, search, components, macros)
- PostgreSQL query layer (`core/postgres_database.py`, ~3,800 lines) with connection pooling, keyset pagination, batch loading
- Input validation module (`utils/input_validation.py`, ~620 lines)
- Rate limiting infrastructure (Flask-Limiter)
- CSRF protection, XSS protection (Jinja2 autoescape)

**Key gap:** The 11 cached Jinja2 filters from `jinja_filters.py` are NOT imported in `search_server.py` — only 2 simple filters are registered. This is an easy quick win.

**What needs to be built:**
- Template adapter layer — current templates use relative file paths for navigation (e.g., `../../index.html`); dynamic mode needs URL-based routing (`/r/privacy/`). This must be solved before adding page routes.
- Flask route handlers for: dashboard, subreddit indexes, post pages with comment trees, user pages. Routes call the database query layer directly (e.g., `postgres_database.get_posts_paginated_keyset()`), NOT the REST API over HTTP — calling your own API introduces unnecessary serialization/deserialization overhead.
- The `REDDARCHIVER_SERVE_MODE` environment variable to enable dynamic mode (matching the existing env-var-only configuration pattern of `search_server.py`)
- 301 redirect handlers for static-style paths (see [README.md > URL Compatibility](README.md#url-compatibility-across-modes))

**What does NOT need to be built (already exists):**
- Database queries — API endpoints already handle all needed data retrieval
- Pagination — keyset pagination (O(1)) already implemented
- Search — fully functional in search_server.py
- Templates — all page templates exist and are production-ready
- Security — validation, escaping, rate limiting all in place

---

## Capabilities unique to dynamic mode

Not available in static or hybrid:

- Date range browsing (parameterized queries)
- Flair/tag filtering (without pre-computing pages)
- Domain filtering (without pre-computing pages)
- Score threshold filtering
- Cross-subreddit browsing (`/all/` route)
- Arbitrary sort orders and combinations
- Content available immediately after import (no export step)
- Zero disk usage for HTML files

Note: Full-text search and the REST API are already available in hybrid mode. Dynamic mode's unique value is the filtering/browsing features above and eliminating the export step entirely.

### Where dynamic mode fits

See [README.md > Serving Modes](README.md#serving-modes) for a full comparison of static, hybrid, and dynamic modes. In summary: dynamic mode trades static hosting compatibility and offline browsing for instant content availability, dynamic filtering, and zero disk usage. It is the most feature-rich mode but requires Flask + PostgreSQL to be running at all times.

---

## Phase 1: Quick wins (improves hybrid mode immediately)

- Import `jinja_filters.py` into `search_server.py` and register all 11 cached filters
- Immediately improves search results display with proper date/number/score formatting
- Benefits hybrid mode users right away, no mode change needed

---

## Phase 2: Template adaptation (prerequisite for page routes)

- Current templates use relative paths (`../../index.html`) for navigation links
- Dynamic mode needs either: (a) template conditionals checking a `dynamic_mode` context variable, or (b) a URL-building helper function passed to templates via Jinja2 globals
- Option (b) is cleaner — a `url_for_page()` function registered as a Jinja2 global that returns the right URL based on serving mode
- This must be solved before adding page routes, since templates won't render correct navigation links without it

---

## Phase 3: Core page routes

- Add route: `/r/<subreddit>/` — subreddit index (calls `postgres_database.get_posts_paginated_keyset()` + renders `pages/subreddit.html`)
- Add route: `/r/<subreddit>/comments/<post_id>/<slug>/` — post page with comments (calls `postgres_database.rebuild_threads_keyset()` + renders `pages/link.html`)
- Add route: `/user/<username>/` — user profile (calls `postgres_database.stream_user_batches()` + renders `pages/user.html`)
- Add route: `/` — dashboard (calls `postgres_database.get_all_subreddit_statistics_from_db()` + renders `pages/index.html`)
- Handle platform-specific paths: `/v/<subverse>/` (Voat), `/g/<guild>/` (Ruqqus)
- All routes call the database query layer directly, not the REST API

---

## Phase 4: Dynamic-only features

- Query parameter support: `?sort=comments&page=2&flair=Discussion&min_score=100&from=2024-01-01`
- All filtering happens via PostgreSQL WHERE clauses — no pre-computation
- Cross-subreddit view: `/all/` route showing posts from all archived subreddits
- Flair browsing: `/r/<subreddit>/?flair=Discussion` — dynamic equivalent of the static flair index, but with sorting/pagination query params. The static flair index pages ([Feature 1](01-static-index-improvements.md#phase-2-flair-index)) are not needed in dynamic mode because flair filtering is just a WHERE clause.
- Title browsing: `/r/<subreddit>/titles/<letter>/` — same URLs as static mode, but generated on-the-fly from `SELECT ... ORDER BY LOWER(title)` instead of pre-computed HTML files

---

## Phase 5: Performance & caching

- Response caching (Flask-Caching or ETag headers) for immutable archive content
- Browser cache headers (`Cache-Control: max-age=86400` for post pages)
- Optional Redis layer for frequently accessed pages

---

## Answered Questions

### Dynamic mode scope

**Recommendation: Feature parity with hybrid first, then dynamic-only features.**

Phase 1 — match hybrid mode output (all page types that currently require static HTML):
- Dashboard / main index
- Subreddit index pages (all 3 sort orders, paginated)
- Individual post pages with comment trees
- User profile pages (paginated)
- Search (already works in hybrid mode)
- REST API (already works in hybrid mode)

Phase 2 — dynamic-only features (not available in static or hybrid):
- Date range filtering (`?from=2024-01-01&to=2024-06-30`)
- Flair filtering (`?flair=Discussion`)
- Domain filtering (`?domain=eff.org`)
- Score threshold filtering (`?min_score=1000`)
- Cross-subreddit combined view (`/all/`)
- Arbitrary sort combinations

Phase 1 ensures dynamic mode is a strict superset of hybrid mode — no regression when switching. Phase 2 justifies choosing dynamic mode over hybrid.

---

## Testing Strategy

### Unit tests
- URL builder function (`url_for_page()`) produces correct URLs for all page types in both hybrid and dynamic modes
- 301 redirect mapping from static paths to dynamic URLs
- Template rendering with dynamic-mode URL context variable
- `REDDARCHIVER_SERVE_MODE` env var parsing and mode detection

### Integration tests
- Each Flask route returns 200 with correct template and database content (dynamic mode)
- Flask without `SERVE_MODE=dynamic` returns 404 for page routes but 200 for `/search` and `/api/` (hybrid mode)
- Pagination parameters (`?page=2&sort=comments`) produce correct query results
- Dynamic-only filters (`?flair=Discussion&min_score=100`) return filtered results
- 301 redirects from static paths to dynamic equivalents
- Jinja2 filter registration (all 11 cached filters available in both hybrid and dynamic modes)

### End-to-end tests
- Import test data → start Flask with `SERVE_MODE=dynamic` → request every page type → verify rendered HTML
- Compare dynamic page output against static/hybrid HTML for same data (content parity check)
- Performance baseline: page render time under 200ms for typical subreddit index
- Cross-subreddit `/all/` route with data from multiple test subreddits
- Mode switching: verify hybrid → dynamic transition works without re-import

---

## Migration

Existing databases work as-is with dynamic serving. The schema is unchanged. Users running hybrid mode set `REDDARCHIVER_SERVE_MODE=dynamic` (or use `--profile dynamic` in Docker) to switch to dynamic mode. No re-import needed.

---

## Cross-References

- See [README.md > Serving Modes](README.md#serving-modes) for full mode comparison and selection guide
- See [README.md > URL Compatibility](README.md#url-compatibility-across-modes) for static-to-dynamic URL mapping
- See [README.md > Infrastructure](README.md#infrastructure-considerations) for Docker profiles and nginx config per mode
- See [01-static-index-improvements.md](01-static-index-improvements.md) — title and flair indexes have dynamic equivalents in Phase 4
- See [03-incremental-update-system.md](03-incremental-update-system.md) — dynamic mode skips re-export after incremental updates
- See [04-visual-themes.md > Phase 4](04-visual-themes.md#phase-4-persistence--custom-branding) — template changes should be coordinated with Phase 2 template adaptation
