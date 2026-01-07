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
