# Pull Request

## Description

Please include a summary of the changes and the related issue. Include relevant motivation and context.

**Fixes**: # (issue number)

**Type of Change**:
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Performance improvement
- [ ] Refactoring (no functional changes)
- [ ] Test addition or update
- [ ] Build/CI configuration change

## Changes Made

### Core Changes
-
-

### Supporting Changes
-
-

## Testing Performed

### Test Environment
- **OS**: (e.g., Ubuntu 22.04)
- **Python Version**:
- **PostgreSQL Version**:
- **Docker**: Yes/No

### Test Cases

**Unit Tests**:
- [ ] All existing tests pass
- [ ] New tests added for new functionality
- [ ] Edge cases covered

**Integration Tests**:
- [ ] Tested with small dataset (<100MB)
- [ ] Tested with medium dataset (100MB-1GB)
- [ ] Tested with large dataset (>1GB)
- [ ] Tested resume functionality (if applicable)

**Manual Testing**:
Describe specific scenarios tested:
1.
2.
3.

**Test Results**:
```
# Paste test output here
pytest -v
```

## Performance Impact

Does this change affect performance?
- [ ] No performance impact
- [ ] Performance improvement (describe below)
- [ ] Potential performance regression (describe below)

**Performance Metrics** (if applicable):
- Before:
- After:
- Change:

## Database Changes

Does this PR include database schema changes?
- [ ] No database changes
- [ ] New tables or columns
- [ ] Index changes
- [ ] Migration script included

**Migration Path**:
- [ ] Backward compatible
- [ ] Requires data migration
- [ ] Migration script: `sql/migrations/XXX_description.sql`

## Documentation

- [ ] README.md updated (if user-facing changes)
- [ ] CHANGELOG.md updated
- [ ] ARCHITECTURE.md updated (if architectural changes)
- [ ] Code comments added/updated
- [ ] API documentation updated (if applicable)
- [ ] docs/TROUBLESHOOTING.md updated (if resolving common issues)

## Breaking Changes

Does this PR introduce breaking changes?
- [ ] No breaking changes
- [ ] Breaking changes (describe below)

**Breaking Change Details**:
- What breaks:
- Migration path:
- Deprecation timeline:

## Dependencies

Does this PR add or update dependencies?
- [ ] No dependency changes
- [ ] New dependencies added (list below)
- [ ] Dependency versions updated (list below)

**New/Updated Dependencies**:
- Package: version (reason)

## Code Quality

- [ ] Code follows project style guidelines (see CONTRIBUTING.md)
- [ ] Self-review completed
- [ ] No debugging code or commented-out code
- [ ] No hardcoded values that should be configurable
- [ ] Error handling is appropriate
- [ ] Logging is adequate (INFO for key events, DEBUG for details)

## Security Considerations

- [ ] No security implications
- [ ] Security implications addressed (describe below)

**Security Notes**:
- SQL injection protection:
- Input validation:
- Authentication/authorization:
- Sensitive data handling:

## Deployment Notes

Are there special deployment considerations?
- [ ] No special deployment steps
- [ ] Environment variables need updating
- [ ] Configuration changes required
- [ ] Database migration required
- [ ] Docker image rebuild required

**Deployment Steps**:
1.
2.
3.

## Screenshots

If applicable, add screenshots to demonstrate changes:

**Before**:


**After**:


## Checklist

### Code Quality
- [ ] My code follows the style guidelines of this project
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] My changes generate no new warnings or errors

### Testing
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] I have tested this code with a real dataset

### Documentation
- [ ] I have updated the documentation accordingly
- [ ] I have updated CHANGELOG.md with my changes
- [ ] I have added docstrings to new functions/classes

### Dependencies
- [ ] Any dependent changes have been merged and published
- [ ] I have checked that my changes don't break existing functionality

## Additional Notes

Add any additional notes or context for reviewers here:


## Reviewer Checklist

For reviewers - please verify:
- [ ] Code quality and style
- [ ] Test coverage is adequate
- [ ] Documentation is clear and complete
- [ ] Performance implications are acceptable
- [ ] Security considerations are addressed
- [ ] Breaking changes are justified and documented
- [ ] CHANGELOG.md is updated
