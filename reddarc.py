

import os
import json
import argparse
import glob
import re
import shutil
from datetime import datetime
from urllib.parse import urlparse
from typing import Dict, List, Optional, Tuple, Any, Set
from core.incremental_processor import IncrementalProcessor
from processing.incremental_statistics import IncrementalStatistics
from utils.simple_json_utils import save_subreddit_list
from utils.console_output import console, print_header, print_section, print_info, print_success, print_warning, print_error, create_progress_bar
# PostgreSQL database backend (required)
from core.postgres_database import PostgresDatabase, get_postgres_connection_string
from monitoring.performance_monitor import PerformanceMonitor
# Version information
from version import __version__, get_version_string


def get_thread_meta(thread: dict) -> dict:
    # Handle comments count for both in-memory and database posts
    if 'comments' in thread and isinstance(thread['comments'], list):
        # In-memory post with comments list
        comments_count = len(thread['comments'])
    else:
        # Database post - use num_comments field
        comments_count = thread.get('num_comments', 0)

    return {
        'id': thread['id'],
        'path': thread['permalink'].replace(f'r/{thread["subreddit"]}', '').strip('/') + '.html',
        'title': thread['title'],
        'score': thread['score'],
        'replies': str(int(float(comments_count))) if comments_count is not None else '0',
        'body_short': thread['selftext'][:200],
        'date': datetime.utcfromtimestamp(int(float(thread['created_utc']))).strftime('%Y-%m-%d'),
        'author': thread['author'],
        'subreddit': thread['subreddit'],
        'url': thread.get('url', ''),
        'is_self': thread.get('is_self', False),
        'created_utc': thread['created_utc'],
        # Enhanced display fields
        'flair': thread.get('link_flair_text', ''),
        'flair_css': thread.get('link_flair_css_class', ''),
        'author_flair': thread.get('author_flair_text', ''),
        'edited': thread.get('edited', False),
        'distinguished': thread.get('distinguished', None),
        'stickied': thread.get('stickied', False),
        'locked': thread.get('locked', False),
        'gilded': thread.get('gilded', 0),
        'num_comments': comments_count,
        'over_18': thread.get('over_18', False),
        'spoiler': thread.get('spoiler', False),
        'archived': thread.get('archived', False),
        # Additional enhanced fields
        'subreddit_subscribers': thread.get('subreddit_subscribers', 0),
        'num_crossposts': thread.get('num_crossposts', 0),
        'author_created_utc': thread.get('author_created_utc', None),
        # Award display fields
        'upvote_ratio': thread.get('upvote_ratio', None),
        'total_awards_received': thread.get('total_awards_received', 0),
        # Deleted user tracking
        'author_fullname': thread.get('author_fullname', None),
    }


def get_comment_meta(comment: dict) -> dict:
    return {
        'id': comment['id'],
        'body': comment.get('body', ''),
        'body_short': comment.get('body', '')[:200],
        'score': comment.get('score', ''),
        'date': datetime.utcfromtimestamp(int(comment['created_utc'])).strftime('%Y-%m-%d'),
        'author': comment.get('author', '[deleted]'),
        'subreddit': comment.get('subreddit', ''),
        'link_id': comment.get('link_id', ''),
        'parent_id': comment.get('parent_id', ''),
        'created_utc': comment.get('created_utc', 0),
        # Enhanced display fields
        'author_flair': comment.get('author_flair_text', ''),
        'author_flair_css': comment.get('author_flair_css_class', ''),
        'edited': comment.get('edited', False),
        'distinguished': comment.get('distinguished', None),
        'stickied': comment.get('stickied', False),
        'gilded': comment.get('gilded', 0),
        'controversiality': comment.get('controversiality', 0),
        # Additional enhanced fields
        'ups': comment.get('ups', 0),
        'downs': comment.get('downs', 0),
        'author_created_utc': comment.get('author_created_utc', None),
        # Deleted user tracking
        'author_fullname': comment.get('author_fullname', None),
    }


def parse_seo_config(config: Any) -> Dict[str, Any]:
    """Parse SEO configuration from TOML config and handle asset management"""
    seo_config = {}
    
    print('Processing SEO configuration...')
    
    for section_name in config.sections():
        section = config[section_name]
        seo_data = {}
        
        # PRESERVE ALL ORIGINAL CONFIG FIELDS
        for key, value in section.items():
            seo_data[key] = value
        
        # Parse SEO fields (all optional)
        seo_data['base_url'] = section.get('base_url', None)
        seo_data['site_name'] = section.get('site_name', f'r/{section_name} Archive')
        seo_data['og_image_src'] = section.get('og_image', None)
        seo_data['favicon_src'] = section.get('favicon', None)
        
        # Process assets and determine output paths
        seo_data['og_image'] = process_seo_asset(seo_data['og_image_src'], section_name, 'og_image')
        seo_data['favicon'] = process_seo_asset(seo_data['favicon_src'], section_name, 'favicon')
        
        seo_config[section_name] = seo_data
    
    return seo_config

def process_seo_asset(asset_path: Optional[str], subreddit: str, asset_type: str) -> Optional[str]:
    """Process SEO assets - copy to output directory and return output path"""
    if not asset_path:
        # Use default asset
        if asset_type == 'og_image':
            # Try WebP first, then PNG fallback
            default_webp = 'seo-assets/defaults/og-image.webp'
            default_png = 'seo-assets/defaults/og-image.png'
            if os.path.exists(default_webp):
                return copy_asset_to_output(default_webp, subreddit, 'og-image.webp')
            elif os.path.exists(default_png):
                return copy_asset_to_output(default_png, subreddit, 'og-image.png')
        elif asset_type == 'favicon':
            # Try ICO first, then SVG fallback
            default_ico = 'seo-assets/defaults/favicon.ico'
            default_svg = 'seo-assets/defaults/favicon.svg'
            if os.path.exists(default_ico):
                return copy_asset_to_output(default_ico, subreddit, 'favicon.ico')
            elif os.path.exists(default_svg):
                return copy_asset_to_output(default_svg, subreddit, 'favicon.svg')
        return None
    
    # Check if custom asset exists
    if not os.path.exists(asset_path):
        print(f'Warning: SEO asset not found: {asset_path} (using default if available)')
        return process_seo_asset(None, subreddit, asset_type)  # Fall back to default
    
    # Copy custom asset to output directory
    filename = os.path.basename(asset_path)
    return copy_asset_to_output(asset_path, subreddit, filename)

def copy_asset_to_output(src_path: str, subreddit: str, filename: str) -> Optional[str]:
    """Copy asset file to output directory and return relative path"""
    if not os.path.exists(src_path):
        return None

    # Create output directory
    output_dir = f'r/static/seo/{subreddit}'
    os.makedirs(output_dir, exist_ok=True)

    # Copy file
    output_path = f'{output_dir}/{filename}'
    try:
        shutil.copy2(src_path, output_path)
        # Return relative path from site root
        return f'static/seo/{subreddit}/{filename}'
    except Exception as e:
        print(f'Warning: Failed to copy SEO asset {src_path}: {e}')
        return None


def verify_fts_indexes_for_subreddit(subreddit_name: str, postgres_db: PostgresDatabase) -> List[Dict[str, Any]]:
    """
    Verify PostgreSQL FTS indexes for a subreddit and return search metadata.

    PostgreSQL search uses native full-text search with GIN indexes - no pre-built
    index files are required. This function returns metadata for tracking purposes only.

    Args:
        subreddit_name: Subreddit to verify
        postgres_db: PostgresDatabase instance

    Returns:
        List with single search metadata dictionary (for compatibility with old API)
    """
    try:
        # Get post count from database
        with postgres_db.pool.get_connection() as conn:
            from psycopg.rows import dict_row
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM posts WHERE subreddit = %s",
                    (subreddit_name,)
                )
                total_posts = cursor.fetchone()['count']

        # PostgreSQL FTS doesn't need pre-built indexes - return metadata for tracking only
        print_info(f"PostgreSQL FTS ready for r/{subreddit_name}: {total_posts} posts searchable", indent=2)

        return [{
            'name': subreddit_name,
            'posts': total_posts,
            'chunks': 0,  # PostgreSQL FTS doesn't use chunks
            'index_size_mb': 0.0  # No index files generated
        }]

    except Exception as e:
        print_warning(f"Failed to verify FTS indexes for r/{subreddit_name}: {e}", indent=2)
        return []


def discover_subreddits(input_dir: str) -> Dict[str, Dict[str, str]]:
    """Auto-discover .zst files and pair them into subreddits"""
    print_section('Auto-discovering subreddit files')
    print_info(f'Scanning directory: {input_dir}')
    
    # Find all .zst files recursively
    zst_files = glob.glob(os.path.join(input_dir, '**/*.zst'), recursive=True)
    
    if not zst_files:
        print_error(f'No .zst files found in {input_dir}')
        return {}
    
    print_success(f'Found {console.format_number(len(zst_files))} .zst files')
    
    # Pattern definitions for different naming conventions
    patterns = [
        # Pattern 1: subreddit_comments.zst + subreddit_submissions.zst
        {
            'name': 'Standard naming',
            'comments': r'(?P<name>.*?)_comments\.zst$',
            'submissions': r'(?P<name>.*?)_submissions\.zst$'
        },
        # Pattern 2: RC_date_subreddit.zst + RS_date_subreddit.zst
        {
            'name': 'Pushshift format',
            'comments': r'RC_\d{4}-\d{2}_(?P<name>.*?)\.zst$',
            'submissions': r'RS_\d{4}-\d{2}_(?P<name>.*?)\.zst$'
        },
        # Pattern 3: subreddit/comments.zst + subreddit/submissions.zst
        {
            'name': 'Directory-based',
            'comments': r'(?P<name>[^/\\]+)[/\\]comments\.zst$',
            'submissions': r'(?P<name>[^/\\]+)[/\\]submissions\.zst$'
        }
    ]
    
    subreddits = {}
    matched_files = set()
    
    # Try each pattern
    for pattern in patterns:
        print(f'  Trying pattern: {pattern["name"]}')
        pattern_matches = {}
        
        for file_path in zst_files:
            if file_path in matched_files:
                continue  # Already matched by previous pattern
                
            # Try comments pattern
            comments_match = re.search(pattern['comments'], file_path)
            if comments_match:
                subreddit = comments_match.group('name')
                # Strip path - only use basename for subreddit name
                subreddit = os.path.basename(subreddit)
                if subreddit not in pattern_matches:
                    pattern_matches[subreddit] = {}
                pattern_matches[subreddit]['comments'] = file_path

            # Try submissions pattern
            submissions_match = re.search(pattern['submissions'], file_path)
            if submissions_match:
                subreddit = submissions_match.group('name')
                # Strip path - only use basename for subreddit name
                subreddit = os.path.basename(subreddit)
                if subreddit not in pattern_matches:
                    pattern_matches[subreddit] = {}
                pattern_matches[subreddit]['submissions'] = file_path
        
        # Find complete pairs for this pattern
        for subreddit, files in pattern_matches.items():
            if 'comments' in files and 'submissions' in files:
                subreddits[subreddit] = files
                matched_files.add(files['comments'])
                matched_files.add(files['submissions'])
                print_info(f'Found {subreddit}', indent=2)
    
    if not subreddits:
        print_error('No matching subreddit pairs found.')
        print_info('Expected naming patterns:')
        print_info('Standard: subreddit_comments.zst + subreddit_submissions.zst', indent=1)
        print_info('Pushshift: RC_2024-01_subreddit.zst + RS_2024-01_subreddit.zst', indent=1)
        print_info('Directory: subreddit/comments.zst + subreddit/submissions.zst', indent=1)
        return {}
    
    # Show unmatched files
    unmatched = [f for f in zst_files if f not in matched_files]
    if unmatched:
        print_warning(f'{len(unmatched)} unmatched files (missing pairs):', indent=1)
        for f in unmatched[:5]:  # Show first 5
            print_info(os.path.basename(f), indent=2)
        if len(unmatched) > 5:
            print_info(f'... and {len(unmatched) - 5} more', indent=2)
    
    print_success(f'Discovered {len(subreddits)} complete subreddit pairs')
    return subreddits

def discover_single_subreddit(subreddit_name: str, comments_file: str, submissions_file: str) -> Dict[str, Dict[str, str]]:
    """Create subreddit files dictionary for single subreddit processing"""
    print_section(f'Single Subreddit Mode: r/{subreddit_name}')
    
    # Validate files exist and are readable
    for file_path in [comments_file, submissions_file]:
        if not os.path.exists(file_path):
            print_error(f'File not found: {file_path}')
            return {}
        
        # Check file size for sanity
        try:
            file_size = os.path.getsize(file_path)
            print_info(f'{os.path.basename(file_path)}: {console.format_size(file_size)}', indent=1)
        except Exception as e:
            print_warning(f'Could not read file size for {file_path}: {e}', indent=1)
    
    print_success(f'Ready to process r/{subreddit_name}')
    
    return {
        subreddit_name: {
            'comments': comments_file,
            'submissions': submissions_file
        }
    }


def create_global_seo_config(args: argparse.Namespace, output_dir: str) -> Dict[str, Any]:
    """Create global SEO configuration for all subreddits"""
    seo_config = {}

    # Base configuration
    if hasattr(args, 'base_url') and args.base_url:
        seo_config['base_url'] = args.base_url.rstrip('/')

    seo_config['site_name'] = getattr(args, 'site_name', 'Redd Archive')
    seo_config['project_url'] = getattr(args, 'project_url', 'https://github.com/19-84/redd-archiver')
    seo_config['site_description'] = getattr(args, 'site_description', None)
    seo_config['contact'] = getattr(args, 'contact', None)
    seo_config['team_id'] = getattr(args, 'team_id', None)
    seo_config['donation_address'] = getattr(args, 'donation_address', None)

    # Handle asset copying to output directory
    if hasattr(args, 'favicon') and args.favicon:
        seo_config['favicon'] = copy_global_asset(args.favicon, 'favicon', output_dir)

    if hasattr(args, 'og_image') and args.og_image:
        seo_config['og_image'] = copy_global_asset(args.og_image, 'og-image', output_dir)

    return seo_config

def copy_global_asset(src_path: str, asset_name: str, output_dir: str) -> Optional[str]:
    """Copy global SEO asset to output directory"""
    if not os.path.exists(src_path):
        print(f'Warning: SEO asset not found: {src_path}')
        return None
    
    # Create static assets directory in output
    assets_dir = os.path.join(output_dir, 'static', 'seo')
    os.makedirs(assets_dir, exist_ok=True)
    
    # Determine filename with extension
    _, ext = os.path.splitext(src_path)
    filename = asset_name + ext
    
    # Copy file
    output_path = os.path.join(assets_dir, filename)
    try:
        shutil.copy2(src_path, output_path)
        # Return relative path from site root
        return f'static/seo/{filename}'
    except Exception as e:
        print(f'Warning: Failed to copy SEO asset {src_path}: {e}')
        return None

def copy_static_assets(output_dir: str, minify_css: bool = True) -> None:
    """
    Copy static CSS/JS assets to output directory with optional CSS minification.

    Args:
        output_dir: Output directory path
        minify_css: Whether to minify CSS files during copy (default: True)
    """
    from html_modules.css_minifier import minify_css_file, should_minify_css

    static_src = 'static'
    static_dst = os.path.join(output_dir, 'static')

    if not os.path.exists(static_src):
        print_warning('Static assets directory not found')
        return

    print('Copying static assets...')

    try:
        # Remove existing static directory
        if os.path.exists(static_dst):
            shutil.rmtree(static_dst)

        # Track CSS minification stats
        css_stats = {
            'files': 0,
            'original_size': 0,
            'minified_size': 0
        }

        # Walk through source directory and copy files
        for root, dirs, files in os.walk(static_src):
            # Calculate relative path from static_src
            rel_path = os.path.relpath(root, static_src)
            dst_dir = os.path.join(static_dst, rel_path) if rel_path != '.' else static_dst

            # Create destination directory
            os.makedirs(dst_dir, exist_ok=True)

            # Copy files
            for filename in files:
                src_file = os.path.join(root, filename)
                dst_file = os.path.join(dst_dir, filename)

                # Minify CSS files if enabled
                if minify_css and should_minify_css(filename):
                    try:
                        original_size, minified_size = minify_css_file(src_file, dst_file)
                        css_stats['files'] += 1
                        css_stats['original_size'] += original_size
                        css_stats['minified_size'] += minified_size
                    except Exception as e:
                        print_warning(f'Failed to minify {filename}, copying unminified: {e}')
                        shutil.copy2(src_file, dst_file)
                else:
                    # Copy non-CSS files normally
                    shutil.copy2(src_file, dst_file)

                    # Fix permissions for web manifest (must be readable by web server)
                    if filename == 'site.webmanifest':
                        os.chmod(dst_file, 0o644)

        # Report results
        if css_stats['files'] > 0:
            reduction_pct = ((css_stats['original_size'] - css_stats['minified_size'])
                           / css_stats['original_size'] * 100)
            print_success(
                f'Copied static assets to {static_dst} | '
                f'Minified {css_stats["files"]} CSS files: '
                f'{css_stats["original_size"]:,} → {css_stats["minified_size"]:,} bytes '
                f'({reduction_pct:.1f}% reduction)'
            )
        else:
            print_success(f'Copied static assets to {static_dst}')

    except Exception as e:
        print_warning(f'Failed to copy static assets: {e}')

def detect_resume_state_and_files(args: argparse.Namespace) -> Tuple[str, Optional[Dict[str, Any]], Dict[str, Dict[str, str]]]:
    """
    Detect if we should resume and return the correct file list.
    Returns: (resume_state, state_data, subreddit_files)
    """
    # Handle single subreddit mode
    if args.subreddit:
        if args.resume and os.path.exists(args.output):
            # Check if single subreddit is already processed
            from utils.simple_json_utils import load_subreddit_stats
            try:
                existing_stats = load_subreddit_stats(args.output)
                if args.subreddit in existing_stats:
                    print_warning(f'Subreddit r/{args.subreddit} already exists in archive')
                    print_info('Processing will update existing subreddit data', indent=1)
                    print_info('Use --force-rebuild to completely replace existing data', indent=1)
            except Exception as e:
                print_info(f'Could not check existing subreddit data: {e}', indent=1)
        
        # Always return start_fresh for single subreddit mode to use normal processing flow
        return 'start_fresh', None, {}
    
    # If not resuming or no output directory, start fresh
    if not args.resume or not os.path.exists(args.output):
        if args.resume and not os.path.exists(args.output):
            print_info("No output directory found, starting fresh")
        return 'start_fresh', None, {}
    
    # Check for resume state
    processor = IncrementalProcessor(args.output, args.memory_limit)
    resume_state, state_data = processor.detect_processing_state()
    
    if resume_state in ['resume_subreddits', 'resume_from_emergency']:
        print_info("Resuming interrupted processing...")
        
        # Get completed subreddits from saved state
        completed_subreddits = state_data.get('completed_subreddits', [])
        print_info(f"Completed: {len(completed_subreddits)} subreddits", indent=1)
        
        # Re-discover all files first
        print_info("Re-discovering all files to calculate remaining subreddits...", indent=1)
        all_discovered_files = discover_subreddits(args.input_dir)
        
        if not all_discovered_files:
            print_error("Could not discover any subreddit files")
            return 'start_fresh', None, {}
        
        # Calculate remaining subreddits by subtracting completed ones
        remaining_subreddits = []
        remaining_files = {}
        
        for discovered_name, files in all_discovered_files.items():
            # Check if this subreddit was completed
            is_completed = False
            
            # Direct name match
            if discovered_name in completed_subreddits:
                is_completed = True
            else:
                # Try cleaned name match (handle directory paths)
                clean_name = discovered_name.split('/')[-1]
                if clean_name in completed_subreddits:
                    is_completed = True
                
                # Also check reverse - completed might have directory paths
                for completed_name in completed_subreddits:
                    if completed_name.split('/')[-1] == clean_name:
                        is_completed = True
                        break
            
            # If not completed, add to remaining
            if not is_completed:
                remaining_subreddits.append(discovered_name)
                remaining_files[discovered_name] = files
        
        print_info(f"Remaining: {len(remaining_subreddits)} subreddits", indent=1)
        
        if not remaining_files:
            print_warning("No remaining subreddits found - all appear to be completed", indent=1)
            return 'already_complete', state_data, {}
        
        print_success(f"Found files for {len(remaining_files)} remaining subreddits", indent=1)
        
        # Update state data with calculated remaining subreddits for consistency
        state_data['remaining_subreddits'] = remaining_subreddits
        state_data['total_subreddits'] = len(all_discovered_files)
        
        return resume_state, state_data, remaining_files
    
    elif resume_state == 'already_complete':
        return resume_state, state_data, {}
    
    else:
        print_info("No valid resume state found, starting fresh")
        return 'start_fresh', None, {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Generate multi-platform archive websites from Reddit, Voat, and Ruqqus data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Auto-detect platform and process
  python reddarc.py /data/reddit-files/      # Reddit (.zst)
  python reddarc.py /data/voat-sql/          # Voat (.sql.gz)
  python reddarc.py /data/ruqqus/            # Ruqqus (.7z)

  # Explicit platform selection
  python reddarc.py /data --platform ruqqus --output archive/
  python reddarc.py /data --platform voat --output archive/

  # Process specific communities
  python reddarc.py /ruqqus/ --guild News,Conservative --output archive/
  python reddarc.py /voat/ --subverse technology,pics --output archive/
  python reddarc.py /reddit/ --subreddit example --comments-file /reddit/example_comments.zst --submissions-file /reddit/example_submissions.zst

  # List available communities before importing
  python reddarc.py /ruqqus/ --list-communities
  python reddarc.py /voat/ --list-communities

  # Multi-platform archive (sequential imports)
  python reddarc.py /reddit/ --output multi-archive/
  python reddarc.py /ruqqus/ --platform ruqqus --output multi-archive/
  python reddarc.py /voat/ --platform voat --output multi-archive/

  # With SEO and filtering
  python reddarc.py /data/ --output archive/ --base-url https://example.com --site-name "My Archive" --min-score 5
        '''
    )

    parser.add_argument('--version', action='version',
                        version=get_version_string(),
                        help='Show version information and exit')
    
    parser.add_argument('input_dir', help='Directory containing .zst files')
    parser.add_argument('--output', '-o', default='redd-archive-output',
                        help='Output directory (default: redd-archive-output)')
    
    # SEO Arguments (optional)
    parser.add_argument('--base-url', help='Base URL for canonical links and sitemaps')
    parser.add_argument('--site-name', default='Redd Archive', help='Site name for meta tags')
    parser.add_argument('--project-url', default='https://github.com/19-84/redd-archiver', help='Project repository URL for footer links')
    parser.add_argument('--site-description', help='Site description for API and SEO meta tags')
    parser.add_argument('--contact', help='Contact method: email, URL, Matrix, GitHub username, etc. (shown in API)')
    parser.add_argument('--team-id', help='Team identifier for registry leaderboard grouping')
    parser.add_argument('--donation-address', help='Donation method: URL, crypto address (BTC/ETH/XMR), payment link, etc. (shown in API/footer)')
    parser.add_argument('--favicon', help='Path to favicon file (will be copied to output)')
    parser.add_argument('--og-image', help='Path to Open Graph image (will be copied to output)')
    
    # Processing Arguments
    parser.add_argument('--min-score', type=int, default=0, help='Minimum post score')
    parser.add_argument('--min-comments', type=int, default=0, help='Minimum comment count')
    parser.add_argument('--hide-deleted-comments', action='store_true',
                        help='Hide deleted and removed comments in output')
    parser.add_argument('--no-user-pages', action='store_true',
                        help='Skip user page generation to reduce memory usage for large archives')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Show discovered files without processing')
    parser.add_argument('--resume', action='store_true',
                        help='Resume interrupted processing (auto-detected)')
    parser.add_argument('--force-rebuild', action='store_true',
                        help='Force full rebuild, ignoring existing progress')

    # Import/Export Mode Arguments (mutually exclusive, PostgreSQL-only)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--import-only', action='store_true',
                        help='Import mode: Stream .zst files to PostgreSQL database only (no HTML generation)')
    mode_group.add_argument('--export-from-database', action='store_true',
                        help='Export mode: Generate HTML archive from existing PostgreSQL data only (no data import)')

    # Single Subreddit Processing Arguments
    parser.add_argument('--subreddit', '-s',
                        help='Process a specific subreddit (use with --comments-file and --submissions-file)')
    parser.add_argument('--comments-file',
                        help='Path to comments .zst file for single subreddit mode')
    parser.add_argument('--submissions-file',
                        help='Path to submissions .zst file for single subreddit mode')

    # Multi-Platform Support Arguments
    parser.add_argument('--platform',
                        choices=['reddit', 'voat', 'ruqqus', 'auto'],
                        default='auto',
                        help='Platform type: reddit (.zst), voat (.sql.gz), ruqqus (.7z), or auto-detect (default: auto)')
    parser.add_argument('--guild', '--guilds',
                        dest='guilds',
                        help='Ruqqus guild(s) to import (comma-separated, e.g., "News,Politics")')
    parser.add_argument('--subverse', '--subverses',
                        dest='subverses',
                        help='Voat subverse(s) to import (comma-separated, e.g., "technology,pics")')
    parser.add_argument('--list-communities', action='store_true',
                        help='List available communities in archive without importing')

    # Performance Override Arguments (for debugging/testing only)
    parser.add_argument('--force-parallel-users', action='store_true',
                        help='Force parallel user processing regardless of system resource detection (override auto-detection)')
    parser.add_argument('--debug-memory-limit', type=float, default=None,
                        help='Override memory limit for debugging (default: auto-detect optimal limit)')
    parser.add_argument('--debug-max-connections', type=int, default=None,
                        help='Override database connections for debugging (default: auto-detect, range: 1-20)')
    parser.add_argument('--debug-max-workers', type=int, default=None,
                        help='Override parallel workers for debugging (default: auto-detect, range: 1-16)')
    
    # Logging Arguments
    parser.add_argument('--log-file',
                        help='Path to log file for error/debug logging (default: output_dir/.archive-error.log)')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Logging level for file output (default: INFO)')
    
    args = parser.parse_args()

    # Validate PostgreSQL is configured (REQUIRED for all operations)
    if not os.environ.get('DATABASE_URL'):
        print_error("PostgreSQL is required but DATABASE_URL is not configured")
        print_info("Set DATABASE_URL environment variable:", indent=1)
        print_info("Example: export DATABASE_URL='postgresql://user:password@localhost:5432/archive_db'", indent=2)
        print_info("", indent=1)
        print_info("For local development, you can use:", indent=1)
        print_info("docker-compose up -d  # Start PostgreSQL in Docker", indent=2)
        print_info("export DATABASE_URL='postgresql://archiver:archiver_pass@localhost:5432/archive_db'", indent=2)
        return

    # Auto-detect optimal performance settings
    from monitoring.system_optimizer import get_system_optimizer, print_performance_analysis

    system_optimizer = get_system_optimizer()
    profile = system_optimizer.get_profile()

    # Apply automatic optimization with debug overrides
    optimal_memory_limit = args.debug_memory_limit if args.debug_memory_limit is not None else profile.memory_limit_gb
    optimal_db_connections = args.debug_max_connections if args.debug_max_connections is not None else profile.max_db_connections
    optimal_parallel_workers = args.debug_max_workers if args.debug_max_workers is not None else profile.max_parallel_workers

    # Validate debug overrides if provided
    if args.debug_max_connections is not None:
        if not (1 <= args.debug_max_connections <= 20):
            print_error('--debug-max-connections must be between 1 and 20')
            return
        print_info(f'🐛 Debug override: database connections = {args.debug_max_connections}')

    if args.debug_max_workers is not None:
        if not (1 <= args.debug_max_workers <= 16):
            print_error('--debug-max-workers must be between 1 and 16')
            return
        print_info(f'🐛 Debug override: parallel workers = {args.debug_max_workers}')

    if args.debug_memory_limit is not None:
        print_info(f'🐛 Debug override: memory limit = {args.debug_memory_limit}GB')

    # Set environment variables for the optimized settings
    os.environ['ARCHIVE_MAX_DB_CONNECTIONS'] = str(optimal_db_connections)
    os.environ['ARCHIVE_MAX_PARALLEL_WORKERS'] = str(optimal_parallel_workers)

    # Store optimized settings in args for compatibility
    args.memory_limit = optimal_memory_limit
    args.user_page_batch_size = None  # Always use auto-tuning
    args.max_db_connections = optimal_db_connections
    args.max_parallel_workers = optimal_parallel_workers

    # Print performance analysis
    print_performance_analysis()
    
    # Validate single community mode arguments (subreddit/subverse/guild)
    community_filter = args.subreddit or args.subverses or args.guilds
    if community_filter:
        if not (args.comments_file and args.submissions_file):
            platform_name = 'subreddit' if args.subreddit else ('subverse' if args.subverses else 'guild')
            print_error(f'Single {platform_name} mode requires both --comments-file and --submissions-file')
            print_info(f'Example: python reddarc.py /data --{platform_name} example --comments-file /data/example_comments.zst --submissions-file /data/example_submissions.zst')
            return
        if not all(os.path.exists(f) for f in [args.comments_file, args.submissions_file]):
            print_error('One or both specified files do not exist:')
            print_error(f'  Comments: {args.comments_file} (exists: {os.path.exists(args.comments_file)})')
            print_error(f'  Submissions: {args.submissions_file} (exists: {os.path.exists(args.submissions_file)})')
            return
        prefix = 'r/' if args.subreddit else ('v/' if args.subverses else 'g/')
        print_info(f'Single community mode: processing {prefix}{community_filter}')
    elif args.comments_file or args.submissions_file:
        print_error('--comments-file and --submissions-file require --subreddit, --subverse, or --guild to be specified')
        return

    # Validate input directory
    if not os.path.exists(args.input_dir):
        print_error(f'Input directory does not exist: {args.input_dir}')
        return

    if not os.path.isdir(args.input_dir):
        print_error(f'Input path is not a directory: {args.input_dir}')
        return

    # Platform detection and importer setup
    from core.importers import detect_platform, get_importer

    if args.platform == 'auto':
        try:
            detected_platform = detect_platform(args.input_dir)
            print_info(f'🔍 Auto-detected platform: {detected_platform}')
            args.platform = detected_platform
        except ValueError as e:
            print_error(str(e))
            print_info('Tip: Use --platform flag to specify manually', indent=1)
            return
    else:
        print_info(f'📦 Using specified platform: {args.platform}')

    # Get platform-specific importer
    try:
        importer = get_importer(args.platform)
        platform_meta = importer.get_platform_metadata()
        print_info(f'Platform: {platform_meta["display_name"]} ({platform_meta["community_term"]}s)')
    except ValueError as e:
        print_error(str(e))
        return

    # Parse community filters if provided
    filter_communities = None
    if args.guilds:
        filter_communities = [g.strip() for g in args.guilds.split(',')]
        print_info(f'Filtering Ruqqus guilds: {", ".join(filter_communities)}')
    elif args.subverses:
        filter_communities = [s.strip() for s in args.subverses.split(',')]
        print_info(f'Filtering Voat subverses: {", ".join(filter_communities)}')
    elif args.subreddit:
        filter_communities = [args.subreddit]
        print_info(f'Filtering Reddit subreddit: {args.subreddit}')

    # List communities mode
    if args.list_communities:
        print_info(f'\n📋 Discovering {platform_meta["community_term"]}s in archive...\n')
        try:
            files = importer.detect_files(args.input_dir)

            # Quick scan to list unique communities
            communities = set()
            for post_file in files.get('posts', []):
                print_info(f'Scanning: {os.path.basename(post_file)}', indent=1)
                count = 0
                for post in importer.stream_posts(post_file):
                    communities.add(post['subreddit'])
                    count += 1
                    if count >= 10000:  # Limit scan for large archives
                        break

            print_info(f'\n✅ Found {len(communities)} {platform_meta["community_term"]}(s):\n')
            for community in sorted(communities):
                print_info(f'  - {community}')

            print_info(f'\nTo import specific {platform_meta["community_term"]}s, use:')
            if args.platform == 'ruqqus':
                print_info(f'  --guild "{",".join(list(communities)[:3])}"', indent=1)
            elif args.platform == 'voat':
                print_info(f'  --subverse "{",".join(list(communities)[:3])}"', indent=1)
            else:
                print_info(f'  --subreddit {list(communities)[0]}', indent=1)

            return
        except Exception as e:
            print_error(f'Failed to list communities: {e}')
            return
    
    # Setup file logging if requested
    if args.log_file or hasattr(args, 'output'):
        # Determine log file path
        if args.log_file:
            log_file_path = args.log_file
            # Validate: if log path has no directory component, place in output directory
            if not os.path.dirname(log_file_path):
                os.makedirs(args.output, exist_ok=True)
                log_file_path = os.path.join(args.output, log_file_path)
                print_info(f'Log file has no directory - placing in output directory: {log_file_path}')
        else:
            # Default to output directory
            os.makedirs(args.output, exist_ok=True)
            log_file_path = os.path.join(args.output, '.archive-error.log')
        
        # Setup file logging using the enhanced console system
        console.setup_file_logging(log_file_path, args.log_level)
        print_info(f'File logging enabled: {log_file_path} (level: {args.log_level})')
    
    # ✅ FIXED: Check resume state FIRST, then discover appropriate files
    resume_state, state_data, subreddit_files = detect_resume_state_and_files(args)

    # Handle special resume states
    if resume_state == 'already_complete':
        print_success("Archive generation already complete!")
        print_info(f"Output: {args.output}/r/index.html", indent=1)
        return
    
    # If starting fresh or no files from resume, do discovery
    if resume_state == 'start_fresh' or not subreddit_files:
        # Check if single community mode (Reddit --subreddit, Voat --subverse, or Ruqqus --guild)
        has_single_community = args.subreddit or (filter_communities and len(filter_communities) > 0)

        if has_single_community:
            # Single community mode - check if explicit files provided
            if args.comments_file and args.submissions_file:
                # Explicit file paths provided - use them directly (any platform)
                community_name = args.subreddit or (filter_communities[0] if filter_communities else 'community')

                if args.platform == 'reddit':
                    # Legacy Reddit mode
                    subreddit_files = discover_single_subreddit(
                        community_name,
                        args.comments_file,
                        args.submissions_file
                    )
                else:
                    # Voat/Ruqqus with explicit files - bypass file detection
                    subreddit_files = {
                        community_name: {
                            'comments': [args.comments_file],
                            'submissions': [args.submissions_file],
                            'platform': args.platform,
                            'importer': importer,
                            'filter_communities': filter_communities
                        }
                    }
            else:
                # Use importer for single community
                print_section(f'Discovering {platform_meta["community_term"]} files')
                try:
                    files = importer.detect_files(args.input_dir)
                    # Create single entry with filtered community
                    community_name = filter_communities[0] if filter_communities else args.subreddit
                    subreddit_files = {
                        community_name: {
                            'comments': files.get('comments', []),
                            'submissions': files.get('posts', []),
                            'platform': args.platform,
                            'importer': importer,
                            'filter_communities': filter_communities
                        }
                    }
                except Exception as e:
                    print_error(f"Failed to detect files: {e}")
                    return
        else:
            # Multi-community discovery using importer
            print_section('Starting fresh - discovering all files')
            if args.platform == 'reddit':
                # Use legacy discovery for Reddit (maintains existing behavior)
                subreddit_files = discover_subreddits(args.input_dir)
            else:
                # Use importer for Voat/Ruqqus
                try:
                    files = importer.detect_files(args.input_dir)
                    # Create synthetic subreddit_files structure for non-Reddit platforms
                    # We'll process all files as one batch since Voat/Ruqqus don't split by community
                    subreddit_files = {
                        f'{args.platform}_archive': {
                            'comments': files.get('comments', []),
                            'submissions': files.get('posts', []),
                            'platform': args.platform,
                            'importer': importer,
                            'filter_communities': filter_communities
                        }
                    }
                except Exception as e:
                    print_error(f"Failed to detect files: {e}")
                    return

        if not subreddit_files:
            return
    
    # Dry run - show what would be processed
    if args.dry_run:
        console.discovery_results(subreddit_files)
        print_info(f'Total: {len(subreddit_files)} subreddits ready for processing')
        return

    # Route to appropriate processing mode based on CLI flags
    if args.import_only:
        # Import mode: Stream to database only, no HTML generation
        process_import_only(
            args.input_dir,
            args.output,
            subreddit_files,
            args
        )
    elif args.export_from_database:
        # Export mode: Generate HTML from database only, no data import
        process_export_only(
            args.input_dir,
            args.output,
            subreddit_files,
            args
        )
    else:
        # Default mode: Combined import + export (original behavior)
        process_archive_incremental(
            args.input_dir,
            args.output,
            subreddit_files,  # ✅ Now contains ONLY the files that need processing
            args,
            resume_state,
            state_data
        )


def process_import_only(input_dir: str, output_dir: str, subreddit_files: Dict[str, Dict[str, str]], args: argparse.Namespace) -> None:
    """
    Import mode: Stream .zst files to PostgreSQL database only (no HTML generation).

    This function performs data import exclusively:
    - Streams posts and comments to PostgreSQL
    - Updates progress tracking in database
    - Captures SEO metadata (already in posts table)
    - Skips all HTML generation

    Args:
        input_dir: Directory containing .zst files
        output_dir: Output directory (for database path resolution)
        subreddit_files: Dictionary mapping subreddit names to file paths
        args: Command-line arguments

    Returns:
        None
    """
    print_section("Import Mode: Streaming data to PostgreSQL database")
    print_info("HTML generation disabled - use --export-from-database to generate HTML later")

    # Validate PostgreSQL is configured
    connection_string = get_postgres_connection_string()
    if not connection_string or 'postgresql://' not in connection_string:
        print_error("Import mode requires PostgreSQL to be configured")
        print_info("Set DATABASE_URL environment variable to PostgreSQL connection string", indent=1)
        return

    # Initialize PostgreSQL database connection
    try:
        db = PostgresDatabase(connection_string, workload_type='batch_insert')
        print_success(f"Connected to PostgreSQL database")
    except Exception as e:
        print_error(f"Failed to connect to PostgreSQL: {e}")
        return

    # Drop indexes for bulk loading (10-15x faster imports)
    print_info("Dropping indexes for bulk loading...")
    db.drop_indexes_for_bulk_load()

    # Process each subreddit
    total_subreddits = len(subreddit_files)
    processed_count = 0

    for subreddit, files in subreddit_files.items():
        processed_count += 1

        # Determine platform and community term
        platform = files.get('platform', 'reddit')
        importer_obj = files.get('importer')
        filter_communities = files.get('filter_communities')

        # Get platform-specific terminology
        if importer_obj:
            platform_meta = importer_obj.get_platform_metadata()
            community_prefix = platform_meta['url_prefix']
            community_term = platform_meta['community_term']
        else:
            community_prefix = 'r'
            community_term = 'subreddit'

        print_section(f"Importing {community_prefix}/{subreddit} ({processed_count}/{total_subreddits})")

        try:
            # Mark subreddit as importing
            db.update_progress_status(subreddit, 'importing', import_started_at=datetime.now())

            # Stream posts to database using importer
            print_info("Streaming posts to database...", indent=1)

            if importer_obj and platform != 'reddit':
                # Use importer for non-Reddit platforms
                posts_batch = []
                posts_processed = 0
                import time
                post_start_time = time.time()

                for post_file in files['submissions']:
                    for post in importer_obj.stream_posts(post_file, filter_communities):
                        posts_batch.append(post)
                        posts_processed += 1
                        if len(posts_batch) >= 10000:
                            successful, failed, failed_ids = db.insert_posts_batch(posts_batch)
                            posts_batch.clear()

                # Insert remaining posts
                if posts_batch:
                    successful, failed, failed_ids = db.insert_posts_batch(posts_batch)
                    posts_batch.clear()

                post_time = time.time() - post_start_time
                post_stats = {
                    'records_processed': posts_processed,
                    'processing_time': post_time,
                    'records_per_second': posts_processed / post_time if post_time > 0 else 0
                }
            else:
                # Use legacy stream_to_database for Reddit
                submissions_path = os.path.join(input_dir, files['submissions'])
                from core.watchful import stream_to_database
                post_stats = stream_to_database(
                    submissions_path, connection_string,
                    'posts', {'subreddit': subreddit},
                    batch_size=10000,
                    db=db
                )

            # Sync transactions before comments
            db.sync_transactions()

            # Stream comments to database using importer
            print_info("Streaming comments to database...", indent=1)

            if importer_obj and platform != 'reddit':
                # Load all post IDs into a set for orphan filtering
                # Query all posts (not filtered by subreddit) since we're processing one platform batch
                print_info("Loading post IDs for orphan comment filtering...", indent=2)
                valid_post_ids = set()
                with db.pool.get_connection() as conn:
                    with conn.cursor() as cur:
                        # Load all post IDs from database (platform-specific)
                        cur.execute("SELECT id FROM posts WHERE platform = %s", (platform,))
                        valid_post_ids = {row['id'] for row in cur}
                print_info(f"Loaded {len(valid_post_ids):,} post IDs for filtering", indent=2)

                # Use importer for non-Reddit platforms with orphan filtering
                comments_batch = []
                comments_processed = 0
                orphaned_count = 0
                comment_start_time = time.time()

                for comment_file in files['comments']:
                    for comment in importer_obj.stream_comments(comment_file, filter_communities):
                        # Filter out orphaned comments (reference missing posts)
                        if comment['post_id'] not in valid_post_ids:
                            orphaned_count += 1
                            continue

                        comments_batch.append(comment)
                        comments_processed += 1
                        if len(comments_batch) >= 20000:
                            successful, failed = db.insert_comments_batch(comments_batch)
                            if orphaned_count > 0:
                                print_info(f"Filtered {orphaned_count:,} orphaned comments", indent=2)
                                orphaned_count = 0
                            comments_batch.clear()

                # Insert remaining comments
                if comments_batch:
                    successful, failed = db.insert_comments_batch(comments_batch)
                    comments_batch.clear()

                if orphaned_count > 0:
                    print_info(f"Total orphaned comments filtered: {orphaned_count:,}", indent=2)

                comment_time = time.time() - comment_start_time
                comment_stats = {
                    'records_processed': comments_processed,
                    'processing_time': comment_time,
                    'records_per_second': comments_processed / comment_time if comment_time > 0 else 0
                }
            else:
                # Use legacy stream_to_database for Reddit
                comments_path = os.path.join(input_dir, files['comments'])
                comment_stats = stream_to_database(
                    comments_path, connection_string,
                    'comments', {'subreddit': subreddit},
                    batch_size=20000,
                    db=db
                )

            # Update user statistics
            print_info("Updating user statistics...", indent=1)
            db.update_user_statistics(subreddit_filter=subreddit)

            # PERFORMANCE FIX: ANALYZE removed - will be called once at end of ALL imports
            # Running ANALYZE after every subreddit was causing 30s waste per subreddit
            # ANALYZE is called once after index creation (line ~832)

            # Mark subreddit as imported
            db.update_progress_status(
                subreddit, 'imported',
                import_completed_at=datetime.now(),
                posts_imported=post_stats['records_processed'],
                comments_imported=comment_stats['records_processed']
            )

            print_success(f"Import complete: {post_stats['records_processed']} posts, {comment_stats['records_processed']} comments")

        except Exception as e:
            print_error(f"Import failed for r/{subreddit}: {e}")
            db.update_progress_status(subreddit, 'failed', error_message=str(e))
            continue

    # Recreate indexes after bulk loading
    print_section("Recreating indexes (this may take 60-90 minutes for large datasets)")
    db.create_indexes_after_bulk_load()

    # Final ANALYZE after index creation
    print_info("Running final ANALYZE after index creation...")
    db.analyze_tables(['posts', 'comments', 'users'])

    # Cleanup database connection
    db.cleanup()

    print_section("Import Complete")
    print_success(f"Successfully imported {processed_count}/{total_subreddits} subreddits")
    print_info("Use --export-from-database to generate HTML archive from this data", indent=1)


def process_export_only(input_dir: str, output_dir: str, subreddit_files_param: Dict[str, Dict[str, str]], args: argparse.Namespace) -> None:
    """
    Export mode: Generate HTML archive from existing PostgreSQL data only (no data import).

    This function performs HTML generation exclusively:
    - Queries PostgreSQL for imported subreddits
    - Generates HTML pages from database data
    - Creates SEO files, sitemaps, search indices
    - Updates progress tracking in database
    - Skips all data import

    Args:
        input_dir: Directory containing .zst files (not used in export mode, for API compatibility)
        output_dir: Output directory for HTML files
        subreddit_files_param: Not used in export mode (for API compatibility)
        args: Command-line arguments

    Returns:
        None
    """
    print_section("Export Mode: Generating HTML from PostgreSQL database")
    print_info("Data import disabled - processing existing database content only")

    # Validate PostgreSQL is configured
    connection_string = get_postgres_connection_string()
    if not connection_string or 'postgresql://' not in connection_string:
        print_error("Export mode requires PostgreSQL to be configured")
        print_info("Set DATABASE_URL environment variable to PostgreSQL connection string", indent=1)
        return

    # Initialize PostgreSQL database connection
    try:
        db = PostgresDatabase(connection_string, workload_type='user_processing')
        print_success(f"Connected to PostgreSQL database")
    except Exception as e:
        print_error(f"Failed to connect to PostgreSQL: {e}")
        return

    # Ensure indexes exist for optimal export performance
    # This is safe to call even if indexes already exist (will be no-op)
    print_info("Ensuring indexes exist for optimal export performance...")
    db.create_indexes_after_bulk_load()

    # Query database for imported subreddits
    imported_subreddits = db.get_all_imported_subreddits()

    if not imported_subreddits:
        print_warning("No imported subreddits found in database")
        print_info("Use --import-only to import data first", indent=1)
        db.cleanup()
        return

    print_info(f"Found {len(imported_subreddits)} imported subreddits in database")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Copy static assets
    copy_static_assets(output_dir)

    # Change to output directory for file operations
    original_cwd = os.getcwd()
    os.chdir(output_dir)

    try:
        # Create global SEO configuration
        seo_config = create_global_seo_config(args, '.')

        # Initialize statistics manager with PostgreSQL database
        stats_manager = IncrementalStatistics(output_dir, postgres_db=db)

        # Process each subreddit for HTML generation
        total_subreddits = len(imported_subreddits)
        processed_count = 0

        for subreddit in imported_subreddits:
            processed_count += 1
            print_section(f"Exporting r/{subreddit} ({processed_count}/{total_subreddits})")

            try:
                # Mark subreddit as exporting
                db.update_progress_status(subreddit, 'exporting', export_started_at=datetime.now())

                # Generate HTML pages from database
                print_info("Generating HTML pages from database...", indent=1)

                from core.write_html import process_subreddit_database_backed

                html_stats = process_subreddit_database_backed(
                    subreddit,
                    db,  # Pass PostgresDatabase instance
                    imported_subreddits,  # List of all subreddits for navigation
                    seo_config,
                    args
                )

                # PERFORMANCE NOTE: ANALYZE not needed per subreddit in export mode
                # Query planner statistics should already be current from import phase
                # or from create_indexes_after_bulk_load() which runs before export

                # Calculate statistics from database
                print_info("Calculating statistics from database...", indent=1)
                subreddit_stats = db.calculate_subreddit_statistics(subreddit)

                # Query actual filtered/archived counts (what was actually generated with filters)
                with db.pool.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT COUNT(*) as filtered_count
                            FROM posts
                            WHERE LOWER(subreddit) = LOWER(%s)
                            AND score >= %s
                            AND num_comments >= %s
                        """, (subreddit, args.min_score, args.min_comments))
                        filtered_posts = cur.fetchone()['filtered_count']

                # Update stats with actual archived count (posts that met filter criteria)
                subreddit_stats['archived_posts'] = filtered_posts
                subreddit_stats['archived_comments'] = subreddit_stats.get('total_comments', 0)

                stats_manager.save_subreddit_stats(subreddit, subreddit_stats)

                # Persist statistics to PostgreSQL database
                print_info("Persisting statistics to database...", indent=1)
                db.save_subreddit_statistics(
                    subreddit,
                    subreddit_stats,
                    raw_data_size=0,  # Will be updated after HTML generation
                    output_size=0     # Will be updated after HTML generation
                )

                # Verify PostgreSQL FTS indexes
                print_info("Verifying PostgreSQL FTS indexes...", indent=1)
                search_info = verify_fts_indexes_for_subreddit(subreddit, db)

                if search_info:
                    search_metadata = {
                        'posts': search_info[0]['posts'],
                        'chunks': search_info[0]['chunks'],
                        'index_size_mb': search_info[0]['index_size_mb']
                    }
                    stats_manager.save_search_metadata(subreddit, search_metadata)

                # Mark subreddit as completed
                db.update_progress_status(
                    subreddit, 'completed',
                    export_completed_at=datetime.now(),
                    posts_exported=subreddit_stats.get('archived_posts', 0),
                    pages_generated=html_stats.get('pages_generated', 0)
                )

                print_success(f"Export complete: {html_stats.get('pages_generated', 0)} pages generated")

            except Exception as e:
                print_error(f"Export failed for r/{subreddit}: {e}")
                db.update_progress_status(subreddit, 'failed', error_message=str(e))
                continue

        # Generate global pages and SEO files
        print_section("Generating global pages and SEO files")

        # Update homepage with all statistics
        update_homepage_incremental_with_stats(stats_manager, seo_config, db, args.min_score, args.min_comments)

        # Update global search page
        update_global_search_incremental(stats_manager, seo_config)

        # Generate sitemaps and robots.txt from database
        print_info("Generating sitemaps from database...", indent=1)
        from html_modules.html_seo import generate_sitemap_from_database, generate_robots_txt_from_database

        sitemap_success = generate_sitemap_from_database(db, output_dir, seo_config)
        robots_success = generate_robots_txt_from_database(db, output_dir, seo_config)

        if sitemap_success and robots_success:
            print_success("SEO files generated successfully", indent=1)

        # Generate user pages if not disabled
        if not args.no_user_pages:
            print_section("Generating user pages")

            # Get user count from database
            db_info = db.get_database_info()
            total_users = db_info.get('user_count', 0)

            if total_users > 0:
                print_info(f"Found {total_users:,} users in database")

                # Generate enhanced SEO config for user pages
                enhanced_seo_config = seo_config.copy()

                # Use sequential processing for user pages
                from html_modules.html_pages import write_user_page_from_db

                # Load subreddit statistics for user page footers
                subs_with_stats = []
                try:
                    with db.pool.get_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute("SELECT subreddit, total_posts, archived_posts, total_comments, archived_comments FROM subreddit_statistics")
                            for row in cur.fetchall():
                                subs_with_stats.append({
                                    'name': row['subreddit'],
                                    'stats': {
                                        'total_posts': row['total_posts'],
                                        'archived_posts': row['archived_posts'],
                                        'total_comments': row['total_comments'],
                                        'archived_comments': row['archived_comments']
                                    }
                                })
                    print_info(f"✅ Loaded stats for {len(subs_with_stats)} subreddits (user page footers)", indent=2)
                except Exception as e:
                    print_warning(f"Failed to load subreddit stats for footer: {e}", indent=2)
                    subs_with_stats = [{'name': name, 'stats': {}} for name in imported_subreddits]

                print_info(f"Generating user pages for {total_users} users", indent=1)
                write_user_page_from_db(
                    subs_with_stats,
                    '.',  # output_dir
                    batch_size=None,  # Auto-tuning
                    min_activity=0,
                    seo_config=enhanced_seo_config,
                    min_score=args.min_score,
                    min_comments=args.min_comments,
                    hide_deleted=args.hide_deleted_comments
                )
                print_success("User pages generated successfully", indent=1)
            else:
                print_warning("No users found in database", indent=1)

    finally:
        # Restore original working directory
        os.chdir(original_cwd)

    # Cleanup database connection
    db.cleanup()

    print_section("Export Complete")
    print_success(f"Successfully exported {processed_count}/{total_subreddits} subreddits")
    print_success(f"HTML archive generated at: {output_dir}")


def process_archive_incremental(input_dir: str, output_dir: str, subreddit_files: Dict[str, Dict[str, str]], args: argparse.Namespace, resume_state: Optional[str] = None, state_data: Optional[Dict[str, Any]] = None) -> None:
    """
    Process archive incrementally with automatic two-phase processing:
    Processing workflow:
    1. Process each subreddit incrementally with homepage updates
    2. Generate all user pages automatically at the end

    Args:
        input_dir: Directory containing .zst files
        output_dir: Output directory for HTML files
        subreddit_files: Dictionary mapping subreddit names to file paths
        args: Command-line arguments
        resume_state: State returned from detect_resume_state_and_files()
        state_data: Data from saved progress state (if resuming)
    """
    
    # Create output directory
    if os.path.exists(output_dir):
        if not args.force_rebuild:
            print_info(f'Output directory already exists: {output_dir}')
        else:
            print_info('Force rebuild requested - clearing existing progress')
    
    os.makedirs(output_dir, exist_ok=True)

    # Initialize PostgreSQL database connection FIRST (needed by stats_manager)
    connection_string = get_postgres_connection_string()
    reddit_db = PostgresDatabase(connection_string, workload_type='user_processing')
    print_info('🗄️  PostgreSQL database initialized')

    # Initialize incremental processor, statistics system, and performance monitor
    processor = IncrementalProcessor(output_dir, args.memory_limit)
    stats_manager = IncrementalStatistics(output_dir, postgres_db=reddit_db)  # Pass database immediately
    perf_monitor = PerformanceMonitor(output_dir)
    
    # Don't disable saves here - only disable during specific restoration operations
    # Saves should work normally for new subreddit processing during resume
    
    # Handle force rebuild - clear existing statistics
    if args.force_rebuild:
        print_info("Force rebuild requested - clearing existing statistics")
        stats_manager.clear_all_stats()
    
    # ✅ FIXED: Use resume state passed from main() instead of detecting again
    if resume_state in ['resume_subreddits', 'resume_from_emergency'] and state_data:
        # Restore processor state from passed parameters
        processor.completed_subreddits = state_data.get('completed_subreddits', [])
        processor.failed_subreddits = state_data.get('failed_subreddits', [])
        processor.remaining_subreddits = state_data.get('remaining_subreddits', [])
        processor.total_subreddits = state_data.get('total_subreddits', 0)
        
        print_info(f"Resuming from {len(processor.completed_subreddits)} completed subreddits")
        print_info(f"Processing {len(subreddit_files)} remaining subreddits", indent=1)
        
        # Show summary of existing statistics
        stats_summary = stats_manager.get_stats_summary()
        print_info(f"Existing statistics: {stats_summary['total_subreddits']} subreddits, {stats_summary['total_posts']:,} posts", indent=1)
    else:
        # Get stats summary for non-resume case
        stats_summary = stats_manager.get_stats_summary()

    # Initialize performance timing early
    from monitoring.performance_timing import get_timing
    timing = get_timing()

    # Copy static assets BEFORE changing directory
    with timing.time_phase("Copy Static Assets", silent=True):
        copy_static_assets(output_dir)

    # Change working directory to output directory for file operations
    original_cwd = os.getcwd()
    os.chdir(output_dir)

    try:
        # Create global SEO configuration FIRST
        with timing.time_phase("Initialize SEO Config", silent=True):
            seo_config = create_global_seo_config(args, '.')
        
        # ✅ RESUME FIX: Control saves during resume to preserve existing data
        if resume_state in ['resume_subreddits', 'resume_from_emergency']:
            print_info("RESUME MODE: Disabling saves during restoration, will enable for new processing", indent=1)
            os.environ['ARCHIVE_RESUME_MODE'] = 'true'   # Enable resume mode - blocks existing file overwrites
            os.environ['ARCHIVE_RESUME_ACTIVE'] = 'true'  # Block global overwrites
            stats_manager.disable_saves()  # Prevent overwriting during restoration phase
        else:
            print_info("FRESH START: Normal file updates enabled", indent=1)
            os.environ['ARCHIVE_RESUME_MODE'] = 'false'
            os.environ['ARCHIVE_RESUME_ACTIVE'] = 'false'
        
        # Initialize subreddit processing queue
        if resume_state == 'start_fresh':
            processor.initialize_subreddit_list(subreddit_files)
        
        # Incremental Subreddit Processing
        print_section(f"Processing {len(subreddit_files)} subreddits incrementally")
        
        # ✅ RESUME FIX: Always clear resume mode after restoration phase
        if resume_state in ['resume_subreddits', 'resume_from_emergency']:
            print_info("RESUME: Restoration phase complete - enabling all file updates", indent=1)
            os.environ['ARCHIVE_RESUME_MODE'] = 'false'
            os.environ['ARCHIVE_RESUME_ACTIVE'] = 'false'
            stats_manager.enable_saves()  # Always enable saves after resume restoration
            
            if hasattr(processor, '_restoring_from_resume'):
                processor._restoring_from_resume = False
        
        # Process new subreddits if any exist
        if len(subreddit_files) > 0:
            print_info("Processing new subreddits - full updates enabled", indent=1)
        else:
            print_info("No new subreddits to process - but global pages can still be updated", indent=1)
        
        processed_subreddits = {}
        all_subreddit_info = []

        # Start performance monitoring session
        processing_mode = "database"  # Always PostgreSQL
        subreddit_target = args.subreddit if args.subreddit else f"{len(subreddit_files)} subreddits"
        perf_session = perf_monitor.start_session(processing_mode, subreddit_target)

        # Step 4.1: Start phase tracking for overall processing
        perf_monitor.start_phase("Data Processing Phase")

        print_info('🗄️  Using PostgreSQL database backend')

        # Database already initialized earlier (line 1078) and passed to stats_manager

        # Pre-compile Jinja2 templates early to separate compilation from HTML generation timing
        with timing.time_phase("Precompile Jinja2 Templates", silent=True):
            from html_modules.jinja_env import precompile_templates
            from core import write_html
            compiled_count = precompile_templates()
            write_html._TEMPLATES_PRECOMPILED = True  # Prevent duplicate precompilation
            print_info(f'Pre-compiled {compiled_count} Jinja2 templates', indent=1)

        # Drop indexes for bulk loading (10-15x faster imports)
        with timing.time_phase("Drop Indexes"):
            reddit_db.drop_indexes_for_bulk_load()

        print_info(f'Statistics persistence: PostgreSQL', indent=1)

        for subreddit, files in subreddit_files.items():
            if not processor.should_continue():
                print_warning("Processing interrupted by user")
                break

            try:
                # Extract clean subreddit name early (handles paths like "/data/darknet" -> "darknet")
                # This ensures consistent naming across all database operations
                clean_subreddit_name = subreddit.split('/')[-1]

                # Start processing this subreddit (using discovery key for file operations)
                processor.start_subreddit_processing(subreddit)

                # Mark subreddit as 'importing' in processing_metadata table (using clean name)
                reddit_db.update_progress_status(
                    clean_subreddit_name,
                    'importing',
                    import_started_at=datetime.now()
                )

                # Set logging context for this subreddit (using clean name)
                console.set_context(subreddit=clean_subreddit_name, phase="subreddit_processing")
                
                # Load data for this subreddit only
                comments_path = os.path.join('..', files['comments'])
                submissions_path = os.path.join('..', files['submissions'])

                print_info(f"Loading data for r/{subreddit} into PostgreSQL database...", indent=1)

                # Auto-tune batch size for database streaming operations
                from processing.batch_processing_utils import create_batch_config
                import psutil

                available_memory = psutil.virtual_memory().available / (1024 * 1024)  # MB
                target_memory = min(100.0, available_memory * 0.2)  # Use 20% of available memory for DB streaming

                stream_batch_config = create_batch_config(
                    memory_limit_mb=target_memory,
                    performance_target=1500.0,  # Target for database streaming operations
                    auto_tune=True
                )
                stream_batch_size = stream_batch_config.initial_batch_size
                print_info(f'Auto-tuning database streaming: batch_size={stream_batch_size}, memory_limit={target_memory:.1f}MB', indent=2)

                # Stream data directly to PostgreSQL database
                from core.watchful import stream_to_database

                # Process submissions to posts table in database
                print_info("Streaming submissions to database...", indent=2)
                with timing.time_phase(f"Stream Posts ({subreddit})", silent=True):
                    post_stats = stream_to_database(
                        submissions_path, connection_string,
                        'posts', {'subreddit': subreddit},
                        batch_size=stream_batch_size,
                        db=reddit_db  # PERFORMANCE FIX: Reuse existing connection
                    )
                print_info(f"⏱️  Posts streamed: {post_stats['records_processed']} in {post_stats['processing_time']:.2f}s ({post_stats['records_per_second']:.0f}/sec)", indent=3)

                # ✅ CRITICAL: Ensure all posts are committed before inserting comments
                # This prevents foreign key constraint violations when comments reference posts
                reddit_db.sync_transactions()

                # Process comments to comments table in database
                print_info("Streaming comments to database...", indent=2)
                with timing.time_phase(f"Stream Comments ({subreddit})", silent=True):
                    comment_stats = stream_to_database(
                        comments_path, connection_string,
                        'comments', {'subreddit': subreddit},
                        batch_size=stream_batch_size,
                        db=reddit_db  # PERFORMANCE FIX: Reuse existing connection
                    )
                print_info(f"⏱️  Comments streamed: {comment_stats['records_processed']} in {comment_stats['processing_time']:.2f}s ({comment_stats['records_per_second']:.0f}/sec)", indent=3)

                print_info(f"Database streaming complete: {post_stats['records_processed']} posts, {comment_stats['records_processed']} comments", indent=2)

                # Update user statistics after data insertion
                # This populates the PostgreSQL users table from posts and comments data
                # Required for user page generation to work with PostgreSQL backend
                print_info("Updating user statistics in PostgreSQL...", indent=2)
                with timing.time_phase(f"User Stats Update ({clean_subreddit_name})"):
                    reddit_db.update_user_statistics(subreddit_filter=clean_subreddit_name)
                print_success(f"User statistics updated for r/{clean_subreddit_name}", indent=2)

                # Mark subreddit as 'imported' in processing_metadata table with counts (using clean name)
                reddit_db.update_progress_status(
                    clean_subreddit_name,
                    'imported',
                    import_completed_at=datetime.now(),
                    posts_imported=post_stats['records_processed'],
                    comments_imported=comment_stats['records_processed']
                )

                # Save filter values for this subreddit
                print_info(f"Saving filters (score≥{args.min_score}, comments≥{args.min_comments})", indent=2)
                reddit_db.save_subreddit_filters(
                    clean_subreddit_name,
                    min_score=args.min_score,
                    min_comments=args.min_comments
                )

                # PERFORMANCE FIX: ANALYZE removed - will be called once at end of ALL imports
                # Running ANALYZE after every subreddit was causing 30s waste per subreddit
                # ANALYZE is now called once after index creation (line ~1297)

                # Update performance monitoring with streaming stats
                perf_monitor.update_processing_counts(
                    posts=post_stats['records_processed'],
                    comments=comment_stats['records_processed']
                )
                perf_monitor.update_database_metrics(operations=2)  # streaming operations

                # Check for streaming errors
                total_errors = post_stats.get('bad_lines', 0) + comment_stats.get('bad_lines', 0)
                if total_errors > 0:
                    print_warning(f"Streaming completed with {total_errors} errors", indent=2)
                    for _ in range(total_errors):
                        perf_monitor.record_error()

                # Check memory after database operations
                processor.check_memory_usage()

                # ✅ MEMORY FIX: Skip thread reconstruction - HTML is generated directly from database
                # HTML generation (process_subreddit_database_backed) streams directly from database
                # Reconstructing threads into memory is unnecessary and wastes 3+ GB
                print_info("PostgreSQL backend - HTML will be generated directly from database", indent=2)
                print_info("Skipping in-memory thread reconstruction (not needed)", indent=3)

                # Create minimal subreddit_data structure for compatibility
                # This is just for name mapping - no actual post data (preserve original case)
                subreddit_data = {clean_subreddit_name: []}
                thread_count = post_stats['records_processed']  # Use actual post count from streaming

                # Update performance monitoring
                perf_monitor.update_processing_counts(threads=thread_count)
                perf_monitor.update_database_metrics(operations=0)  # No in-memory thread reconstruction

                # Handle subreddit name mismatch between discovery and actual data
                # Discovery might include directory paths like "test-index/holofractal"
                # but actual data contains just "holofractal"
                actual_subreddit = None
                if subreddit in subreddit_data:
                    actual_subreddit = subreddit
                else:
                    # Try to find by cleaned name (last part after slash)
                    clean_name = subreddit.split('/')[-1]
                    if clean_name in subreddit_data:
                        actual_subreddit = clean_name
                        print_info(f"Mapped discovered name '{subreddit}' to actual subreddit '{clean_name}'", indent=1)
                
                if not actual_subreddit:
                    print_warning(f"No matching subreddit found for '{subreddit}' in data", indent=1)
                    print_info(f"Available subreddits: {list(subreddit_data.keys())}", indent=2)
                    processor.fail_subreddit_processing(subreddit, f"Subreddit '{subreddit}' not found in data")
                    continue
                
                posts = subreddit_data[actual_subreddit]
                # Use actual subreddit name for all file generation and processing
                # ✅ MEMORY LEAK FIX: Store only subreddit name, not full post data to prevent accumulation
                processed_subreddits[actual_subreddit] = True

                # Verify PostgreSQL FTS indexes
                print_info("Verifying PostgreSQL FTS indexes...", indent=2)
                subreddit_search_info = verify_fts_indexes_for_subreddit(actual_subreddit, reddit_db)
                all_subreddit_info.extend(subreddit_search_info)

                # Update performance monitoring for FTS verification
                if subreddit_search_info:
                    perf_monitor.update_processing_counts(indices=len(subreddit_search_info))

                # Extract users from PostgreSQL database
                users = set()
                print_info("Extracting users from database...", indent=2)
                try:
                    with reddit_db.pool.get_connection() as conn:
                        from psycopg.rows import dict_row
                        with conn.cursor(row_factory=dict_row) as cursor:
                            # Get unique authors from posts
                            cursor.execute(
                                "SELECT DISTINCT author FROM posts WHERE subreddit = %s AND author IS NOT NULL",
                                (actual_subreddit,)
                            )
                            for row in cursor:
                                users.add(row['author'])

                            # Get unique authors from comments
                            cursor.execute(
                                "SELECT DISTINCT author FROM comments WHERE subreddit = %s AND author IS NOT NULL",
                                (actual_subreddit,)
                            )
                            for row in cursor:
                                users.add(row['author'])

                    print_info(f"Extracted {len(users)} unique users from database", indent=2)
                except Exception as e:
                    print_warning(f"Failed to extract users from database: {e}", indent=2)
                    users = set()  # Empty set as fallback
                
                # Generate pages for this subreddit using actual name (no user pages yet)
                enhanced_seo_config = create_enhanced_seo_config(actual_subreddit, files, seo_config)

                # Calculate statistics using PostgreSQL database
                # PostgreSQL database connection already initialized as reddit_db
                # Note: We're already in output_dir from os.chdir() above
                try:
                    # Calculate statistics using the database-backed approach with PostgreSQL
                    stats_manager.add_subreddit_statistics_from_postgres(
                        actual_subreddit, reddit_db, args.min_score, args.min_comments
                    )
                    print_info(f"PostgreSQL statistics calculated for {actual_subreddit}")

                    # For compatibility, still get stats in the old format for HTML generation
                    # Use the proper database-backed statistics method with all required parameters
                    with reddit_db.pool.get_connection() as conn:
                        from core.write_html import calculate_subreddit_statistics_from_database
                        # Create cursors from the connection for the statistics function
                        with conn.cursor() as cursor:
                            subreddit_stats = calculate_subreddit_statistics_from_database(
                                cursor, cursor, actual_subreddit, args.min_score, args.min_comments, enhanced_seo_config
                            )
                except Exception as e:
                    print_error(f"Failed to calculate database statistics for {actual_subreddit}: {e}")
                    # Fallback to default stats
                    subreddit_stats = {'archived_posts': 0, 'archived_comments': 0, 'unique_authors': 0}

                # Format stats for compatibility with existing code
                stats = {
                    'subreddits': {
                        actual_subreddit: {
                            'filtered_links': subreddit_stats['archived_posts'],
                            'comments': subreddit_stats['archived_comments']
                        }
                    }
                }

                # Generate HTML pages from PostgreSQL database
                print_info("Generating HTML pages from database...", indent=2)

                # Use complete database-backed processing pipeline with PostgreSQL
                # Note: We're already in output_dir from os.chdir() above
                from core.write_html import process_subreddit_database_backed

                with timing.time_phase(f"HTML Generation ({actual_subreddit})", silent=True):
                    html_stats = process_subreddit_database_backed(
                        actual_subreddit,
                        reddit_db,  # Pass PostgresDatabase instance
                        list(processed_subreddits.keys()),  # List of completed subreddits
                        enhanced_seo_config,
                        args
                    )

                pages_generated = html_stats.get('pages_generated', 0)
                html_time = timing.timings.get(f"HTML Generation ({actual_subreddit})", 0)
                pages_per_sec = pages_generated / html_time if html_time > 0 else 0
                print_info(f"⏱️  HTML generated: {pages_generated} pages in {html_time:.2f}s ({pages_per_sec:.1f} pages/sec)", indent=3)

                # Update performance monitoring
                perf_monitor.update_processing_counts(pages=html_stats.get('pages_generated', 0))
                perf_monitor.update_database_metrics(operations=5)  # HTML generation operations

                # User statistics maintained via update_user_statistics() during data insertion
                # This eliminates the N+1 query bottleneck (2,000+ queries removed)
                print_info("✅ User tracking handled automatically by PostgresDatabase", indent=2)

                # Update processed_subreddits with complete statistics
                processed_subreddits[actual_subreddit] = {
                    'stats': subreddit_stats,
                    'search_entries': 0,
                    'users_linked': 0,  # Tracked automatically, no separate linking phase needed
                    'html_pages': html_stats.get('pages_generated', 0),
                    'processing_mode': 'database'
                }

                # ✅ MEMORY FIX: Save statistics instead of keeping full post data
                stats_manager.save_subreddit_stats(actual_subreddit, subreddit_stats)

                # Save search metadata using PostgreSQL streaming stats
                search_metadata = {
                    'posts': thread_count,  # Use streaming stats from PostgreSQL
                    'chunks': subreddit_search_info[0]['chunks'] if subreddit_search_info else 0,
                    'index_size_mb': subreddit_search_info[0]['index_size_mb'] if subreddit_search_info else 0
                }
                stats_manager.save_search_metadata(actual_subreddit, search_metadata)

                # Complete subreddit processing with actual name
                processor.complete_subreddit_processing(actual_subreddit, users)

                # Mark subreddit as 'completed' in processing_metadata table with pages count
                reddit_db.update_progress_status(
                    actual_subreddit,
                    'completed',
                    export_completed_at=datetime.now(),
                    pages_generated=html_stats.get('pages_generated', 0)
                )

                # Save/update filter values for this subreddit (in case of re-export with different filters)
                print_info(f"Updating filters (score≥{args.min_score}, comments≥{args.min_comments})", indent=2)
                reddit_db.save_subreddit_filters(
                    actual_subreddit,
                    min_score=args.min_score,
                    min_comments=args.min_comments
                )

                # PostgreSQL already maintains user statistics via update_user_statistics()
                print_info("PostgreSQL backend: user statistics already tracked by database", indent=1)
                
                # ✅ MEMORY FIX: Always run incremental updates after subreddit completion
                # Protection against overwrites is handled at the function level via environment variables
                print_info("Running incremental updates after subreddit completion...", indent=1)

                # ✅ MEMORY FIX: Generate progressive homepage update using persistent statistics
                update_homepage_incremental_with_stats(stats_manager, seo_config, reddit_db, args.min_score, args.min_comments)
                
                # ✅ MEMORY FIX: Update global search page incrementally
                update_global_search_incremental(stats_manager, seo_config)

                # 🧠 MEMORY MANAGEMENT: Cleanup after subreddit processing (PostgreSQL mode)
                with timing.time_phase(f"Memory Cleanup ({actual_subreddit})", silent=True):
                    memory_before = processor.check_memory_usage()
                    print_info(f"Memory before cleanup: {memory_before:.1%}", indent=1)

                    # Clear main data structures
                    # Only subreddit_data and posts exist (no threads variable in PostgreSQL mode)
                    del subreddit_data, posts
                    # thread_count is just an integer, no need to delete explicitly

                    # Clear accumulated processing artifacts
                    if 'subreddit_search_info' in locals():
                        del subreddit_search_info
                    if 'users' in locals():
                        users.clear()
                        del users
                    if 'current_subreddit_user_data' in locals():
                        del current_subreddit_user_data

                    # Clear any template/HTML caches that might exist
                    # Note: This addresses template cache accumulation
                    try:
                        from html_modules.html_templates import clear_template_cache
                        clear_template_cache()
                    except (ImportError, AttributeError):
                        pass  # Template cache clearing not available

                    # Generation-aware garbage collection for connection pool cleanup
                    import gc

                    # Generation-aware collection for optimal cleanup
                    collected_gen0 = gc.collect(generation=0)  # Young objects (most likely to be freed)
                    collected_gen1 = gc.collect(generation=1)  # Middle-aged objects
                    collected_gen2 = gc.collect(generation=2)  # Old objects and cycles

                    memory_after = processor.check_memory_usage()
                    memory_reclaimed = memory_before - memory_after
                    print_info(f"Memory after optimal GC: {memory_after:.1%} (reclaimed: {memory_reclaimed:.1%})", indent=1)
                    print_info(f"GC collected: gen0={collected_gen0}, gen1={collected_gen1}, gen2={collected_gen2} (total: {collected_gen0+collected_gen1+collected_gen2})", indent=2)

                # Memory threshold enforcement
                if memory_after > 0.80:  # 80% threshold for proactive cleanup
                    print_warning(f"High memory usage after cleanup ({memory_after:.1%}), triggering additional cleanup", indent=1)
                    
                    # Clear any remaining accumulated data structures
                    if len(processed_subreddits) > 5:  # Keep only recent entries
                        oldest_keys = list(processed_subreddits.keys())[:-3]  # Keep last 3
                        for key in oldest_keys:
                            del processed_subreddits[key]
                        print_info(f"Cleared {len(oldest_keys)} older processed_subreddits entries", indent=2)
                    
                    if len(all_subreddit_info) > 10:  # Limit subreddit info accumulation
                        all_subreddit_info = all_subreddit_info[-5:]  # Keep only last 5
                        print_info("Trimmed all_subreddit_info to last 5 entries", indent=2)
                    
                    # Final garbage collection after additional cleanup
                    final_collected = gc.collect()
                    final_memory = processor.check_memory_usage()
                    print_info(f"Final memory after aggressive cleanup: {final_memory:.1%} (additional gc: {final_collected})", indent=2)
                
            except Exception as e:
                processor.fail_subreddit_processing(subreddit, str(e))
                print_error(f"Error processing r/{subreddit}: {e}")
                continue

        # Recreate indexes after all bulk loading completes
        print_section("Recreating indexes for export phase")
        print_info("This may take time for large datasets but is essential for optimal query performance...")
        with timing.time_phase("Create All Indexes"):
            reddit_db.create_indexes_after_bulk_load()
        with timing.time_phase("ANALYZE Tables"):
            reddit_db.analyze_tables(['posts', 'comments', 'users'])

        # User Page Generation (if not disabled)
        print_info(f"🔍 [DIAGNOSTIC] User page check: no_user_pages={args.no_user_pages}, should_continue={processor.should_continue()}")
        if not args.no_user_pages and processor.should_continue():
            processor.start_user_page_generation()

            # Set logging context for user page generation
            console.set_context(subreddit=None, phase="user_page_generation")

            print_section("🚀 Generating user pages (parallel processing integrated)")
            print_info("📋 Parallel user processing will activate based on system resources", indent=1)

            # ✅ Check PostgreSQL user database status
            # ✅ FIX: Recreate database connection if needed for user page generation
            print_info("Checking PostgreSQL user database status...", indent=1)

            # Ensure we have a valid database connection
            needs_recreation = False
            if reddit_db is None:
                needs_recreation = True
            else:
                # Check if the connection pool is still usable
                try:
                    if not reddit_db.health_check():
                        print_warning("Database health check failed, connection pool may be closed", indent=2)
                        needs_recreation = True
                except Exception as e:
                    print_warning(f"Database health check raised exception: {e}", indent=2)
                    needs_recreation = True

            if needs_recreation:
                print_info("Recreating database connection for user page generation...", indent=2)
                try:
                    connection_string = get_postgres_connection_string()
                    reddit_db = PostgresDatabase(connection_string, workload_type='user_processing')
                    print_success("Database connection recreated successfully", indent=2)
                except Exception as e:
                    print_error(f"Failed to recreate database connection: {e}", indent=2)
                    total_users = 0

            # Check PostgreSQL users table
            if reddit_db:
                try:
                    db_info = reddit_db.get_database_info()
                    total_users = db_info.get('user_count', 0)
                    print_info(f"PostgreSQL user database: {total_users} users", indent=1)
                except Exception as e:
                    print_error(f"Failed to query PostgreSQL users: {e}", indent=1)
                    total_users = 0

            print_info(f"Found {len(processed_subreddits)} subreddits from current session", indent=1)

        try:
            # Generate user pages if we have users in the PostgreSQL database
            if total_users > 0:
                # Get all completed subreddits for navigation
                from utils.simple_json_utils import load_subreddit_stats
                all_completed_subreddits = load_subreddit_stats('.')
                all_subreddit_names = set(processed_subreddits.keys()) | set(all_completed_subreddits.keys())

                print_info(f"Found {total_users:,} total users in PostgreSQL database", indent=1)
                
                # Generate enhanced SEO config for user pages
                enhanced_seo_config = create_enhanced_seo_config_global(subreddit_files, seo_config)
                
                # ✅ OPTIMIZATION: Detect if we're processing a single subreddit for incremental user page updates
                is_single_subreddit_mode = (
                    args.subreddit and  # Single subreddit specified
                    len(processed_subreddits) == 1 and  # Only one subreddit processed in this session  
                    args.subreddit in processed_subreddits  # The processed subreddit matches the target
                )
                
                # Choose between parallel and sequential processing based on system resources and user count
                import psutil
                available_memory = psutil.virtual_memory().available / (1024 * 1024)  # MB
                cpu_count = psutil.cpu_count()

                print_info(f"🔍 [DIAGNOSTIC] System resources: {total_users} users, {cpu_count} cores, {available_memory:.0f}MB memory", indent=1)

                # Determine optimal processing mode
                use_parallel = (
                    total_users >= 1000 and          # Worth parallelizing for large user counts
                    available_memory >= 2000 and     # Need at least 2GB available memory
                    cpu_count >= 4                   # Need at least 4 cores for effective parallelization
                )

                print_info(f"🔍 [DIAGNOSTIC] Parallel processing decision:", indent=1)
                print_info(f"    - Users >= 1000: {total_users >= 1000} ({total_users} users)", indent=1)
                print_info(f"    - Memory >= 2000MB: {available_memory >= 2000} ({available_memory:.0f}MB available)", indent=1)
                print_info(f"    - CPU >= 4 cores: {cpu_count >= 4} ({cpu_count} cores)", indent=1)
                print_info(f"    - Final decision: use_parallel = {use_parallel}", indent=1)

                # Step 4.1: Start user page performance tracking
                user_tracker = perf_monitor.start_user_page_tracking(total_users)

                if use_parallel:
                    print_info(f"🚀 Using PARALLEL user processing ({cpu_count} cores, {available_memory:.0f}MB memory)", indent=1)
                    try:
                        from processing.parallel_user_processing import write_user_pages_parallel, write_user_pages_parallel_for_subreddit
                        print_info("✅ Parallel processing module imported successfully", indent=2)
                    except ImportError as e:
                        print_info(f"❌ Failed to import parallel processing module: {e}", indent=2)
                        print_info("Falling back to sequential processing", indent=2)
                        use_parallel = False

                    if is_single_subreddit_mode:
                        # ✅ PARALLEL INCREMENTAL MODE: Process users from specific subreddit in parallel
                        print_info(f"Parallel incremental user page generation for r/{args.subreddit}", indent=1)

                        # Load subreddit statistics for user page footers
                        subs_with_stats = []
                        try:
                            with reddit_db.pool.get_connection() as conn:
                                with conn.cursor() as cur:
                                    cur.execute("SELECT subreddit, total_posts, archived_posts, total_comments, archived_comments FROM subreddit_statistics")
                                    for row in cur.fetchall():
                                        subs_with_stats.append({
                                            'name': row['subreddit'],
                                            'stats': {
                                                'total_posts': row['total_posts'],
                                                'archived_posts': row['archived_posts'],
                                                'total_comments': row['total_comments'],
                                                'archived_comments': row['archived_comments']
                                            }
                                        })
                            print_info(f"✅ Loaded stats for {len(subs_with_stats)} subreddits (user page footers)", indent=2)
                        except Exception as e:
                            print_warning(f"Failed to load subreddit stats for footer: {e}", indent=2)
                            subs_with_stats = [{'name': name, 'stats': {}} for name in all_subreddit_names]

                        with timing.time_phase(f"User Pages Parallel Incremental", silent=True):
                            success = write_user_pages_parallel_for_subreddit(
                                subs_with_stats,
                                '.',  # output_dir
                                args.subreddit,  # target subreddit
                                batch_size=None,  # Auto-optimized
                                min_activity=0,
                                seo_config=enhanced_seo_config,
                                min_score=args.min_score,
                                min_comments=args.min_comments,
                                hide_deleted=args.hide_deleted_comments
                            )

                        user_time = timing.timings.get("User Pages Parallel Incremental", 0)
                        print_info(f"⏱️  User pages: {total_users} users in {user_time:.2f}s ({total_users/user_time:.1f} users/sec)" if user_time > 0 else f"⏱️  User pages: {total_users} users completed", indent=2)

                        if success:
                            print_success(f"Parallel incremental user pages generated for r/{args.subreddit}", indent=1)
                        else:
                            print_warning(f"Parallel processing had issues for r/{args.subreddit}, but some pages may have been generated", indent=1)
                    else:
                        # ✅ PARALLEL FULL MODE: Process all users in parallel
                        print_info(f"Parallel full user page generation for all users ({total_users} users)", indent=1)

                        # Load subreddit statistics for user page footers
                        subs_with_stats = []
                        try:
                            with reddit_db.pool.get_connection() as conn:
                                with conn.cursor() as cur:
                                    cur.execute("SELECT subreddit, total_posts, archived_posts, total_comments, archived_comments FROM subreddit_statistics")
                                    for row in cur.fetchall():
                                        subs_with_stats.append({
                                            'name': row['subreddit'],
                                            'stats': {
                                                'total_posts': row['total_posts'],
                                                'archived_posts': row['archived_posts'],
                                                'total_comments': row['total_comments'],
                                                'archived_comments': row['archived_comments']
                                            }
                                        })
                            print_info(f"✅ Loaded stats for {len(subs_with_stats)} subreddits (user page footers)", indent=2)
                        except Exception as e:
                            print_warning(f"Failed to load subreddit stats for footer: {e}", indent=2)
                            subs_with_stats = [{'name': name, 'stats': {}} for name in all_subreddit_names]

                        with timing.time_phase(f"User Pages Parallel Full", silent=True):
                            success = write_user_pages_parallel(
                                subs_with_stats,
                                '.',  # output_dir
                                batch_size=None,  # Auto-optimized
                                min_activity=0,
                                seo_config=enhanced_seo_config,
                                min_score=args.min_score,
                                min_comments=args.min_comments,
                                hide_deleted=args.hide_deleted_comments
                            )

                        user_time = timing.timings.get("User Pages Parallel Full", 0)
                        print_info(f"⏱️  User pages: {total_users} users in {user_time:.2f}s ({total_users/user_time:.1f} users/sec)" if user_time > 0 else f"⏱️  User pages: {total_users} users completed", indent=2)

                        if success:
                            print_success("Parallel full user pages generated successfully", indent=1)
                        else:
                            print_warning("Parallel processing had issues, but some pages may have been generated", indent=1)

                else:
                    print_info(f"📝 Using SEQUENTIAL user processing (system: {cpu_count} cores, {available_memory:.0f}MB memory, {total_users} users)", indent=1)
                    print_info("🔍 Sequential processing will be used due to system constraints or user count", indent=2)

                    if is_single_subreddit_mode:
                        # ✅ SEQUENTIAL INCREMENTAL MODE: Only update user pages for users with content in the target subreddit
                        from html_modules.html_pages import write_user_page_incremental

                        print_info(f"Sequential incremental user page generation for r/{args.subreddit}", indent=1)
                        with timing.time_phase(f"User Pages Sequential Incremental", silent=True):
                            write_user_page_incremental(
                                [{'name': name} for name in all_subreddit_names],
                                '.',  # output_dir - current working directory (we're already in output_dir)
                                args.subreddit,  # target_subreddit
                                batch_size=None,  # Enable auto-tuning for optimal performance
                                min_activity=0,   # Include all users
                                seo_config=enhanced_seo_config,
                                min_score=args.min_score,
                                min_comments=args.min_comments,
                                hide_deleted=args.hide_deleted_comments
                            )
                        user_time = timing.timings.get("User Pages Sequential Incremental", 0)
                        print_info(f"⏱️  User pages: {total_users} users in {user_time:.2f}s", indent=2)
                        print_success(f"Sequential incremental user pages generated for r/{args.subreddit}", indent=1)
                    else:
                        # ✅ SEQUENTIAL FULL MODE: Generate all user pages (original behavior)
                        from html_modules.html_pages import write_user_page_from_db

                        print_info(f"Sequential full user page generation for all users", indent=1)
                        with timing.time_phase(f"User Pages Sequential Full", silent=True):
                            write_user_page_from_db(
                                [{'name': name} for name in all_subreddit_names],
                                '.',  # output_dir - current working directory (we're already in output_dir)
                                batch_size=None,  # Enable auto-tuning for optimal performance
                                min_activity=0,   # Include all users
                                seo_config=enhanced_seo_config,
                                min_score=args.min_score,
                                min_comments=args.min_comments,
                                hide_deleted=args.hide_deleted_comments
                            )
                        user_time = timing.timings.get("User Pages Sequential Full", 0)
                        print_info(f"⏱️  User pages: {total_users} users in {user_time:.2f}s", indent=2)
                        print_success("Sequential full user pages generated successfully", indent=1)
                
                # Step 4.1: Complete user page performance tracking and display summary
                user_metrics = perf_monitor.get_user_page_metrics()
                if user_metrics:
                    print_section("User Page Performance Summary")
                    console.user_page_performance_summary(user_metrics)

                # ✅ FIX: Mark user pages as generated in activity tracking
                processor.user_activity['user_pages_generated'] = True
                processor._save_user_activity()
            else:
                print_warning("No users found, skipping user page generation", indent=1)
        
        except Exception as e:
            print_error("Error during user page generation", indent=1)
            print_error(str(e), indent=2)
            import traceback
            traceback.print_exc()
        
        # Generate final homepage and global elements using statistics manager
        print_section("Finalizing archive with statistics")
        try:
            # ✅ RESUME FIX: Always finalize to ensure global pages reflect current statistics
            # This is safe because resume mode has been cleared and statistics are current
            should_finalize = True  # Always finalize during resume to update global pages

            if resume_state in ['resume_subreddits', 'resume_from_emergency'] and len(subreddit_files) == 0:
                print_info("RESUME: No new subreddits processed, but updating global pages with current statistics", indent=1)
            elif len(subreddit_files) > 0:
                print_info("Finalizing archive with newly processed subreddits", indent=1)
            else:
                print_info("Finalizing archive with current statistics", indent=1)

            with timing.time_phase("Finalize Archive"):
                finalize_archive_with_stats(stats_manager, all_subreddit_info, seo_config, postgres_db=reddit_db, min_score=args.min_score, min_comments=args.min_comments)
        except Exception as e:
            print_error(f"Error in finalize_archive_with_stats: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback to basic index generation
            print_warning("Attempting fallback index generation", indent=1)
            try:
                from html_modules.html_dashboard import write_index
                all_stats = stats_manager.get_all_subreddit_stats()
                if all_stats:
                    processed_subs = []
                    for subreddit_data in all_stats:
                        processed_subs.append({
                            'name': subreddit_data['name'],
                            'num_links': subreddit_data['stats'].get('archived_posts', 0),
                            'stats': subreddit_data['stats']
                        })
                    
                    write_index(processed_subs, seo_config or {}, 0, 0, 0, reddit_db=None)
                    print_success("Fallback index generation successful", indent=1)
                else:
                    print_error("No statistics available for fallback generation", indent=1)
            except Exception as e2:
                print_error(f"Fallback also failed: {e2}", indent=1)
        
        # Complete processing
        processor.complete_processing()

        # End performance monitoring session and display results
        print_section("Performance Analysis")
        final_metrics = perf_monitor.end_session()

        # Step 4.1: Display comprehensive performance summary
        perf_monitor.display_performance_summary()

        # Display performance comparison if available
        perf_monitor.compare_approaches()

        # Display detailed timing breakdown
        print_section("Detailed Timing Breakdown")
        timing.print_summary()

        # Save timing data for historical analysis
        timing_file = os.path.join(output_dir, '.archive-timing.json')
        timing.save_to_file(timing_file)

        # Clean up progress files
        processor.cleanup()

        print_success(f'Archive generated successfully in {output_dir}')
        print_info(f'Homepage: {output_dir}/r/index.html', indent=1)
        
    except Exception as e:
        print_error(f"Fatal error during processing: {e}")
        processor._save_progress_state('error')
        raise
    finally:
        # Restore original working directory
        os.chdir(original_cwd)


def create_enhanced_seo_config(subreddit: str, files: Dict[str, str], base_seo_config: Dict[str, Any]) -> Dict[str, Any]:
    """Create enhanced SEO config for a single subreddit"""
    enhanced_config = {subreddit: base_seo_config.copy()}
    enhanced_config[subreddit]['posts'] = os.path.join('..', files['submissions'])
    enhanced_config[subreddit]['comments'] = os.path.join('..', files['comments'])
    return enhanced_config


def create_enhanced_seo_config_global(subreddit_files: Dict[str, Dict[str, str]], base_seo_config: Dict[str, Any]) -> Dict[str, Any]:
    """Create enhanced SEO config for all subreddits"""
    enhanced_config = {}
    for subreddit, files in subreddit_files.items():
        clean_name = subreddit.split('/')[-1]
        enhanced_config[clean_name] = base_seo_config.copy()
        enhanced_config[clean_name]['posts'] = os.path.join('..', files['submissions'])
        enhanced_config[clean_name]['comments'] = os.path.join('..', files['comments'])
    return enhanced_config


def update_homepage_incremental(processed_subreddits: Dict[str, Any], subreddit_info: List[Dict[str, Any]], seo_config: Dict[str, Any]) -> None:
    """Update homepage with currently processed subreddits"""
    try:
        from html_modules.html_dashboard import write_index
        from html_modules.html_statistics import calculate_subreddit_statistics
        
        # Format processed subreddits for homepage with proper statistics
        processed_subs = []
        for name, post_list in processed_subreddits.items():
            try:
                # Calculate proper statistics for this subreddit
                stats = calculate_subreddit_statistics(post_list, 0, 0, seo_config, name)
                
                processed_subs.append({
                    'name': name,
                    'num_links': stats['archived_posts'],
                    'stats': stats
                })
            except Exception as e:
                print(f"    ⚠️  Warning: Error calculating stats for {name}: {e}")
                # Fallback to basic stats
                processed_subs.append({
                    'name': name,
                    'stats': {
                        'archived_posts': len(post_list),
                        'archived_comments': sum(len(p.get('comments', [])) for p in post_list),
                        'unique_users': len(set(
                            [p['author'] for p in post_list] + 
                            [c.get('author', '') for p in post_list for c in p.get('comments', [])]
                        )),
                        'output_size': 0,
                        'raw_data_size': 0
                    }
                })
        
        # Generate updated homepage with error handling
        try:
            write_index(processed_subs, seo_config, reddit_db=None)
            print_info(f"Homepage updated with {len(processed_subreddits)} subreddits", indent=1)
        except Exception as e:
            print_warning(f"Homepage generation failed: {e}", indent=1)
            # Try with minimal data
            try:
                minimal_subs = []
                for name in processed_subreddits.keys():
                    minimal_subs.append({
                        'name': name,
                        'stats': {
                            'archived_posts': 0,
                            'archived_comments': 0,
                            'unique_users': 0,
                            'output_size': 0,
                            'raw_data_size': 0
                        }
                    })
                write_index(minimal_subs, seo_config, reddit_db=None)
                print_info(f"Homepage updated with minimal data for {len(processed_subreddits)} subreddits", indent=1)
            except Exception as e2:
                print_error(f"Critical error: Unable to update homepage: {e2}", indent=1)
        
    except Exception as e:
        print_error(f"Critical error in homepage update: {e}", indent=1)


def update_homepage_incremental_with_stats(stats_manager: IncrementalStatistics, seo_config: Dict[str, Any], postgres_db: PostgresDatabase, min_score: int = 0, min_comments: int = 0) -> None:
    """
    Update homepage using persistent statistics instead of keeping full post data in memory.
    This is the memory-efficient replacement for update_homepage_incremental.

    Args:
        stats_manager: IncrementalStatistics instance
        seo_config: SEO configuration
        postgres_db: PostgresDatabase instance (required)
        min_score: Minimum score filter for dashboard display (default: 0)
        min_comments: Minimum comments filter for dashboard display (default: 0)
    """
    try:
        from html_modules.html_dashboard import write_index

        # Generate updated homepage using PostgreSQL database
        write_index(
            postgres_db,  # PostgreSQL database (required)
            seo_config=seo_config,
            min_score=min_score,
            min_comments=min_comments
        )

        print_info("Homepage updated using PostgreSQL database", indent=1)
        
    except Exception as e:
        print_error(f"Error updating homepage with statistics: {e}", indent=1)
        import traceback
        traceback.print_exc()


def update_global_search_incremental(stats_manager: IncrementalStatistics, seo_config: Dict[str, Any]) -> None:
    """
    Update global search page using persistent search metadata.
    This ensures the global search page includes all completed subreddits.
    Uses atomic JSON manager to safely merge subreddit data during resume operations.
    """
    try:
        # CRITICAL FIX: Read directly from persistent search metadata files
        # instead of relying on potentially incomplete in-memory cache
        from utils.simple_json_utils import load_search_metadata
        output_dir = stats_manager.output_dir
        all_persistent_search_metadata = load_search_metadata(output_dir)
        
        print_info(f"Loading search metadata from persistent files: found {len(all_persistent_search_metadata)} entries", indent=1)
        
        if not all_persistent_search_metadata:
            print_info("No search metadata available for global search update", indent=1)
            return
        
        # Create subreddit info list for global search from persistent data
        subreddit_info = []
        for search_data in all_persistent_search_metadata.values():
            subreddit_info.append({
                'name': search_data['name'],
                'posts': search_data.get('posts', 0),
                'chunks': search_data.get('chunks', 0),
                'index_size_mb': search_data.get('index_size_mb', 0)
            })
        
        # Sort by post count for popular suggestions
        subreddit_info.sort(key=lambda x: x['posts'], reverse=True)
        
        # Update global subreddit list for search using atomic manager
        print_info('Updating global subreddit list for search using atomic manager...', indent=1)
        
        # Use simple JSON merging for safe write - critical for resume operations
        success = save_subreddit_list(output_dir, subreddit_info)
        
        if success:
            print_info(f"Global subreddit list updated successfully with {len(subreddit_info)} subreddits", indent=1)
        else:
            print_error("Failed to update global subreddit list", indent=1)
            return

    except Exception as e:
        print_error(f"Error updating global search: {e}", indent=1)
        import traceback
        traceback.print_exc()


def finalize_archive_with_stats(stats_manager: IncrementalStatistics, subreddit_info: List[Dict[str, Any]], seo_config: Dict[str, Any], postgres_db: Optional[PostgresDatabase] = None, min_score: int = 0, min_comments: int = 0) -> None:
    """
    Generate final archive elements using persistent statistics (memory-efficient version).

    Args:
        stats_manager: IncrementalStatistics instance for loading persistent stats
        subreddit_info: List of subreddit search metadata
        seo_config: SEO configuration dictionary
        postgres_db: PostgresDatabase instance (for database-first mode)
        min_score: Minimum score filter for dashboard display (default: 0)
        min_comments: Minimum comments filter for dashboard display (default: 0)
    """
    try:
        from html_modules.html_dashboard import write_index

        # Generate root-level homepage (index.html) using persistent statistics
        print_info("Generating main homepage...", indent=1)

        # Get ALL subreddit statistics (historical + current session)
        all_subreddit_stats = stats_manager.get_all_subreddit_stats()

        # FALLBACK: If stats_manager is empty, query database directly
        if not all_subreddit_stats and postgres_db:
            print_info("Stats manager empty - falling back to database query", indent=1)
            try:
                # Query processing_metadata for imported subreddits
                imported_subreddits = postgres_db.get_all_imported_subreddits()

                if not imported_subreddits:
                    # Last resort: query posts table directly for subreddit list
                    print_info("No metadata found - querying posts table directly", indent=2)
                    with postgres_db.pool.get_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                SELECT DISTINCT subreddit
                                FROM posts
                                ORDER BY subreddit
                            """)
                            imported_subreddits = [row[0] for row in cur.fetchall()]

                # Build statistics from database for each subreddit
                all_subreddit_stats = []
                for subreddit in imported_subreddits:
                    with postgres_db.pool.get_connection() as conn:
                        with conn.cursor() as cur:
                            # Get post and comment counts
                            cur.execute("""
                                SELECT
                                    COUNT(*) as post_count,
                                    COALESCE(SUM((json_data->>'num_comments')::int), 0) as comment_count
                                FROM posts
                                WHERE subreddit = %s
                            """, (subreddit,))
                            post_count, comment_count = cur.fetchone()

                            all_subreddit_stats.append({
                                'name': subreddit,
                                'stats': {
                                    'archived_posts': post_count,
                                    'archived_comments': comment_count,
                                    'output_size': 0  # Unknown, but not critical
                                }
                            })

                print_success(f"Loaded statistics for {len(all_subreddit_stats)} subreddits from database", indent=2)

            except Exception as e:
                print_error(f"Failed to query database for subreddit statistics: {e}", indent=2)
                import traceback
                traceback.print_exc()
                return
        elif not all_subreddit_stats:
            print_warning("No subreddit statistics available and no database connection", indent=1)
            return

        # Format statistics for homepage generation
        processed_subs = []
        for subreddit_data in all_subreddit_stats:
            name = subreddit_data['name']
            stats = subreddit_data['stats']

            processed_subs.append({
                'name': name,
                'num_links': stats.get('archived_posts', 0),
                'stats': stats
            })

        # Calculate total output size from all statistics
        total_output_size = sum(s['stats'].get('output_size', 0) for s in processed_subs)

        # Generate main homepage at root level using PostgreSQL database
        write_index(
            postgres_db,  # PostgreSQL database (required)
            seo_config=seo_config,
            min_score=min_score,
            min_comments=min_comments
        )

        # Generate sitemaps and SEO files from PostgreSQL database
        print_info("Generating sitemaps and SEO files...", indent=1)
        print_info("🗄️  Using database-backed SEO generation", indent=2)
        from html_modules.html_seo import (
            generate_sitemap_from_database,
            generate_robots_txt_from_database
        )

        # Generate sitemaps using database queries (use current working directory as output)
        output_dir = os.getcwd()  # Current working directory where databases would be
        sitemap_success = generate_sitemap_from_database(postgres_db, output_dir, seo_config)

        # Generate robots.txt using database information
        robots_success = generate_robots_txt_from_database(postgres_db, output_dir, seo_config)

        if sitemap_success and robots_success:
            print_success("Generated database-backed sitemaps and SEO files", indent=2)
        else:
            print_warning("Some database-backed SEO files failed to generate", indent=2)

    except Exception as e:
        print_warning(f"Failed to generate SEO files: {e}", indent=1)
        import traceback
        traceback.print_exc()


def finalize_archive(processed_subreddits: Dict[str, Any], subreddit_info: List[Dict[str, Any]], seo_config: Dict[str, Any]) -> None:
    """Generate final archive elements (sitemaps, robots.txt, etc.) - LEGACY VERSION"""
    try:
        from html_modules.html_seo import generate_chunked_sitemaps
        from html_modules.html_dashboard import write_index

        # Generate root-level homepage (index.html)
        print_info("Generating main homepage...", indent=1)
        
        # Format processed subreddits for homepage using proper statistics calculation
        processed_subs = []
        for name, post_list in processed_subreddits.items():
            # Use the existing calculate_subreddit_statistics function
            from html_modules.html_statistics import calculate_subreddit_statistics
            
            # Calculate proper statistics for this subreddit
            stats = calculate_subreddit_statistics(post_list, 0, 0, seo_config, name)
            
            processed_subs.append({
                'name': name,
                'num_links': stats['archived_posts'],
                'stats': stats
            })
        
        # Calculate total output size manually since calculate_final_output_sizes may not exist
        total_output_size = 0
        try:
            from html_modules.html_statistics import calculate_final_output_sizes
            total_output_size = calculate_final_output_sizes(processed_subs)
        except (ImportError, AttributeError):
            print(f"    Note: Using estimated output size")
            total_output_size = sum(len(posts) * 50000 for posts in processed_subreddits.values())  # Rough estimate
        
        # Generate main homepage at root level
        write_index(processed_subs, seo_config, 0, 0, reddit_db=None)
        
        # Generate sitemaps
        user_index = {}  # Empty for now, would be populated if user pages generated
        
        # Fix the list comprehension to use correct variable names
        subs_for_sitemap = []
        for name, post_list in processed_subreddits.items():
            subs_for_sitemap.append({'name': name, 'num_links': len(post_list)})
        
        generate_chunked_sitemaps(subs_for_sitemap, user_index, seo_config)
        
        print_success("Generated sitemaps and SEO files", indent=1)

    except Exception as e:
        print_warning(f"Failed to generate SEO files: {e}", indent=1)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
