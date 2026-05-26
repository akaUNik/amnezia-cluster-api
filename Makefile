.PHONY: test

test:
	uv run pytest
	uv run mypy
