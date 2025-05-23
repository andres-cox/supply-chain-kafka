"""Schemas for tracking service data models."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ShipmentPriority(str, Enum):
    """Priority levels for shipments."""

    STANDARD = "standard"
    HIGH = "high"
    EXPRESS = "express"


class Location(BaseModel):
    """Represents a location in the tracking system."""

    name: str
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    type: Literal["warehouse", "distribution_center", "delivery_point"] = "warehouse"


# Predefined locations for the demo
PREDEFINED_LOCATIONS = {
    "start": Location(
        name="Main Warehouse",
        lat=41.8781,
        lon=-87.6298,
        type="warehouse"
    ),
    "dc1": Location(
        name="Distribution Center 1",
        lat=41.9742,
        lon=-87.9073,
        type="distribution_center"
    ),
    "dc2": Location(
        name="Distribution Center 2",
        lat=42.0451,
        lon=-87.6877,
        type="distribution_center"
    ),
    "final": Location(
        name="Delivery Point",
        lat=41.8819,
        lon=-87.6278,
        type="delivery_point"
    ),
}

# Demo routes with checkpoints
ROUTES = {
    "standard": ["start", "dc1", "dc2", "final"],
    "express": ["start", "dc1", "final"]
}


class TrackingItem(BaseModel):
    """Represents an item being tracked in the system."""

    sku: str = Field(..., min_length=3, max_length=50)
    quantity: int = Field(..., gt=0, le=1000)
    price: float = Field(..., gt=0, description="USD price per unit")
    status: Literal[
        "received",
        "processing",
        "in_transit",
        "at_distribution_center",
        "out_for_delivery",
        "delivered"
    ] = "received"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    location: Location | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sku": "PROD-001",
                "quantity": 2,
                "price": 9.99,
                "status": "received",
                "location": PREDEFINED_LOCATIONS["start"].model_dump()
            }
        }
    )


class TrackingEvent(BaseModel):
    """Represents a tracking event in the system."""

    order_id: str = Field(..., description="Reference to the original order")
    customer_id: str = Field(..., min_length=5)
    items: list[TrackingItem]
    event_type: Literal[
        "order_received",
        "status_update",
        "location_update",
        "delivery_complete"
    ]
    current_location: Location
    next_location: Location | None = None
    route_checkpoints: list[str]  # List of location IDs in the route
    current_checkpoint: int = 0  # Current position in the route
    priority: ShipmentPriority = ShipmentPriority.STANDARD  # Add priority field
    estimated_delivery: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def model_serializer(cls, obj):
        """Serialize model to dictionary format."""
        data = obj.model_dump()
        data["created_at"] = data["created_at"].isoformat()
        if data["estimated_delivery"]:
            data["estimated_delivery"] = data["estimated_delivery"].isoformat()
        for item in data["items"]:
            item["timestamp"] = item["timestamp"].isoformat()
        return data

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "order_id": "ord-12345678",
                "customer_id": "cust-12345",
                "event_type": "order_received",
                "items": [
                    {
                        "sku": "PROD-001",
                        "quantity": 2,
                        "price": 9.99,
                        "status": "received"
                    }
                ],
                "current_location": PREDEFINED_LOCATIONS["start"].model_dump(),
                "route_checkpoints": ROUTES["standard"]
            }
        }
    )
