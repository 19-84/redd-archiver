# Gunicorn configuration for search server
# This file configures worker initialization to pre-load the search engine

# Import hooks from search_server module

# Gunicorn will automatically call these hooks at the right times
# - on_starting: Called before master process initialization
# - post_worker_init: Called after each worker starts (pre-initializes search engine)
