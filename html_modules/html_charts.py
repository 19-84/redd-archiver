# ABOUTME: Server-rendered SVG charts — zero-JavaScript visualizations for
# ABOUTME: archive pages (Feature 7 Phase 5: subscriber history sparkline).
"""Inline SVG chart rendering.

The archive's zero-JavaScript design rules out client-side chart libraries;
these helpers render small, self-contained SVG fragments at generation time
(static export) or request time (dynamic mode).
"""

from __future__ import annotations

from typing import Any

# Downsample long series to roughly this many points — a 5-year daily series
# at full resolution bloats pages for no visible gain at sparkline size.
_MAX_POINTS = 120


def _downsample(series: list[tuple[Any, int]], max_points: int = _MAX_POINTS) -> list[tuple[Any, int]]:
    if len(series) <= max_points:
        return series
    step = len(series) / max_points
    sampled = [series[int(i * step)] for i in range(max_points)]
    if sampled[-1] != series[-1]:
        sampled.append(series[-1])
    return sampled


def subscriber_sparkline(series: list[dict[str, Any]], width: int = 600, height: int = 80) -> str:
    """Render a (date, count) series as an inline SVG area sparkline.

    Returns "" for series too short to draw. The SVG uses the theme's accent
    via currentColor, so it follows dark/light mode without extra tokens.
    """
    points = [(row["date"], int(row["count"])) for row in series if row.get("count") is not None]
    if len(points) < 2:
        return ""
    points = _downsample(points)

    counts = [c for _, c in points]
    lo, hi = min(counts), max(counts)
    span = (hi - lo) or 1
    pad = 4
    inner_w = width - 2 * pad
    inner_h = height - 2 * pad

    coords = []
    last_i = len(points) - 1
    for i, (_, count) in enumerate(points):
        x = pad + (i / last_i) * inner_w
        y = pad + (1 - (count - lo) / span) * inner_h
        coords.append(f"{x:.1f},{y:.1f}")

    line = " ".join(coords)
    area = f"{pad:.1f},{height - pad:.1f} {line} {width - pad:.1f},{height - pad:.1f}"
    first_date, last_date = points[0][0], points[-1][0]
    return (
        f'<svg class="subscriber-sparkline" viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'role="img" aria-label="Subscribers from {first_date} to {last_date}: '
        f'low {lo:,}, high {hi:,}" preserveAspectRatio="none">'
        f'<polygon points="{area}" fill="currentColor" opacity="0.15"/>'
        f'<polyline points="{line}" fill="none" stroke="currentColor" stroke-width="1.5"/>'
        f"</svg>"
    )
