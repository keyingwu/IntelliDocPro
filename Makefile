.PHONY: server web dev install

server:
	@echo "Starting docstill server..."
	cd docstill && uv run uvicorn server.app:app --reload

web:
	@echo "Starting webapp..."
	cd webapp && npm run dev

