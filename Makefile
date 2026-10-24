.PHONY: help run migrate makemigrations seed test lint check

PYTHON = .venv/bin/python

help:
	@echo "Available commands:"
	@echo "  make run             - Start the Django development server"
	@echo "  make makemigrations  - Generate Django migrations"
	@echo "  make migrate         - Apply database migrations"
	@echo "  make seed            - Seed realistic Nigerian demo data"
	@echo "  make test            - Run pytest suite with coverage"
	@echo "  make check           - Run Django system checks"

run:
	$(PYTHON) manage.py runserver 0.0.0.0:8000

makemigrations:
	$(PYTHON) manage.py makemigrations

migrate:
	$(PYTHON) manage.py migrate

seed:
	$(PYTHON) manage.py seed_data

test:
	$(PYTHON) -m pytest tests/ -v

check:
	$(PYTHON) manage.py check
