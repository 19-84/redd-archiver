#!/usr/bin/env python
"""
ABOUTME: Theme palette system (Feature 4 Phases 3-4) - named palettes, accent override, CSS injection
ABOUTME: Static export bakes tokens into the CSS; dynamic mode injects an inline <style> block
"""

import colorsys
import re
from collections.abc import Callable

from html_modules.theme_data import BASE_PALETTE, DEFAULT_DARK, DEFAULT_LIGHT

# A color transform maps one RGB triple to another (alpha is preserved by the caller)
ColorFn = Callable[[int, int, int], tuple[int, int, int]]

_HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGBA_RE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([0-9.]+)\s*)?\)")

# Colors below this saturation are treated as neutral (never re-hued)
_MIN_SATURATION = 0.15


def _hsl(r: int, g: int, b: int) -> tuple[float, float, float]:
    """RGB (0-255) to (hue degrees, lightness 0-1, saturation 0-1)."""
    h, lightness, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return h * 360, lightness, s


def _rgb(h_deg: float, lightness: float, s: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb(h_deg / 360 % 1.0, lightness, s)
    return round(r * 255), round(g * 255), round(b * 255)


def _in_band(h: float, s: float, band: tuple[float, float]) -> bool:
    return s >= _MIN_SATURATION and band[0] <= h <= band[1]


def _map_colors(value: str, fn: ColorFn | None) -> str:
    """Apply fn to every color literal in a CSS value, preserving alpha and
    leaving the original text untouched when fn does not change the color."""
    if fn is None:
        return value

    def hex_sub(m: re.Match[str]) -> str:
        hx = m.group(1)
        if len(hx) == 3:
            hx = "".join(c * 2 for c in hx)
        r, g, b = (int(hx[i : i + 2], 16) for i in (0, 2, 4))
        r2, g2, b2 = fn(r, g, b)
        if (r2, g2, b2) == (r, g, b):
            return m.group(0)
        return f"#{r2:02x}{g2:02x}{b2:02x}"

    def rgba_sub(m: re.Match[str]) -> str:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        r2, g2, b2 = fn(r, g, b)
        if (r2, g2, b2) == (r, g, b):
            return m.group(0)
        alpha = m.group(4)
        if alpha is None:
            return f"rgb({r2}, {g2}, {b2})"
        return f"rgba({r2}, {g2}, {b2}, {alpha})"

    return _RGBA_RE.sub(rgba_sub, _HEX_RE.sub(hex_sub, value))


def _sepia(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Re-hue the blue/indigo/purple accent-and-surface family to warm amber.
    Semantic colors (greens, reds, yellows) and neutrals pass through."""
    h, lightness, s = _hsl(r, g, b)
    if not _in_band(h, s, (185, 300)):
        return r, g, b
    return _rgb(38, lightness, s * 0.9)


def _hc_dark(r: int, g: int, b: int) -> tuple[int, int, int]:
    """High-contrast dark: accent-family colors snap to black / white / yellow."""
    h, lightness, s = _hsl(r, g, b)
    if not _in_band(h, s, (185, 300)):
        return r, g, b
    if lightness < 0.35:
        return 0, 0, 0
    if lightness > 0.72:
        return 255, 255, 255
    return 255, 255, 0


def _hc_light(r: int, g: int, b: int) -> tuple[int, int, int]:
    """High-contrast light: accent-family colors snap to black / white / deep blue."""
    h, lightness, s = _hsl(r, g, b)
    if not _in_band(h, s, (185, 300)):
        return r, g, b
    if lightness < 0.4:
        return 0, 0, 0
    if lightness > 0.72:
        return 255, 255, 255
    return 0, 0, 204


def _hue_to(band: tuple[float, float], target_hue: float) -> ColorFn:
    """Rotate every in-band color to the target hue, keeping saturation/lightness ladders."""

    def fn(r: int, g: int, b: int) -> tuple[int, int, int]:
        h, lightness, s = _hsl(r, g, b)
        if not _in_band(h, s, band):
            return r, g, b
        return _rgb(target_hue, lightness, s)

    return fn


def _restyle(
    band: tuple[float, float],
    hue: float,
    *,
    sat_scale: float = 1.0,
    sat_floor: float = 0.0,
    light_scale: float = 1.0,
) -> ColorFn:
    """Single-hue theme factory: rotate in-band colors to ``hue`` with optional
    saturation scaling/floor and lightness scaling. The default palette's
    lightness ladders (surface depth, hover states) carry the structure."""

    def fn(r: int, g: int, b: int) -> tuple[int, int, int]:
        h, lightness, s = _hsl(r, g, b)
        if not _in_band(h, s, band):
            return r, g, b
        return _rgb(hue, min(1.0, lightness * light_scale), min(1.0, max(s * sat_scale, sat_floor)))

    return fn


def _restyle_split(
    band: tuple[float, float],
    surface_hue: float,
    accent_hue: float,
    *,
    threshold: float = 0.45,
    surface_sat: float = 1.0,
    accent_sat_floor: float = 0.0,
) -> ColorFn:
    """Dual-hue theme factory: dark in-band colors (surfaces) go to one hue,
    bright ones (accents, links, light text) to another."""

    def fn(r: int, g: int, b: int) -> tuple[int, int, int]:
        h, lightness, s = _hsl(r, g, b)
        if not _in_band(h, s, band):
            return r, g, b
        if lightness < threshold:
            return _rgb(surface_hue, lightness, min(1.0, s * surface_sat))
        return _rgb(accent_hue, lightness, min(1.0, max(s, accent_sat_floor)))

    return fn


def _midnight_dark(r: int, g: int, b: int) -> tuple[int, int, int]:
    """OLED midnight: crush the dark surface ladder toward true black, keep the
    blue accents untouched (only colors darker than the threshold change)."""
    h, lightness, s = _hsl(r, g, b)
    if not _in_band(h, s, (185, 300)) or lightness >= 0.35:
        return r, g, b
    return _rgb(h, lightness * 0.25, s * 0.6)


def _hex_rgb(hx: str) -> tuple[int, int, int]:
    hx = hx.lstrip("#")
    return int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)


def _rgba_of(hx: str, alpha: float) -> str:
    r, g, b = _hex_rgb(hx)
    a = f"{alpha:g}"
    return f"rgba({r}, {g}, {b}, {a})"


def _shade(hx: str, dl: float) -> str:
    """Lighten (dl > 0) or darken (dl < 0) a hex color by shifting HSL lightness."""
    h, lightness, s = _hsl(*_hex_rgb(hx))
    r, g, b = _rgb(h, min(1.0, max(0.0, lightness + dl)), s)
    return f"#{r:02x}{g:02x}{b:02x}"


def _grad(a: str, b: str) -> str:
    return f"linear-gradient(135deg, {a} 0%, {b} 100%)"


# Alpha ladders copied from the default palette's ramps so themed ramps keep the
# same translucency structure as the original.
_DEPTH_ALPHAS = [0.95, 0.96, 0.97, 0.98, 0.99, 0.995, 0.998] + [0.999] * 13 + [1]
_DEPTH_BORDER_ALPHAS = [0.15, 0.16, 0.17, 0.18, 0.19, 0.22, 0.25, 0.28, 0.32, 0.35, 0.38, 0.42, 0.46, 0.5, 0.55]


def _depth_ramp(surface: str, deep: str, *, light: bool) -> dict[str, str]:
    """21-step comment nesting ramp interpolating surface -> deep."""
    (r1, g1, b1), (r2, g2, b2) = _hex_rgb(surface), _hex_rgb(deep)
    prefix = "--comment-depth-light-" if light else "--comment-depth-"
    ramp = {}
    for i, alpha in enumerate(_DEPTH_ALPHAS):
        t = i / 20
        r, g, b = (round(r1 + (r2 - r1) * t), round(g1 + (g2 - g1) * t), round(b1 + (b2 - b1) * t))
        ramp[f"{prefix}{i}"] = f"rgba({r}, {g}, {b}, {alpha:g})"
    return ramp


def _mode_pins(
    *,
    body_bg: str,
    text: str,
    title: str,
    muted: str,
    surface: str,
    surface_deep: str,
    accent: str,
    accent_text: str,
    grad: tuple[str, str],
    navbar: str,
    navbar_text: str,
    navbar_link: str,
    code_bg: str,
    code_text: str,
    code_border: str,
    pre_bg: str,
    pre_text: str,
    op_author: str,
    title_hover: str | None = None,
    light: bool = False,
) -> dict[str, str]:
    """Derive the high-visibility token set for one mode from a theme's core colors.

    Mirrors the default palette's structure (same alpha ladders, gradient shapes,
    surface translucency) so themed pages keep the default's visual hierarchy while
    carrying the theme's authentic palette. Tokens not covered here fall back to the
    theme's hue transform.
    """
    title_hover = title_hover or accent_text
    g1, g2 = grad
    grad2 = (_shade(g1, -0.06), _shade(g2, -0.06))
    surface_lo = _shade(surface, -0.03)
    pins = {
        "--body-bg": body_bg,
        "--body-text": text,
        "--navbar-bg": navbar,
        "--navbar-brand-text": navbar_text,
        "--navbar-nav-nav-link-text": navbar_link,
        "--links-title-text": title,
        "--links-title-hover-text": title_hover,
        "--body-a-text": accent_text,
        "--body-a-hover-text": _shade(accent_text, -0.08 if light else 0.08),
        "--navbar-a-text": navbar_text,
        "--navbar-a-hover-text": navbar_link,
        "--suggestion-item-hover-bg": g2,
        "--suggestion-item-hover-text": "#ffffff",
        "--submission-bg": _rgba_of(surface, 0.98),
        "--submission-border": f"1px solid {_rgba_of(accent, 0.25)}",
        "--submission-title-text": title,
        "--text-muted-text": muted,
        # accent alpha ladders (shared rgba vars + structural borders)
        "--primary-15": _rgba_of(accent, 0.15),
        "--primary-20": _rgba_of(accent, 0.2),
        "--primary-25": _rgba_of(accent, 0.25),
        "--primary-30": _rgba_of(accent, 0.3),
        "--primary-40": _rgba_of(accent, 0.4),
        "--primary-50": _rgba_of(accent, 0.5),
        "--dark-bg-90": _rgba_of(surface, 0.9),
        "--dark-bg-95": _rgba_of(surface, 0.95),
        "--gradient-primary": _grad(g1, g2),
        "--gradient-secondary": _grad(*grad2),
        "--btn-primary-bg": _grad(g1, g2),
        "--btn-primary-shadow": f"0 4px 15px {_rgba_of(accent, 0.4)}",
        "--btn-primary-bg-2": _grad(*grad2),
        "--btn-primary-shadow-2": f"0 6px 20px {_rgba_of(accent, 0.5)}",
        # comment thread structure
        "--deep-marker-text": _rgba_of(accent, 0.8),
        "--deep-marker-bg": _rgba_of(accent, 0.1),
        "--thread-line-border": f"2px solid {_rgba_of(accent, 0.5)}",
        "--comment-deep-border": f"2px solid {_rgba_of(accent, 0.8)}",
        "--comment-deep-border-left": f"2px solid {_rgba_of(accent, 0.8)}",
        "--comment-bg": _grad(_rgba_of(accent, 0.2), _rgba_of(_shade(accent, -0.08), 0.15)),
        "--comment-border": f"2px solid {_rgba_of(accent, 0.6)}",
        "--comment-shadow": f"0 0 20px {_rgba_of(accent, 0.4)}",
        # markdown
        "--md-blockquote-border-left": f"4px solid {accent_text}",
        "--md-blockquote-bg": _rgba_of(accent, 0.12),
        "--md-blockquote-text": text,
        "--md-code-border": f"1px solid {code_border}",
        "--md-code-bg": code_bg,
        "--md-code-text": code_text,
        "--md-pre-bg": pre_bg,
        "--md-pre-text": pre_text,
        # author / byline chips
        "--byline-author-text": accent_text,
        "--byline-author-bg": _rgba_of(accent, 0.1),
        "--byline-author-border": f"1px solid {_rgba_of(accent, 0.2)}",
        "--byline-author-text-2": _shade(accent_text, 0.1),
        "--byline-author-bg-2": _rgba_of(accent, 0.2),
        "--byline-author-border-2": _rgba_of(accent, 0.3),
        "--byline-author-shadow": f"0 4px 12px {_rgba_of(accent, 0.3)}",
        "--byline-author-bg-3": _rgba_of(accent, 0.25),
        "--author-text": accent_text,
        "--author-bg": _rgba_of(accent, 0.05),
        "--author-bg-2": _rgba_of(accent, 0.15),
        "--author-border": _rgba_of(accent, 0.2),
        "--author-shadow": f"0 2px 8px {_rgba_of(accent, 0.2)}",
        "--op-author-text": op_author,
        "--op-badge-text": accent_text,
        "--op-badge-bg": _rgba_of(accent, 0.15),
        "--op-badge-border": f"1px solid {_rgba_of(accent, 0.3)}",
        "--op-badge-shadow": f"0 1px 4px {_rgba_of(accent, 0.2)}",
        "--user-flair-bg": _rgba_of(accent, 0.15),
        "--badge-flair-bg": _grad(g1, g2),
        "--badge-flair-bg-2": _grad(*grad2),
        "--badge-flair-border": f"1px solid {_rgba_of(accent, 0.4)}",
        "--badge-flair-shadow": f"0 4px 12px {_rgba_of(accent, 0.4)}",
        "--badge-flair-shadow-2": f"0 6px 16px {_rgba_of(accent, 0.5)}",
        # cards & listing chrome
        "--links-link-border": f"1px solid {_rgba_of(accent, 0.2)}",
        "--links-link-shadow": f"0 8px 30px {_rgba_of(accent, 0.25)}",
        "--links-link-border-2": _rgba_of(accent, 0.3),
        "--card-shadow": f"0 12px 40px {_rgba_of(accent, 0.3)}",
        "--card-border": _rgba_of(accent, 0.4),
        "--card-header-bg": _grad(_rgba_of(surface, 0.98), _rgba_of(surface_lo, 0.99)),
        "--card-header-border-bottom": f"1px solid {_rgba_of(accent, 0.2)}",
        "--card-body-bg": _rgba_of(surface, 0.92),
        "--card-title-a-text": accent_text,
        "--card-title-a-text-2": _shade(accent_text, -0.08),
        "--card-title-a-bg": _grad(accent_text, accent),
        "--card-strong-text": title,
        "--card-collapsed-summary-bg": _rgba_of(surface, 0.5),
        "--subreddit-header-bg": _rgba_of(surface, 0.5),
        "--card-stat-section-bg": _rgba_of(accent, 0.05),
        "--expand-collapse-all-bg": _grad(*grad2),
        "--expand-collapse-all-shadow": f"0 4px 12px {_rgba_of(accent, 0.4)}",
        "--progress-bar-shadow": f"0 1px 3px {_rgba_of(accent, 0.4)}",
        "--progress-bar-bg": _shade(surface, 0.08 if not light else -0.08),
        "--badge-data-tooltip-shadow": f"0 4px 16px {_rgba_of(accent, 0.4)}",
        # alerts, tooltips, dropdowns
        "--alert-info-bg": _grad(_rgba_of(surface, 0.95), _rgba_of(surface_lo, 0.98)),
        "--alert-info-text": title,
        "--alert-heading-text": accent_text,
        "--data-tooltip-bg": _rgba_of(surface_deep if not light else surface, 0.98),
        "--data-tooltip-text": title,
        "--data-tooltip-border": f"1px solid {_rgba_of(accent, 0.3)}",
        "--dropdown-menu-bg": _rgba_of(surface, 0.98),
        "--dropdown-menu-border": f"1px solid {_rgba_of(accent, 0.3)}",
        "--dropdown-item-bg": _grad(g1, g2),
        # pagination
        "--pagination-page-link-bg": _rgba_of(surface, 0.95),
        "--pagination-page-link-text": accent_text,
        "--pagination-page-link-bg-2": _grad(g1, g2),
        "--disabled-page-link-bg": _rgba_of(surface, 0.3),
        "--disabled-page-link-text": _rgba_of(accent, 0.3),
        # search / forms
        "--suggestions-border-color": accent,
        "--suggestion-item-text": title,
        "--suggestion-item-bg": surface,
        "--suggestion-item-post-count-text": muted,
        "--subreddit-suggestions-bg": surface,
        "--form-control-border": f"2px solid {accent}" if not light else f"1px solid {code_border}",
        "--form-control-text": title,
        "--form-control-shadow": f"0 0 0 3px {_rgba_of(accent, 0.3)}",
        "--query-bg": code_bg,
        "--query-text": muted,
        "--search-progress-bg": _rgba_of(surface, 0.95),
        # nesting ramps
        "--comment-data-depth-bg": f"var(--comment-depth{'-light' if light else ''}-0)",
        "--comment-data-depth-border-left": f"2px solid {_rgba_of(accent, 0.4)}",
    }
    for i, alpha in enumerate(_DEPTH_BORDER_ALPHAS):
        suffix = "" if i == 0 else f"-{i + 1}"
        width = 1 if i < 9 else 2
        pins[f"--comment-data-depth-border{suffix}"] = f"{width}px solid {_rgba_of(accent, alpha)}"
    for i in range(1, 16):
        pins[f"--comment-data-depth-bg-{i + 1}"] = f"var(--comment-depth{'-light' if light else ''}-{i})"
    pins.update(_depth_ramp(surface, surface_deep, light=light))
    if light:
        pins.update({f"--comment-depth-{i}": _rgba_of(surface_deep, 1) for i in range(16, 21)})
        pins["--badge-secondary-bg"] = _grad(g1, g2)
        pins["--badge-secondary-shadow"] = f"0 2px 12px {_rgba_of(accent, 0.3)}"
    else:
        pins["--badge-primary-bg"] = _grad(g1, g2)
    return pins


def _hc_pins(bg: str, fg: str, accent: str) -> dict[str, str]:
    """High-contrast pins: solid surfaces, hard 2px borders, no translucency."""
    pins = {
        "--body-bg": bg,
        "--body-text": fg,
        "--navbar-bg": bg,
        "--navbar-brand-text": fg,
        "--navbar-nav-nav-link-text": accent,
        "--navbar-a-text": fg,
        "--navbar-a-hover-text": accent,
        "--body-a-text": accent,
        "--body-a-hover-text": fg,
        "--suggestion-item-hover-bg": accent,
        "--suggestion-item-hover-text": bg,
        "--links-title-text": fg,
        "--links-title-hover-text": accent,
        "--submission-bg": bg,
        "--submission-border": f"2px solid {fg}",
        "--submission-title-text": fg,
        "--text-muted-text": fg,
        "--card-body-bg": bg,
        "--card-header-bg": bg,
        "--card-border": fg,
        "--card-shadow": "none",
        "--card-header-border-bottom": f"2px solid {fg}",
        "--card-strong-text": fg,
        "--card-title-a-bg": f"linear-gradient(135deg, {accent} 0%, {accent} 100%)",
        "--card-collapsed-summary-bg": bg,
        "--subreddit-header-bg": bg,
        "--alert-info-bg": bg,
        "--alert-info-text": fg,
        "--dropdown-menu-bg": bg,
        "--dropdown-menu-border": f"2px solid {fg}",
        "--data-tooltip-bg": bg,
        "--data-tooltip-text": fg,
        "--data-tooltip-border": f"2px solid {fg}",
        "--pagination-page-link-bg": bg,
        "--pagination-page-link-text": accent,
        "--disabled-page-link-bg": bg,
        "--disabled-page-link-text": fg,
        "--md-blockquote-border-left": f"4px solid {accent}",
        "--md-blockquote-bg": bg,
        "--md-blockquote-text": fg,
        "--md-code-border": f"1px solid {fg}",
        "--md-code-bg": bg,
        "--md-code-text": accent,
        "--md-pre-bg": bg,
        "--md-pre-text": fg,
        "--form-control-border": f"2px solid {fg}",
        "--form-control-text": fg,
        "--suggestion-item-bg": bg,
        "--suggestion-item-text": fg,
        "--subreddit-suggestions-bg": bg,
        "--query-bg": bg,
        "--query-text": fg,
        "--search-progress-bg": bg,
        "--byline-author-text": accent,
        "--byline-author-bg": bg,
        "--byline-author-border": f"1px solid {accent}",
        "--byline-author-text-2": accent,
        "--byline-author-bg-2": bg,
        "--byline-author-border-2": accent,
        "--author-text": accent,
        "--author-bg": bg,
        "--author-bg-2": bg,
        "--author-border": accent,
        "--comment-header-text": fg,
        "--thread-line-border": f"2px solid {fg}",
        "--comment-deep-border": f"2px solid {fg}",
        "--comment-deep-border-left": f"2px solid {fg}",
        "--deep-marker-text": accent,
        "--deep-marker-bg": bg,
        "--comment-data-depth-border-left": f"2px solid {fg}",
    }
    is_dark = bg == "#000000"
    # .badge-flair text is white, so the badge surface must stay dark in both modes
    flair_bg = bg if is_dark else _grad(accent, accent)
    pins.update(
        {
            "--badge-flair-bg": flair_bg,
            "--badge-flair-bg-2": flair_bg,
            "--badge-flair-border": f"1px solid {accent if is_dark else fg}",
            "--badge-flair-shadow": "none",
            "--badge-flair-shadow-2": "none",
            # .dropdown-item:hover text is hardcoded white; keep its surface dark
            "--dropdown-item-bg": "#333333" if is_dark else _grad(accent, accent),
        }
    )
    ramp = "rgba(0, 0, 0, 1)" if is_dark else "rgba(255, 255, 255, 1)"
    prefix = "--comment-depth-" if is_dark else "--comment-depth-light-"
    pins.update({f"{prefix}{i}": ramp for i in range(21)})
    if not is_dark:
        pins.update({f"--comment-depth-{i}": ramp for i in range(16, 21)})
    for i in range(15):
        suffix = "" if i == 0 else f"-{i + 1}"
        pins[f"--comment-data-depth-border{suffix}"] = f"1px solid {fg}"
    return pins


# Per-theme recipe: color transforms applied to the default palette, explicit
# anchor pins (spec values from roadmap/04-visual-themes.md), and the hue band
# the --accent-color override re-targets AFTER the theme transform ran.
_THEME_BUILDERS: dict[str, dict] = {
    "default": {
        "dark_fn": None,
        "light_fn": None,
        "pins_dark": {},
        "pins_light": {},
        "accent_band_dark": (185, 300),
        "accent_band_light": (185, 300),
    },
    "sepia": {
        "dark_fn": _sepia,
        "light_fn": _sepia,
        "pins_dark": _mode_pins(
            body_bg="linear-gradient(135deg, #1f1910 0%, #2c2416 50%, #271f12 100%)",
            text="#e8dcc8",
            title="#f3ead6",
            muted="rgba(232, 220, 200, 0.65)",
            surface="#2c2416",
            surface_deep="#191408",
            accent="#c8963e",
            accent_text="#d4a76a",
            title_hover="#e0b878",
            grad=("#b98a3e", "#8a6420"),
            navbar="linear-gradient(135deg, #2c2416 0%, #3a2f1d 100%)",
            navbar_text="#f3ead6",
            navbar_link="#d4a76a",
            code_bg="#33291a",
            code_text="#d9b26a",
            code_border="#4d3f28",
            pre_bg="#191408",
            pre_text="#e8dcc8",
            op_author="#c8963e",
        ),
        "pins_light": _mode_pins(
            body_bg="linear-gradient(135deg, #f5f0e8 0%, #e8dcc4 100%)",
            text="#3d3425",
            title="#2e2718",
            muted="rgba(61, 52, 37, 0.65)",
            surface="#faf6ee",
            surface_deep="#e4dac4",
            accent="#8b6914",
            accent_text="#8b6914",
            title_hover="#6b4f0f",
            grad=("#a07b1c", "#77590e"),
            navbar="linear-gradient(135deg, #8b6914 0%, #6b4f0f 100%)",
            navbar_text="#f5f0e8",
            navbar_link="#f0e2c4",
            code_bg="#efe7d5",
            code_text="#77590e",
            code_border="#d9cba8",
            pre_bg="#f3ecdc",
            pre_text="#4a3f2a",
            op_author="#a07b1c",
            light=True,
        ),
        "accent_band_dark": (15, 75),
        "accent_band_light": (15, 75),
    },
    "high-contrast": {
        "dark_fn": _hc_dark,
        "light_fn": _hc_light,
        "pins_dark": _hc_pins("#000000", "#ffffff", "#ffff00"),
        "pins_light": _hc_pins("#ffffff", "#000000", "#0000cc"),
        "accent_band_dark": (45, 75),
        "accent_band_light": (220, 260),
    },
    # Arctic blue-gray (nordtheme.com): desaturated frost accents on polar-night
    # surfaces. Closest relative of the default palette.
    "nord": {
        "dark_fn": _restyle((185, 300), 213, sat_scale=0.55),
        "light_fn": _restyle((185, 300), 213, sat_scale=0.6),
        "pins_dark": _mode_pins(
            body_bg="linear-gradient(135deg, #2e3440 0%, #3b4252 50%, #343c4a 100%)",
            text="#d8dee9",
            title="#eceff4",
            muted="rgba(216, 222, 233, 0.65)",
            surface="#3b4252",
            surface_deep="#242933",
            accent="#88c0d0",
            accent_text="#88c0d0",
            title_hover="#8fbcbb",
            grad=("#5e81ac", "#4c6a92"),
            navbar="linear-gradient(135deg, #3b4252 0%, #434c5e 100%)",
            navbar_text="#eceff4",
            navbar_link="#88c0d0",
            code_bg="#3b4252",
            code_text="#88c0d0",
            code_border="#4c566a",
            pre_bg="#2e3440",
            pre_text="#d8dee9",
            op_author="#81a1c1",
        ),
        "pins_light": _mode_pins(
            body_bg="linear-gradient(135deg, #eceff4 0%, #e5e9f0 100%)",
            text="#2e3440",
            title="#2e3440",
            muted="rgba(46, 52, 64, 0.6)",
            surface="#ffffff",
            surface_deep="#d8dee9",
            accent="#5e81ac",
            accent_text="#5e81ac",
            title_hover="#4c6a92",
            grad=("#5e81ac", "#4c6a92"),
            navbar="linear-gradient(135deg, #5e81ac 0%, #4c6a92 100%)",
            navbar_text="#eceff4",
            navbar_link="#d8dee9",
            code_bg="#e5e9f0",
            code_text="#4c566a",
            code_border="#d8dee9",
            pre_bg="#eceff4",
            pre_text="#2e3440",
            op_author="#5e81ac",
            light=True,
        ),
        "accent_band_dark": (195, 230),
        "accent_band_light": (195, 230),
    },
    # Precision palette (ethanschoonover.com/solarized): teal-leaning dark base,
    # warm paper light base, measured blue accents.
    "solarized": {
        "dark_fn": _restyle((185, 300), 203, sat_scale=0.9),
        "light_fn": _restyle((185, 300), 203, sat_scale=0.95),
        "pins_dark": _mode_pins(
            body_bg="linear-gradient(135deg, #002b36 0%, #073642 50%, #032f3a 100%)",
            text="#93a1a1",
            title="#eee8d5",
            muted="rgba(131, 148, 150, 0.7)",
            surface="#073642",
            surface_deep="#00222b",
            accent="#268bd2",
            accent_text="#4ba3dd",
            title_hover="#2aa198",
            grad=("#268bd2", "#1e6ea6"),
            navbar="linear-gradient(135deg, #073642 0%, #0a4050 100%)",
            navbar_text="#eee8d5",
            navbar_link="#2aa198",
            code_bg="#073642",
            code_text="#2aa198",
            code_border="#586e75",
            pre_bg="#002b36",
            pre_text="#93a1a1",
            op_author="#b58900",
        ),
        "pins_light": _mode_pins(
            body_bg="linear-gradient(135deg, #fdf6e3 0%, #eee8d5 100%)",
            text="#657b83",
            title="#073642",
            muted="rgba(101, 123, 131, 0.75)",
            surface="#fffdf6",
            surface_deep="#eee8d5",
            accent="#268bd2",
            accent_text="#268bd2",
            title_hover="#1e6ea6",
            grad=("#268bd2", "#1a6091"),
            navbar="linear-gradient(135deg, #268bd2 0%, #1a6091 100%)",
            navbar_text="#fdf6e3",
            navbar_link="#eee8d5",
            code_bg="#eee8d5",
            code_text="#cb4b16",
            code_border="#d3cbb7",
            pre_bg="#f7f0dd",
            pre_text="#586e75",
            op_author="#b58900",
            light=True,
        ),
        "accent_band_dark": (190, 215),
        "accent_band_light": (190, 215),
    },
    # draculatheme.com: purple/pink accents on dark slate.
    "dracula": {
        "dark_fn": _restyle((185, 300), 265, sat_scale=1.0),
        "light_fn": _restyle((185, 300), 263, sat_scale=0.9),
        "pins_dark": _mode_pins(
            body_bg="linear-gradient(135deg, #282a36 0%, #1e1f29 50%, #24262f 100%)",
            text="#f8f8f2",
            title="#f8f8f2",
            muted="rgba(248, 248, 242, 0.6)",
            surface="#2c2e3c",
            surface_deep="#1e1f29",
            accent="#bd93f9",
            accent_text="#bd93f9",
            title_hover="#ff79c6",
            grad=("#bd93f9", "#9d6ef0"),
            navbar="linear-gradient(135deg, #282a36 0%, #343747 100%)",
            navbar_text="#f8f8f2",
            navbar_link="#8be9fd",
            code_bg="#343746",
            code_text="#50fa7b",
            code_border="#44475a",
            pre_bg="#21222c",
            pre_text="#f8f8f2",
            op_author="#ffb86c",
        ),
        "pins_light": _mode_pins(
            body_bg="linear-gradient(135deg, #f8f8f2 0%, #efeff6 100%)",
            text="#282a36",
            title="#282a36",
            muted="rgba(40, 42, 54, 0.6)",
            surface="#ffffff",
            surface_deep="#dfdfe8",
            accent="#644ac9",
            accent_text="#644ac9",
            title_hover="#a3399c",
            grad=("#644ac9", "#8a3fa8"),
            navbar="linear-gradient(135deg, #644ac9 0%, #8a3fa8 100%)",
            navbar_text="#f8f8f2",
            navbar_link="#e9e4fb",
            code_bg="#f1eff8",
            code_text="#644ac9",
            code_border="#d8d4ea",
            pre_bg="#f4f2fa",
            pre_text="#383a59",
            op_author="#a3399c",
            light=True,
        ),
        "accent_band_dark": (240, 290),
        "accent_band_light": (240, 290),
    },
    # github.com/morhetz/gruvbox: amber/orange retro on gray-brown. Differs from
    # sepia via the neutral gray-brown base and hotter orange accents.
    "gruvbox": {
        "dark_fn": _restyle((185, 300), 24, sat_scale=0.95),
        "light_fn": _restyle((185, 300), 24, sat_scale=0.9),
        "pins_dark": _mode_pins(
            body_bg="linear-gradient(135deg, #1d2021 0%, #282828 50%, #232627 100%)",
            text="#ebdbb2",
            title="#fbf1c7",
            muted="rgba(235, 219, 178, 0.65)",
            surface="#3c3836",
            surface_deep="#211f1e",
            accent="#fabd2f",
            accent_text="#fabd2f",
            title_hover="#fe8019",
            grad=("#d79921", "#b57614"),
            navbar="linear-gradient(135deg, #3c3836 0%, #504945 100%)",
            navbar_text="#fbf1c7",
            navbar_link="#fabd2f",
            code_bg="#3c3836",
            code_text="#b8bb26",
            code_border="#504945",
            pre_bg="#1d2021",
            pre_text="#ebdbb2",
            op_author="#fe8019",
        ),
        "pins_light": _mode_pins(
            body_bg="linear-gradient(135deg, #fbf1c7 0%, #f2e5bc 100%)",
            text="#3c3836",
            title="#282828",
            muted="rgba(60, 56, 54, 0.65)",
            surface="#fffbeb",
            surface_deep="#e8dcb2",
            accent="#b57614",
            accent_text="#b57614",
            title_hover="#af3a03",
            grad=("#d79921", "#af3a03"),
            navbar="linear-gradient(135deg, #d79921 0%, #b57614 100%)",
            navbar_text="#fbf1c7",
            navbar_link="#fdf3ce",
            code_bg="#f2e5bc",
            code_text="#79740e",
            code_border="#d5c4a1",
            pre_bg="#f7ecc8",
            pre_text="#3c3836",
            op_author="#af3a03",
            light=True,
        ),
        "accent_band_dark": (10, 50),
        "accent_band_light": (10, 50),
    },
    # Neon magenta accents over deep violet surfaces; icy text.
    "cyberpunk": {
        "dark_fn": _restyle_split((185, 300), 255, 318, threshold=0.45, surface_sat=1.2, accent_sat_floor=0.85),
        "light_fn": _restyle((185, 300), 318, sat_scale=1.0, sat_floor=0.6),
        "pins_dark": _mode_pins(
            body_bg="linear-gradient(135deg, #0a0a14 0%, #14102a 50%, #0e0b1d 100%)",
            text="#d6f6ff",
            title="#eafcff",
            muted="rgba(214, 246, 255, 0.6)",
            surface="#171232",
            surface_deep="#080614",
            accent="#ff2ec4",
            accent_text="#ff5ad1",
            title_hover="#00f0ff",
            grad=("#ff2ec4", "#7a1fff"),
            navbar="linear-gradient(135deg, #0d0b1e 0%, #1b1440 100%)",
            navbar_text="#00f0ff",
            navbar_link="#ff5ad1",
            code_bg="#1b1440",
            code_text="#00f0ff",
            code_border="#3a2a6e",
            pre_bg="#0d0b1e",
            pre_text="#c8f4ff",
            op_author="#fcee0a",
        ),
        "pins_light": _mode_pins(
            body_bg="linear-gradient(135deg, #fdfbff 0%, #f5ecfa 100%)",
            text="#1a1025",
            title="#1a1025",
            muted="rgba(26, 16, 37, 0.6)",
            surface="#ffffff",
            surface_deep="#e9def0",
            accent="#cc0099",
            accent_text="#cc0099",
            title_hover="#7a1fff",
            grad=("#cc0099", "#7a1fff"),
            navbar="linear-gradient(135deg, #cc0099 0%, #7a1fff 100%)",
            navbar_text="#ffffff",
            navbar_link="#ffe0f5",
            code_bg="#f5ecfa",
            code_text="#cc0099",
            code_border="#e6c8e0",
            pre_bg="#f8f4fc",
            pre_text="#2a1f35",
            op_author="#7a1fff",
            light=True,
        ),
        "accent_band_dark": (280, 340),
        "accent_band_light": (280, 340),
    },
    # True-black surfaces for OLED displays; default blue accents untouched.
    "midnight": {
        "dark_fn": _midnight_dark,
        "light_fn": None,
        "pins_dark": _mode_pins(
            body_bg="#000000",
            text="#d4d4d8",
            title="#e4e4e7",
            muted="rgba(212, 212, 216, 0.6)",
            surface="#0a0a0c",
            surface_deep="#020203",
            accent="#3b82f6",
            accent_text="#60a5fa",
            grad=("#3b82f6", "#1d4ed8"),
            navbar="linear-gradient(135deg, #0a0a0c 0%, #111114 100%)",
            navbar_text="#e4e4e7",
            navbar_link="#60a5fa",
            code_bg="#0f0f11",
            code_text="#93c5fd",
            code_border="#1f2937",
            pre_bg="#050506",
            pre_text="#d4d4d8",
            op_author="#3b82f6",
        ),
        "pins_light": {},
        "accent_band_dark": (185, 300),
        "accent_band_light": (185, 300),
    },
    # Nostalgic old.reddit look: classic link blue, flat white cards (light),
    # old night-mode grays (dark).
    "old-reddit": {
        "dark_fn": _restyle((185, 300), 203, sat_scale=0.5),
        "light_fn": _restyle((185, 300), 207, sat_scale=0.9),
        "pins_dark": _mode_pins(
            body_bg="#1a1a1b",
            text="#d7dadc",
            title="#d7dadc",
            muted="rgba(215, 218, 220, 0.6)",
            surface="#272729",
            surface_deep="#161617",
            accent="#24a0ed",
            accent_text="#4fbcff",
            grad=("#0079d3", "#005ba1"),
            navbar="linear-gradient(135deg, #1a1a1b 0%, #222224 100%)",
            navbar_text="#d7dadc",
            navbar_link="#4fbcff",
            code_bg="#272729",
            code_text="#4fbcff",
            code_border="#343536",
            pre_bg="#141415",
            pre_text="#d7dadc",
            op_author="#0079d3",
        ),
        "pins_light": _mode_pins(
            body_bg="#ffffff",
            text="#1a1a1b",
            title="#336699",
            muted="rgba(26, 26, 27, 0.55)",
            surface="#ffffff",
            surface_deep="#eaedf0",
            accent="#336699",
            accent_text="#336699",
            title_hover="#1c4670",
            grad=("#5f99cf", "#4a83b8"),
            navbar="linear-gradient(135deg, #cee3f8 0%, #cee3f8 100%)",
            navbar_text="#1a4b8c",
            navbar_link="#336699",
            code_bg="#f5f5f5",
            code_text="#444444",
            code_border="#e1e1e1",
            pre_bg="#f7f7f8",
            pre_text="#1a1a1b",
            op_author="#0055df",
            light=True,
        ),
        "accent_band_dark": (190, 220),
        "accent_band_light": (190, 220),
    },
    # Green-on-black CRT phosphor (dark) / green-on-paper (light).
    "phosphor": {
        "dark_fn": _restyle((185, 300), 120, sat_scale=1.0, sat_floor=0.5),
        "light_fn": _restyle((185, 300), 130, sat_scale=0.9),
        "pins_dark": _mode_pins(
            body_bg="#000000",
            text="#33ff33",
            title="#66ff66",
            muted="rgba(51, 255, 51, 0.55)",
            surface="#001400",
            surface_deep="#000500",
            accent="#33ff33",
            accent_text="#33ff33",
            title_hover="#99ff99",
            grad=("#00b41e", "#007a12"),
            navbar="linear-gradient(135deg, #001400 0%, #002200 100%)",
            navbar_text="#33ff33",
            navbar_link="#66ff66",
            code_bg="#001a00",
            code_text="#66ff66",
            code_border="#0d660d",
            pre_bg="#000d00",
            pre_text="#33ff33",
            op_author="#99ff99",
        ),
        "pins_light": _mode_pins(
            body_bg="linear-gradient(135deg, #f2fbf2 0%, #e4f5e4 100%)",
            text="#0a5c0a",
            title="#084d08",
            muted="rgba(10, 92, 10, 0.65)",
            surface="#ffffff",
            surface_deep="#def0de",
            accent="#0d7a0d",
            accent_text="#0d7a0d",
            title_hover="#0a5c0a",
            grad=("#128a12", "#0a5c0a"),
            navbar="linear-gradient(135deg, #128a12 0%, #0a5c0a 100%)",
            navbar_text="#f2fbf2",
            navbar_link="#d2f0d2",
            code_bg="#e4f5e4",
            code_text="#0a5c0a",
            code_border="#b8dcb8",
            pre_bg="#eef8ee",
            pre_text="#143f14",
            op_author="#128a12",
            light=True,
        ),
        "accent_band_dark": (90, 150),
        "accent_band_light": (90, 150),
    },
}

THEME_NAMES: tuple[str, ...] = tuple(_THEME_BUILDERS)


def validate_accent_color(value: str) -> str:
    """Normalize an accent color to '#rrggbb'; raise ValueError for anything else."""
    m = re.fullmatch(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})", value.strip())
    if not m:
        raise ValueError(f"invalid accent color {value!r} (expected hex like '#8b6914')")
    hx = m.group(1).lower()
    if len(hx) == 3:
        hx = "".join(c * 2 for c in hx)
    return f"#{hx}"


def _compose(*fns: ColorFn | None) -> ColorFn | None:
    chain = [f for f in fns if f is not None]
    if not chain:
        return None

    def fn(r: int, g: int, b: int) -> tuple[int, int, int]:
        for f in chain:
            r, g, b = f(r, g, b)
        return r, g, b

    return fn


def build_palette(theme: str = "default", accent_color: str | None = None) -> dict[str, dict[str, str]]:
    """Materialize a theme's full dark/light token dicts.

    Non-default transforms also re-skin the mode-shared BASE_PALETTE entries they
    change (gradients, --primary-*, comment-depth ramps); those overrides ride
    along in both mode dicts so the toggle/media blocks stay self-contained.
    """
    if theme not in _THEME_BUILDERS:
        raise ValueError(f"unknown theme {theme!r} (available: {', '.join(THEME_NAMES)})")
    spec = _THEME_BUILDERS[theme]

    accent_hue = None
    if accent_color is not None:
        r, g, b = (int(validate_accent_color(accent_color)[i : i + 2], 16) for i in (1, 3, 5))
        accent_hue = _hsl(r, g, b)[0]

    palette: dict[str, dict[str, str]] = {}
    for mode, defaults in (("dark", DEFAULT_DARK), ("light", DEFAULT_LIGHT)):
        accent_fn = _hue_to(spec[f"accent_band_{mode}"], accent_hue) if accent_hue is not None else None
        fn = _compose(spec[f"{mode}_fn"], accent_fn)
        tokens = {k: _map_colors(v, fn) for k, v in defaults.items()}
        tokens.update({k: w for k, v in BASE_PALETTE.items() if (w := _map_colors(v, fn)) != v})
        tokens.update({k: _map_colors(v, accent_fn) for k, v in spec[f"pins_{mode}"].items()})
        palette[mode] = tokens
    return palette


# Materialized palettes (no accent override) - the spec's "themes as Python dicts"
THEMES: dict[str, dict[str, dict[str, str]]] = {name: build_palette(name) for name in THEME_NAMES}

_TOGGLE_HEADER_RE = re.compile(
    r"(#dark-theme-toggle:checked\s*~\s*body,\s*\n#dark-theme-toggle:checked\s*~\s*\.site-content)\s*\{[^}]*\}"
)
_ROOT_BLOCK_RE = re.compile(r":root\s*\{[^}]*\}")


def _render_decls(tokens: dict[str, str], indent: str = "  ") -> str:
    return "\n".join(f"{indent}{k}: {v};" for k, v in tokens.items())


def _replace_root_after(css: str, banner: str, tokens: dict[str, str]) -> str:
    """Replace the first :root block following the given banner comment."""
    idx = css.index(banner)
    m = _ROOT_BLOCK_RE.search(css, idx)
    if m is None:
        raise ValueError(f"no :root block found after banner {banner!r}")
    return css[: m.start()] + ":root {\n" + _render_decls(tokens) + "\n  }" + css[m.end() :]


def apply_theme_to_css(css: str, theme: str = "default", accent_color: str | None = None) -> str:
    """Rewrite the three token blocks (dark :root, light toggle, light media) for the theme.

    Used at static export time so token values are baked into the shipped CSS.
    Comments inside the blocks are dropped; everything else is untouched.
    """
    palette = build_palette(theme, accent_color)
    css = _replace_root_after(css, "DESIGN TOKENS", palette["dark"])
    m = _TOGGLE_HEADER_RE.search(css)
    if m is None:
        raise ValueError("dark-theme-toggle token block not found in CSS")
    css = css[: m.start()] + m.group(1) + " {\n" + _render_decls(palette["light"]) + "\n}" + css[m.end() :]
    return _replace_root_after(css, "SYSTEM COLOR-SCHEME SUPPORT", palette["light"])


def render_inline_theme_css(theme: str = "default", accent_color: str | None = None) -> str:
    """Token blocks for dynamic mode's inline <style>, placed after the stylesheet link.

    Returns '' when the defaults already baked into the static CSS apply, so the
    default configuration serves byte-identical pages with no extra block.
    """
    if theme == "default" and accent_color is None:
        return ""
    palette = build_palette(theme, accent_color)
    dark = _render_decls(palette["dark"])
    light = _render_decls(palette["light"])
    return (
        f":root {{\n{dark}\n}}\n"
        f"@media (prefers-color-scheme: light) {{\n:root {{\n{light}\n}}\n}}\n"
        f"#dark-theme-toggle:checked ~ body,\n#dark-theme-toggle:checked ~ .site-content {{\n{light}\n}}"
    )
