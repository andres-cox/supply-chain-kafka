"""Kafka consumer for processing notification events."""

import json
import time
from collections.abc import Callable
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaError, KafkaException
from logging_utils.config import get_kafka_logger

from .schemas import Notification, NotificationPreferences

logger = get_kafka_logger("notification-service")

# Configuration constants
DEFAULT_CONSUMER_CONFIG = {
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,
    "session.timeout.ms": 30000,
    "max.poll.interval.ms": 300000,
}

DELIVERY_STATUSES = {
    "processing": {
        "notify": True,
        "priority": "low",
        "subject": "Order Processing",
    },
    "at_distribution_center": {
        "notify": True,
        "priority": "medium",
        "subject": "At Distribution Center",
    },
    "in_transit": {
        "notify": True,
        "priority": "medium",
        "subject": "In Transit",
    },
    "delivered": {
        "notify": True,
        "priority": "medium",
        "subject": "Delivery Completed",
    },
    "delayed": {
        "notify": True,
        "priority": "high",
        "subject": "Delivery Delayed",
    },
}


class NotificationConsumer:
    """Consumer for processing notification events."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        auto_offset_reset: str = "earliest",
        enable_auto_commit: bool = True,
    ):
        """Initialize the notification consumer.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            group_id: Consumer group ID
            auto_offset_reset: Where to start consuming from if no offset is stored
            enable_auto_commit: Whether to auto-commit offsets
            mock_mode: (ignored, always False)
        """
        self.stats = {"messages_processed": 0, "errors": 0, "start_time": time.time()}

        logger.info(
            f"Initializing consumer with bootstrap_servers={bootstrap_servers}, "
            f"group_id={group_id}"
        )

        config = DEFAULT_CONSUMER_CONFIG.copy()
        config.update(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "auto.offset.reset": auto_offset_reset,
                "enable.auto.commit": enable_auto_commit,
            }
        )
        self.consumer = Consumer(config)

        # Mock storage for user preferences (in production, use a database)
        self._preferences: dict[str, NotificationPreferences] = {}

    def subscribe(self, topics: list[str]) -> None:
        """Subscribe to the specified Kafka topics.

        Args:
            topics: List of topic names to subscribe to
        """
        logger.info(f"Subscribing to topics: {topics}")
        self.consumer.subscribe(topics)
        logger.info("Successfully subscribed to topics")

    def process_messages(self, notification_handler: Callable[[Notification], None]) -> None:
        """Process incoming messages continuously.

        Args:
            notification_handler: Callback function to handle notifications
        """
        logger.info("Starting message processing loop")
        last_status_log = time.time()
        STATUS_LOG_INTERVAL = 300  # Log status every 5 minutes

        try:
            while True:
                try:
                    msg = self.consumer.poll(timeout=1.0)

                    # Log periodic status
                    now = time.time()
                    if now - last_status_log >= STATUS_LOG_INTERVAL:
                        self._log_status()
                        last_status_log = now

                    if msg is None:
                        continue

                    if msg.error():
                        if msg.error().code() == KafkaError._PARTITION_EOF:
                            logger.debug("Reached end of partition")
                            continue
                        logger.error(f"Kafka error: {msg.error()}")
                        self.stats["errors"] += 1
                        raise KafkaException(msg.error())

                    # Log message metadata for debugging
                    logger.debug(
                        f"Received message | topic={msg.topic()} | partition={msg.partition()} | offset={msg.offset()} | timestamp={msg.timestamp()}"
                    )

                    # Parse and process message
                    value_str = msg.value().decode("utf-8")
                    value = json.loads(value_str)

                    # Process based on topic
                    topic = msg.topic()
                    if topic == "alerts.fraud":
                        self._process_fraud_alert(value, notification_handler)
                    elif topic == "locations.updated":
                        self._process_delivery_update(value, notification_handler)

                    self.stats["messages_processed"] += 1

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode message: {e}")
                    self.stats["errors"] += 1
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    self.stats["errors"] += 1

        except KeyboardInterrupt:
            logger.info("Shutting down consumer...")
        finally:
            self._log_status()  # Log final stats
            self.consumer.close()

    def _log_status(self) -> None:
        """Log consumer status and statistics."""
        runtime = time.time() - self.stats["start_time"]
        msg_rate = self.stats["messages_processed"] / runtime if runtime > 0 else 0

        logger.info(
            f"Consumer status | messages_processed={self.stats['messages_processed']} | errors={self.stats['errors']} | runtime_seconds={runtime:.2f} | messages_per_second={msg_rate:.2f}"
        )

    def _process_fraud_alert(
        self, alert_data: dict, notification_handler: Callable[[Notification], None]
    ) -> None:
        """Process a fraud alert and create a notification.

        Args:
            alert_data: Fraud alert data from Kafka
            notification_handler: Callback to handle the notification
        """
        try:
            notification = Notification(
                customer_id=alert_data["customer_id"],
                type="fraud_alert",
                subject="Suspicious Activity Detected",
                message=f"Alert: {alert_data['details']} for Order #{alert_data['order_id']}",
                priority="high",
            )
            notification_handler(notification)
            logger.info(f"Created fraud alert notification: {notification.notification_id}")
        except Exception as e:
            logger.error(f"Error creating fraud alert notification: {e}")
            self.stats["errors"] += 1

    def _process_delivery_update(
        self, update_data: dict, notification_handler: Callable[[Notification], None]
    ) -> None:
        """Process a delivery update and create a notification if needed.

        Args:
            update_data: Delivery update data from Kafka (tracking_service schema)
            notification_handler: Callback to handle the notification
        """
        try:
            # Extract status from event_type or items
            status = None
            if "event_type" in update_data:
                if update_data["event_type"] == "delivery_complete":
                    status = "delivered"
                elif update_data["event_type"] == "location_update":
                    # Try to infer from items or fallback
                    status = update_data.get("items", [{}])[0].get("status", "in_transit")
            if not status and "items" in update_data and update_data["items"]:
                status = update_data["items"][0].get("status", "in_transit")
            if not status:
                status = "in_transit"

            status_config = DELIVERY_STATUSES.get(status)

            if status_config and status_config["notify"]:
                notification = Notification(
                    customer_id=update_data.get("customer_id", "unknown"),
                    type="delivery_update" if status == "delivered" else "delay",
                    subject=status_config["subject"],
                    message=self._format_delivery_message(update_data, status),
                    priority=status_config["priority"],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                notification_handler(notification)
                logger.info(
                    f"Created delivery notification | notification_id={notification.notification_id} | customer_id={notification.customer_id} | type={notification.type} | priority={notification.priority}"
                )
        except Exception as e:
            logger.error(f"Error creating delivery notification: {e}", exc_info=True)
            self.stats["errors"] += 1

    def _format_delivery_message(self, update_data: dict, status: str = None) -> str:
        """Format a delivery update message for tracking_service schema."""
        order_id = update_data.get("order_id", "unknown")
        if status is None:
            status = update_data.get("items", [{}])[0].get("status", "in_transit")
        if status == "delivered":
            return f"Your order #{order_id} has been delivered!"
        elif status == "delayed":
            est = update_data.get("estimated_delivery", "TBD")
            return (
                f"Your order #{order_id} is experiencing a delay. "
                f"New estimated delivery: {est}"
            )
        elif status == "at_distribution_center":
            return f"Your order #{order_id} has arrived at a distribution center."
        elif status == "processing":
            return f"Your order #{order_id} is being processed."
        elif status == "in_transit":
            return f"Your order #{order_id} is in transit."
        return f"Status update for order #{order_id}: {status}"

    def set_preferences(self, preferences: NotificationPreferences) -> None:
        """Set notification preferences for a customer.

        Args:
            preferences: The customer's notification preferences
        """
        self._preferences[preferences.customer_id] = preferences
        logger.info(f"Updated preferences for customer: {preferences.customer_id}")

    def get_preferences(self, customer_id: str) -> NotificationPreferences:
        """Get notification preferences for a customer.

        Args:
            customer_id: The customer ID to look up

        Returns:
            NotificationPreferences: The customer's preferences
        """
        return self._preferences.get(customer_id)

    def close(self) -> None:
        """Close the consumer connection."""
        self.consumer.close()
        logger.info("Consumer closed")
