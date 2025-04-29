#!/bin/bash

set -e

NAMESPACE=default
POD_NAME=kafka-client
TOPIC=test-topic
BROKER=kafka:9092
IMAGE=bitnami/kafka:latest

echo "🚀 Creating Kafka client pod..."
kubectl run $POD_NAME \
  --namespace $NAMESPACE \
  --restart='Never' \
  --image=$IMAGE \
  --command -- sleep infinity

echo "⏳ Waiting for pod to be ready..."
kubectl wait --for=condition=Ready pod/$POD_NAME -n $NAMESPACE --timeout=30s

echo "✅ Creating topic: $TOPIC"
kubectl exec -n $NAMESPACE $POD_NAME -- \
  kafka-topics.sh --bootstrap-server $BROKER \
  --create --if-not-exists --topic $TOPIC --partitions 1 --replication-factor 1

echo "📃 Listing topics"
kubectl exec -n $NAMESPACE $POD_NAME -- \
  kafka-topics.sh --bootstrap-server $BROKER --list

echo "📝 Producing messages"
kubectl exec -n $NAMESPACE $POD_NAME -- bash -c \
  "echo -e 'Hello\nKafka\nFrom script' | kafka-console-producer.sh --bootstrap-server $BROKER --topic $TOPIC"

echo "📬 Consuming messages"
kubectl exec -n $NAMESPACE $POD_NAME -- \
  kafka-console-consumer.sh --bootstrap-server $BROKER \
  --topic $TOPIC --from-beginning --timeout-ms 5000

echo "🧹 Cleaning up Kafka client pod"
kubectl delete pod $POD_NAME -n $NAMESPACE
