.PHONY: install dev web test lint fmt

install:          ## Install the backend (editable) + dev tools
	pip install -e ".[dev]"

dev:              ## Run the API with reload on :8000
	uvicorn chess_llm.api:app --reload --port 8000

web:              ## Run the Next.js frontend on :3000
	cd web && npm install && npm run dev

test:             ## Run the test suite
	pytest

lint:             ## Lint the backend
	ruff check .

fmt:              ## Auto-format the backend
	ruff format .
