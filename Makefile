.PHONY: db api ui dev down

SHELL := /bin/bash
UV ?= uv
API_BASE_URL ?= http://0.0.0.0:8000

db:
	docker compose up -d

api:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

ui:
	API_BASE_URL=$(API_BASE_URL) streamlit run ui/app.py

dev: db
	@bash -c "$(UV) run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 & API_BASE_URL=$(API_BASE_URL) $(UV) run streamlit run ui/app.py & wait"

down:
	docker compose down
