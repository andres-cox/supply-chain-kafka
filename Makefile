.PHONY: build-base build-all up down logs test clean

# Build base image with common dependencies
build-base:
	docker build -t supply-chain-base:latest -f infra/docker/Dockerfile.base .

# Build all service images
build-services: build-base
	docker build -t order-service:latest -f order_service/Dockerfile .
	docker build -t warehouse-service:latest -f warehouse_service/Dockerfile .
	docker build -t tracking-service:latest -f tracking_service/Dockerfile .

build-all: build-base build-services

# Clean up docker images
clean:
	docker rmi supply-chain-base:latest order-service:latest warehouse-service:latest tracking-service:latest || true

# Start all services
up:
	docker-compose up -d

# Stop all services
down:
	docker-compose down

# View logs from all services
logs:
	docker-compose logs -f

# Run tests for all services
test:
	cd order_service && poetry run pytest
	cd warehouse_service && poetry run pytest
	cd tracking_service && poetry run pytest

# Format all Python code
format:
	cd order_service && poetry run ruff format .
	cd warehouse_service && poetry run ruff format .
	cd tracking_service && poetry run ruff format .

# Build and push to minikube
minikube-build: build-all
	minikube image load supply-chain-base:latest
	minikube image load order-service:latest
	minikube image load warehouse-service:latest
	minikube image load tracking-service:latest

# Deploy to minikube
minikube-deploy:
	kubectl apply -f infra/k8s/order-service.yaml
	kubectl apply -f infra/k8s/warehouse-service.yaml
	kubectl apply -f infra/k8s/tracking-service.yaml

# Delete all services from minikube
minikube-delete:
	kubectl delete -f infra/k8s/order-service.yaml
	kubectl delete -f infra/k8s/warehouse-service.yaml
	kubectl delete -f infra/k8s/tracking-service.yaml

# Restart all services in minikube
# This is useful for when you change the code and want to see the changes in minikube
minikube-rollout:
	kubectl rollout restart deployment order-service
	kubectl rollout restart deployment warehouse-service
	kubectl rollout restart deployment tracking-service

start-minikube:
	bash ./infra/minikube/start-minikube.sh

install-kafka:
	bash ./infra/kafka/install-kafka.sh

test-kafka:
	bash ./infra/kafka/test-kafka.sh
