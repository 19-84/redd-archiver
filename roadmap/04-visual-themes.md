# Feature 4: Visual Themes

**Status:** In progress (Phase 1 implemented)
**Last updated:** 2026-06-11

**Goal:** Replace the hardcoded dark/light toggle with a flexible CSS theme system where each theme provides both dark and light palettes, supports system preference detection, and allows operator customization — all without JavaScript (except for optional persistence in static mode).

**Problem:** The current dark/light toggle works via a CSS checkbox hack with 478 duplicated selector overrides. Adding new visual styles (e.g., sepia, high-contrast) would require duplicating all 478 selectors again. The toggle doesn't respect OS-level color scheme preferences. Archive operators have no way to customize colors or branding.

---

## Architecture

### Two independent axes

The theme system separates two concerns:

| Axis | Controlled by | Scope |
|---|---|---|
| **Theme** (palette personality) | Operator via `--theme` CLI flag at export time | Instance-level: all visitors see the same theme |
| **Mode** (luminance direction) | End user via dark/light toggle + system preference | Per-visitor: each user picks their preferred mode |

A **theme** is a named palette that defines both a dark and a light set of design tokens. The operator chooses the theme; the user chooses the mode.

### Theme palette matrix

Each theme provides values for both modes:

| Theme | Dark Background | Dark Text | Dark Accent | Light Background | Light Text | Light Accent | Use Case |
|---|---|---|---|---|---|---|---|
| Default | `#0f172a` | `#e2e8f0` | `#3b82f6` | `#ffffff` | `#1e293b` | `#2563eb` | General purpose |
| Sepia | `#2c2416` | `#e8dcc8` | `#c49b3a` | `#f5f0e8` | `#3d3425` | `#8b6914` | Extended reading sessions |
| High Contrast | `#000000` | `#ffffff` | `#ffff00` | `#ffffff` | `#000000` | `#0000cc` | Accessibility / low vision |

### Token delivery by serving mode

The main CSS file (`redd-archiver-universal.css`) uses only `var()` references for all theme-able values — no hardcoded colors. Token values are delivered differently depending on the serving mode:

| Mode | Token delivery | How it works |
|---|---|---|
| **Static** | Baked into the CSS file at export time | The export pipeline reads the `--theme` flag and writes the selected theme's dark/light token values directly into `:root` and `@media (prefers-color-scheme: light)` blocks at the top of the CSS file |
| **Dynamic** | Injected via `<style>` block in `base.html` | Flask reads the active theme from config (`REDDARCHIVER_THEME` env var) and renders a `<style>` block with the theme's token values into the template. The main CSS file remains static and fully cacheable |

---

## Current State Audit

| Aspect | Current State |
|---|---|
| CSS file | `static/css/redd-archiver-universal.css` (4,294 lines) |
| Theme toggle | CSS checkbox hack: `<input type="checkbox" id="dark-theme-toggle">` in `templates_jinja2/base/base.html` (line 46) |
| Toggle UI | `<label for="dark-theme-toggle">` in `templates_jinja2/components/navigation.html` (line 38) |
| Dark theme selectors | 478 `#dark-theme-toggle:checked` overrides scattered throughout the CSS |
| CSS custom properties | ~52 `var(--...)` usages (partial adoption — mostly for comment depth colors, gradients, and shadows) |
| System preference | Theme toggle is manual only. One `@media (prefers-color-scheme: dark)` block exists (CSS line ~4250, platform-badge colors), but the overall dark/light theme does not follow the OS setting |
| System fonts | Yes — native font stack, no external font loading |
| CSS minifier | `html_modules/css_minifier.py` using `rcssmin` — used by default (`copy_static_assets(output_dir, minify_css=True)` in `reddarc.py`, called at the two export sites without overriding the default) |
| Themes available | 2 (dark default, light via toggle) |

### Key files

- `static/css/redd-archiver-universal.css` — the single consolidated CSS file
- `templates_jinja2/base/base.html` — base template with theme toggle input (line 46)
- `templates_jinja2/components/navigation.html` — navigation with toggle label (line 38)
- `html_modules/css_minifier.py` — CSS minification utility

---

## Phase 1: Design Token Extraction

Implemented. 184 design tokens in a `:root` block with a single light-mode token-override block; 478 toggle-selector occurrences reduced to 194. The remaining toggle rules are light-only declarations with no base counterpart (their dark value comes from inheritance), specificity-contested pairs, `!important` mismatches, and media-scoped overrides — tokenizing those would require inventing dark-mode values and risk visual drift; they can be hand-curated in Phase 3. Equivalence was machine-verified by simulating the cascade (importance, specificity, source order) for every (selector, property) pair in both modes against the pre-refactor stylesheet. `tests/test_css_tokens.py` enforces dark/light token parity going forward.

Replace all hardcoded colors in `redd-archiver-universal.css` with CSS custom properties. Collapse the 478 `#dark-theme-toggle:checked` selector overrides into a single variable-override block.

**Before (current pattern, repeated 478 times):**
```css
.card { background: #1e293b; color: #e2e8f0; }
#dark-theme-toggle:checked ~ body .card { background: #ffffff; color: #1e293b; }
```

**After (token-based):**
```css
:root {
  --bg-card: #1e293b;
  --text-card: #e2e8f0;
  /* ... all color tokens ... */
}

#dark-theme-toggle:checked ~ body {
  --bg-card: #ffffff;
  --text-card: #1e293b;
  /* ... all overrides in ONE block ... */
}

.card { background: var(--bg-card); color: var(--text-card); }
```

**Outcome:** Zero visual change. Same checkbox toggle, same dark/light behavior. The CSS file becomes dramatically smaller and all theme-able values are centralized in one place.

**Estimated token count:** 80–120 design tokens covering backgrounds, text colors, borders, shadows, accents, and component-specific colors.

---

## Phase 2: System Preference Support

Replace the checkbox toggle with a `@media (prefers-color-scheme)` approach. Users see their OS preference on first load, with a manual override toggle.

```css
/* Dark mode is the default (tokens in :root) */
:root {
  --bg-card: #1e293b;
  /* ... */
}

/* System light preference */
@media (prefers-color-scheme: light) {
  :root {
    --bg-card: #ffffff;
    /* ... */
  }
}

/* Manual toggle overrides system preference */
#dark-theme-toggle:checked ~ body {
  --bg-card: #ffffff;
  /* ... */
}
```

**Outcome:** First-time visitors see a theme matching their OS settings. The manual toggle still works as an override. Pure CSS, no JavaScript.

---

## Phase 3: Theme-Agnostic CSS + Theme Definitions

Decouple the CSS from any specific theme. The main stylesheet uses only `var()` references. Theme palettes are defined as standalone data (Python dicts) that the export pipeline and Flask both consume.

### Theme definition format

Each theme is a Python dictionary with dark and light token sets:

```python
THEMES = {
    "default": {
        "dark": {
            "bg-primary": "#0f172a",
            "text-primary": "#e2e8f0",
            "accent": "#3b82f6",
            # ... 80-120 tokens ...
        },
        "light": {
            "bg-primary": "#ffffff",
            "text-primary": "#1e293b",
            "accent": "#2563eb",
            # ...
        },
    },
    "sepia": {
        "dark": {
            "bg-primary": "#2c2416",
            "text-primary": "#e8dcc8",
            "accent": "#c49b3a",
            # ...
        },
        "light": {
            "bg-primary": "#f5f0e8",
            "text-primary": "#3d3425",
            "accent": "#8b6914",
            # ...
        },
    },
    "high-contrast": {
        "dark": {
            "bg-primary": "#000000",
            "text-primary": "#ffffff",
            "accent": "#ffff00",
            # ...
        },
        "light": {
            "bg-primary": "#ffffff",
            "text-primary": "#000000",
            "accent": "#0000cc",
            # ...
        },
    },
}
```

### Static export: tokens baked into CSS

The export pipeline reads `--theme` and generates the `:root` and `@media` blocks with that theme's values:

```css
/* Generated by export pipeline for --theme sepia */
:root {
  --bg-primary: #2c2416;
  --text-primary: #e8dcc8;
  --accent: #c49b3a;
  /* ... sepia dark tokens ... */
}

@media (prefers-color-scheme: light) {
  :root {
    --bg-primary: #f5f0e8;
    --text-primary: #3d3425;
    --accent: #8b6914;
    /* ... sepia light tokens ... */
  }
}

/* Manual dark/light toggle override */
#dark-theme-toggle:checked ~ body {
  /* ... sepia light tokens (same values as @media block) ... */
}
```

### Dynamic mode: tokens injected via template

Flask reads `REDDARCHIVER_THEME` from config and renders a `<style>` block in `base.html`:

```html
<!-- Rendered by Flask from theme config -->
<style>
  :root {
    --bg-primary: {{ theme.dark['bg-primary'] }};
    --text-primary: {{ theme.dark['text-primary'] }};
    --accent: {{ theme.dark['accent'] }};
    {# ... all dark tokens ... #}
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg-primary: {{ theme.light['bg-primary'] }};
      --text-primary: {{ theme.light['text-primary'] }};
      --accent: {{ theme.light['accent'] }};
      {# ... all light tokens ... #}
    }
  }
</style>

<!-- Main CSS is theme-agnostic — fully cacheable -->
<link rel="stylesheet" href="/static/css/redd-archiver-universal.css">
```

The main CSS file contains zero hardcoded colors and is identical regardless of theme. Only the inline `<style>` block changes per theme.

**Outcome:** The CSS is fully theme-agnostic. Theme selection is an operator/instance decision. Users control only dark/light mode. Adding a new theme requires only a new Python dict entry — no CSS changes.

---

## Phase 4: Custom Branding

### CLI flags

```bash
reddarc.py --output /var/www/html/ \
  --theme sepia \                    # Select theme palette (default, sepia, high-contrast)
  --accent-color "#8b6914" \         # Override accent color for both modes
  --custom-css /path/to/overrides.css  # Additional CSS appended after main stylesheet
```

| Flag | Default | Description |
|---|---|---|
| `--theme` | `default` | Theme palette (`default`, `sepia`, `high-contrast`) |
| `--accent-color` | (per theme) | Override primary accent color (hex value), applied to both dark and light modes |
| `--custom-css` | None | Path to additional CSS file, appended after main stylesheet |

### Dynamic mode configuration

```bash
# Environment variables for Flask
REDDARCHIVER_THEME=sepia
REDDARCHIVER_ACCENT_COLOR=#8b6914
```

### Persistence

- **Dynamic mode:** Cookie-based persistence for mode preference (dark/light). Flask reads the mode cookie and pre-selects the toggle state server-side. No JavaScript needed.
- **Static mode:** Optional tiny `<script>` tag (reads `localStorage`, applies mode preference before first paint). Gated behind `--enable-theme-persistence` CLI flag to preserve the zero-JavaScript design for operators who want it. Only persists mode (dark/light), not theme — theme is baked in at export time.

| Flag | Default | Description |
|---|---|---|
| `--enable-theme-persistence` | `false` | Add localStorage script for static mode dark/light preference memory |

---

## Testing Strategy

### Unit tests
- Design token extraction: verify all hardcoded colors replaced with `var()` references
- Token override completeness: every token defined in `:root` has a corresponding value in both dark and light palettes for every theme
- Theme definition validation: every theme has both `dark` and `light` keys with identical token sets
- CSS validity: parsed output has no syntax errors
- CLI flag validation: `--theme` rejects invalid values, `--accent-color` validates hex format

### Integration tests
- Dark/light toggle: switching mode applies correct token values (visual regression via screenshot comparison)
- System preference: `prefers-color-scheme: light` applies light tokens when toggle is in default state
- Manual override: toggle overrides system preference
- Theme injection (static): export with `--theme sepia` → verify `:root` contains sepia dark tokens, `@media` block contains sepia light tokens
- Theme injection (dynamic): Flask with `REDDARCHIVER_THEME=sepia` → verify inline `<style>` contains sepia tokens
- Theme-agnostic CSS: main stylesheet contains zero hardcoded color values (only `var()` references)
- `--accent-color` override: verify accent token is replaced in both dark and light palettes

### End-to-end tests
- Full pipeline: export with `--theme sepia` → verify rendered pages use sepia colors
- Default theme: export without `--theme` → verify default palette applied
- Custom CSS: `--custom-css` file is appended correctly and overrides are applied
- Persistence (dynamic): set mode via toggle → reload page → verify mode persists via cookie
- Persistence (static): `--enable-theme-persistence` → verify `<script>` tag present and functional
- Zero visual regression: Phase 1 output is pixel-identical to pre-refactor output
- Dynamic/static parity: same theme produces visually identical results in both serving modes

---

## Migration

Phase 1 is a CSS-only refactor with zero visual change. Existing archives can adopt the new CSS by re-running `--export-from-database`. No database or template migration needed.

Phase 3 changes how token values are delivered (baked into CSS or injected via template) but the visual output is identical. Operators using `--export-from-database` get the default theme automatically. Operators wanting a different theme re-export with `--theme <name>`.

---

## Cross-References

- See [02-dynamic-serving-mode.md > Phase 2](02-dynamic-serving-mode.md#phase-2-template-adaptation-prerequisite-for-page-routes) — template adaptation concerns overlap with Phase 3 (inline `<style>` injection in dynamic mode)
- See [README.md > Serving Modes](README.md#serving-modes) — token delivery differs between static and dynamic modes
