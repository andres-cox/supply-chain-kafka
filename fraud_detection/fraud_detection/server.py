"""FastAPI server implementation for the Fraud Detection Service."""

import os
import threading
from contextlib import asynccontextmanager
from typing import Optional, List

from confluent_kafka.admin import AdminClient
from fastapi import FastAPI, HTTPException
from logging_utils.config import setup_service_logger, get_kafka_logger

from .consumer import FraudDetectionConsumer
from .producer import FraudAlertProducer
from .schemas import FraudAlert

# Configure service logger
logger = setup_service_logger("fraud-detection", log_level=os.getenv("LOG_LEVEL", "INFO"))

# Configure Kafka-specific logger
kafka_logger = get_kafka_logger("fraud-detection")


class FraudDetectionState:
    """Class to manage fraud detection service state."""

    def __init__(self):
        """Initialize fraud detection state."""
        self.producer: Optional[FraudAlertProducer] = None
        self.consumer: Optional[FraudDetectionConsumer] = None
        self._alerts: dict[str, FraudAlert] = {}

    def store_alert(self, alert: FraudAlert) -> None:
        """Store a fraud alert.

        Args:
            alert: The fraud alert to store
        """
        self._alerts[alert.alert_id] = alert

    def get_alert(self, alert_id: str) -> Optional[FraudAlert]:
        """Get a fraud alert by ID.

        Args:
            alert_id: The alert ID to look up

        Returns:
            The fraud alert if found, None otherwise
        """
        return self._alerts.get(alert_id)

    def list_alerts(self, order_id: Optional[str] = None) -> List[FraudAlert]:
        """Get all fraud alerts, optionally filtered by order ID.

        Args:
            order_id: Optional order ID to filter by

        Returns:
            List of matching fraud alerts
        """
        if order_id:
            return [alert for alert in self._alerts.values() if alert.order_id == order_id]
        return list(self._alerts.values())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the lifecycle of the FastAPI application.

    Args:
        app: The FastAPI application instance
    """
    # Startup: Initialize producer and consumer
    state.producer = FraudAlertProducer(bootstrap_servers="kafka:9092", client_id="fraud-detection")

    # Create consumer with proper configuration
    state.consumer = FraudDetectionConsumer(
        bootstrap_servers="kafka:9092",
        group_id="fraud-detection",
        auto_offset_reset="earliest",
    )

    # Subscribe to relevant topics
    state.consumer.subscribe(["orders.created", "locations.updated"])
    logger.info("Subscribed to topics: orders.created, locations.updated")

    # Start consumer in a background thread
    consumer_thread = threading.Thread(
        target=state.consumer.process_messages,
        args=(handle_fraud_alert,),
        daemon=True,
    )
    consumer_thread.start()
    logger.info("Consumer thread started")

    yield

    # Shutdown
    if state.consumer:
        state.consumer.close()
    if state.producer:
        state.producer.close()


# Initialize FastAPI app and state
app = FastAPI(title="Fraud Detection Service", lifespan=lifespan)
state = FraudDetectionState()


def handle_fraud_alert(alert: FraudAlert) -> None:
    """Handle generated fraud alerts.

    Args:
        alert: The fraud alert to process
    """
    # Store the alert
    state.store_alert(alert)

    # Publish to Kafka
    if state.producer:
        state.producer.send_fraud_alert("alerts.fraud", alert)

    logger.info(f"Processed fraud alert: {alert.alert_id}")


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


@app.get("/alerts/{alert_id}", response_model=FraudAlert)
async def get_fraud_alert(alert_id: str):
    """Get a specific fraud alert by ID.

    Args:
        alert_id: The ID of the alert to retrieve

    Returns:
        FraudAlert: The fraud alert information

    Raises:
        HTTPException: If the alert is not found
    """
    alert = state.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@app.get("/alerts", response_model=List[FraudAlert])
async def list_fraud_alerts(order_id: Optional[str] = None):
    """List all fraud alerts, optionally filtered by order ID.

    Args:
        order_id: Optional order ID to filter alerts by

    Returns:
        list[FraudAlert]: List of matching fraud alerts
    """
    return state.list_alerts(order_id)
