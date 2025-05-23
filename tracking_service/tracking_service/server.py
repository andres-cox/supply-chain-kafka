"""FastAPI server implementation for the Tracking Service."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from confluent_kafka.admin import AdminClient
from fastapi import FastAPI, HTTPException
from logging_utils.config import get_kafka_logger, setup_service_logger

from tracking_service.consumer import TrackingConsumer
from tracking_service.producer import TrackingProducer
from tracking_service.schemas import (
    PREDEFINED_LOCATIONS,
    ROUTES,
    Location,
    ShipmentPriority,
    TrackingEvent,
    TrackingItem,
)

# Configure service logger
logger = setup_service_logger(
    "tracking-service",
    log_level=os.getenv("LOG_LEVEL", "INFO")
)

# Configure Kafka-specific logger
kafka_logger = get_kafka_logger("tracking-service")


def calculate_next_location(route_checkpoints: list[str], current_checkpoint: int) -> tuple[Location | None, int]:
    """Calculate the next location in the route."""
    if current_checkpoint + 1 < len(route_checkpoints):
        next_checkpoint = current_checkpoint + 1
        return PREDEFINED_LOCATIONS[route_checkpoints[next_checkpoint]], next_checkpoint
    return None, current_checkpoint


def get_status_for_location(location_type: str) -> str:
    """Get the appropriate status for a location type."""
    return {
        "warehouse": "processing",
        "distribution_center": "at_distribution_center",
        "delivery_point": "delivered"
    }.get(location_type, "in_transit")


class TrackingState:
    """Class to manage tracking service state."""

    def __init__(self) -> None:
        """Initialize tracking state."""
        self.producer: Optional[TrackingProducer] = None
        self._tracking_store: dict[str, TrackingEvent] = {}
        self.consumer: Optional[TrackingConsumer] = None
        self._update_tasks: dict[str, asyncio.Task] = {}

    async def simulate_route_progress(self, order_id: str) -> None:
        """Simulate package movement along its route."""
        event = self._tracking_store[order_id]
        try:
            while event.current_checkpoint < len(event.route_checkpoints) - 1:
                # Wait between updates (shorter for demo)
                await asyncio.sleep(20)  # 20 seconds between updates for demo

                # Update location and status
                next_location, next_checkpoint = calculate_next_location(
                    event.route_checkpoints, event.current_checkpoint
                )
                
                if next_location:
                    event.current_checkpoint = next_checkpoint
                    event.current_location = next_location
                    new_status = get_status_for_location(next_location.type)
                    
                    # Update items status
                    for item in event.items:
                        item.status = new_status
                        item.location = next_location
                        item.timestamp = datetime.utcnow()

                    # Calculate next location
                    event.next_location, _ = calculate_next_location(
                        event.route_checkpoints, event.current_checkpoint
                    )

                    # Log the update
                    logger.info(
                        f"Package location updated | order_id={order_id} | stage={new_status} | checkpoint={event.current_checkpoint + 1}/{len(event.route_checkpoints)} | "
                        f"from={event.current_location.name} | to={next_location.name} | next={event.next_location.name if event.next_location else 'FINAL'} | status={new_status}"
                    )

                    # Emit location update
                    if self.producer:
                        event.event_type = "delivery_complete" if new_status == "delivered" else "location_update"
                        self.producer.send_tracking_update("locations.updated", event)

        except Exception as e:
            logger.error(
                "Error in route simulation",
                extra={
                    "order_id": order_id,
                    "error": str(e)
                }
            )

    def store_event(self, event: TrackingEvent) -> None:
        """Store a tracking event and start location simulation."""
        self._tracking_store[event.order_id] = event
        
        # Log initial state
        logger.info(
            "New tracking event created",
            extra={
                "order_id": event.order_id,
                "customer_id": event.customer_id,
                "start_location": event.current_location.name,
                "route_type": "express" if len(event.route_checkpoints) < 4 else "standard",
                "estimated_delivery": event.estimated_delivery.isoformat() if event.estimated_delivery else "unknown"
            }
        )

        # Start location simulation
        task = asyncio.create_task(self.simulate_route_progress(event.order_id))
        self._update_tasks[event.order_id] = task

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


async def handle_tracking_event(event: TrackingEvent) -> None:
    """Handle incoming tracking events (async).

    Args:
        event: The tracking event to process
    """
    state.store_event(event)
    if event.event_type in ["location_update", "delivery_complete"]:
        if state.producer:
            state.producer.send_tracking_update(
                topic="locations.updated",
                tracking_event=event
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the lifecycle of the FastAPI application."""
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
    state.consumer.subscribe(["orders.created"])
    logger.info("Subscribed to topic: orders.created")

    # Start consumer as asyncio background task
    consumer_task = asyncio.create_task(state.consumer.process_messages(handle_tracking_event))
    logger.info("Consumer background task started")

    yield

    logger.info("Shutting down tracking service...")
    if state.consumer:
        state.consumer.close()
    if state.producer:
        state.producer.close()
    consumer_task.cancel()
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
