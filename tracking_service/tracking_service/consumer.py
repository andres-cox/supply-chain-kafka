"""Kafka consumer for processing order tracking events."""

import json
from typing import Callable

from confluent_kafka import Consumer, KafkaError, KafkaException
from logging_utils.config import get_kafka_logger

from tracking_service.schemas import TrackingEvent, TrackingItem

# Configure Kafka-specific logger
logger = get_kafka_logger("tracking-service")


class TrackingConsumer:
    """Consumer for processing order tracking events from Kafka."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        auto_offset_reset: str = "earliest",
        enable_auto_commit: bool = True,
    ):
        """Initialize the tracking consumer.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            group_id: Consumer group ID
            auto_offset_reset: Where to start consuming from if no offset is stored
            enable_auto_commit: Whether to auto-commit offsets
        """
        logger.info(
            f"Initializing consumer with bootstrap_servers={bootstrap_servers}, "
            f"group_id={group_id}"
        )
        self.consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": auto_offset_reset,
                "enable.auto.commit": enable_auto_commit,
            }
        )

    def subscribe(self, topics: list[str]) -> None:
        """Subscribe to the specified Kafka topics.

        Args:
            topics: List of topic names to subscribe to
        """
        logger.info(f"Subscribing to topics: {topics}")
        self.consumer.subscribe(topics)
        logger.info("Successfully subscribed to topics")

    def process_messages(self, handler: Callable[[TrackingEvent], None]) -> None:
        """Process incoming messages continuously.

        Args:
            handler: Callback function to handle each tracking event
        """
        logger.info("Starting message processing loop")
        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug("Reached end of partition")
                        continue
                    logger.error(f"Kafka error: {msg.error()}")
                    raise KafkaException(msg.error())

                try:
                    # Log raw message for debugging
                    value_str = msg.value().decode("utf-8")
                    logger.info(f"Received message: {value_str}")

                    # Parse message value
                    value = json.loads(value_str)
                    logger.debug(f"Parsed message value: {value}")

                    # Convert order data to tracking items
                    tracking_items = [
                        TrackingItem(
                            sku=item["sku"],
                            quantity=item["quantity"],
                            price=item["price"],
                            status="received",
                        )
                        for item in value.get("items", [])
                    ]

                    # Create tracking event
                    tracking_event = TrackingEvent(
                        order_id=value["order_id"],
                        customer_id=value["customer_id"],
                        items=tracking_items,
                        event_type="order_received",
                    )

                    # Process the event using the handler
                    handler(tracking_event)
                    logger.info(
                        f"Successfully processed order: {tracking_event.order_id}"
                    )

                except json.JSONDecodeError as e:
                    logger.error(
                        f"Failed to decode message: {e}, raw message: {value_str}"
                    )
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)

        except KeyboardInterrupt:
            logger.info("Shutting down consumer...")
        finally:
            self.consumer.close()

    def close(self) -> None:
        """Close the consumer connection."""
        self.consumer.close()
        logger.info("Consumer closed")
