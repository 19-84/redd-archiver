# ABOUTME: CSS minification utilities for Redd-Archiver build optimization
# ABOUTME: Provides functions to minify CSS files during static asset copying

import rcssmin
import os
from utils.console_output import print_info, print_success, print_error


def minify_css_file(input_path, output_path):
    """
    Minify a single CSS file.

    Args:
        input_path: Absolute path to source CSS file
        output_path: Absolute path to output minified CSS file

    Returns:
        tuple: (original_size, minified_size) in bytes

    Raises:
        FileNotFoundError: If input file doesn't exist
        IOError: If unable to read or write files
    """
    try:
        # Read source CSS
        with open(input_path, 'r', encoding='utf-8') as f:
            css = f.read()

        original_size = len(css)

        # Minify CSS (keep_bang_comments preserves /*! ... */ license comments)
        minified = rcssmin.cssmin(css, keep_bang_comments=True)

        minified_size = len(minified)

        # Write minified CSS
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(minified)

        return original_size, minified_size

    except FileNotFoundError as e:
        raise FileNotFoundError(f"CSS source file not found: {input_path}") from e
    except IOError as e:
        raise IOError(f"Failed to minify CSS {input_path}: {e}") from e


def minify_css_directory(input_dir, output_dir, verbose=True):
    """
    Minify all CSS files in a directory (non-recursive).

    Args:
        input_dir: Source directory containing CSS files
        output_dir: Output directory for minified CSS files
        verbose: Print progress messages (default: True)

    Returns:
        dict: Statistics with keys:
            - 'files_processed': Number of CSS files minified
            - 'total_original_size': Total size before minification (bytes)
            - 'total_minified_size': Total size after minification (bytes)
            - 'reduction_percent': Percentage reduction in size
            - 'failed_files': List of files that failed to minify
    """
    stats = {
        'files_processed': 0,
        'total_original_size': 0,
        'total_minified_size': 0,
        'reduction_percent': 0.0,
        'failed_files': []
    }

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Find all CSS files
    css_files = [f for f in os.listdir(input_dir) if f.endswith('.css')]

    if not css_files:
        if verbose:
            print_info(f"No CSS files found in {input_dir}")
        return stats

    if verbose:
        print_info(f"Minifying {len(css_files)} CSS files...")

    # Process each CSS file
    for filename in css_files:
        input_path = os.path.join(input_dir, filename)
        output_path = os.path.join(output_dir, filename)

        try:
            original_size, minified_size = minify_css_file(input_path, output_path)

            stats['files_processed'] += 1
            stats['total_original_size'] += original_size
            stats['total_minified_size'] += minified_size

            reduction = ((original_size - minified_size) / original_size) * 100

            if verbose:
                print_info(
                    f"  • {filename}: {original_size:,} → {minified_size:,} bytes "
                    f"({reduction:.1f}% reduction)",
                    indent=1
                )

        except Exception as e:
            stats['failed_files'].append({'filename': filename, 'error': str(e)})
            if verbose:
                print_error(f"  • Failed to minify {filename}: {e}", indent=1)

    # Calculate overall reduction
    if stats['total_original_size'] > 0:
        stats['reduction_percent'] = (
            (stats['total_original_size'] - stats['total_minified_size'])
            / stats['total_original_size']
        ) * 100

    if verbose and stats['files_processed'] > 0:
        print_success(
            f"✓ Minified {stats['files_processed']} CSS files: "
            f"{stats['total_original_size']:,} → {stats['total_minified_size']:,} bytes "
            f"({stats['reduction_percent']:.1f}% reduction)"
        )

        if stats['failed_files']:
            print_error(f"Failed to minify {len(stats['failed_files'])} files")

    return stats


def should_minify_css(filename):
    """
    Determine if a CSS file should be minified.

    Skip files that are already minified (.min.css) or are source maps (.css.map).

    Args:
        filename: CSS filename to check

    Returns:
        bool: True if file should be minified, False otherwise
    """
    # Skip already minified files
    if '.min.css' in filename:
        return False

    # Skip source maps
    if filename.endswith('.css.map'):
        return False

    # Minify all other CSS files
    return filename.endswith('.css')
