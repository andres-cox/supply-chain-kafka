"""FastAPI server implementation for the Tracking Service."""

import os
import threading
from contextlib import asynccontextmanager
from typing import Optional

from confluent_kafka.admin import AdminClient
from fastapi import FastAPI, HTTPException
from logging_utils.config import setup_service_logger, get_kafka_logger

from tracking_service.consumer import TrackingConsumer
from tracking_service.producer import TrackingProducer
from tracking_service.schemas import TrackingEvent

# Configure service logger
logger = setup_service_logger(
    "tracking-service",
    log_level=os.getenv("LOG_LEVEL", "INFO")
)

# Configure Kafka-specific logger
kafka_logger = get_kafka_logger("tracking-service")


class TrackingState:
    """Class to manage tracking service state."""

    def __init__(self):
        """Initialize tracking state."""
        self.producer: Optional[TrackingProducer] = None
        self._tracking_store: dict[str, TrackingEvent] = {}
        self.consumer: Optional[TrackingConsumer] = None

    def store_event(self, event: TrackingEvent) -> None:
        """Store a tracking event.

        Args:
            event: The tracking event to store
        """
        self._tracking_store[event.order_id] = event

    def get_event(self, order_id: str) -> Optional[TrackingEvent]:
        """Get a tracking event by order ID.

        Args:
            order_id: The order ID to look up

        Returns:
            The tracking event if found, None otherwise
        """
        return self._tracking_store.get(order_id)

    def list_events(self) -> list[TrackingEvent]:
        """Get all tracking events.

        Returns:
            List of all tracking events
        """
        return list(self._tracking_store.values())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the lifecycle of the FastAPI application.

    Args:
        app: The FastAPI application instance
    """
    # Startup: Initialize producer and consumer
    state.producer = TrackingProducer(
        bootstrap_servers="kafka:9092", client_id="tracking-service"
    )

    # Create consumer with proper configuration
    state.consumer = TrackingConsumer(
        bootstrap_servers="kafka:9092",
        group_id="tracking-service",  # Changed to match service name
        auto_offset_reset="earliest",
    )

    # Subscribe to orders.created topic
    state.consumer.subscribe(["orders.created"])
    logger.info("Subscribed to topic: orders.created")

    # Start consumer in a background thread
    consumer_thread = threading.Thread(
        target=state.consumer.process_messages,
        args=(handle_tracking_event,),
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
app = FastAPI(title="Tracking Service", lifespan=lifespan)
state = TrackingState()


def handle_tracking_event(event: TrackingEvent) -> None:
    """Handle incoming tracking events.

    Args:
        event: The tracking event to process
    """
    state.store_event(event)


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


@app.get("/tracking/{order_id}", response_model=TrackingEvent)
async def get_tracking_status(order_id: str):
    """Get tracking status for a specific order.

    Args:
        order_id: The ID of the order to track

    Returns:
        TrackingEvent: The tracking information for the order

    Raises:
        HTTPException: If the order is not found
    """
    event = state.get_event(order_id)
    if not event:
        raise HTTPException(status_code=404, detail="Order not found")
    return event


@app.get("/tracking", response_model=list[TrackingEvent])
async def list_tracking_events():
    """List all tracking events.

    Returns:
        list[TrackingEvent]: List of all tracking events
    """
    return state.list_events()
