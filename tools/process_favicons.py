#!/usr/bin/env python3
"""
ABOUTME: Generate web-optimized favicons from source images.
ABOUTME: Creates favicon.ico, favicon.svg, apple-touch-icon.png, favicon-192.png, favicon-512.png
"""

from PIL import Image
import shutil
from pathlib import Path
import sys


def process_favicons(source_dir: Path, output_dir: Path):
    """
    Process favicon source files into web-ready formats.

    Args:
        source_dir: Directory containing source PNG/SVG files
        output_dir: Directory to write processed favicons
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Processing favicons from {source_dir} to {output_dir}")

    # Copy SVG directly (already optimized)
    svg_source = source_dir / "128x128-noun-folder-650-FF001C.svg"
    if svg_source.exists():
        shutil.copy(svg_source, output_dir / "favicon.svg")
        print("✓ favicon.svg copied")
    else:
        print(f"⚠ Warning: {svg_source} not found")

    # Load source images
    try:
        img_512 = Image.open(source_dir / "512x512-noun-folder-650-FF001C.png")
        img_128 = Image.open(source_dir / "128x128-noun-folder-650-FF001C.png")
    except FileNotFoundError as e:
        print(f"✗ Error: Required source image not found: {e}")
        sys.exit(1)

    # Apple touch icon (180x180 from 512x512 source)
    print("Generating apple-touch-icon.png (180x180)...")
    apple_touch = img_512.resize((180, 180), Image.Resampling.LANCZOS)
    apple_touch.save(output_dir / "apple-touch-icon.png", optimize=True)
    print("✓ apple-touch-icon.png")

    # Android icons (192x192, 512x512)
    print("Generating Android icons...")
    img_512.resize((192, 192), Image.Resampling.LANCZOS).save(
        output_dir / "favicon-192.png", optimize=True
    )
    print("✓ favicon-192.png")

    shutil.copy(
        source_dir / "512x512-noun-folder-650-FF001C.png",
        output_dir / "favicon-512.png"
    )
    print("✓ favicon-512.png")

    # Multi-resolution favicon.ico (16x16, 32x32, 48x48)
    print("Generating multi-resolution favicon.ico...")
    sizes = [(16, 16), (32, 32), (48, 48)]
    icons = [img_128.resize(size, Image.Resampling.LANCZOS) for size in sizes]

    # Save as ICO with all sizes
    icons[0].save(
        output_dir / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=icons[1:]
    )
    print("✓ favicon.ico (16x16, 32x32, 48x48)")

    print(f"\n✓ All favicons generated successfully in {output_dir}")
    print("\nGenerated files:")
    for f in sorted(output_dir.glob("favicon*")) + sorted(output_dir.glob("apple-touch*")):
        size = f.stat().st_size
        print(f"  - {f.name} ({size:,} bytes)")


if __name__ == "__main__":
    # Default paths
    script_dir = Path(__file__).parent.parent
    source_dir = script_dir / "seo-assets" / "source"
    output_dir = script_dir / "seo-assets" / "defaults"

    # Allow command-line override
    if len(sys.argv) > 1:
        source_dir = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_dir = Path(sys.argv[2])

    process_favicons(source_dir, output_dir)
