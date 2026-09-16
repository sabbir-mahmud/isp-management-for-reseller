# Common tasks. `make help` lists them.
.DEFAULT_GOAL := help
PYTHON := venv/bin/python
PIP := venv/bin/pip

.PHONY: help install run test lint format check migrate seed superuser invoices clean docker-up docker-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Create the virtualenv and install dev dependencies
	python3 -m venv venv
	$(PIP) install -r requirements-dev.txt

run: ## Start the development server
	$(PYTHON) manage.py runserver

test: ## Run the test suite
	$(PYTHON) -m pytest

coverage: ## Run the tests with a coverage report
	$(PYTHON) -m pytest --cov=apps --cov-report=term-missing

lint: ## Lint and check formatting
	venv/bin/ruff check .
	venv/bin/ruff format --check .

format: ## Reformat the code
	venv/bin/ruff format .
	venv/bin/ruff check --fix .

check: ## Django system checks, including the deployment audit
	$(PYTHON) manage.py check
	$(PYTHON) manage.py makemigrations --check --dry-run
	DEBUG=False $(PYTHON) manage.py check --deploy

migrate: ## Apply database migrations
	$(PYTHON) manage.py migrate

seed: ## Fill an empty database with demo data
	$(PYTHON) manage.py seed_demo

superuser: ## Create an owner account
	$(PYTHON) manage.py createsuperuser

invoices: ## Generate this month's invoices (add ARGS="--dry-run")
	$(PYTHON) manage.py generate_invoices $(ARGS)

docker-up: ## Start the Postgres-backed stack
	docker compose up --build

docker-down: ## Stop the stack
	docker compose down

clean: ## Remove caches and build artefacts
	find . -path ./venv -prune -o -name '__pycache__' -type d -print0 | xargs -0 rm -rf
	rm -rf .pytest_cache .ruff_cache staticfiles htmlcov .coverage
