API_DIR=/Users/manmohan/Documents/FinalSemester/dons_hack/api
WEB_DIR=/Users/manmohan/Documents/FinalSemester/dons_hack/web

.PHONY: install api web verify

install:
	cd $(API_DIR) && uv sync
	cd $(WEB_DIR) && npm install

api:
	cd $(API_DIR) && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd $(WEB_DIR) && npm run dev -- --host 0.0.0.0 --port 5173

verify:
	cd $(WEB_DIR) && npm run lint && npm run build
