.PHONY: sync test lint
sync:
	uv sync --all-packages
test:
	uv run pytest
lint:
	uv run ruff check .
