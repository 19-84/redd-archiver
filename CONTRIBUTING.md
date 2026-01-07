# Contributing to Redd-Archiver

Thank you for your interest in contributing! Redd-Archiver is a production-ready archive generator for link aggregator platforms (Reddit, Voat, Ruqqus), and we welcome contributions.

## Getting Started

1. Set up development environment:
```bash
# Navigate to redd-archiver directory
cd redd-archiver

# Copy environment template
cp .env.example .env
# Edit .env and change passwords

# Start PostgreSQL with Docker
docker compose up -d postgres

# Install dependencies with uv (recommended)
uv sync

# Configure database
export DATABASE_URL="postgresql://reddarchiver:your_password@localhost:5432/reddarchiver"
```

2. Run tests:
```bash
uv run pytest tests/
```

## Development Guidelines

- Follow existing code style (PEP 8)
- Add tests for new features
- Update CHANGELOG.md for user-facing changes
- Use [conventional commit](https://www.conventionalcommits.org/) messages (feat:, fix:, docs:, etc.)
- Test with Docker before submitting
- Keep dependencies minimal and justified

## Code Structure

```
redd-archiver/
├── reddarc.py           # Main CLI entry point
├── search_server.py     # Flask search API server
├── version.py           # Version metadata
├── core/                # Core processing & database
│   └── importers/       # Multi-platform importers (Reddit, Voat, Ruqqus)
├── api/                 # REST API v1 (30+ endpoints)
├── mcp_server/          # MCP Server for AI integration (29 tools)
├── utils/               # Utility functions
├── processing/          # Data processing modules
├── monitoring/          # Performance & monitoring
├── html_modules/        # 18 specialized HTML generation modules
├── templates_jinja2/    # Jinja2 templates for HTML generation
├── sql/                 # Database schema, indexes, and migrations
└── tests/               # Test suite
```

**Key Modules**:
- `core/postgres_database.py` - PostgreSQL backend (ONLY database implementation)
- `core/write_html.py` - HTML generation coordinator
- `core/watchful.py` - .zst streaming utilities
- `core/importers/` - Platform-specific importers (reddit, voat, ruqqus)
- `api/routes.py` - REST API endpoints
- `mcp_server/server.py` - MCP server for AI assistants
- `processing/parallel_user_processing.py` - Parallel user page generation
- `monitoring/performance_monitor.py` - Performance monitoring

## Testing

**Prerequisites**: Ensure all dependencies are installed before running tests.

```bash
# Install dependencies first
pip install -r requirements.txt
# or using uv
uv sync

# Run unit tests
pytest tests/ -v

# Integration test with Docker
docker-compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit test \
  --comments-file /data/test_comments.zst \
  --submissions-file /data/test_submissions.zst

# Benchmarks
docker-compose run --rm benchmark-test
```

## Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with tests
4. Update documentation if needed
5. Test thoroughly (local + Docker)
6. Commit with conventional commit format (`git commit -m 'feat: add amazing feature'`)
7. Push to your branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Reporting Issues

When reporting issues, please include:
- Redd-Archiver version (`python reddarc.py --version`)
- PostgreSQL version
- Operating system and Python version
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs or error messages

## Areas for Contribution

Priority areas where contributions are especially welcome:

1. **Performance Optimizations**
   - PostgreSQL query optimization
   - Batch processing improvements
   - Memory efficiency enhancements

2. **Features**
   - Additional export formats (JSON, Markdown)
   - Advanced search features
   - PostgreSQL replication support
   - Direct Reddit API integration

3. **Documentation**
   - Usage examples
   - Deployment guides
   - Performance tuning guides
   - Video tutorials

4. **Testing**
   - Additional test coverage
   - Integration tests
   - Performance benchmarks
   - Edge case handling

## Code Review Process

All submissions require review. We look for:
- Functionality and correctness
- Code quality and maintainability
- Test coverage
- Documentation completeness
- Performance impact

## Questions?

Open an [issue](https://github.com/19-84/redd-archiver/issues) or [discussion](https://github.com/19-84/redd-archiver/discussions).

---

Thank you for contributing to Redd-Archiver!
