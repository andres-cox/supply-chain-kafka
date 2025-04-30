"""Schemas for tracking service data models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TrackingItem(BaseModel):
    """Represents an item being tracked in the system.

    Attributes:
        sku (str): Stock Keeping Unit identifier
        quantity (int): Number of items
        price (float): Price per unit in USD
        status (str): Current tracking status
        timestamp (datetime): When the status was updated
    """

    sku: str = Field(..., min_length=3, max_length=50)
    quantity: int = Field(..., gt=0, le=1000)
    price: float = Field(..., gt=0, description="USD price per unit")
    status: Literal["received", "processing", "shipped", "delivered"] = "received"
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sku": "PROD-001",
                "quantity": 2,
                "price": 9.99,
                "status": "received",
            }
        }
    )


class TrackingEvent(BaseModel):
    """Represents a tracking event in the system.

    Attributes:
        order_id (str): Reference to the original order
        customer_id (str): Customer identifier
        items (list[TrackingItem]): List of items being tracked
        event_type (str): Type of tracking event
        created_at (datetime): When the event was created
    """

    order_id: str = Field(..., description="Reference to the original order")
    customer_id: str = Field(..., min_length=5)
    items: list[TrackingItem]
    event_type: Literal["order_received", "status_update", "delivery_complete"]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def model_serializer(cls, obj):
        """Serialize model to dictionary format.

        Args:
            obj: The TrackingEvent instance to serialize.

        Returns:
            dict: Serialized tracking event data with ISO formatted datetime.
        """
        data = obj.model_dump()
        data["created_at"] = data["created_at"].isoformat()
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
                        "status": "received",
                    }
                ],
            }
        }
    )
