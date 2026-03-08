ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
API_DIR := $(ROOT_DIR)/api
WEB_DIR := $(ROOT_DIR)/web
VENV := $(API_DIR)/.venv
VENV_ACTIVATE := $(VENV)/bin/activate

.PHONY: init install api web verify

init:
	@if [ ! -f $(API_DIR)/pyproject.toml ]; then \
		echo "Initializing uv project in $(API_DIR)..."; \
		cd $(API_DIR) && uv init --app; \
	fi
	@if [ ! -d $(API_DIR)/.venv ]; then \
		echo "Creating virtual environment in $(API_DIR)..."; \
		cd $(API_DIR) && uv venv; \
	fi

install: init
	cd $(API_DIR) && source $(VENV_ACTIVATE) && uv sync
	cd $(WEB_DIR) && npm install

api:
	cd $(API_DIR) && source $(VENV_ACTIVATE) && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd $(WEB_DIR) && npm run dev -- --host 0.0.0.0 --port 5173

verify:
	cd $(WEB_DIR) && npm run lint && npm run build
