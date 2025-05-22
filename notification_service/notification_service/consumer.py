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

# Mock data for testing
MOCK_NOTIFICATIONS = [
    {
        "topic": "fraud.alerts",
        "value": {
            "customer_id": "mock-customer-1",
            "order_id": "mock-order-1",
            "details": "Suspicious activity detected",
        },
    },
    {
        "topic": "delivery.updates",
        "value": {
            "customer_id": "mock-customer-2",
            "order_id": "mock-order-2",
            "status": "delivered",
        },
    },
]


class NotificationConsumer:
    """Consumer for processing notification events."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        auto_offset_reset: str = "earliest",
        enable_auto_commit: bool = True,
        mock_mode: bool = False,
    ):
        """Initialize the notification consumer.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            group_id: Consumer group ID
            auto_offset_reset: Where to start consuming from if no offset is stored
            enable_auto_commit: Whether to auto-commit offsets
            mock_mode: If True, will only log actions instead of sending actual notifications
        """
        self.mock_mode = mock_mode
        self.stats = {"messages_processed": 0, "errors": 0, "start_time": time.time()}

        logger.info(
            f"Initializing consumer with bootstrap_servers={bootstrap_servers}, "
            f"group_id={group_id}, mock_mode={mock_mode}"
        )

        if not mock_mode:
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
        if not self.mock_mode:
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

        if self.mock_mode:
            logger.info("Running in mock mode - no actual notifications will be sent")
            self._process_mock_messages(notification_handler)
            return

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
                        "Received message",
                        extra={
                            "topic": msg.topic(),
                            "partition": msg.partition(),
                            "offset": msg.offset(),
                            "timestamp": msg.timestamp(),
                        },
                    )

                    # Parse and process message
                    value_str = msg.value().decode("utf-8")
                    value = json.loads(value_str)

                    # Process based on topic
                    topic = msg.topic()
                    if topic == "fraud.alerts":
                        self._process_fraud_alert(value, notification_handler)
                    elif topic == "delivery.updates":
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
            if not self.mock_mode:
                self.consumer.close()

    def _process_mock_messages(self, notification_handler: Callable[[Notification], None]) -> None:
        """Process mock messages for testing.

        Args:
            notification_handler: Callback function to handle notifications
        """
        for mock_msg in MOCK_NOTIFICATIONS:
            logger.info(f"[MOCK] Processing message from topic: {mock_msg['topic']}")
            if mock_msg["topic"] == "fraud.alerts":
                self._process_fraud_alert(mock_msg["value"], notification_handler)
            elif mock_msg["topic"] == "delivery.updates":
                self._process_delivery_update(mock_msg["value"], notification_handler)
            self.stats["messages_processed"] += 1

    def _log_status(self) -> None:
        """Log consumer status and statistics."""
        runtime = time.time() - self.stats["start_time"]
        msg_rate = self.stats["messages_processed"] / runtime if runtime > 0 else 0

        logger.info(
            "Consumer status",
            extra={
                "messages_processed": self.stats["messages_processed"],
                "errors": self.stats["errors"],
                "runtime_seconds": runtime,
                "messages_per_second": round(msg_rate, 2),
                "mock_mode": self.mock_mode,
            },
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
            if self.mock_mode:
                logger.info(f"[MOCK] Would send fraud alert: {notification.message}")
                logger.info(f"[MOCK] To: {notification.customer_id}")
                logger.info("[MOCK] Via: Email and SMS (if configured)")
            else:
                notification_handler(notification)
            logger.info(
                f"{'[MOCK] ' if self.mock_mode else ''}Created fraud alert notification: {notification.notification_id}"
            )
        except Exception as e:
            logger.error(f"Error creating fraud alert notification: {e}")
            self.stats["errors"] += 1

    def _process_delivery_update(
        self, update_data: dict, notification_handler: Callable[[Notification], None]
    ) -> None:
        """Process a delivery update and create a notification if needed.

        Args:
            update_data: Delivery update data from Kafka
            notification_handler: Callback to handle the notification
        """
        try:
            status = update_data.get("status", "unknown")
            status_config = DELIVERY_STATUSES.get(status)

            if status_config and status_config["notify"]:
                notification = Notification(
                    customer_id=update_data["customer_id"],
                    type="delivery_update" if status == "delivered" else "delay",
                    subject=status_config["subject"],
                    message=self._format_delivery_message(update_data),
                    priority=status_config["priority"],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )

                if self.mock_mode:
                    logger.info(f"[MOCK] Would send delivery update: {notification.message}")
                    logger.info(f"[MOCK] To: {notification.customer_id}")
                    logger.info("[MOCK] Via: Email and SMS (if configured)")
                else:
                    notification_handler(notification)

                logger.info(
                    f"{'[MOCK] ' if self.mock_mode else ''}Created delivery notification",
                    extra={
                        "notification_id": notification.notification_id,
                        "customer_id": notification.customer_id,
                        "type": notification.type,
                        "priority": notification.priority,
                    },
                )
        except Exception as e:
            logger.error(f"Error creating delivery notification: {e}", exc_info=True)
            self.stats["errors"] += 1

    def _format_delivery_message(self, update_data: dict) -> str:
        """Format a delivery update message.

        Args:
            update_data: Delivery update data

        Returns:
            str: Formatted message
        """
        if update_data.get("status") == "delivered":
            return f"Your order #{update_data['order_id']} has been delivered!"
        elif update_data.get("status") == "delayed":
            return (
                f"Your order #{update_data['order_id']} is experiencing a delay. "
                f"New estimated delivery: {update_data.get('estimated_delivery', 'TBD')}"
            )
        return f"Status update for order #{update_data['order_id']}: {update_data.get('status', 'unknown')}"

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
        if not self.mock_mode:
            self.consumer.close()
        logger.info("Consumer closed")
