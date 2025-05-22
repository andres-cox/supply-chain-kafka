"""Kafka producer for publishing fraud alerts."""

import json
from typing import Optional

from confluent_kafka import Producer
from logging_utils.config import get_kafka_logger

from .schemas import FraudAlert

logger = get_kafka_logger("fraud-detection")


class FraudAlertProducer:
    """Producer for publishing fraud alerts to Kafka."""

    def __init__(
        self,
        bootstrap_servers: str,
        client_id: str,
        acks: str = "all",
    ):
        """Initialize the fraud alert producer.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            client_id: Producer client ID
            acks: The number of acknowledgments the producer requires
        """
        self.producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "client.id": client_id,
                "acks": acks,
            }
        )

    def _delivery_callback(self, err: Optional[Exception], msg) -> None:
        """Handle delivery reports from Kafka.

        Args:
            err: Error that occurred during delivery
            msg: The delivered message
        """
        if err:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.debug(f"Message delivered to {msg.topic()} [{msg.partition()}]")

    def send_fraud_alert(self, topic: str, fraud_alert: FraudAlert, key: Optional[str] = None) -> None:
        """Send a fraud alert to Kafka.

        Args:
            topic: Kafka topic to send the alert to
            fraud_alert: The fraud alert to send
            key: Optional message key (defaults to order_id)
        """
        try:
            # Serialize the alert
            value = json.dumps(FraudAlert.model_serializer(fraud_alert))

            # Use order_id as key if none provided
            message_key = key if key is not None else fraud_alert.order_id

            # Produce the message
            self.producer.produce(
                topic=topic,
                key=message_key,
                value=value.encode("utf-8"),
                callback=self._delivery_callback,
            )

            # Trigger any available delivery callbacks
            self.producer.poll(0)

        except Exception as e:
            logger.error(f"Failed to send fraud alert: {e}")

    def flush(self, timeout: float = 10.0) -> None:
        """Wait for all messages to be delivered.

        Args:
            timeout: Maximum time to wait in seconds
        """
        remaining = self.producer.flush(timeout)
        if remaining > 0:
            logger.warning(f"{remaining} messages still pending delivery")

    def close(self) -> None:
        """Close the producer connection."""
        if self.producer:
            self.producer.flush()  # Ensure any pending messages are sent
