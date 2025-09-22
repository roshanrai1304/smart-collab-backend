# Smart Collab Backend - Makefile
# Commands for development, testing, and deployment

.PHONY: help install deps sync-deps lint lint-fix format check test migrate runserver shell clean reset-db setup dev

# Default target
help: ## Show this help message
	@echo "Smart Collab Backend - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Dependencies Management
install: ## Install dependencies using uv
	@echo "📦 Installing dependencies..."
	uv pip install -r requirements.txt

deps: install ## Alias for install

sync-deps: ## Sync dependencies from requirements.in and update requirements.txt
	@echo "🔄 Syncing dependencies..."
	uv pip compile requirements.in --output-file requirements.txt
	uv pip sync requirements.txt

upgrade-deps: ## Upgrade all dependencies to latest versions
	@echo "⬆️ Upgrading dependencies..."
	uv pip compile requirements.in --upgrade --output-file requirements.txt
	uv pip sync requirements.txt

add-dep: ## Add a new dependency (usage: make add-dep PACKAGE=package-name)
	@if [ -z "$(PACKAGE)" ]; then \
		echo "❌ Please specify PACKAGE. Usage: make add-dep PACKAGE=package-name"; \
		exit 1; \
	fi
	@echo "➕ Adding $(PACKAGE) to requirements.in..."
	@echo "$(PACKAGE)" >> requirements.in
	@make sync-deps

# Code Quality & Linting
lint: ## Check for linting errors using flake8 and other tools
	@echo "🔍 Running linting checks..."
	@echo "--- Flake8 ---"
	-flake8 apps/ config/ --max-line-length=120 --exclude=migrations,__pycache__,.venv
	@echo "--- Django Check ---"
	python manage.py check
	@echo "--- Import sorting (isort) ---"
	-isort apps/ config/ --check-only --diff
	@echo "--- Code formatting (black) ---"
	-black apps/ config/ --check --diff

lint-install: ## Install linting tools
	@echo "🛠️ Installing linting tools..."
	uv pip install flake8 black isort pylint

lint-fix: ## Auto-fix linting issues where possible
	@echo "🔧 Auto-fixing linting issues..."
	@echo "--- Fixing import order ---"
	isort apps/ config/
	@echo "--- Formatting code ---"
	black apps/ config/
	@echo "--- Running final check ---"
	python manage.py check

format: lint-fix ## Alias for lint-fix

# Testing
test: ## Run all tests
	@echo "🧪 Running tests..."
	python manage.py test

test-verbose: ## Run tests with verbose output
	@echo "🧪 Running tests (verbose)..."
	python manage.py test --verbosity=2

coverage: ## Run tests with coverage report
	@echo "📊 Running tests with coverage..."
	coverage run --source='.' manage.py test
	coverage report
	coverage html

# Database Management
migrate: ## Run database migrations
	@echo "🗃️ Running migrations..."
	python manage.py makemigrations
	python manage.py migrate

reset-db: ## Reset database (WARNING: This will delete all data!)
	@echo "⚠️ Resetting database..."
	@read -p "Are you sure you want to reset the database? [y/N] " confirm && [ "$$confirm" = "y" ]
	rm -f db.sqlite3
	python manage.py migrate
	python manage.py createsuperuser --noinput --username admin --email admin@example.com || true

makemigrations: ## Create new migrations
	@echo "📝 Creating migrations..."
	python manage.py makemigrations

# Development Server
runserver: ## Start development server
	@echo "🚀 Starting development server..."
	python manage.py runserver --settings=config.settings.development

dev: runserver ## Alias for runserver

shell: ## Open Django shell
	@echo "🐚 Opening Django shell..."
	python manage.py shell

# Setup & Initialization
setup: ## Initial project setup
	@echo "🔧 Setting up project..."
	@make sync-deps
	@make migrate
	@echo "✅ Project setup complete!"

setup-dev: ## Setup for development (includes linting tools)
	@echo "🛠️ Setting up development environment..."
	@make sync-deps
	@make lint-install
	@make migrate
	@echo "✅ Development setup complete!"

# Utility Commands
check: ## Run Django system checks
	@echo "✅ Running Django checks..."
	python manage.py check

collectstatic: ## Collect static files
	@echo "📁 Collecting static files..."
	python manage.py collectstatic --noinput

clean: ## Clean up cache and temporary files
	@echo "🧹 Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .coverage htmlcov/

# Email Testing
test-email: ## Test email functionality (usage: make test-email EMAIL=test@example.com)
	@if [ -z "$(EMAIL)" ]; then \
		echo "❌ Please specify EMAIL. Usage: make test-email EMAIL=test@example.com"; \
		exit 1; \
	fi
	@echo "📧 Testing email to $(EMAIL)..."
	python manage.py test_email --email $(EMAIL) --type all

# Data Management
create-admin: ## Create admin user
	@echo "👤 Creating admin user..."
	python manage.py create_admin

reset-data: ## Reset all data (WARNING: This will delete all data!)
	@echo "⚠️ Resetting all data..."
	@read -p "Are you sure you want to reset all data? [y/N] " confirm && [ "$$confirm" = "y" ]
	python manage.py reset_data

# Production Commands
prod-check: ## Run production readiness checks
	@echo "🏭 Running production checks..."
	python manage.py check --deploy
	python manage.py collectstatic --dry-run --noinput

# Docker Commands (if using Docker)
docker-build: ## Build Docker image
	@echo "🐳 Building Docker image..."
	docker build -t smart-collab-backend .

docker-run: ## Run Docker container
	@echo "🐳 Running Docker container..."
	docker run -p 8000:8000 smart-collab-backend

# Git Helpers
git-hooks: ## Install git pre-commit hooks
	@echo "🪝 Installing git hooks..."
	@echo "#!/bin/bash\nmake lint" > .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "✅ Pre-commit hook installed (runs 'make lint' before commits)"

# Environment Info
info: ## Show environment information
	@echo "ℹ️ Environment Information:"
	@echo "Python: $$(python --version)"
	@echo "Django: $$(python -c 'import django; print(django.get_version())')"
	@echo "UV: $$(uv --version 2>/dev/null || echo 'Not installed')"
	@echo "Virtual Environment: $$(echo $$VIRTUAL_ENV)"
	@echo "Current Directory: $$(pwd)"

# All-in-one commands
full-check: ## Run all checks (lint, test, django check)
	@echo "🔍 Running full project checks..."
	@make lint
	@make test
	@make check
	@echo "✅ All checks completed!"

fresh-start: ## Fresh start (clean, install, migrate, runserver)
	@echo "🆕 Fresh start..."
	@make clean
	@make sync-deps
	@make migrate
	@make runserver
