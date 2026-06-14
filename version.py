"""
ABOUTME: Version information for Redd-Archiver Archive Generator
ABOUTME: Provides version string, version tuple, and release metadata
"""

__version__ = "1.1.0"
__version_info__ = (1, 1, 0)
__release_date__ = "2026-06-12"
__release_codename__ = "Living Archive"

# Compatibility information
MIN_PYTHON_VERSION = (3, 10)
MIN_POSTGRESQL_VERSION = (14, 0)


def get_version_string():
    """Return formatted version string with release information"""
    return f"reddarc {__version__} ({__release_codename__})"


def get_full_version_info():
    """Return complete version information as dictionary"""
    return {
        "version": __version__,
        "version_info": __version_info__,
        "release_date": __release_date__,
        "codename": __release_codename__,
        "min_python": ".".join(map(str, MIN_PYTHON_VERSION)),
        "min_postgresql": ".".join(map(str, MIN_POSTGRESQL_VERSION)),
    }
