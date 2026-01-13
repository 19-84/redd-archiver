# ABOUTME: Nginx reverse proxy Dockerfile with Alpine-slim for minimal attack surface
# ABOUTME: Configured for non-root operation with read-only filesystem support

FROM nginx:alpine-slim

# Security: Remove unnecessary packages and create non-root user
RUN apk --no-cache del \
    && rm -rf /var/cache/apk/* \
    && rm -rf /tmp/*

# Security: Configure non-root user (nginx user already exists in base image, UID 101)
# Note: We don't set USER nginx here because the entrypoint script needs root privileges.
# The nginx.conf file contains "user nginx;" directive which makes nginx itself drop
# privileges after starting. This is the standard nginx security model.
RUN chown -R nginx:nginx /var/cache/nginx \
    && chown -R nginx:nginx /var/log/nginx \
    && chown -R nginx:nginx /etc/nginx/conf.d \
    && touch /var/run/nginx.pid \
    && chown -R nginx:nginx /var/run/nginx.pid

# Security: Remove default Nginx configuration
RUN rm -f /etc/nginx/conf.d/default.conf

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Create placeholder page for fresh installs (shown when no archive exists)
RUN mkdir -p /usr/share/nginx/placeholder && \
    cat > /usr/share/nginx/placeholder/index.html << 'PLACEHOLDER'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Redd-Archiver - Setup Required</title>
    <style>
        *{box-sizing:border-box;margin:0;padding:0}
        body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#1a1a2e;color:#eee;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
        .container{max-width:600px;background:#16213e;border-radius:12px;padding:40px;box-shadow:0 10px 40px rgba(0,0,0,0.3)}
        h1{color:#ff6b6b;margin-bottom:20px;font-size:28px}
        .status{background:#0f3460;border-left:4px solid #4ecca3;padding:15px 20px;margin:20px 0;border-radius:0 8px 8px 0}
        .status h3{color:#4ecca3;margin-bottom:8px}
        p{line-height:1.6;margin-bottom:15px;color:#b8b8b8}
        code{background:#0f3460;padding:3px 8px;border-radius:4px;font-family:"SF Mono",Monaco,monospace;font-size:14px;color:#4ecca3}
        pre{background:#0f3460;padding:15px;border-radius:8px;overflow-x:auto;margin:15px 0;font-size:13px}
        pre code{padding:0;background:none}
        a{color:#4ecca3}
        .step{margin:25px 0}
        .step-num{display:inline-block;background:#ff6b6b;color:#fff;width:28px;height:28px;border-radius:50%;text-align:center;line-height:28px;font-weight:bold;margin-right:10px}
        .links{margin-top:30px;padding-top:20px;border-top:1px solid #0f3460}
        .links a{display:inline-block;margin-right:20px;margin-bottom:10px}
    </style>
</head>
<body>
    <div class="container">
        <h1>Redd-Archiver</h1>
        <div class="status"><h3>Services Running</h3><p style="margin:0">PostgreSQL, Search Server, and Nginx are ready.</p></div>
        <p>No archive data has been imported yet. Follow these steps to create your first archive:</p>
        <div class="step"><span class="step-num">1</span><strong>Download Archive Data</strong><p>Get .zst files from <a href="https://academictorrents.com/details/56aa49f9653ba545f48df2e33679f014d2829c10" target="_blank">Academic Torrents</a> and place them in <code>data/</code></p></div>
        <div class="step"><span class="step-num">2</span><strong>Run the Archive Generator</strong><pre><code>docker compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit YOUR_SUBREDDIT \
  --comments-file /data/YOUR_SUBREDDIT_comments.zst \
  --submissions-file /data/YOUR_SUBREDDIT_submissions.zst \
  --output /output/</code></pre></div>
        <div class="step"><span class="step-num">3</span><strong>Refresh This Page</strong><p>Once processing completes, refresh to see your archive!</p></div>
        <div class="links"><a href="/health">Health Check</a> <a href="/api/v1/stats">API Stats</a> <a href="https://github.com/19-84/redd-archiver" target="_blank">Documentation</a></div>
    </div>
</body>
</html>
PLACEHOLDER

# Expose non-privileged port 8080 (will be mapped to 80 on host)
EXPOSE 8080

# Note: Container starts as root, but nginx worker processes run as 'nginx' user
# due to "user nginx;" directive in nginx.conf (line 4).
# This is the standard nginx security model - master process as root, workers as nginx.

# Health check - use 127.0.0.1 instead of localhost to force IPv4
# (Alpine wget tries IPv6 first, which fails if nginx not listening on ::)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:80/health || exit 1

# Start Nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
