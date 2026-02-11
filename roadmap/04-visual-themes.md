# Feature 4: Visual Themes

**Status:** Planned
**Last updated:** 2026-02-11

**Goal:** Replace the hardcoded dark/light toggle with a flexible CSS theme system that supports multiple themes, system preference detection, and operator customization — all without JavaScript (except for optional persistence).

**Problem:** The current dark/light toggle works via a CSS checkbox hack with 478 duplicated selector overrides. Adding a third theme (e.g., sepia, high-contrast) would require duplicating all 478 selectors again. The toggle doesn't respect OS-level color scheme preferences. Archive operators have no way to customize colors or branding.

---

## Current State Audit

| Aspect | Current State |
|---|---|
| CSS file | `static/css/redd-archiver-universal.css` (4,294 lines) |
| Theme toggle | CSS checkbox hack: `<input type="checkbox" id="dark-theme-toggle">` in `templates_jinja2/base/base.html` (line 46) |
| Toggle UI | `<label for="dark-theme-toggle">` in `templates_jinja2/components/navigation.html` (line 38) |
| Dark theme selectors | 478 `#dark-theme-toggle:checked` overrides scattered throughout the CSS |
| CSS custom properties | ~52 `var(--...)` usages (partial adoption — mostly for comment depth colors, gradients, and shadows) |
| System preference | Not supported — no `@media (prefers-color-scheme)` rules |
| System fonts | Yes — native font stack, no external font loading |
| CSS minifier | `html_modules/css_minifier.py` using `rcssmin` — exists but not used in default build |
| Themes available | 2 (dark default, light via toggle) |

### Key files

- `static/css/redd-archiver-universal.css` — the single consolidated CSS file
- `templates_jinja2/base/base.html` — base template with theme toggle input (line 46)
- `templates_jinja2/components/navigation.html` — navigation with toggle label (line 38)
- `html_modules/css_minifier.py` — CSS minification utility

---

## Phase 1: Design Token Extraction

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

Add `@media (prefers-color-scheme: light)` using the token system. Users see their OS preference on first load.

```css
/* Dark theme is the default (tokens in :root) */
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

## Phase 3: Additional Themes

Add sepia and high-contrast themes. Replace the checkbox toggle with a `<select>` element + CSS `:has()` selector (CSS-only, no JavaScript). Four themes total.

**Theme palette:**

| Theme | Background | Text | Accent | Use Case |
|---|---|---|---|---|
| Dark (default) | `#0f172a` | `#e2e8f0` | `#3b82f6` | Default, reduced eye strain |
| Light | `#ffffff` | `#1e293b` | `#2563eb` | Bright environments |
| Sepia | `#f5f0e8` | `#3d3425` | `#8b6914` | Extended reading sessions |
| High Contrast | `#000000` | `#ffffff` | `#ffff00` | Accessibility / low vision |

**CSS-only theme selector using `:has()`:**
```css
/* Theme selection via hidden <select> in <body> */
body:has(#theme-select option[value="light"]:checked) {
  --bg-card: #ffffff;
  /* ... light tokens ... */
}

body:has(#theme-select option[value="sepia"]:checked) {
  --bg-card: #f5f0e8;
  /* ... sepia tokens ... */
}

body:has(#theme-select option[value="high-contrast"]:checked) {
  --bg-card: #000000;
  /* ... high-contrast tokens ... */
}
```

**Template change:** The checkbox input and label are replaced with a `<select>` dropdown in the navigation bar. This is the only template change required.

**Browser support:** CSS `:has()` is supported in Chrome 105+, Firefox 121+, Safari 15.4+. For older browsers, the default dark theme applies (graceful degradation).

---

## Phase 4: Persistence + Custom Branding

### Persistence

- **Dynamic mode:** Cookie-based persistence. Flask reads the theme cookie and adds a `data-theme` attribute to `<body>`, which CSS uses for theme selection. No JavaScript needed.
- **Static mode:** Optional tiny `<script>` tag (reads `localStorage`, applies `data-theme` before first paint). Gated behind `--enable-theme-persistence` CLI flag to preserve the zero-JavaScript design for operators who want it.

### Custom branding (CLI flags)

```bash
reddarc.py --output /var/www/html/ \
  --theme sepia \                    # Default theme for this archive
  --accent-color "#8b6914" \         # Override accent color
  --custom-css /path/to/overrides.css  # Additional CSS appended after main stylesheet
```

| Flag | Default | Description |
|---|---|---|
| `--theme` | `dark` | Default theme (`dark`, `light`, `sepia`, `high-contrast`) |
| `--accent-color` | (per theme) | Override primary accent color (hex value) |
| `--custom-css` | None | Path to additional CSS file, appended after main stylesheet |
| `--enable-theme-persistence` | `false` | Add localStorage script for static mode theme memory |

---

## Testing Strategy

### Unit tests
- Design token extraction: verify all hardcoded colors replaced with `var()` references
- Token override completeness: every token defined in `:root` has an override in each theme block
- CSS validity: parsed output has no syntax errors
- CLI flag validation: `--theme` rejects invalid values, `--accent-color` validates hex format

### Integration tests
- Theme toggle: switching themes applies correct token values (visual regression via screenshot comparison)
- System preference: `prefers-color-scheme: light` applies light tokens when toggle is in default state
- Manual override: toggle overrides system preference
- `:has()` selector: theme `<select>` applies correct theme in supported browsers
- Graceful degradation: unsupported browsers render the default dark theme

### End-to-end tests
- Full pipeline: export with `--theme sepia` → verify CSS contains sepia as default theme
- Custom CSS: `--custom-css` file is appended correctly and overrides are applied
- Persistence (dynamic): set theme via UI → reload page → verify theme persists via cookie
- Persistence (static): `--enable-theme-persistence` → verify `<script>` tag present and functional
- Zero visual regression: Phase 1 output is pixel-identical to pre-refactor output

---

## Migration

Phase 1 is a CSS-only refactor with zero visual change. Existing archives can adopt the new CSS by re-running `--export-from-database`. No database or template migration needed until Phase 3 (theme selector replaces toggle in templates).

---

## Cross-References

- See [02-dynamic-serving-mode.md > Phase 2](02-dynamic-serving-mode.md#phase-2-template-adaptation-prerequisite-for-page-routes) — template adaptation concerns overlap with Phase 3 template changes (theme selector)
- See [README.md > Serving Modes](README.md#serving-modes) — persistence behavior differs between static and dynamic modes
