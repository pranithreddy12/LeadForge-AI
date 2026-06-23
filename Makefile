SHELL := /bin/bash

.PHONY: help up down restart logs migrate seed keys test fmt

help:
	@echo "make up        — start the full stack via docker compose"
	@echo "make down      — stop the stack"
	@echo "make restart   — restart api + worker (after .env or code edits)"
	@echo "make logs      — tail api+worker logs"
	@echo "make migrate   — run alembic upgrade head inside the api container"
	@echo "make seed      — populate demo data"
	@echo "make keys      — show which external API keys are LIVE vs demo"
	@echo "make test      — backend pytest"
	@echo "make fmt       — ruff format / lint"

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api worker

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python -m app.cli seed

keys:
	docker compose exec api python -m app.cli keys

restart:
	docker compose restart api worker

test:
	docker compose exec api pytest -q

fmt:
	docker compose exec api ruff check --fix .
