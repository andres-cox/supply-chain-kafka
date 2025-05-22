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

# Run service
run:
	poetry run uvicorn fraud_detection.main:app --reload --host 0.0.0.0 --port 8004

# Clean up
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +