"""FastAPI server implementation for the Notification Service."""

import os
import threading
from contextlib import asynccontextmanager

from confluent_kafka.admin import AdminClient
from fastapi import FastAPI, HTTPException
from logging_utils.config import get_kafka_logger, setup_service_logger

from .consumer import NotificationConsumer
from .handler import NotificationHandler
from .schemas import Notification, NotificationPreferences

# Configure service logger
logger = setup_service_logger("notification-service", log_level=os.getenv("LOG_LEVEL", "INFO"))

# Configure Kafka-specific logger
kafka_logger = get_kafka_logger("notification-service")


class NotificationState:
    """Class to manage notification service state."""

    def __init__(self):
        """Initialize notification state."""
        self.consumer: NotificationConsumer | None = None
        self.mock_mode: bool = os.getenv("MOCK_MODE", "false").lower() == "true"
        if self.mock_mode:
            logger.info("🛈 Starting notification service in MOCK mode")
        self.handler = NotificationHandler()
        self._notifications: dict[str, Notification] = {}

    def store_notification(self, notification: Notification) -> None:
        """Store a notification.

        Args:
            notification: The notification to store
        """
        self._notifications[notification.notification_id] = notification

    def get_notification(self, notification_id: str) -> Notification | None:
        """Get a notification by ID.

        Args:
            notification_id: The notification ID to look up

        Returns:
            The notification if found, None otherwise
        """
        return self._notifications.get(notification_id)

    def list_notifications(
        self, customer_id: str | None = None, notification_type: str | None = None
    ) -> list[Notification]:
        """Get all notifications, optionally filtered.

        Args:
            customer_id: Optional customer ID to filter by
            notification_type: Optional notification type to filter by

        Returns:
            List of matching notifications
        """
        notifications = self._notifications.values()

        if customer_id:
            notifications = [n for n in notifications if n.customer_id == customer_id]

        if notification_type:
            notifications = [n for n in notifications if n.type == notification_type]

        return list(notifications)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the lifecycle of the FastAPI application.

    Args:
        app: The FastAPI application instance
    """
    # Startup: Initialize consumer
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    group_id = os.getenv("KAFKA_CONSUMER_GROUP", "notification-group")

    state.consumer = NotificationConsumer(
        bootstrap_servers=bootstrap_servers, group_id=group_id, mock_mode=state.mock_mode
    )

    # Set up notification handler
    handler = NotificationHandler()

    # Subscribe to topics
    topics = ["fraud.alerts", "delivery.updates"]
    if not state.mock_mode:
        state.consumer.subscribe(topics)
    logger.info(f"{'[MOCK] ' if state.mock_mode else ''}Subscribed to topics: {', '.join(topics)}")

    # Start consumer in background thread
    consumer_thread = threading.Thread(
        target=state.consumer.process_messages, args=(handle_notification,), daemon=True
    )
    consumer_thread.start()
    logger.info(f"{'[MOCK] ' if state.mock_mode else ''}Consumer thread started")

    yield  # FastAPI will run the application here

    # Shutdown
    logger.info("Shutting down notification service...")
    if state.consumer:
        state.consumer.close()
    logger.info("Shutdown complete")

# Initialize FastAPI app and state
app = FastAPI(title="Notification Service", lifespan=lifespan)
state = NotificationState()


def handle_notification(notification: Notification) -> None:
    """Handle incoming notifications.

    Args:
        notification: The notification to process
    """
    # Store the notification
    state.store_notification(notification)

    # Get customer preferences
    if state.consumer:
        preferences = state.consumer.get_preferences(notification.customer_id)
        if preferences:
            # Send through configured channels
            state.handler.send_notification(notification, preferences)
        else:
            logger.warning(f"No preferences found for customer {notification.customer_id}")

    logger.info(f"Processed notification: {notification.notification_id}")


@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy"}


@app.get("/health/ready")
async def readiness_check():
    """Check if the service is ready to handle requests."""
    try:
        admin = AdminClient({"bootstrap.servers": "kafka:9092"})
        cluster_metadata = admin.list_topics(timeout=10)
        if cluster_metadata is not None:
            return {"status": "ready", "kafka": "connected"}
    except Exception:
        return {"status": "not ready", "kafka": "disconnected"}


@app.post("/preferences", response_model=NotificationPreferences)
async def set_preferences(preferences: NotificationPreferences):
    """Set notification preferences for a customer.

    Args:
        preferences: The notification preferences to set

    Returns:
        NotificationPreferences: The updated preferences
    """
    if state.consumer:
        state.consumer.set_preferences(preferences)
        return preferences
    raise HTTPException(status_code=503, detail="Service unavailable")


@app.get("/preferences/{customer_id}", response_model=NotificationPreferences)
async def get_preferences(customer_id: str):
    """Get notification preferences for a customer.

    Args:
        customer_id: The customer ID to look up

    Returns:
        NotificationPreferences: The customer's notification preferences

    Raises:
        HTTPException: If preferences are not found
    """
    if not state.consumer:
        raise HTTPException(status_code=503, detail="Service unavailable")

    preferences = state.consumer.get_preferences(customer_id)
    if not preferences:
        raise HTTPException(status_code=404, detail="Preferences not found")
    return preferences


@app.get("/notifications/{notification_id}", response_model=Notification)
async def get_notification(notification_id: str):
    """Get a specific notification by ID.

    Args:
        notification_id: The ID of the notification to retrieve

    Returns:
        Notification: The notification information

    Raises:
        HTTPException: If the notification is not found
    """
    notification = state.get_notification(notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification


@app.get("/notifications", response_model=list[Notification])
async def list_notifications(customer_id: str | None = None, notification_type: str | None = None):
    """List all notifications, optionally filtered.

    Args:
        customer_id: Optional customer ID to filter by
        notification_type: Optional notification type to filter by

    Returns:
        list[Notification]: List of matching notifications
    """
    return state.list_notifications(customer_id, notification_type)
