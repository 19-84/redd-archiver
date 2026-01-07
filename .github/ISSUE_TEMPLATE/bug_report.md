---
name: Bug Report
about: Report a bug or unexpected behavior in Redd-Archiver
title: '[BUG] '
labels: bug
assignees: ''
---

## Bug Description

A clear and concise description of what the bug is.

## Steps to Reproduce

1. Go to '...'
2. Run command '...'
3. See error

## Expected Behavior

A clear and concise description of what you expected to happen.

## Actual Behavior

A clear and concise description of what actually happened.

## Environment

**Redd-Archiver Version**: (e.g., v1.0.0)

**Operating System**: (e.g., Ubuntu 22.04, macOS 14, Windows 11)

**Python Version**: (output of `python --version`)

**PostgreSQL Version**: (output of `psql --version`)

**Docker Version** (if applicable): (output of `docker --version`)

**Deployment Method**:
- [ ] Docker Compose
- [ ] Local PostgreSQL
- [ ] Other (please specify)

## Dataset Information

**Input Size**: (e.g., 93.6MB .zst file)

**Subreddit(s)**: (e.g., r/technology)

**Approximate Record Count**:
- Posts:
- Comments:
- Users:

## Error Output

```
Paste complete error output here, including stack traces
```

## Relevant Configuration

**Environment Variables** (redact sensitive information):
```bash
DATABASE_URL=postgresql://...
REDDARCHIVER_MAX_DB_CONNECTIONS=8
# Add any other relevant configuration
```

**Command Used**:
```bash
python reddarc.py /data --output archive/ --min-score 10
```

## Logs

Attach or paste relevant log excerpts from `.archive-error.log` or console output.

```
[Paste logs here]
```

## Screenshots

If applicable, add screenshots to help explain your problem.

## Additional Context

Add any other context about the problem here:
- Did this work in a previous version?
- Does the issue occur consistently or intermittently?
- Are there any workarounds you've found?

## Checklist

- [ ] I have searched existing issues to avoid duplicates
- [ ] I have included complete error messages and stack traces
- [ ] I have provided my environment information
- [ ] I have included steps to reproduce the issue
- [ ] I have checked the docs/TROUBLESHOOTING.md documentation
