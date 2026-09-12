.PHONY: check lint test web-test build

check: lint test web-test build

lint:
	uv run ruff check src tests

test:
	uv run pytest -q

web-test:
	cd web && npm test

build:
	cd web && npm run build
