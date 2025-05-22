# Build stage
ARG BASE_IMAGE=supply-chain-base:latest
FROM ${BASE_IMAGE} as builder

WORKDIR /app/service

# Copy service-specific files
COPY fraud_detection/pyproject.toml fraud_detection/poetry.lock ./
COPY fraud_detection/fraud_detection ./fraud_detection

# Install service-specific dependencies
RUN poetry install --no-interaction --no-ansi --only main --no-root

# Runtime stage
FROM ${BASE_IMAGE}

# Copy installed dependencies and service code
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /app/service/fraud_detection /app/fraud_detection

EXPOSE 8000
CMD ["python", "-m", "fraud_detection.main"]