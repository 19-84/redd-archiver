.PHONY: help setup test lint format docker-build docker-test docker-logs clean install-hooks

help:
	@echo "Redd-Archiver Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup          - Install dependencies and setup environment"
	@echo "  make install-hooks  - Install pre-commit hooks"
	@echo ""
	@echo "Development:"
	@echo "  make test           - Run tests locally"
	@echo "  make lint           - Run linters (ruff check)"
	@echo "  make format         - Format code (ruff format)"
	@echo "  make clean          - Remove cache and temp files"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build   - Build Docker containers"
	@echo "  make docker-test    - Run tests in Docker"
	@echo "  make docker-logs    - View Docker logs"
	@echo ""

setup:
	@echo "Installing dependencies..."
	uv sync --all-extras
	@echo "Installing pre-commit hooks..."
	uv run pre-commit install
	@echo "Setup complete! Run 'make test' to verify."

install-hooks:
	uv run pre-commit install

test:
	@echo "Running tests..."
	uv run pytest tests/ -v

test-cov:
	@echo "Running tests with coverage..."
	uv run pytest tests/ -v --cov=. --cov-report=html --cov-report=term
	@echo "Coverage report: htmlcov/index.html"

lint:
	@echo "Running ruff check..."
	uv run ruff check .

format:
	@echo "Formatting code..."
	uv run ruff format .

format-check:
	@echo "Checking code formatting..."
	uv run ruff format --check .

docker-build:
	@echo "Building Docker containers..."
	docker compose build --quiet

docker-up:
	@echo "Starting Docker services..."
	docker compose up -d
	@echo "Waiting for services to be healthy..."
	sleep 10
	docker compose ps

docker-test:
	@echo "Running tests in Docker..."
	docker compose up -d postgres
	sleep 5
	docker compose exec reddarchiver-builder uv run pytest tests/ -v

docker-logs:
	docker compose logs -f

docker-down:
	docker compose down

clean:
	@echo "Cleaning cache and temporary files..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	@echo "Clean complete!"

lock:
	@echo "Updating uv.lock..."
	uv lock

sync:
	@echo "Syncing dependencies from uv.lock..."
	uv sync --frozen --all-extras
