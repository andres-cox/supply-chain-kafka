# Stage 1: Build
FROM python:3.10-slim as builder

WORKDIR /app
ENV POETRY_VERSION=2.1.2

# Install Poetry
RUN pip install "poetry==$POETRY_VERSION"

# Copy ALL files needed for installation
COPY pyproject.toml poetry.lock ./
COPY warehouse_service ./warehouse_service

# Install dependencies (including your package)
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --only main

# Stage 2: Runtime
FROM python:3.10-slim

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /app/warehouse_service /app/warehouse_service

# Expose the FastAPI port
EXPOSE 8000

# Start the FastAPI server
CMD ["python", "-m", "warehouse_service.server"]