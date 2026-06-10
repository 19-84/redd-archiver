"""
HTML Modules Package for red-arch
This package contains all modularized components for HTML generation.

Import from submodules directly (`from html_modules.html_seo import ...`).
This file deliberately re-exports nothing: an eager aggregator here would make
every `html_modules.<submodule>` import pull in the whole package and its
heavyweight dependencies (psutil, rcssmin, ...), which lightweight consumers
like the search server don't ship.
"""
