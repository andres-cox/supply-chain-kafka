.PHONY: install test format run clean

# Install dependencies
install:
	poetry install

# Run tests
test:
	poetry run pytest

# Format code
format:
	poetry run ruff format .
	poetry run ruff check --fix .


