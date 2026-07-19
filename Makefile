.PHONY: server web dev install docker

docker:
	docker compose up --build

server:
	@echo "Starting IntelliDocPro server..."
	cd backend && uv run uvicorn server.app:app --reload

web:
	@echo "Starting webapp..."
	cd webapp && npm run dev
