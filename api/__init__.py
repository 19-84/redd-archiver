#!/usr/bin/env python
# ABOUTME: API module initialization with blueprint registration for Redd Archiver REST API
# ABOUTME: Version 1 REST API for programmatic access to archive data with CORS and rate limiting

from flask import Blueprint

# Create API v1 blueprint with /api/v1 prefix
api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1')

# Import route handlers (this registers routes with the blueprint)
from . import routes

def register_api(app):
    """
    Register API blueprint with Flask application.

    Args:
        app: Flask application instance

    Usage:
        from api import register_api
        register_api(app)
    """
    app.register_blueprint(api_v1)

    # Log API registration
    from utils.console_output import print_success
    print_success("REST API v1 registered at /api/v1")
