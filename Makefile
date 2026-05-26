IMAGE_NAME ?= amnezia-cluster-api:smoke

.PHONY: test smoke app-smoke docker-build

test:
	uv run pytest
	uv run mypy

smoke: app-smoke docker-build

app-smoke:
	DEVELOPMENT=true SERVER_PUBLIC_HOST=127.0.0.1 uv run python -c "from src.main import app; assert any(route.path == '/health' for route in app.routes)"

docker-build:
	docker build -f src/Dockerfile -t $(IMAGE_NAME) .
