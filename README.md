# Supply Chain Kafka Microservices

A microservices-based supply chain management system using Kafka for event-driven communication.

## 1. Microservices Architecture

| Microservice | Responsibility | Input Topics (Consumes) | Output Topics (Produces) |
|--------------|----------------|------------------------|------------------------|
| Order Service | Creates and validates orders | - | orders.created |
| Tracking Service | Updates real-time location (GPS/API) | orders.created | locations.updated |
| Warehouse Service | Manages inventory, processes orders | orders.created | - |
| Fraud Detection | Analyzes orders and routes for anomalies | orders.created, locations.updated | alerts.fraud |
| Notification Service | Sends emails/SMS notifications | locations.updated, alerts.fraud | - |
| Analytics Service | Processes location data for insights | locations.updated | - |

## 2. Development Setup

### Prerequisites
- Docker and Docker Compose
- Python 3.10+
- Poetry 2.1.2+
- Minikube (for local Kubernetes deployment)

### Quick Start

1. Build base image and services:
```bash
make build-base    # Build the common base image
make build-all     # Build all service images
```

2. Start services locally:
```bash
make up           # Start all services with docker-compose
```

3. View logs:
```bash
make logs         # Watch logs from all services
```

### Project Structure
```
supply-chain-kafka/
├── libs/                    # Shared libraries
│   └── logging_utils/       # Common logging utilities using Loguru
├── infra/
│   ├── docker/             # Base Dockerfile and common configs
│   ├── k8s/                # Kubernetes manifests
│   └── kafka/              # Kafka setup and testing
├── [service_name]/         # Each service follows this structure:
│   ├── Dockerfile          # Extends from base image
│   ├── pyproject.toml      # Poetry dependencies
│   └── [service_name]/     # Service implementation
```

## 3. Features

### Standardized Logging
- Centralized logging configuration using Loguru
- Colored terminal output for better readability
- Structured JSON logging for ELK/Grafana integration
- Kafka-specific logging context
- Log rotation and compression

### Docker Infrastructure
- Multi-stage builds for optimal image size
- Common base image with shared dependencies
- Development-friendly with hot-reload
- Consistent environment across services

### Development Workflow
- Poetry for dependency management
- Make commands for common operations
- Automated tests and formatting
- Local development with docker-compose
- Kubernetes deployment ready

## 4. Docker Compose Services

Services run on the following ports:
- Order Service: 8001
- Warehouse Service: 8002
- Tracking Service: 8003
- Kafka: 9092

## 5. Kafka Setup

Topics (all with replication=1, partitions=3):
- orders.created (produced by Order Service)
- locations.updated (produced by Tracking Service)
- alerts.fraud (produced by Fraud Detection Service)

## 6. Development Commands

```bash
# Build and Deploy
make build-base        # Build base image
make build-all        # Build all services
make up              # Start services
make down            # Stop services

# Development
make logs           # View all logs
make test           # Run tests
make format         # Format code

# Kubernetes
make minikube-build  # Build for minikube
make minikube-deploy # Deploy to kubernetes
```

## 7. Environment Variables

Common to all services:
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka connection string (default: kafka:9092)
- `LOG_LEVEL`: Logging level (default: INFO)

## 8. Contributing

1. Use Poetry for dependency management
2. Follow the project structure
3. Implement logging using logging_utils
4. Build from base Docker image
5. Add tests for new features

## 9. Monitoring

- Logs viewable through docker-compose logs
- Structured logging ready for ELK/Grafana
- Health check endpoints on all services
- Kafka topic monitoring through admin endpoints