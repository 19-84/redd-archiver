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
        "pins_dark": {
            "--body-bg": "linear-gradient(135deg, #1f1910 0%, #2c2416 50%, #271f12 100%)",
            "--body-text": "#e8dcc8",
        },
        "pins_light": {
            "--body-bg": "linear-gradient(135deg, #f5f0e8 0%, #e8dcc4 100%)",
            "--body-text": "#3d3425",
        },
        "accent_band_dark": (15, 75),
        "accent_band_light": (15, 75),
    },
    "high-contrast": {
        "dark_fn": _hc_dark,
        "light_fn": _hc_light,
        "pins_dark": {"--body-bg": "#000000", "--body-text": "#ffffff"},
        "pins_light": {"--body-bg": "#ffffff", "--body-text": "#000000"},
        "accent_band_dark": (45, 75),
        "accent_band_light": (220, 260),
    },
    # Arctic blue-gray (nordtheme.com): desaturated frost accents on polar-night
    # surfaces. Closest relative of the default palette.
    "nord": {
        "dark_fn": _restyle((185, 300), 213, sat_scale=0.55),
        "light_fn": _restyle((185, 300), 213, sat_scale=0.6),
        "pins_dark": {
            "--body-bg": "linear-gradient(135deg, #2e3440 0%, #3b4252 50%, #343c4a 100%)",
            "--body-text": "#d8dee9",
        },
        "pins_light": {
            "--body-bg": "linear-gradient(135deg, #eceff4 0%, #e5e9f0 100%)",
            "--body-text": "#2e3440",
        },
        "accent_band_dark": (195, 230),
        "accent_band_light": (195, 230),
    },
    # Precision palette (ethanschoonover.com/solarized): teal-leaning dark base,
    # warm paper light base, measured blue accents.
    "solarized": {
        "dark_fn": _restyle((185, 300), 203, sat_scale=0.9),
        "light_fn": _restyle((185, 300), 203, sat_scale=0.95),
        "pins_dark": {
            "--body-bg": "linear-gradient(135deg, #002b36 0%, #073642 50%, #032f3a 100%)",
            "--body-text": "#93a1a1",
        },
        "pins_light": {
            "--body-bg": "linear-gradient(135deg, #fdf6e3 0%, #eee8d5 100%)",
            "--body-text": "#657b83",
        },
        "accent_band_dark": (190, 215),
        "accent_band_light": (190, 215),
    },
    # draculatheme.com: purple/pink accents on dark slate.
    "dracula": {
        "dark_fn": _restyle((185, 300), 265, sat_scale=1.0),
        "light_fn": _restyle((185, 300), 263, sat_scale=0.9),
        "pins_dark": {
            "--body-bg": "linear-gradient(135deg, #282a36 0%, #1e1f29 50%, #24262f 100%)",
            "--body-text": "#f8f8f2",
        },
        "pins_light": {
            "--body-bg": "linear-gradient(135deg, #f8f8f2 0%, #efeff6 100%)",
            "--body-text": "#282a36",
        },
        "accent_band_dark": (240, 290),
        "accent_band_light": (240, 290),
    },
    # github.com/morhetz/gruvbox: amber/orange retro on gray-brown. Differs from
    # sepia via the neutral gray-brown base and hotter orange accents.
    "gruvbox": {
        "dark_fn": _restyle((185, 300), 24, sat_scale=0.95),
        "light_fn": _restyle((185, 300), 24, sat_scale=0.9),
        "pins_dark": {
            "--body-bg": "linear-gradient(135deg, #1d2021 0%, #282828 50%, #232627 100%)",
            "--body-text": "#ebdbb2",
        },
        "pins_light": {
            "--body-bg": "linear-gradient(135deg, #fbf1c7 0%, #f2e5bc 100%)",
            "--body-text": "#3c3836",
        },
        "accent_band_dark": (10, 50),
        "accent_band_light": (10, 50),
    },
    # Neon magenta accents over deep violet surfaces; icy text.
    "cyberpunk": {
        "dark_fn": _restyle_split((185, 300), 255, 318, threshold=0.45, surface_sat=1.2, accent_sat_floor=0.85),
        "light_fn": _restyle((185, 300), 318, sat_scale=1.0, sat_floor=0.6),
        "pins_dark": {
            "--body-bg": "linear-gradient(135deg, #0a0a14 0%, #14102a 50%, #0e0b1d 100%)",
            "--body-text": "#d6f6ff",
        },
        "pins_light": {
            "--body-bg": "linear-gradient(135deg, #fdfbff 0%, #f5ecfa 100%)",
            "--body-text": "#1a1025",
        },
        "accent_band_dark": (280, 340),
        "accent_band_light": (280, 340),
    },
    # True-black surfaces for OLED displays; default blue accents untouched.
    "midnight": {
        "dark_fn": _midnight_dark,
        "light_fn": None,
        "pins_dark": {"--body-bg": "#000000", "--body-text": "#d4d4d8"},
        "pins_light": {},
        "accent_band_dark": (185, 300),
        "accent_band_light": (185, 300),
    },
    # Nostalgic old.reddit look: classic link blue, flat white cards (light),
    # old night-mode grays (dark).
    "old-reddit": {
        "dark_fn": _restyle((185, 300), 203, sat_scale=0.5),
        "light_fn": _restyle((185, 300), 207, sat_scale=0.9),
        "pins_dark": {"--body-bg": "#1a1a1b", "--body-text": "#d7dadc"},
        "pins_light": {"--body-bg": "#ffffff", "--body-text": "#1a1a1b"},
        "accent_band_dark": (190, 220),
        "accent_band_light": (190, 220),
    },
    # Green-on-black CRT phosphor (dark) / green-on-paper (light).
    "phosphor": {
        "dark_fn": _restyle((185, 300), 120, sat_scale=1.0, sat_floor=0.5),
        "light_fn": _restyle((185, 300), 130, sat_scale=0.9),
        "pins_dark": {"--body-bg": "#000000", "--body-text": "#33ff33"},
        "pins_light": {
            "--body-bg": "linear-gradient(135deg, #f2fbf2 0%, #e4f5e4 100%)",
            "--body-text": "#0a5c0a",
        },
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
