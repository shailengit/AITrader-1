.PHONY: help install backend frontend dev test lint docker-build docker-up docker-down

help: ## Show this help message
	@echo "TradeCraft Development Commands"
	@echo "==============================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies (backend + frontend)
	cd backend && python -m venv venv && ./venv/bin/pip install -r requirements.txt
	cd frontend && npm install

backend: ## Run backend development server
	cd backend && ./venv/bin/uvicorn app.main:app --reload --port 8000

frontend: ## Run frontend development server
	cd frontend && npm run dev

dev: ## Run both backend and frontend (requires tmux or two terminals)
	@echo "Start backend: make backend"
	@echo "Start frontend: make frontend"

test: ## Run all tests (backend pytest + frontend typecheck)
	cd backend && ./venv/bin/pytest -q
	cd frontend && npx tsc --noEmit

lint: ## Run linters (backend ruff + frontend eslint)
	cd backend && ./venv/bin/ruff check app/
	cd frontend && npm run lint

docker-build: ## Build Docker images
	docker-compose build

docker-up: ## Start all services with Docker Compose
	docker-compose up -d

docker-down: ## Stop all Docker services
	docker-compose down

migrate: ## Run Alembic migrations
	cd backend && ./venv/bin/alembic upgrade head

migrate-create: ## Create a new Alembic migration (requires MESSAGE)
	cd backend && ./venv/bin/alembic revision --autogenerate -m "$(MESSAGE)"
