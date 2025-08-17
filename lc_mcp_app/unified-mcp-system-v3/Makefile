.PHONY: help install install-dev test lint type-check format check-all clean
.PHONY: mcp-server lc-app docker-build docker-up docker-down
.PHONY: test-coverage test-unit test-integration

# Default target
help:
	@echo "🚀 Unified MCP System - Available Commands:"
	@echo ""
	@echo "📦 Installation:"
	@echo "  install      Install production dependencies"
	@echo "  install-dev  Install development dependencies"
	@echo ""
	@echo "🏃 Running Services:"
	@echo "  mcp-server   Start MCP Agent Server (port 8000)"
	@echo "  lc-app       Start LC MCP App (port 8001)"
	@echo "  dev          Start both services in development mode"
	@echo ""
	@echo "🐳 Docker:"
	@echo "  docker-build Build Docker images"
	@echo "  docker-up    Start all services with Docker Compose"
	@echo "  docker-down  Stop all Docker services"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  test         Run all tests"
	@echo "  test-unit    Run unit tests only"
	@echo "  test-integration Run integration tests only"
	@echo "  test-coverage Run tests with coverage report"
	@echo ""
	@echo "🔍 Code Quality:"
	@echo "  lint         Run linting (ruff)"
	@echo "  type-check   Run type checking (mypy)"
	@echo "  format       Format code (ruff + black)"
	@echo "  check-all    Run all quality checks"
	@echo ""
	@echo "🧹 Maintenance:"
	@echo "  clean        Clean up build artifacts and cache"

# Installation
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

# Running Services
mcp-server:
	@echo "🚀 Starting MCP Agent Server on port 8000..."
	python -m mcp_agent.server

lc-app:
	@echo "🚀 Starting LC MCP App on port 8001..."
	python -m lc_mcp_app.server

dev:
	@echo "🚀 Starting both services in development mode..."
	@echo "MCP Server: http://localhost:8000"
	@echo "LC MCP App: http://localhost:8001"
	@echo "Press Ctrl+C to stop all services"
	@(python -m mcp_agent.server &) && python -m lc_mcp_app.server

# Docker
docker-build:
	@echo "🐳 Building Docker images..."
	docker-compose build

docker-up:
	@echo "🐳 Starting all services with Docker Compose..."
	@echo "MCP Server: http://localhost:8000"
	@echo "LC MCP App: http://localhost:8001"
	@echo "Prometheus: http://localhost:9090"
	@echo "Redis: localhost:6379"
	docker-compose up --build

docker-down:
	@echo "🐳 Stopping all Docker services..."
	docker-compose down

# Testing
test:
	@echo "🧪 Running all tests..."
	pytest

test-unit:
	@echo "🧪 Running unit tests..."
	pytest -m unit

test-integration:
	@echo "🧪 Running integration tests..."
	pytest -m integration

test-coverage:
	@echo "🧪 Running tests with coverage..."
	pytest --cov=lc_mcp_app --cov=mcp_agent --cov-report=html --cov-report=term-missing

# Code Quality
lint:
	@echo "🔍 Running linting..."
	ruff check .
	ruff check . --fix

type-check:
	@echo "🔍 Running type checking..."
	mypy lc_mcp_app mcp_agent

format:
	@echo "🎨 Formatting code..."
	ruff format .
	black .
	isort .

check-all: lint type-check test
	@echo "✅ All checks passed!"

# Maintenance
clean:
	@echo "🧹 Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name "*.pyo" -delete 2>/dev/null || true
	find . -name "*~" -delete 2>/dev/null || true
	rm -rf build/ dist/ htmlcov/ .coverage 2>/dev/null || true

# Health checks
health-check:
	@echo "🏥 Checking service health..."
	@curl -f http://localhost:8000/health || echo "❌ MCP Server not responding"
	@curl -f http://localhost:8001/health || echo "❌ LC MCP App not responding"

# Development utilities
logs:
	@echo "📋 Showing service logs..."
	docker-compose logs -f

restart:
	@echo "🔄 Restarting all services..."
	docker-compose restart

# Database operations
db-migrate:
	@echo "🗄️ Running database migrations..."
	python -m mcp_agent.database.migrate

db-reset:
	@echo "🗄️ Resetting database..."
	rm -f mcp_agent.db
	python -m mcp_agent.database.migrate

# Security
security-scan:
	@echo "🔒 Running security scan..."
	pip-audit
	bandit -r lc_mcp_app mcp_agent

# Performance
benchmark:
	@echo "⚡ Running performance benchmarks..."
	python scripts/benchmark.py

# Release
release-check:
	@echo "🚀 Checking release readiness..."
	@make check-all
	@make test-coverage
	@echo "✅ Ready for release!"
