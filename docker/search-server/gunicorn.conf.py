# Gunicorn configuration for search server
# This file configures worker initialization to pre-load the search engine

import multiprocessing
import os

# Worker count scales with host CPUs (was hardcoded at 4): each sync worker
# handles one request at a time, and responses are mostly DB-bound. Capped at
# 8 — each worker owns a PostgreSQL connection pool, and max_connections is
# finite. Override with GUNICORN_WORKERS.
workers = int(os.environ.get("GUNICORN_WORKERS", "0")) or min(8, multiprocessing.cpu_count() + 1)

# Gunicorn will automatically call these hooks at the right times
# - on_starting: Called before master process initialization
# - post_worker_init: Called after each worker starts (pre-initializes search engine)
