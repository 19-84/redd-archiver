# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | ✅ Yes             |
| < 1.0   | ❌ No (deprecated) |

## Reporting a Vulnerability

If you discover a security vulnerability in Redd-Archiver, please:

1. **Do NOT** open a public issue
2. Report via [GitHub Security Advisories](https://github.com/19-84/redd-archiver/security/advisories/new)
3. Provide:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment
   - Suggested fix (if any)
   - Your contact information for follow-up

We will acknowledge your report within 48 hours and provide a timeline for resolution.

## Security Considerations

### Database Security

**PostgreSQL Configuration:**
- Always use strong, randomly generated passwords
- Never commit `.env` files with real credentials to version control
- Enable PostgreSQL SSL/TLS in production deployments
- Use connection pooling limits to prevent resource exhaustion
- Restrict database user permissions (principle of least privilege)
- Keep PostgreSQL updated with security patches

**Best Practices:**
```bash
# Generate strong password
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Set restrictive file permissions
chmod 600 .env

# Use SSL connection in production
DATABASE_URL="postgresql://user:pass@host:5432/db?sslmode=require"
```

### Input Validation

Redd-Archiver processes untrusted Pushshift data dumps:

- **SQL Injection Prevention**: All database queries use parameterized statements via psycopg3
- **XSS Prevention**: Jinja2 autoescaping enabled by default for all HTML output
- **Path Traversal**: File operations validate and sanitize paths
- **Data Sanitization**: Pushshift data is sanitized before HTML generation

### Docker Security

**Container Hardening:**
- Search server runs with read-only root filesystem
- Containers use non-root users where appropriate
- Secrets passed via environment variables, never hardcoded
- Minimal base images (Alpine Linux) reduce attack surface
- Resource limits prevent DoS via resource exhaustion

**Best Practices:**
```yaml
# Review security settings in docker-compose.yml
read_only: true        # Immutable filesystem
user: "1000:1000"      # Non-root user
cap_drop: [ALL]        # Drop unnecessary capabilities
```

### Known Safe Operations

The following operations are designed to be safe:

1. **Static HTML Output**
   - No server-side code execution in generated archives
   - All dynamic content rendered at build time

2. **PostgreSQL FTS Search**
   - No eval() or exec() usage anywhere in codebase
   - Parameterized queries prevent injection

3. **Template Rendering**
   - Jinja2 autoescaping prevents XSS
   - No unsafe template filters used

### Dependency Security

**Dependencies** are defined in `pyproject.toml`. Key packages:
- `psycopg[binary,pool]` - PostgreSQL driver with connection pooling
- `jinja2` - Template engine with autoescaping
- `zstandard` - .zst decompression
- `orjson` - Fast JSON parsing
- `rcssmin` - CSS minification

All dependencies:
- Use known-good versions with no critical CVEs
- Are from trusted sources (PyPI official packages)
- Have permissive licenses (MIT/BSD/Apache/Unlicense)
- Are regularly updated for security patches

### Deployment Security Checklist

Before deploying to production:

- [ ] Changed all default passwords (PostgreSQL, Flask)
- [ ] Generated strong FLASK_SECRET_KEY
- [ ] Enabled PostgreSQL SSL/TLS
- [ ] Set restrictive .env file permissions (chmod 600)
- [ ] Configured firewall rules (only expose required ports)
- [ ] Enabled Docker resource limits
- [ ] Reviewed and applied security updates
- [ ] Set up log monitoring and alerting
- [ ] Configured backup strategy
- [ ] Documented incident response plan

## Updates and Patches

Security updates are released as:
- **Patch versions** (1.0.x) for security fixes
- **Minor versions** (1.x.0) for non-breaking security improvements
- **Out-of-band releases** for critical vulnerabilities

Subscribe to [release notifications](https://github.com/19-84/redd-archiver/releases) to stay informed.

## Responsible Disclosure

We follow responsible disclosure principles:
- 90-day disclosure timeline after patch availability
- Credit given to security researchers (with permission)
- CVE assignment for vulnerabilities when appropriate

## Security Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [PostgreSQL Security Best Practices](https://www.postgresql.org/docs/current/security.html)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Python Security Documentation](https://docs.python.org/3/library/security_warnings.html)

---

**Last Updated:** 2025-12-27
