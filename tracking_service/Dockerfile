# Build stage
ARG BASE_IMAGE=supply-chain-base:latest
FROM ${BASE_IMAGE} as builder

WORKDIR /app/service

# Copy service-specific files from tracking_service directory
COPY tracking_service/pyproject.toml tracking_service/poetry.lock ./
COPY tracking_service/tracking_service ./tracking_service

# Install service-specific dependencies
RUN poetry install --no-interaction --no-ansi --only main --no-root

# Runtime stage
FROM ${BASE_IMAGE}

# Copy installed dependencies and service code
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /app/service/tracking_service /app/tracking_service

EXPOSE 8000
CMD ["python", "-m", "tracking_service.main"]