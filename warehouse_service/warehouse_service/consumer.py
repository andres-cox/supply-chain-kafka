"""Kafka producer for publishing order events."""

import json
from datetime import datetime, timezone

from confluent_kafka import Consumer

from .inventory import process_order
from .logger import logger

# Global flag for controlling the consumer loop
RUNNING = True


def create_consumer():
    """Create a Kafka consumer instance."""
    return Consumer(
        {
            "bootstrap.servers": "kafka:9092",
            "group.id": "warehouse-service",
            "auto.offset.reset": "earliest",
        }
    )


def consume_orders():
    """Consume messages from the orders.created topic."""
    consumer = create_consumer()
    try:
        consumer.subscribe(["orders.created"])
        while RUNNING:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error(f"Consumer error: {msg.error()}")
                continue
            try:
                value = msg.value()
                order_data = json.loads(value)
                # Add created_at if missing using timezone-aware datetime
                if "created_at" not in order_data:
                    order_data["created_at"] = datetime.now(timezone.utc).isoformat()
                process_order(order_data)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse message: {e}")
                continue  # Changed from raise to continue
            except Exception as e:
                logger.error(f"Error processing order: {e}")
                continue  # Changed from raise to continue
    finally:
        consumer.close()
