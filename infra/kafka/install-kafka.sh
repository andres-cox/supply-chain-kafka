#!/bin/bash
# Add Helm repo and install Kafka
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

helm install kafka bitnami/kafka -f infra/kafka/values.yaml --version 32.2.0

# Get defaults of chart
# helm show values bitnami/kafka --version 20.0.6 > infra/kafka/kafka-defaults-20.0.6.yaml

# kubectl port-forward service/kafka 9092:9092

echo "Kafka deployed. Use 'kubectl get pods' to check status."