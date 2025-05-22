"""FastAPI server implementation for the Tracking Service."""

import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from confluent_kafka.admin import AdminClient
from fastapi import FastAPI, HTTPException
from logging_utils.config import get_kafka_logger, setup_service_logger

from tracking_service.consumer import TrackingConsumer
from tracking_service.producer import TrackingProducer
from tracking_service.schemas import ShipmentPriority, TrackingEvent

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
        """Store a tracking event."""
        self._tracking_store[event.order_id] = event
        logger.info(
            f"Stored tracking event",
            extra={
                "order_id": event.order_id,
                "event_type": event.event_type,
                "location": event.current_location.name,
                "status": event.items[0].status if event.items else None
            }
        )

    def get_event(self, order_id: str) -> Optional[TrackingEvent]:
        """Get a tracking event by order ID."""
        return self._tracking_store.get(order_id)

    def list_events(
        self,
        customer_id: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[ShipmentPriority] = None
    ) -> list[TrackingEvent]:
        """Get tracking events with optional filters."""
        events = self._tracking_store.values()

        if customer_id:
            events = [e for e in events if e.customer_id == customer_id]
        if status:
            events = [e for e in events if any(item.status == status for item in e.items)]
        if priority:
            events = [e for e in events if e.priority == priority]

        return list(events)


def handle_tracking_event(event: TrackingEvent) -> None:
    """Handle incoming tracking events.

    Args:
        event: The tracking event to process
    """
    # Store the event
    state.store_event(event)

    # Produce location update if needed
    if event.event_type in ["location_update", "delivery_complete"]:
        if state.producer:
            state.producer.send_tracking_update(
                topic="locations.updated",
                tracking_event=event
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the lifecycle of the FastAPI application."""
    # Startup: Initialize producer and consumer
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    
    state.producer = TrackingProducer(
        bootstrap_servers=bootstrap_servers,
        client_id="tracking-service"
    )

    state.consumer = TrackingConsumer(
        bootstrap_servers=bootstrap_servers,
        group_id="tracking-service-group",
        auto_offset_reset="earliest",
    )

    # Subscribe to orders.created topic
    state.consumer.subscribe(["orders.created"])
    logger.info("Subscribed to topic: orders.created")

    # Start consumer in background thread
    consumer_thread = threading.Thread(
        target=state.consumer.process_messages,
        args=(handle_tracking_event,),
        daemon=True,
    )
    consumer_thread.start()
    logger.info("Consumer thread started")

    yield

    # Shutdown
    logger.info("Shutting down tracking service...")
    if state.consumer:
        state.consumer.close()
    if state.producer:
        state.producer.close()
    logger.info("Shutdown complete")


# Initialize FastAPI app and state
app = FastAPI(title="Tracking Service", lifespan=lifespan)
state = TrackingState()


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
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {"status": "not ready", "kafka": "disconnected"}


@app.get("/tracking/{order_id}")
async def get_tracking(order_id: str):
    """Get tracking information for an order.

    Args:
        order_id: The order ID to look up

    Returns:
        Current tracking status and location
    """
    event = state.get_event(order_id)
    if not event:
        raise HTTPException(status_code=404, detail="Order not found")
    return event


@app.get("/tracking")
async def list_tracking(
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[ShipmentPriority] = None
):
    """List tracking events with optional filters.

    Args:
        customer_id: Filter by customer ID
        status: Filter by current status
        priority: Filter by shipment priority

    Returns:
        List of matching tracking events
    """
    return state.list_events(customer_id, status, priority)
